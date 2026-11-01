"""Private investment-learning API; independent of market startup and web UI."""
from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import re
import threading
import time
from collections import OrderedDict, deque
from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError, field_validator

from learning_content import build_lesson, catalog, default_curriculum, public_lesson, validate_curriculum
from learning_store import LearningStore, StoreError, utcnow


Text = Annotated[str, Field(strict=True, max_length=20000)]
Short = Annotated[str, Field(strict=True, min_length=1, max_length=200)]
Percent = Annotated[StrictInt, Field(ge=0, le=100)]
SYMBOL = re.compile(r"^[A-Z0-9.^=_-]{1,32}$")
MAX_IMPORT_BYTES = 160 * 1024 * 1024


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Company(Model):
    symbol: Annotated[str, Field(strict=True, min_length=1, max_length=32)]
    name: Annotated[str, Field(strict=True, min_length=1, max_length=120)]
    industry: Annotated[str, Field(strict=True, min_length=1, max_length=80)]

    @field_validator("symbol")
    @classmethod
    def symbol_valid(cls, value):
        if not SYMBOL.fullmatch(value):
            raise ValueError("올바른 종목 코드를 입력해 주세요.")
        return value


class Notes(Model):
    business: Text
    customers: Text
    financials: Text
    growthDrivers: Text
    macro: Text
    newFacts: Text
    unknowns: Text
    judgment: Text
    indicators: Text


class Insight(Model):
    growth: Text
    risk: Text
    metrics: Text


def valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("날짜는 YYYY-MM-DD 형식이어야 합니다.")
    date.fromisoformat(value)
    return value


