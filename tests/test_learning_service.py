"""Learning API contracts against actual durable adapters, never market startup."""
import concurrent.futures
import asyncio
import copy
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from learning_content import build_lesson, default_curriculum
from learning_service import MAX_IMPORT_BYTES, create_router
from learning_store import LearningStore


def client_for(store):
    app = FastAPI()
    app.include_router(create_router(store))
    return TestClient(app)


@pytest.fixture(params=["sqlite", "postgres"])
def store(tmp_path, request, monkeypatch):
    if request.param == "postgres":
        url = os.environ.get("LEARNING_TEST_DATABASE_URL")
        if not url:
            pytest.skip("Set LEARNING_TEST_DATABASE_URL to exercise real PostgreSQL")
        result = LearningStore(database_url=url)
    else:
        result = LearningStore(database_url="", sqlite_path=str(tmp_path / "learning.sqlite"))
    created = []
    original = result.create_account
    def create(document):
        value = original(document)
        created.append(value["accountId"])
        return value
    monkeypatch.setattr(result, "create_account", create)
    yield result
    for account_id in created:
        result.delete_account(account_id)


@pytest.fixture
def client(store):
    return client_for(store)


def account(client):
    response = client.post("/api/learning/accounts", json={})
    assert response.status_code == 200, response.text
    result = response.json()
    return result, {"Authorization": "Bearer " + result["token"]}


def mutation(version=0, **fields):
    return {"requestId": str(uuid4()), "expectedVersion": version, **fields}


def editable(**overrides):
    return {"lessonDate": "2026-11-02", "notes": {key: "" for key in (
        "business", "customers", "financials", "growthDrivers", "macro", "newFacts", "unknowns", "judgment", "indicators")},
        "insight": {"growth": "고객 수요와 공급 능력 확인", "risk": "경쟁 심화와 가격 하락", "metrics": "분기 매출과 영업이익률"},
        "understanding": None, "minutes": 0, **overrides}


def save(client, headers, version=0, **overrides):
    response = client.post("/api/learning/sessions", headers=headers,
        json=mutation(version, session=editable(**overrides), complete=True))
    assert response.status_code == 200, response.text
    return response.json()


def quiz_payload(version, correct=True):
    lesson = build_lesson(default_curriculum(), "2026-11-02")
    return mutation(version, answers={q["id"]: q["correctIndex"] if correct else
        (q["correctIndex"] + 1) % len(q["options"]) for q in lesson["questions"]},
        judgment={"answer": "사업보고서의 고객 집중도와 수익성을 함께 확인한다.",
                  "rubric": {"evidence": 2, "logic": 3, "indicators": 1}})


def test_readiness_is_explicit_and_render_refuses_local_disk(tmp_path, monkeypatch):
    monkeypatch.delenv("LEARNING_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("LEARNING_SQLITE_PATH", raising=False)
    with client_for(LearningStore()) as c:
        assert c.get("/api/learning/status").json() == {"configured": False, "storage": None}
        response = c.post("/api/learning/accounts", json={})
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
    monkeypatch.setenv("RENDER", "true")
    with client_for(LearningStore(sqlite_path=str(tmp_path / "forbidden.sqlite"))) as c:
        assert c.post("/api/learning/accounts", json={}).status_code == 503
    assert not (tmp_path / "forbidden.sqlite").exists()


def test_authentication_hashing_isolation_recovery_logout_and_restart(client, store):
    first, headers = account(client)
    assert len(first["recoveryKey"]) >= 43
    second, other = account(client)
    assert first["accountId"] != second["accountId"]
    result = save(client, headers)
    assert client.get("/api/learning/workspace", headers=other).json()["sessions"] == []
    assert client.post(f'/api/learning/sessions/{result["sessionId"]}/quiz', headers=other,
        json=quiz_payload(0)).status_code == 404
    restart = client_for(LearningStore(database_url=store.database_url, sqlite_path=store.sqlite_path))
    restored = restart.post("/api/learning/auth", json={"recoveryKey": first["recoveryKey"]})
    assert restored.status_code == 200
    rh = {"Authorization": "Bearer " + restored.json()["token"]}
    assert restart.get("/api/learning/workspace", headers=rh).json()["version"] == 1
    if store.storage == "sqlite":
        raw = open(store.sqlite_path, "rb").read()
        assert first["token"].encode() not in raw and first["recoveryKey"].encode() not in raw
    else:
        with store._connection() as db:
            recovery_hash, document = db.execute("SELECT recovery_hash,document FROM learning_accounts WHERE id=%s", (first["accountId"],)).fetchone()
            token_hash = db.execute("SELECT token_hash FROM learning_sessions WHERE account_id=%s LIMIT 1", (first["accountId"],)).fetchone()[0]
        assert first["recoveryKey"] != recovery_hash and first["token"] != token_hash
        assert first["recoveryKey"] not in document and first["token"] not in document
    assert client.delete("/api/learning/auth", headers=headers).status_code == 200
    assert client.get("/api/learning/workspace", headers=headers).status_code == 401
    assert restart.get("/api/learning/workspace", headers=rh).status_code == 200
    with store._connection(write=True) as db:
        store._sql(db, "UPDATE learning_sessions SET expires_at=%s WHERE account_id=%s",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), first["accountId"]))
    assert restart.get("/api/learning/workspace", headers=rh).status_code == 401


