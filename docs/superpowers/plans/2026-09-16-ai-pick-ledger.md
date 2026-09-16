# AI PICK Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목 발굴 내부에 누적형 `AI PICK 기록` 하위 탭을 추가하고, 장기 누적에 적합한 고밀도 원장 UI로 전환한다.

**Architecture:** 기존 릴리스 번들과 `screener.js`는 수정하지 않는다. 새 `ai_pick_ledger_v52.js`와 `ai_pick_ledger_v52.css`가 렌더된 `#screener-tab`을 확장해 하위 탭과 AI 원장을 주입한다. 홈 링크와 기존 정적 추천 페이지는 `?tab=screener&view=ai-picks` 진입점으로 통합한다.

**Tech Stack:** Vanilla JavaScript, CSS, FastAPI/Jinja static assets, pytest regression tests

**Spec:** `docs/superpowers/specs/2026-09-16-ai-pick-ledger-design.md`

## Global Constraints

- 기존 시장 스크리너 DOM과 이벤트를 깨뜨리지 않는다.
- AI PICK 성과 데이터는 `/static/data/ai_recommendations.json`을 사용한다.
- 누적 추천일 계산은 `/static/data/ai_daily_rankings.json`을 사용한다.
- 수익률 색상은 양수 빨강, 음수 파랑 기존 규칙을 유지한다.
- 모바일 700px 이하에서는 가로 스크롤 없이 압축 행을 사용한다.
- 한 번에 60개씩 렌더하고 더보기로 60개씩 추가한다.
- 기존 `/static/recommendations.html` 주소는 유지하되 새 탭으로 리다이렉트한다.

---

### Task 1: UI 계약 회귀 테스트

**Files:**
- Create: `tests/test_ai_pick_ledger_ui.py`

**Interfaces:**
- Consumes: `templates/index.html`, `static/js/ai_daily_widget.js`, 신규 원장 JS/CSS
- Produces: 정적 UI 계약 회귀 테스트

- [ ] **Step 1: 실패하는 테스트 작성**
  - `templates/index.html`에 `ai_pick_ledger_v52.css/js`가 포함되는지 검사한다.
  - 홈 링크가 `?tab=screener&view=ai-picks`를 가리키는지 검사한다.
  - 신규 JS에 `data-discovery-view="screener"`, `data-discovery-view="ai-picks"`, 60개 페이지 크기, 8개 원장 헤더 키워드가 존재하는지 검사한다.
  - CSS에 700px 모바일 분기와 원장 모바일 행 스타일이 존재하는지 검사한다.

- [ ] **Step 2: 테스트 실행 후 실패 확인**

```bash
pytest -q tests/test_ai_pick_ledger_ui.py
```

Expected: 신규 파일/참조가 아직 없으므로 FAIL.

### Task 2: AI PICK 원장 모듈과 스타일 구현

**Files:**
- Create: `static/js/ai_pick_ledger_v52.js`
- Create: `static/css/ai_pick_ledger_v52.css`

**Interfaces:**
- Produces: `window.__openAiPickLedger()`; URL `view=ai-picks` 처리; 서브탭 UI

- [ ] **Step 1: 하위 탭 래퍼 구현**
  - `#screener-tab .screener-section`을 `data-discovery-panel="screener"`로 감싼다.
  - 상단에 `시장 스크리너`/`AI PICK 기록` 버튼을 삽입한다.
  - 클릭 시 패널 hidden 상태와 aria-selected를 동기화한다.

- [ ] **Step 2: 데이터 로더와 KPI 구현**
  - 두 JSON을 `cache: no-store`로 병렬 로드한다.
  - 누적 추천일, 추천 건수, 양수 수익률 비율, 평균 수익률을 계산한다.

- [ ] **Step 3: 검색/필터/정렬 구현**
  - 검색: 종목명/코드/symbol.
  - 기간: all/7/30.
  - 성과: all/win/loss.
  - 정렬: latest/return/best/score.

- [ ] **Step 4: 60개 원장 렌더링과 상세 펼침 구현**
  - 기본 60개, 더보기 클릭 시 +60.
  - 각 행 버튼/키보드 접근성을 제공한다.
  - 상세 행은 등급, 상태, 추천 사유만 표시한다.

- [ ] **Step 5: 모바일 압축행 CSS 구현**
  - 700px 이하에서 thead를 숨기고 각 행을 grid 형태로 바꾼다.
  - 핵심 정보는 2~3줄에 유지하고 가로 스크롤을 제거한다.

### Task 3: 앱 진입점 통합

**Files:**
- Modify: `templates/index.html`
- Modify: `static/js/ai_daily_widget.js`
- Modify: `static/recommendations.html`

**Interfaces:**
- Consumes: `window.__openAiPickLedger()` / URL query.
- Produces: 홈→종목 발굴 AI PICK 직행, 기존 URL 호환.

- [ ] **Step 1: index에 신규 CSS/JS 추가**
  - CSS는 릴리스 번들 뒤에 추가한다.
  - JS는 릴리스 번들 및 `ai_daily_widget.js` 뒤에 defer 로드한다.

- [ ] **Step 2: 홈 성과 기록 링크 변경**

```html
<a class="ai-daily-more" href="/?tab=screener&view=ai-picks">전체 기록 →</a>
```

- [ ] **Step 3: recommendations 호환 리다이렉트**
  - 기존 페이지 접근 시 `/?tab=screener&view=ai-picks`로 `location.replace`한다.
  - `<noscript>` 사용자에게 이동 링크를 남긴다.

### Task 4: 검증 및 main 반영

**Files:**
- Test only / branch integration

- [ ] **Step 1: 회귀 테스트 실행**

```bash
pytest -q tests/test_ai_pick_ledger_ui.py tests/test_ai_recommendations.py tests/test_validate_ai_rankings.py
```

Expected: PASS.

- [ ] **Step 2: JS 구문 검사**

```bash
node --check static/js/ai_pick_ledger_v52.js
node --check static/js/ai_daily_widget.js
```

Expected: exit 0.

- [ ] **Step 3: 전체 프로젝트 CI 확인**
  - 기존 smoke/mobile check를 확인한다.
  - 기존 unrelated 실패가 있으면 신규 변경과 구분해 보고한다.

- [ ] **Step 4: main fast-forward/반영 후 Render 배포**
  - 기능 브랜치 HEAD를 main에 반영한다.
  - Render가 자동 배포하지 않으면 수동 배포한다.
  - 최신 commit이 `live`인지 확인한다.

- [ ] **Step 5: 운영 데이터 확인**
  - 운영 `ai_recommendations.json`에서 글로벌텍스프리 코드 `204620`, 당일 수익률 `0.0` 유지 여부를 확인한다.