def valid_time(value):
    if not isinstance(value, str):
        raise ValueError("시각 형식이 올바르지 않습니다.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("시각에 시간대가 필요합니다.")
    return value


class Week(Model):
    id: Annotated[str, Field(strict=True, min_length=1, max_length=120)]
    industry: Annotated[str, Field(strict=True, min_length=1, max_length=80)]
    companies: list[Company] = Field(min_length=3, max_length=3)


class Curriculum(Model):
    id: Annotated[str, Field(strict=True, min_length=1, max_length=120)]
    title: Short
    startDate: str
    weeks: list[Week] = Field(min_length=1, max_length=104)

    @field_validator("startDate")
    @classmethod
    def monday(cls, value):
        valid_date(value)
        if date.fromisoformat(value).weekday() != 0:
            raise ValueError("커리큘럼 시작일은 월요일이어야 합니다.")
        return value

    @field_validator("weeks")
    @classmethod
    def unique_weeks(cls, value):
        if len({week.id for week in value}) != len(value):
            raise ValueError("주차 ID가 중복되었습니다.")
        return value


class Context(Model):
    kind: Short | None = None
    symbol: Short | None = None
    name: Short | None = None
    date: Short | None = None
    key: Short | None = None
    reason: Annotated[str, Field(strict=True, max_length=2000)] | None = None


class Editable(Model):
    id: UUID | None = None
    lessonDate: str
    company: Company | None = None
    topic: Annotated[str, Field(strict=True, max_length=200)] | None = None
    notes: Notes
    insight: Insight
    understanding: Percent | None = None
    minutes: Annotated[StrictInt, Field(ge=0, le=240)] = 0
    sourceContext: Context | None = None

    @field_validator("lessonDate")
    @classmethod
    def calendar_date(cls, value):
        return valid_date(value)


class Mutation(Model):
    requestId: UUID
    expectedVersion: Annotated[StrictInt, Field(ge=0)]


class SavePayload(Mutation):
    session: Editable
    complete: StrictBool


class Rubric(Model):
    evidence: Annotated[StrictInt, Field(ge=0, le=4)]
    logic: Annotated[StrictInt, Field(ge=0, le=4)]
    indicators: Annotated[StrictInt, Field(ge=0, le=4)]


class Judgment(Model):
    answer: Annotated[str, Field(strict=True, min_length=1, max_length=20000)]
    rubric: Rubric

    @field_validator("answer")
    @classmethod
    def reasoning_required(cls, value):
        if not value.strip():
            raise ValueError("판단 이유를 작성해 주세요.")
        return value


class QuizPayload(Mutation):
    answers: dict[str, StrictInt] = Field(max_length=100)
    judgment: Judgment


class ValidationFields(Model):
    revision: Annotated[StrictInt, Field(ge=1)]
    assumption: Annotated[str, Field(strict=True, min_length=1, max_length=20000)]
    observed: Annotated[str, Field(strict=True, min_length=1, max_length=20000)]
    evidenceUrl: Annotated[str, Field(strict=True, max_length=2000)]
    evidenceDate: str
    outcome: Literal["supported", "contradicted", "inconclusive"]
    currentJudgment: Annotated[str, Field(strict=True, min_length=1, max_length=20000)]
    priceContext: Text | None = None

    @field_validator("assumption", "observed", "currentJudgment")
    @classmethod
    def business_reasoning(cls, value):
        if not value.strip():
            raise ValueError("사업 가정과 실제 근거를 작성해 주세요.")
        return value

    @field_validator("evidenceDate")
    @classmethod
    def real_date(cls, value):
        return valid_date(value)

    @field_validator("evidenceUrl")
    @classmethod
    def safe_url(cls, value):
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("공개 HTTPS 근거 링크를 입력해 주세요.")
        if host.lower() in {"localhost", "localhost.localdomain"} or host.lower().endswith((".local", ".internal")):
            raise ValueError("공개 HTTPS 근거 링크를 입력해 주세요.")
        try:
            if not ipaddress.ip_address(host).is_global:
                raise ValueError("공개 HTTPS 근거 링크를 입력해 주세요.")
        except ValueError as exc:
            if ":" in host or re.fullmatch(r"[\d.]+", host):
                raise ValueError("공개 HTTPS 근거 링크를 입력해 주세요.") from exc
        return value


class ValidationPayload(ValidationFields, Mutation):
    pass


class CurriculumPayload(Mutation):
    curriculum: Curriculum


class ImportPayload(Mutation):
    payload: dict


class Recovery(Model):
    recoveryKey: Annotated[str, Field(strict=True, min_length=43, max_length=128)]


class DeleteAccount(Model):
    confirmation: Literal["DELETE"]


class Empty(Model):
    pass


class PrivateRoute(APIRoute):
    """All private outcomes, including automatic validation errors, are no-store."""
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                public = (request.method, request.url.path) in {
                    ("GET", "/api/learning/status"), ("GET", "/api/learning/catalog"),
                    ("POST", "/api/learning/accounts"), ("POST", "/api/learning/auth"),
                }
                if not public:
                    # Authenticate before consuming even the first body chunk.
                    # Database I/O stays off the event loop, and the verified
                    # identity is reused only for this same request's lifetime.
                    await run_in_threadpool(self.authenticate_request, request)
                limit = MAX_IMPORT_BYTES if request.url.path == "/api/learning/import" else 4 * 1024 * 1024
                chunks, size = [], 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > limit:
                        raise StoreError(413, "요청 크기 제한을 초과했습니다. 가져오기는 160MB, 일반 요청은 4MB까지 가능합니다.")
                    chunks.append(chunk)
                request._body = b"".join(chunks)
                response = await original(request)
            except StoreError as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status)
            except RequestValidationError:
                response = JSONResponse({"detail": "입력 형식과 필수 항목을 확인해 주세요."}, status_code=422)
            except ValidationError:
                response = JSONResponse({"detail": "가져올 기록의 형식 또는 값이 올바르지 않습니다."}, status_code=422)
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            except Exception:
                response = JSONResponse({"detail": "기업 공부 요청을 처리하지 못했습니다. 기록은 저장 완료로 표시되지 않습니다."}, status_code=500)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            return response
        return handler


class AuthLimiter:
    """Bound public credential endpoints without retaining addresses or secrets.

    This per-process guard complements infrastructure-level request limits. It is
    deliberately bounded in memory and uses the server's trusted client address,
    never an arbitrary caller-supplied forwarding header.
    """
    def __init__(self):
        self.buckets = OrderedDict()
        self.lock = threading.Lock()

    def check(self, request, action, limit):
        address = request.client.host if request.client else "unknown"
        key = (action, hashlib.sha256(address.encode()).hexdigest())
        now = time.monotonic()
        with self.lock:
            values = self.buckets.pop(key, deque())
            while values and values[0] <= now - 60:
                values.popleft()
            self.buckets[key] = values
            while len(self.buckets) > 4096:
                self.buckets.popitem(last=False)
            if len(values) >= limit:
                raise StoreError(429, "요청이 많습니다. 1분 후 다시 시도해 주세요.")
            values.append(now)


def workspace(document):
    return copy.deepcopy({key: value for key, value in document.items() if not key.startswith("_")})


def empty_workspace():
    return {"schemaVersion": 1, "version": 0, "curriculum": default_curriculum(), "sessions": [],
            "attempts": [], "reviews": [], "validations": [], "revisions": [], "imports": [], "_lessons": {}}