@pytest.mark.parametrize("path,method,body", [("/workspace", "get", None),
    ("/sessions", "post", {}), ("/account", "delete", {"confirmation": "WRONG"}),
    ("/lessons/2026-02-30", "get", None)])
def test_private_success_and_errors_are_no_store(client, path, method, body):
    _, headers = account(client)
    kwargs = {"headers": headers}
    if body is not None:
        kwargs["json"] = body
    response = client.request(method, "/api/learning" + path, **kwargs)
    assert response.headers["cache-control"] == "no-store"
    unauthorized = client.get("/api/learning/workspace")
    assert unauthorized.status_code == 401 and unauthorized.headers["cache-control"] == "no-store"


def test_draft_completion_server_grade_append_history_and_revision_invalidation(client):
    _, headers = account(client)
    public = client.get("/api/learning/lessons/2026-11-02", headers=headers).json()
    assert all(not ({"correctIndex", "explanation", "concept"} & set(q)) for q in public["questions"])
    assert client.get("/api/learning/lessons/2026-12-14", headers=headers).status_code == 404
    bad = editable(insight={"growth": "", "risk": "", "metrics": ""})
    failed = client.post("/api/learning/sessions", headers=headers, json=mutation(session=bad, complete=True))
    assert failed.status_code == 422
    draft = client.post("/api/learning/sessions", headers=headers, json=mutation(session=bad, complete=False)).json()
    sid = draft["sessionId"]
    assert draft["workspace"]["sessions"][0]["status"] == "in_progress"
    assert client.post(f"/api/learning/sessions/{sid}/quiz", headers=headers, json=quiz_payload(1)).status_code == 422
    completed = save(client, headers, 1, id=sid)
    assert completed["workspace"]["sessions"][0]["status"] == "completed"
    incomplete = quiz_payload(2)
    incomplete["answers"].pop(next(iter(incomplete["answers"])))
    assert client.post(f"/api/learning/sessions/{sid}/quiz", headers=headers, json=incomplete).status_code == 422
    assert client.get("/api/learning/workspace", headers=headers).json()["version"] == 2
    graded = client.post(f"/api/learning/sessions/{sid}/quiz", headers=headers, json=quiz_payload(2)).json()["workspace"]
    attempt = graded["attempts"][0]
    assert attempt["score"] == 100 and attempt["judgment"]["score"] == 50
    assert attempt["judgment"]["assessment"] == "self"
    assert graded["sessions"][0]["status"] == "evaluated"
    changed = editable(id=sid)
    changed["notes"]["newFacts"] = "기존 가정을 변경하는 새 공시 확인"
    edited = client.post("/api/learning/sessions", headers=headers, json=mutation(3, session=changed, complete=True)).json()["workspace"]
    assert edited["sessions"][0]["status"] == "completed"
    assert len(edited["attempts"]) == 1 and len(edited["revisions"]) == 3
    reviewed = client.post(f"/api/learning/sessions/{sid}/reviews", headers=headers, json=quiz_payload(4, False)).json()["workspace"]
    assert len(reviewed["attempts"]) == 2 and len(reviewed["reviews"]) == 1
    assert reviewed["attempts"][-1]["wrongAnswers"] and reviewed["attempts"][-1]["score"] == 0
    assert reviewed["attempts"][-1]["sessionRevision"] == 3
    assert reviewed["reviews"][0]["nextReviewDate"] < graded["sessions"][0]["nextReviewDate"]


