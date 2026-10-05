# 새 PC Codex 인수인계 — Chart View 공유 서버

최종 갱신: 2026-10-05 KST. 최신 main과 이 문서가 작업 시작점이다. 대화 기록·이전 PC의 work/outputs/임시 경로에 의존하지 않는다.

## 두 저장소와 서비스

- **이 저장소** [chart_View](https://github.com/shoon94parkk-del/chart_View): FastAPI API, 수집·공시·데이터 캐시, 별도 Web UI. 루트 `main.py`, `templates/`, `static/`가 활성 경로. 과거 `toss_stock_app/` 사본은 실행 경로가 아니다.
- **모바일 UI** [chart-view-toss](https://github.com/shoon94parkk-del/chart-view-toss): 토스 앱 셸/디자인/네이티브 연동. [사용자 UI 선호·프런트 설정](https://github.com/shoon94parkk-del/chart-view-toss/blob/main/docs/CODEX_HANDOFF.md)을 먼저 읽는다.
- B: https://chart-view-pkv8.onrender.com, Render Chart View workspace `tea-dao48j942hec738cpseg`, service `srv-dao4a50473hc73bclej0`, source main.
- F: https://chart-view-toss.onrender.com, service `srv-dao4n4mk1f9s73algnf0`. Render branch `feat/apps-in-toss-mvp`는 F GitHub Actions가 main에서 동기화한다.
- legacy chart-view-bsg6는 현재 검증 대상이 아니다.

`AGENTS.md`, no-repeat-regression-policy, project-memory, regression-guardrails, decision-log, handover를 읽고 관련 테스트·최근 커밋을 확인한다. 같은 문제가 재발하면 알려진 정상 계약과 회귀 테스트부터 복구한다.

## 최근 상태와 구조

주식 비교·실시간 가격 정합성·공시 기반 분석·수출·반도체 시장가격·선정 기록·인사이트 동선·작은 모바일 UI를 반복 개선했다. 상세 계약은 두 저장소의 최신 project-memory/decision-log에 있다. 특히 오래된 표시 가격을 실시간/오늘 가격으로 재표시하거나 상세의 새 값을 이전 캐시로 되돌리지 않는다. optional 공시·뉴스·밸류가 주가 첫 화면을 막지 않아야 한다.

거장 투자법은 새 독립 캐시 분석이다. `guru_rules.py`의 버핏·린치 수학은 유지; `guru_extensions.py`가 오닐/미너비니/그린블라트 대안을 담당한다. [다섯 방법 계획·기준·검증 기록](guru-five-implementation-2026-10-05.md)과 [데이터 계약](guru-data-contract.md)을 읽는다.

| 파일 | 역할 |
|---|---|
| guru_financials.json | 4년 비교 가능한 연간 계정·원공시·기업행동 검증; 1차2,652종목 확인 기록 |
| guru_market.json | 최대273거래일의 실제 Yahoo OHLCV, 같은 거래일 검증; 새 가격 확인 실패 시 기존 캐시 보존 |
| guru_quarters.json | 오닐 연간 필요조건을 통과한 기업의 원공시 단일 분기 EPS·매출 비교 |
| guru_screening.json | cv-gurus-v2 다섯 전략·조건별 전체 대상/지원제외/대기/자료부족/미충족/충족 집계 |
| guru_evidence.json | 결과와 동일 snapshotVersion의 종목 근거·공시·일봉; API 방문 시 공급자 호출 없음 |

기준일은 `screener.json.tradeDate`. 일봉 현재 종가와 0.1% 이내로 일치해야 한다. 상대강도 비교 대상은 KIND 일반기업 중 **동일 거래일 양수 종가가 검증된 기업**. 이 대상의 유효253거래일 일봉이90% 미만이면 추세/돌파 결과를 게시하지 않는다. 종가·이력 부족은 전체2,652 대상의 insufficient로 표시한다. RS는252거래일 단순 수익률의 동률 중간 백분위이며 RSI/IBD Rating이 아니다.

**그린블라트는 ROA/PER 대안**, EV 매직포뮬러가 아니다. 최근 연간 순이익/기말 자산≥25%, 연간 PER5~20, 금융·유틸리티 제외, 낮은 PER 순 최대30. 오닐은 CAN SLIM의 정량 일부이고 차트 패턴/기관 수급/시장 방향은 확인하지 않는다. 누적 EPS의 차이로 분기 EPS를 만들지 않는다. Q4는 검증 가능한 단일 분기 기본 EPS가 없으면 insufficient이며 임의 복원하지 않는다.

## 새 PC 실행

Git, Python3.11+, Node24.21.0/npm10–11. 프런트와 백엔드를 각각 clone한 뒤 main에서 새 작업 브랜치를 만든다.

```powershell
git clone https://github.com/shoon94parkk-del/chart_View.git
cd chart_View
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt yfinance pytest httpx
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe scripts/build_frontend_bundle.py --check
.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

저장된 guru 데이터의 계산/조회에는 DART 키가 없어도 된다. 실제 공급자 수집은 기존 GitHub Actions Secret `DART_API_KEY`를 사용한다. 키/훅/토큰을 문서·커밋·대화에 쓰지 않는다. 새 PC에서 GitHub/Codex/Render 인증은 본인의 기존 계정으로 한다. 로컬 브라우저 관심·메모와 인증 세션은 clone으로 이동하지 않는다.

## 재현·수집 명령

```powershell
# 공급자 호출 없이 현재 저장 자료로 결과 재계산
.venv/Scripts/python.exe scripts/generate_guru_screening.py
# 일봉 수집; 첫 수집 후 빠진 항목만 재시도 가능
.venv/Scripts/python.exe scripts/generate_guru_market.py --max-seconds 240
.venv/Scripts/python.exe scripts/generate_guru_market.py --only-missing --max-seconds 180
# 기존 DART 키를 설정한 서버/Actions 환경에서만
.venv/Scripts/python.exe scripts/collect_guru_quarters.py --max-companies 400 --max-requests 1000 --max-seconds 300
.venv/Scripts/python.exe scripts/generate_guru_screening.py
```

GitHub Actions **Update Guru Screening**는05:00KST 일정 및 성공한 기술스크리너 갱신 후 실행된다. 수동 실행 inputs: `collect=false`, `collect_extensions=true`면 기존 연간 계정은 재수집하지 않고 추세/필요분기만 수집한다. 초기 연간 갱신 기본400기업/2400요청/1200초와 분기 별도400기업/1000요청/300초는 상한이며, 일봉240초를 더해 job35분이다. DART020이면 더 호출하지 않는다. 같은 날 반복 전 공급자 사용량을 살펴본다. 이력·계정이 부족하다고 한도를 무작정 높이거나 값을0으로 만들지 않는다.

커밋 충돌 시 최신 main의 가격에 맞춰 재계산하고 관찰이 더 오래된 캐시가 최신 자료를 덮어쓰지 않게 merge 스크립트를 사용한다. evidence 먼저/snapshot 나중에 원자 교체하며 다른 버전 API는409다. 가격 종가 기준일·공시일·확인일·생성일은 서로 다르다.

## 배포·검증·남은 작업

**기존 Render 서비스를 수동 배포**한다. GitHub 변경을 올렸다는 사실만으로 배포 완료라고 보고하지 않는다. 이 서비스는 설정에OnCommit이 보여도 이전 main 변경 뒤 자동 배포가 관찰되지 않았다. 사용자는 Edge Render의 수동 배포를 선택했고, 기존 훅을 GitHub Secret에 새로 저장하는 승인은 받지 않았다. 일일 수집과 API 일일 배포 연결은 별도 미완료다.

1. 관련 Python/Node/build/mobile CI를 통과한 정확한 main SHA를 확인.
2. workspace **Chart View**의 위 B 서비스에서 **Deploy latest commit**.
3. Live 이후 `/health.revision`이 해당 SHA인지 확인.
4. 세 공용Web 자산의 Git canonical blob 해시/HTML release key 정합성과 guru 결과·증거 버전을 검증.
5. 전략별 실제 후보 API200·오래된 버전409, 모든 F 직접 전략 경로HTTP200, 모바일320/390/430 동선을 검증.

표시상Live만으로 완료라고 말하지 않는다. 데이터 커밋도 서버 근거 파일을 바꾸므로 새 배포가 필요하다. F raw GitHub CDN이 B보다 먼저 갱신되면 명시적 최신 결과 확인은 B snapshot으로 복구한다. 배포를 연속 중복 실행하지 않는다.

실제 Android/iOS Toss Sandbox, 공개 제출/정책/데이터 공급자 권리는 프런트 `P0_RELEASE_GATE.md`에 남아 있다. 웹 미리보기 검증과 구분한다. 최종 배포 SHA·PR·운영 개수는 계획의 검증 기록과 GitHub Actions/Render를 확인한다. 옛 인수인계 숫자를 오늘 실시간 값으로 간주하지 않는다.