def find_session(document, session_id):
    found = next((s for s in document["sessions"] if s["id"] == session_id), None)
    if found is None:
        raise StoreError(404, "공부 기록을 찾을 수 없습니다.")
    return found


def require_insights(insight):
    if any(not insight[field].strip() for field in ("growth", "risk", "metrics")):
        raise StoreError(422, "완료하려면 성장 이유, 가장 큰 위험, 반드시 확인할 지표를 작성해 주세요.")


def canonical_company(company):
    if company is None:
        return None
    company = company.model_dump() if isinstance(company, Company) else company
    known = next((c for c in catalog()["companies"] if c["symbol"] == company["symbol"]), None)
    if known and known != company:
        raise StoreError(422, "종목 코드와 기업 이름·산업이 공식 공부 목록과 다릅니다.")
    return company


def make_lesson(curriculum, lesson_date, company=None, symbol=None):
    try:
        valid_date(lesson_date)
        if symbol is not None:
            if not SYMBOL.fullmatch(symbol):
                raise StoreError(422, "종목 코드가 올바르지 않습니다.")
            known = next((c for c in catalog()["companies"] if c["symbol"] == symbol), None)
            if not known:
                raise StoreError(422, "알 수 없는 기업은 저장할 때 이름과 산업을 입력해 주세요.")
        return build_lesson(curriculum, lesson_date, symbol=symbol, company=company)
    except ValueError as exc:
        raise StoreError(404, "해당 날짜에는 예정된 공부가 없습니다.") from exc


def save_session(document, value, complete, imported=False):
    data = value.model_dump(mode="json")
    sid = data.pop("id")
    existing = find_session(document, sid) if sid else None
    company = canonical_company(data.pop("company"))
    if existing and "company" not in value.model_fields_set:
        company = existing["company"]
    now = utcnow().isoformat()
    if existing:
        if data["lessonDate"] != existing["lessonDate"] or company != existing["company"]:
            raise StoreError(422, "기존 기록의 날짜나 기업은 변경할 수 없습니다. 새 공부 기록을 만들어 주세요.")
        session = copy.deepcopy(existing)
        session["revision"] += 1
        lesson = session["lesson"]
        completed = complete or existing["completedAt"] is not None
    else:
        sid = str(uuid4())
        private = make_lesson(document["curriculum"], data["lessonDate"], company=company)
        lesson = public_lesson(private)
        document["_lessons"][sid] = private
        session = {"id": sid, "lessonId": lesson["id"], "lesson": lesson, "company": company,
                   "symbols": [c["symbol"] for c in lesson["companies"]], "industry": lesson["industry"],
                   "createdAt": now, "revision": 1, "completedAt": None, "nextReviewDate": None}
        completed = complete
    if completed:
        require_insights(data["insight"])
    session.update(data)
    session["topic"] = data["topic"] or lesson["title"]
    session["status"] = "completed" if completed else "in_progress"
    session["completedAt"] = (session["completedAt"] or now) if completed else None
    session["updatedAt"] = now
    if imported:
        session["provenance"] = "imported"
    if existing:
        document["sessions"][document["sessions"].index(existing)] = session
    else:
        document["sessions"].append(session)
    document["revisions"].append({"id": str(uuid4()), "sessionId": sid, "revision": session["revision"],
                                  "session": copy.deepcopy(session), "createdAt": now,
                                  **({"provenance": "imported"} if imported else {})})
    return {"sessionId": sid}