def test_optimistic_version_conflicts_idempotent_success_and_concurrency(client):
    _, headers = account(client)
    payload = mutation(session=editable(), complete=True)
    first = client.post("/api/learning/sessions", headers=headers, json=payload)
    replay = client.post("/api/learning/sessions", headers=headers, json=payload)
    assert replay.json() == first.json()
    changed = copy.deepcopy(payload)
    changed["session"]["minutes"] = 10
    assert client.post("/api/learning/sessions", headers=headers, json=changed).status_code == 409
    assert client.post("/api/learning/sessions", headers=headers, json=mutation(session=editable(), complete=True)).status_code == 409
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        codes = list(pool.map(lambda _: client.post("/api/learning/sessions", headers=headers,
            json=mutation(1, session=editable(), complete=True)).status_code, range(2)))
    assert sorted(codes) == [200, 409]
    later_replay = client.post("/api/learning/sessions", headers=headers, json=payload).json()
    assert later_replay["requestVersion"] == 1 and later_replay["workspace"]["version"] == 2
    assert len(later_replay["workspace"]["sessions"]) == 2


def test_curriculum_edit_pins_quiz_and_validations_append(client):
    _, headers = account(client)
    result = save(client, headers)
    sid, old_lesson = result["sessionId"], result["workspace"]["sessions"][0]["lesson"]
    curriculum = result["workspace"]["curriculum"]
    curriculum["weeks"][0]["companies"].reverse()
    response = client.put("/api/learning/curriculum", headers=headers, json=mutation(1, curriculum=curriculum))
    assert response.status_code == 200
    assert response.json()["workspace"]["sessions"][0]["lesson"] == old_lesson
    validation = mutation(2, revision=1, assumption="고객 주문 증가가 매출을 견인한다", observed="분기 공시의 제품별 매출을 확인했다",
        evidenceUrl="https://dart.fss.or.kr/", evidenceDate="2026-11-01", outcome="inconclusive", currentJudgment="다음 분기 주문을 관찰한다")
    response = client.post(f"/api/learning/sessions/{sid}/validations", headers=headers, json=validation)
    assert response.status_code == 200 and len(response.json()["workspace"]["validations"]) == 1
    invalid = {**validation, "requestId": str(uuid4()), "expectedVersion": 3, "evidenceUrl": "javascript:alert(1)"}
    assert client.post(f"/api/learning/sessions/{sid}/validations", headers=headers, json=invalid).status_code == 422


def test_backup_atomic_merge_external_provenance_and_delete(client):
    _, headers = account(client)
    saved = save(client, headers)
    client.post(f'/api/learning/sessions/{saved["sessionId"]}/quiz', headers=headers, json=quiz_payload(1))
    backup = client.get("/api/learning/export", headers=headers).json()
    assert "token" not in json.dumps(backup) and "recoveryKey" not in json.dumps(backup)
    _, target = account(client)
    result = client.post("/api/learning/import", headers=target, json=mutation(payload=backup))
    assert result.status_code == 200, result.text
    workspace = result.json()["workspace"]
    assert workspace["sessions"][0]["status"] == "completed"
    assert workspace["attempts"][0]["provenance"] == "imported"
    corrupt = copy.deepcopy(backup)
    corrupt["workspace"]["sessions"].append({**corrupt["workspace"]["sessions"][0], "id": str(uuid4()), "lessonDate": "2026-02-30"})
    assert client.post("/api/learning/import", headers=target, json=mutation(1, payload=corrupt)).status_code == 422
    assert client.get("/api/learning/workspace", headers=target).json() == workspace
    collision = copy.deepcopy(backup)
    collision["workspace"]["sessions"][0]["notes"]["business"] = "충돌"
    collision["workspace"]["revisions"][0]["session"]["notes"]["business"] = "충돌"
    assert client.post("/api/learning/import", headers=target, json=mutation(1, payload=collision)).status_code == 409
    external = {"format": "chartview-learning-result", "schemaVersion": 1, "session": editable(), "externalAssessment": {"score": 99, "notes": "외부 평가"}}
    imported = client.post("/api/learning/import", headers=target, json=mutation(1, payload=external)).json()["workspace"]
    assert len(imported["attempts"]) == 1
    assert imported["imports"][-1]["externalAssessment"]["assessment"] == "external"
    assert all(s["status"] != "evaluated" for s in imported["sessions"])
    assert client.request("DELETE", "/api/learning/account", headers=target, json={"confirmation": "DELETE"}).status_code == 200
    assert client.get("/api/learning/workspace", headers=target).status_code == 401


def test_public_account_creation_and_recovery_are_rate_limited(client):
    for _ in range(10):
        account(client)
    limited = client.post("/api/learning/accounts", json={})
    assert limited.status_code == 429 and limited.headers["cache-control"] == "no-store"
    for _ in range(30):
        assert client.post("/api/learning/auth", json={"recoveryKey": "x" * 43}).status_code == 401
    assert client.post("/api/learning/auth", json={"recoveryKey": "x" * 43}).status_code == 429


def test_strict_values_and_source_context_reject_private_extra_fields(client):
    _, headers = account(client)
    for overrides in ({"minutes": True}, {"understanding": 101}, {"sourceContext": {"kind": "pick", "researchNotes": "private"}},
                      {"insight": {"growth": "a", "risk": "b", "metrics": "c", "score": 100}}):
        response = client.post("/api/learning/sessions", headers=headers,
            json=mutation(session=editable(**overrides), complete=False))
        assert response.status_code == 422
    assert client.get("/api/learning/workspace", headers=headers).json()["version"] == 0


def test_quiz_retry_does_not_append_and_tampered_backup_rolls_back(client):
    _, headers = account(client)
    saved = save(client, headers)
    sid = saved["sessionId"]
    payload = quiz_payload(1)
    first = client.post(f"/api/learning/sessions/{sid}/quiz", headers=headers, json=payload)
    second = client.post(f"/api/learning/sessions/{sid}/quiz", headers=headers, json=payload)
    assert second.json() == first.json()
    assert len(second.json()["workspace"]["attempts"]) == 1
    backup = client.get("/api/learning/export", headers=headers).json()
    backup["workspace"]["sessions"][0]["notes"]["business"] = "이력과 다른 현재 버전"
    _, target = account(client)
    response = client.post("/api/learning/import", headers=target, json=mutation(payload=backup))
    assert response.status_code == 422
    assert client.get("/api/learning/workspace", headers=target).json()["version"] == 0