def submit_quiz(document, sid, payload, is_review):
    session = find_session(document, sid)
    if session["completedAt"] is None or session["status"] == "in_progress":
        raise StoreError(422, "공부를 완료한 뒤 모든 질문과 판단 이유를 제출해 주세요.")
    lesson = document["_lessons"].get(sid)
    if lesson is None:
        raise StoreError(422, "이 가져온 기록의 원래 퀴즈 정의를 검증할 수 없습니다. 새 공부에서 평가를 제출해 주세요.")
    questions = lesson["questions"]
    if set(payload.answers) != {q["id"] for q in questions} or any(
            payload.answers[q["id"]] < 0 or payload.answers[q["id"]] >= len(q["options"]) for q in questions):
        raise StoreError(422, "모든 질문에 유효한 답을 선택해 주세요.")
    correct, wrong, dimensions = 0, [], {}
    for q in questions:
        chosen = payload.answers[q["id"]]
        hit = chosen == q["correctIndex"]
        correct += int(hit)
        dimensions.setdefault(q["dimension"], []).append(int(hit))
        if not hit:
            wrong.append({"questionId": q["id"], "prompt": q["prompt"], "chosen": chosen,
                          "expected": q["correctIndex"], "explanation": q["explanation"], "concept": q["concept"]})
    score = round(correct / len(questions) * 100)
    now = utcnow()
    today = now.astimezone(ZoneInfo("Asia/Seoul")).date()
    due = (today + timedelta(days=1 if score < 60 else 3 if score < 80 else 7)).isoformat()
    judgment = payload.judgment.model_dump()
    judgment.update(score=round(sum(judgment["rubric"].values()) / 12 * 100), assessment="self")
    attempt = {"id": str(uuid4()), "sessionId": sid, "sessionRevision": session["revision"], "submittedAt": now.isoformat(),
               "score": score, "dimensions": {key: round(sum(values) / len(values) * 100) for key, values in dimensions.items()},
               "answers": payload.answers, "wrongAnswers": wrong, "judgment": judgment, "isReview": is_review}
    document["attempts"].append(attempt)
    if is_review:
        document["reviews"].append({"id": str(uuid4()), "sessionId": sid, "attemptId": attempt["id"],
                                     "date": today.isoformat(), "score": score, "nextReviewDate": due})
    session.update(status="evaluated", nextReviewDate=due, updatedAt=now.isoformat())
    return {"sessionId": sid}


class Section(Model):
    title: Short
    minutes: Annotated[StrictInt, Field(ge=0, le=25)]
    body: Text
    prompts: list[Text] = Field(max_length=30)


class Source(Model):
    title: Short
    url: str

    @field_validator("url")
    @classmethod
    def safe_source(cls, value):
        return ValidationFields.safe_url(value)


class Question(Model):
    id: Short
    dimension: Literal["business", "inference"]
    prompt: Text
    options: list[Text] = Field(min_length=2, max_length=10)


class PublicLesson(Model):
    id: Short
    date: str
    kind: Literal["company", "value_chain", "comparison", "scenario", "review"]
    title: Short
    industry: Short
    companies: list[Company] = Field(min_length=1, max_length=10)
    duration: Annotated[StrictInt, Field(ge=25, le=25)]
    sections: list[Section] = Field(min_length=1, max_length=30)
    sources: list[Source] = Field(min_length=1, max_length=30)
    questions: list[Question] = Field(min_length=1, max_length=100)
    judgmentPrompt: Text
    quizVersion: Short

    @field_validator("date")
    @classmethod
    def real_date(cls, value):
        return valid_date(value)

    @field_validator("questions")
    @classmethod
    def unique_questions(cls, value):
        if len({q.id for q in value}) != len(value) or {q.dimension for q in value} != {"business", "inference"}:
            raise ValueError("평가 문항의 ID와 두 평가 영역을 확인해 주세요.")
        return value


class SavedSession(Editable):
    id: UUID
    lessonId: Short
    lesson: PublicLesson
    symbols: list[Short] = Field(min_length=1, max_length=10)
    industry: Short
    status: Literal["in_progress", "completed", "evaluated"]
    completedAt: str | None
    createdAt: str
    updatedAt: str
    revision: Annotated[StrictInt, Field(ge=1)]
    nextReviewDate: str | None
    provenance: Literal["imported"] | None = None

    @field_validator("createdAt", "updatedAt")
    @classmethod
    def timestamp(cls, value):
        return valid_time(value)

    @field_validator("completedAt")
    @classmethod
    def nullable_time(cls, value):
        return valid_time(value) if value is not None else None

    @field_validator("nextReviewDate")
    @classmethod
    def nullable_date(cls, value):
        return valid_date(value) if value is not None else None


class WrongAnswer(Model):
    questionId: Short
    prompt: Text
    chosen: Annotated[StrictInt, Field(ge=0, le=9)]
    expected: Annotated[StrictInt, Field(ge=0, le=9)]
    explanation: Text
    concept: Text


class SavedJudgment(Judgment):
    score: Percent
    assessment: Literal["self"]


class Attempt(Model):
    id: UUID
    sessionId: UUID
    sessionRevision: Annotated[StrictInt, Field(ge=1)]
    submittedAt: str
    score: Percent
    dimensions: dict[Literal["business", "inference"], Percent]
    answers: dict[str, Annotated[StrictInt, Field(ge=0, le=9)]] = Field(max_length=100)
    wrongAnswers: list[WrongAnswer] = Field(max_length=100)
    judgment: SavedJudgment
    isReview: StrictBool
    provenance: Literal["imported"] | None = None

    @field_validator("submittedAt")
    @classmethod
    def timestamp(cls, value):
        return valid_time(value)


class Review(Model):
    id: UUID
    sessionId: UUID
    attemptId: UUID
    date: str
    score: Percent
    nextReviewDate: str
    provenance: Literal["imported"] | None = None

    @field_validator("date", "nextReviewDate")
    @classmethod
    def real_dates(cls, value):
        return valid_date(value)


class ValidationRecord(ValidationFields):
    id: UUID
    sessionId: UUID
    createdAt: str
    provenance: Literal["imported"] | None = None

    @field_validator("createdAt")
    @classmethod
    def timestamp(cls, value):
        return valid_time(value)


class Revision(Model):
    id: UUID
    sessionId: UUID
    revision: Annotated[StrictInt, Field(ge=1)]
    session: SavedSession
    createdAt: str
    provenance: Literal["imported"] | None = None

    @field_validator("createdAt")
    @classmethod
    def timestamp(cls, value):
        return valid_time(value)


class ExternalAssessment(Model):
    score: Percent | None = None
    notes: Text = ""


class ImportedAssessment(ExternalAssessment):
    assessment: Literal["external"]


class ImportRecord(Model):
    id: UUID
    format: Literal["chartview-learning-backup", "chartview-learning-result"]
    importedAt: str
    sessionIds: list[UUID] = Field(max_length=10000)
    sourceExportedAt: str | None = None
    sourceVersion: Annotated[StrictInt, Field(ge=0)] | None = None
    externalAssessment: ImportedAssessment | None = None
    provenance: Literal["imported"] | None = None

    @field_validator("importedAt")
    @classmethod
    def timestamp(cls, value):
        return valid_time(value)

    @field_validator("sourceExportedAt")
    @classmethod
    def nullable_time(cls, value):
        return valid_time(value) if value is not None else None


class BackupWorkspace(Model):
    schemaVersion: Annotated[StrictInt, Field(ge=1, le=1)]
    version: Annotated[StrictInt, Field(ge=0)]
    curriculum: Curriculum
    sessions: list[SavedSession] = Field(max_length=10000)
    attempts: list[Attempt] = Field(max_length=20000)
    reviews: list[Review] = Field(max_length=20000)
    validations: list[ValidationRecord] = Field(max_length=20000)
    revisions: list[Revision] = Field(max_length=20000)
    imports: list[ImportRecord] = Field(max_length=10000)


class Backup(Model):
    format: Literal["chartview-learning-backup"]
    schemaVersion: Annotated[StrictInt, Field(ge=1, le=1)]
    exportedAt: str
    workspace: BackupWorkspace

    @field_validator("exportedAt")
    @classmethod
    def timestamp(cls, value):
        return valid_time(value)


class ExternalResult(Model):
    format: Literal["chartview-learning-result"]
    schemaVersion: Annotated[StrictInt, Field(ge=1, le=1)]
    session: Editable
    externalAssessment: ExternalAssessment | None = None


def validate_saved_session(session):
    if session["lessonDate"] != session["lesson"]["date"] or session["lessonId"] != session["lesson"]["id"]:
        raise StoreError(422, "공부 날짜와 고정된 수업 정의가 일치하지 않습니다.")
    canonical_company(session["company"])
    if session["symbols"] != [c["symbol"] for c in session["lesson"]["companies"]] or session["industry"] != session["lesson"]["industry"]:
        raise StoreError(422, "공부 기업과 수업 정의가 일치하지 않습니다.")
    if session["status"] != "in_progress":
        require_insights(session["insight"])
        if session["completedAt"] is None:
            raise StoreError(422, "완료 기록에 실제 완료 시각이 없습니다.")
    elif session["completedAt"] is not None:
        raise StoreError(422, "미완료 기록의 완료 시각이 잘못되었습니다.")


def compare_record(value):
    """Compare source records while ignoring only explicit import provenance."""
    if isinstance(value, dict):
        return {k: ("completed" if k == "status" and v == "evaluated" else compare_record(v))
                for k, v in value.items() if k != "provenance" and v is not None}
    if isinstance(value, list):
        return [compare_record(v) for v in value]
    return value


def imported_record(value):
    result = copy.deepcopy(value)
    result["provenance"] = "imported"
    if "status" in result and result["status"] == "evaluated":
        result["status"] = "completed"
    if "session" in result:
        result["session"] = imported_record(result["session"])
    return result