def test_saved_history_survives_a_fresh_python_process(client, store):
    credentials, headers = account(client)
    save(client, headers)
    script = """import json,sys
from learning_store import LearningStore
payload=json.load(sys.stdin)
store=LearningStore(database_url=payload['databaseUrl'],sqlite_path=payload['sqlitePath'])
auth=store.recover(payload['recoveryKey'])
doc=store.read(auth['accountId'])
print(json.dumps({'version':doc['version'],'sessions':len(doc['sessions'])}))
"""
    result = subprocess.run([sys.executable, "-c", script], input=json.dumps({"databaseUrl": store.database_url,
        "sqlitePath": store.sqlite_path, "recoveryKey": credentials["recoveryKey"]}), text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == {"version": 1, "sessions": 1}


def test_import_capacity_exceeds_ordinary_command_limit(client):
    _, headers = account(client)
    payload = mutation(payload={"junk": "x" * (4 * 1024 * 1024)})
    assert client.post("/api/learning/import", headers=headers, json=payload).status_code == 422
    assert client.post("/api/learning/sessions", headers=headers, json=payload).status_code == 413


def test_import_version_and_duration_are_strict_integers(client):
    _, headers = account(client)
    external = {"format": "chartview-learning-result", "schemaVersion": True, "session": editable()}
    assert client.post("/api/learning/import", headers=headers, json=mutation(payload=external)).status_code == 422
    save(client, headers)
    backup = client.get("/api/learning/export", headers=headers).json()
    backup["workspace"]["sessions"][0]["lesson"]["duration"] = 25.0
    _, other = account(client)
    assert client.post("/api/learning/import", headers=other, json=mutation(payload=backup)).status_code == 422


def test_custom_company_dated_records_and_external_backup_round_trip(client, store):
    _, headers = account(client)
    custom = {"symbol": "CUSTOM", "name": "새 기업", "industry": "새 산업"}
    first = save(client, headers, company=custom, lessonDate="2027-01-01")
    second = save(client, headers, 1, company=custom, lessonDate="2027-01-02")
    assert first["sessionId"] != second["sessionId"]
    assert len(second["workspace"]["sessions"]) == 2
    external = {"format": "chartview-learning-result", "schemaVersion": 1, "session": editable(),
                "externalAssessment": {"score": 0, "notes": "외부 점수 0도 실제 값으로 보존"}}
    assert client.post("/api/learning/import", headers=headers, json=mutation(2, payload=external)).status_code == 200
    backup = client.get("/api/learning/export", headers=headers).json()
    _, target = account(client)
    imported = client.post("/api/learning/import", headers=target, json=mutation(payload=backup))
    assert imported.status_code == 200, imported.text
    workspace = imported.json()["workspace"]
    assert len(workspace["sessions"]) == 3 and len(workspace["revisions"]) == 3
    assert workspace["imports"][0]["externalAssessment"]["score"] == 0
    repeated = client.post("/api/learning/import", headers=target, json=mutation(1, payload=backup))
    assert repeated.status_code == 200, repeated.text
    assert len(repeated.json()["workspace"]["sessions"]) == 3
    assert len(repeated.json()["workspace"]["revisions"]) == 3
    with store._connection() as db:
        rows = db.execute("SELECT result FROM learning_requests").fetchall()
    assert all("workspace" not in json.loads(row[0]) and len(row[0]) < 300 for row in rows)


def test_unknown_import_properties_cannot_inject_secrets_or_private_answers(client):
    _, headers = account(client)
    save(client, headers)
    backup = client.get("/api/learning/export", headers=headers).json()
    for inject in (lambda doc: doc.update(token="secret"),
                   lambda doc: doc["workspace"].update(_lessons={}),
                   lambda doc: doc["workspace"]["sessions"][0]["lesson"]["questions"][0].update(correctIndex=0)):
        value = copy.deepcopy(backup)
        inject(value)
        response = client.post("/api/learning/import", headers=headers, json=mutation(1, payload=value))
        assert response.status_code == 422
    assert client.get("/api/learning/workspace", headers=headers).json()["version"] == 1


@pytest.mark.parametrize("change", ["duplicate", "long_week", "long_company", "long_industry"])
def test_curriculum_invalid_for_content_is_rejected_before_commit(client, change):
    _, headers = account(client)
    curriculum = default_curriculum()
    if change == "duplicate":
        curriculum["weeks"][0]["companies"][1] = curriculum["weeks"][0]["companies"][0]
    elif change == "long_week":
        curriculum["weeks"][0]["id"] = "w" * 161
    elif change == "long_company":
        curriculum["weeks"][0]["companies"][0]["name"] = "n" * 121
    else:
        curriculum["weeks"][0]["industry"] = "i" * 81
    response = client.put("/api/learning/curriculum", headers=headers, json=mutation(curriculum=curriculum))
    assert response.status_code == 422
    document = client.get("/api/learning/workspace", headers=headers).json()
    assert document["version"] == 0 and document["curriculum"] == default_curriculum()
    assert client.get("/api/learning/lessons/2026-11-02", headers=headers).status_code == 200


def test_document_capacity_is_bounded_and_rejection_is_atomic(client, store, monkeypatch):
    assert store.MAX_DOCUMENT_BYTES == 128 * 1024 * 1024
    assert MAX_IMPORT_BYTES == 160 * 1024 * 1024
    _, headers = account(client)
    monkeypatch.setattr(store, "MAX_DOCUMENT_BYTES", 1024)
    response = client.post("/api/learning/sessions", headers=headers,
        json=mutation(session=editable(), complete=True))
    assert response.status_code == 422
    current = client.get("/api/learning/workspace", headers=headers).json()
    assert current["version"] == 0 and current["sessions"] == [] and current["revisions"] == []


def test_huge_untrusted_revision_is_rejected_without_allocating_its_range(client):
    _, headers = account(client)
    save(client, headers)
    backup = client.get("/api/learning/export", headers=headers).json()
    backup["workspace"]["sessions"][0]["revision"] = 10**9
    backup["workspace"]["revisions"][0]["revision"] = 10**9
    backup["workspace"]["revisions"][0]["session"]["revision"] = 10**9
    _, target = account(client)
    response = client.post("/api/learning/import", headers=target, json=mutation(payload=backup))
    assert response.status_code == 422
    assert client.get("/api/learning/workspace", headers=target).json()["version"] == 0


def test_invalid_backup_curriculum_cannot_merge(client):
    _, headers = account(client)
    save(client, headers)
    backup = client.get("/api/learning/export", headers=headers).json()
    companies = backup["workspace"]["curriculum"]["weeks"][0]["companies"]
    companies[1] = copy.deepcopy(companies[0])
    _, target = account(client)
    response = client.post("/api/learning/import", headers=target, json=mutation(payload=backup))
    assert response.status_code == 422
    assert client.get("/api/learning/workspace", headers=target).json()["version"] == 0


def test_backup_cannot_duplicate_existing_session_revision_with_a_new_id(client):
    _, headers = account(client)
    save(client, headers)
    backup = client.get("/api/learning/export", headers=headers).json()
    _, target = account(client)
    assert client.post("/api/learning/import", headers=target, json=mutation(payload=backup)).status_code == 200
    changed = copy.deepcopy(backup)
    changed["workspace"]["revisions"][0]["id"] = str(uuid4())
    response = client.post("/api/learning/import", headers=target, json=mutation(1, payload=changed))
    assert response.status_code == 409
    current = client.get("/api/learning/workspace", headers=target).json()
    assert current["version"] == 1 and len(current["revisions"]) == 1


def test_backup_restores_fresh_schedule_and_preserves_existing_schedule(client):
    _, headers = account(client)
    original = default_curriculum()
    original["title"] = "복원할 사용자 공부 계획"
    original["weeks"][0]["companies"].reverse()
    assert client.put("/api/learning/curriculum", headers=headers, json=mutation(curriculum=original)).status_code == 200
    save(client, headers, 1)
    backup = client.get("/api/learning/export", headers=headers).json()
    _, fresh = account(client)
    restored = client.post("/api/learning/import", headers=fresh, json=mutation(payload=backup))
    assert restored.status_code == 200, restored.text
    assert restored.json()["workspace"]["curriculum"] == original
    _, existing = account(client)
    current = default_curriculum()
    current["title"] = "현재 계정의 보존할 계획"
    assert client.put("/api/learning/curriculum", headers=existing, json=mutation(curriculum=current)).status_code == 200
    merged = client.post("/api/learning/import", headers=existing, json=mutation(1, payload=backup))
    assert merged.status_code == 200, merged.text
    assert merged.json()["workspace"]["curriculum"] == current
    assert len(merged.json()["workspace"]["sessions"]) == 1


@pytest.mark.parametrize("authorization", [None, "Bearer " + "x" * 43])
def test_unauthenticated_import_never_consumes_request_body(store, authorization):
    app = FastAPI()
    app.include_router(create_router(store))
    consumed = []
    async def body():
        for _ in range(8):
            consumed.append(True)
            yield b"x" * (1024 * 1024)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://learning.test") as transport:
            return await transport.post("/api/learning/import", content=body(),
                headers={"Authorization": authorization} if authorization else {})
    response = asyncio.run(run())
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert consumed == []


def test_authenticated_stream_is_bounded_and_auth_runs_off_event_loop(store, monkeypatch):
    app = FastAPI()
    app.include_router(create_router(store))
    credentials = store.create_account({"schemaVersion": 1, "version": 0, "sessions": []})
    consumed, authentication_threads = [], []
    original = store.authenticate
    def authenticate(token):
        assert not consumed
        authentication_threads.append(threading.get_ident())
        return original(token)
    monkeypatch.setattr(store, "authenticate", authenticate)
    async def body():
        for _ in range(6):
            consumed.append(True)
            yield b"x" * (1024 * 1024)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://learning.test") as transport:
            headers = {"Authorization": "Bearer " + credentials["token"]}
            loaded = await transport.get("/api/learning/workspace", headers=headers)
            assert loaded.status_code == 200
            return await transport.post("/api/learning/sessions", content=body(), headers=headers)
    response = asyncio.run(run())
    assert response.status_code == 413 and response.headers["cache-control"] == "no-store"
    assert len(consumed) == 5
    assert len(authentication_threads) == 2
    assert all(worker != threading.get_ident() for worker in authentication_threads)