def merge_import(document, payload):
    if payload.get("format") == "chartview-learning-result":
        result = ExternalResult.model_validate(payload)
        # Imports always create a dated record; they cannot overwrite an existing
        # session or attest that the account submitted a native quiz.
        if result.session.id is not None:
            raise StoreError(422, "외부 공부 결과는 기존 기록 ID 없이 새 기록으로 가져와 주세요.")
        complete = all(value.strip() for value in result.session.insight.model_dump().values())
        extra = save_session(document, result.session, complete, imported=True)
        entry = {"id": str(uuid4()), "format": result.format, "importedAt": utcnow().isoformat(),
                 "sessionIds": [extra["sessionId"]]}
        if result.externalAssessment:
            entry["externalAssessment"] = {**result.externalAssessment.model_dump(), "assessment": "external"}
        document["imports"].append(entry)
        return extra
    backup = Backup.model_validate(payload)
    source = backup.workspace.model_dump(mode="json", exclude_none=True)
    try:
        source["curriculum"] = validate_curriculum(source["curriculum"])
    except ValueError as exc:
        raise StoreError(422, "가져올 커리큘럼의 주차·기업 형식이 올바르지 않습니다.") from exc
    # Reinsert the contract's nullable values in saved sessions and snapshots.
    source["sessions"] = [s.model_dump(mode="json", exclude={"provenance"}) if s.provenance is None
                          else s.model_dump(mode="json") for s in backup.workspace.sessions]
    source["revisions"] = [r.model_dump(mode="json", exclude_none=False) for r in backup.workspace.revisions]
    for revision in source["revisions"]:
        if revision.get("provenance") is None:
            revision.pop("provenance", None)
        if revision["session"].get("provenance") is None:
            revision["session"].pop("provenance", None)
    collections = ("sessions", "attempts", "reviews", "validations", "revisions", "imports")
    ids = {}
    for collection in collections:
        rows = source[collection]
        if len({row["id"] for row in rows}) != len(rows):
            raise StoreError(422, "가져올 기록에 중복 ID가 있습니다.")
        for row in rows:
            if row["id"] in ids:
                raise StoreError(422, "서로 다른 기록 종류에 같은 ID가 있습니다.")
            ids[row["id"]] = collection
    sessions = {s["id"]: s for s in source["sessions"]}
    revisions = {(r["sessionId"], r["revision"]): r for r in source["revisions"]}
    revision_numbers = {}
    for sid, number in revisions:
        revision_numbers.setdefault(sid, []).append(number)
    if len(revisions) != len(source["revisions"]):
        raise StoreError(422, "공부 버전 이력이 중복되었습니다.")
    for session in source["sessions"]:
        validate_saved_session(session)
        if (session["id"], session["revision"]) not in revisions:
            raise StoreError(422, "현재 공부 버전의 이력이 없습니다.")
        numbers = sorted(revision_numbers.get(session["id"], []))
        if len(numbers) != session["revision"] or any(number != index for index, number in enumerate(numbers, 1)):
            raise StoreError(422, "공부 버전 이력이 중간에 누락되었습니다.")
        snapshot = revisions[(session["id"], session["revision"])]["session"]
        for key in ("lessonDate", "lessonId", "lesson", "company", "symbols", "industry", "topic", "notes", "insight", "understanding", "minutes", "completedAt", "createdAt", "sourceContext"):
            if compare_record(session.get(key)) != compare_record(snapshot.get(key)):
                raise StoreError(422, "현재 공부 내용이 같은 버전의 보존 이력과 다릅니다.")
    for revision in source["revisions"]:
        validate_saved_session(revision["session"])
        sid = revision["sessionId"]
        if sid not in sessions or revision["session"]["id"] != sid or revision["revision"] != revision["session"]["revision"] or revision["revision"] > sessions[sid]["revision"]:
            raise StoreError(422, "공부 버전 이력이 원래 기록과 일치하지 않습니다.")
    attempts = {a["id"]: a for a in source["attempts"]}
    for attempt in source["attempts"]:
        sid = attempt["sessionId"]
        if sid not in sessions or (sid, attempt["sessionRevision"]) not in revisions:
            raise StoreError(422, "평가가 가리키는 공부 버전이 없습니다.")
        if revisions[(sid, attempt["sessionRevision"])]["session"]["completedAt"] is None:
            raise StoreError(422, "미완료 공부 버전에는 평가를 가져올 수 없습니다.")
        questions = {q["id"]: q for q in sessions[sid]["lesson"]["questions"]}
        if set(attempt["answers"]) != set(questions) or set(attempt["dimensions"]) != {"business", "inference"} or any(
                answer >= len(questions[qid]["options"]) for qid, answer in attempt["answers"].items()):
            raise StoreError(422, "평가 답안이 원래 질문과 일치하지 않습니다.")
        wrong_ids = set()
        for wrong in attempt["wrongAnswers"]:
            qid = wrong["questionId"]
            if qid not in questions or qid in wrong_ids or wrong["chosen"] != attempt["answers"][qid] or wrong["expected"] >= len(questions[qid]["options"]) or wrong["chosen"] == wrong["expected"]:
                raise StoreError(422, "오답 이력이 원래 답안과 일치하지 않습니다.")
            wrong_ids.add(qid)
        expected_score = round((len(questions) - len(wrong_ids)) / len(questions) * 100)
        expected_dimensions = {dimension: round(sum(qid not in wrong_ids for qid, q in questions.items() if q["dimension"] == dimension) /
            sum(q["dimension"] == dimension for q in questions.values()) * 100) for dimension in ("business", "inference")}
        if attempt["score"] != expected_score or attempt["dimensions"] != expected_dimensions or attempt["judgment"]["score"] != round(sum(attempt["judgment"]["rubric"].values()) / 12 * 100):
            raise StoreError(422, "평가 점수와 답안·자기평가 이력이 일치하지 않습니다.")
    attempted_revisions = {(a["sessionId"], a["sessionRevision"]) for a in source["attempts"]}
    for session in source["sessions"]:
        if session["status"] == "evaluated" and (session["id"], session["revision"]) not in attempted_revisions:
            raise StoreError(422, "평가 완료 기록에 실제 제출 이력이 없습니다.")
    for review in source["reviews"]:
        attempt = attempts.get(review["attemptId"])
        if not attempt or attempt["sessionId"] != review["sessionId"] or not attempt["isReview"] or attempt["score"] != review["score"]:
            raise StoreError(422, "복습 이력이 평가와 일치하지 않습니다.")
    for validation in source["validations"]:
        if (validation["sessionId"], validation["revision"]) not in revisions:
            raise StoreError(422, "통찰 확인의 원래 공부 버전이 없습니다.")
    for entry in source["imports"]:
        if any(sid not in sessions for sid in entry["sessionIds"]):
            raise StoreError(422, "가져오기 이력이 공부 기록과 일치하지 않습니다.")
    # All schema and cross-reference validation precedes changes. The store also
    # rolls the entire transaction back on any later collision or write failure.
    existing_types = {row["id"]: collection for collection in collections for row in document[collection]}
    existing_revisions = {(row["sessionId"], row["revision"]): row["id"] for row in document["revisions"]}
    for revision in source["revisions"]:
        previous_id = existing_revisions.get((revision["sessionId"], revision["revision"]))
        if previous_id is not None and previous_id != revision["id"]:
            raise StoreError(409, "같은 공부 버전에 다른 이력 ID가 있어 가져오기를 취소했습니다.")
    for collection in collections:
        existing = {row["id"]: row for row in document[collection]}
        for row in source[collection]:
            if row["id"] in existing_types and existing_types[row["id"]] != collection:
                raise StoreError(409, "서로 다른 종류의 기록 ID가 충돌해 가져오기를 취소했습니다.")
            if row["id"] in existing and compare_record(existing[row["id"]]) != compare_record(row):
                raise StoreError(409, "같은 ID에 다른 내용이 있어 가져오기를 취소했습니다. 기존 기록은 유지됩니다.")
    if document["version"] == 0 and not any(document[collection] for collection in collections):
        document["curriculum"] = copy.deepcopy(source["curriculum"])
    existing_session_ids = {s["id"] for s in document["sessions"]}
    for session in source["sessions"]:
        if session["id"] in existing_session_ids:
            continue
        try:
            private = make_lesson(source["curriculum"], session["lessonDate"], company=session["company"])
            if public_lesson(private) == session["lesson"]:
                document["_lessons"][session["id"]] = private
        except StoreError:
            pass  # Old definitions remain readable but cannot grade new attempts.
    for collection in collections:
        existing = {row["id"] for row in document[collection]}
        document[collection].extend(imported_record(row) for row in source[collection] if row["id"] not in existing)
    document["imports"].append({"id": str(uuid4()), "format": backup.format, "importedAt": utcnow().isoformat(),
                                "sessionIds": list(sessions), "sourceExportedAt": backup.exportedAt,
                                "sourceVersion": backup.workspace.version})
    return {}


def create_router(store=None):
    # Lazy configuration is intentionally independent of FastAPI startup readiness.
    selected = store
    limiter = AuthLimiter()

    def storage():
        nonlocal selected
        if selected is None:
            selected = LearningStore()
        return selected

    def identity(request):
        cached = getattr(request.state, "learning_identity", None)
        if cached is not None:
            return cached
        authorization = request.headers.get("Authorization", "")
        match = re.fullmatch(r"Bearer ([A-Za-z0-9_-]{43})", authorization)
        if not match:
            raise StoreError(401, "복구 키로 공부 계정에 연결해 주세요.")
        token = match[1]
        result = storage().authenticate(token), token
        request.state.learning_identity = result
        return result

    def mutate(request, payload, callback):
        account_id, _ = identity(request)
        body = payload.model_dump(mode="json")
        fingerprint = hashlib.sha256(json.dumps({"path": request.url.path, "body": body},
            sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        return storage().transact(account_id, str(payload.requestId), payload.expectedVersion, fingerprint, callback)

    class AuthenticatedRoute(PrivateRoute):
        authenticate_request = staticmethod(identity)

    router = APIRouter(prefix="/api/learning", tags=["learning"], route_class=AuthenticatedRoute)

    @router.get("/status")
    def status():
        return storage().status()

    @router.get("/catalog")
    def get_catalog():
        return catalog()

    @router.post("/accounts")
    def create_account(request: Request, payload: Empty):
        limiter.check(request, "accounts", 10)
        return storage().create_account(empty_workspace())

    @router.post("/auth")
    def recover(request: Request, payload: Recovery):
        limiter.check(request, "auth", 30)
        return storage().recover(payload.recoveryKey)

    @router.delete("/auth")
    def logout(request: Request):
        _, token = identity(request)
        storage().revoke(token)
        return {"ok": True}

    @router.delete("/account")
    def delete_account(request: Request, payload: DeleteAccount):
        account_id, _ = identity(request)
        storage().delete_account(account_id)
        return {"ok": True}

    @router.get("/workspace")
    def get_workspace(request: Request):
        account_id, _ = identity(request)
        return workspace(storage().read(account_id))

    @router.get("/lessons/{lesson_date}")
    def get_lesson(request: Request, lesson_date: str, symbol: str | None = None):
        account_id, _ = identity(request)
        document = storage().read(account_id)
        return public_lesson(make_lesson(document["curriculum"], lesson_date, symbol=symbol))

    @router.post("/sessions")
    def save(request: Request, payload: SavePayload):
        return mutate(request, payload, lambda doc: save_session(doc, payload.session, payload.complete))

    @router.post("/sessions/{session_id}/quiz")
    def quiz(request: Request, session_id: UUID, payload: QuizPayload):
        return mutate(request, payload, lambda doc: submit_quiz(doc, str(session_id), payload, False))

    @router.post("/sessions/{session_id}/reviews")
    def review(request: Request, session_id: UUID, payload: QuizPayload):
        return mutate(request, payload, lambda doc: submit_quiz(doc, str(session_id), payload, True))

    @router.post("/sessions/{session_id}/validations")
    def validate_insight(request: Request, session_id: UUID, payload: ValidationPayload):
        def append(document):
            sid = str(session_id)
            find_session(document, sid)
            if not any(r["sessionId"] == sid and r["revision"] == payload.revision for r in document["revisions"]):
                raise StoreError(422, "확인할 원래 기록의 버전을 찾을 수 없습니다.")
            value = payload.model_dump(exclude={"requestId", "expectedVersion"})
            document["validations"].append({"id": str(uuid4()), "sessionId": sid, "createdAt": utcnow().isoformat(), **value})
            return {"sessionId": sid}
        return mutate(request, payload, append)

    @router.put("/curriculum")
    def update_curriculum(request: Request, payload: CurriculumPayload):
        def update(document):
            try:
                document["curriculum"] = validate_curriculum(payload.curriculum.model_dump())
            except ValueError as exc:
                raise StoreError(422, "주차·기업의 중복, 이름 길이와 커리큘럼 형식을 확인해 주세요.") from exc
        return mutate(request, payload, update)

    @router.get("/export")
    def export(request: Request):
        account_id, _ = identity(request)
        return {"format": "chartview-learning-backup", "schemaVersion": 1, "exportedAt": utcnow().isoformat(),
                "workspace": workspace(storage().read(account_id))}

    @router.post("/import")
    def import_record(request: Request, payload: ImportPayload):
        return mutate(request, payload, lambda doc: merge_import(doc, payload.payload))

    return router


router = create_router()
