# ChartView V40.1 — Stage12 최종 릴리스 노트

기준일: 2026-09-13 KST  
작업 브랜치: `app-release-stage12`  
PR: #11  
기능 소유 버전: V40  
안정화 패치: V40.1

## 최종 재점검에서 추가로 발견한 불합리

### 1. 모바일 YTD 터치 충돌
- 360px 폭에서 `YTD`를 눌렀는데 인접 `전체(max)` 기간이 선택되는 경우가 있었다.
- 원인은 구형 `analysis_ui_v20.css` / V39 계열의 강한 모바일 규칙과 V40 기간 컨트롤 레이아웃이 겹치면서 클릭 영역이 불안정해진 것이었다.
- V40 비교 화면에서 기간 컨트롤을 명시적으로 소유하고 capture-phase 이벤트 위임으로 처리한다.
- YTD는 현재 연도의 `01-01`부터 오늘까지 `start/end`를 명시해 `/api/compare`를 요청한다.
- 360/384/430px에서 기간 버튼은 독립 44px 터치 셀을 유지한다.

### 2. 모바일 비교 차트가 첫 화면 아래로 밀림
- 직접 기간 버튼과 구형 spacing 규칙 때문에 차트 시작점이 목표보다 아래에 있었다.
- 직접 기간 기능은 유지하되 기간 행 안에 배치하고, V40 스코프에서 구형 `!important` 간격을 무효화했다.
- 최종 브라우저 검증에서 360/384/430px 비교 차트 시작점은 모두 약 `408px`으로, 420px 목표를 통과했다.

### 3. 단일 상세의 과도한 세로 길이
- 기존 구조는 `현재가 카드 → 3개 지표 → 탭 → 차트`가 모두 세로로 쌓여 모바일 차트가 약 625px부터 시작했다.
- `static/css/detail_ui_v40.css`에서 현재가와 핵심지표를 한 요약 영역으로 압축하고 44px 액션 버튼은 유지했다.
- 중복 설명/여백만 줄여 첫 화면 정보 밀도를 개선했다.

### 4. 단일 상세의 간헐적 화면 숨김 경쟁 상태
- `ChartViewState.detail.open`은 true인데 레거시 탭 초기화가 늦게 완료되면서 `chart-tab`이 다시 비활성화되어 상세 DOM이 화면에서 숨는 경우가 있었다.
- `static/js/detail_visibility_v40_1.js`를 추가해 V40 중앙 상태를 화면 표시의 source of truth로 사용한다.
- 상세 상태가 열려 있는데 레거시 탭 전환이 화면을 숨기면 차트 탭/상세 표시를 복구한다.
- 정상 닫기에서는 먼저 detail state가 닫히므로 복구 가드가 화면을 다시 열지 않는다.
- A→B 역순 응답, 닫은 뒤 늦은 응답, 빈/6종목 비교 테스트와 함께 통과했다.

### 5. 뉴스 부분 실패가 접힌 상태 안에 숨어 있음
- 기사 일부는 정상인데 특정 종목 provider가 실패해도 `종목별 조회 상태`가 접힌 `<details>` 안에 있어 사용자가 원인을 바로 알기 어려웠다.
- `static/js/news_status_v40_1.js`에서 부분 실패/연결 실패가 있으면 상태 목록을 자동으로 펼친다.
- 실패가 해소되면 자동으로 열었던 상태만 다시 접는다.
- 환경변수 이름이나 내부 provider 설정값은 사용자 화면에 노출하지 않는다.

### 6. 모바일 뉴스 TOP1도 설명이 사라짐
- 기존 모바일 CSS가 모든 뉴스 설명을 숨겨 TOP1의 `이벤트 참고 설명`까지 보이지 않았다.
- `static/css/news_status_v40_1.css`에서 TOP1 설명만 최대 2줄 노출하고 TOP2~3는 계속 압축한다.
- 첫 화면 밀도를 유지하면서 가장 중요한 기사에 최소한의 맥락을 남긴다.

### 7. 데스크톱 비교 화면의 중복 내비게이션과 과도한 상단 공간
- 새 5개 앱 내비게이션이 이미 있는데 레거시 `차트 비교 / 밸류에이션 / 경제 지표 / 종목 발굴` 탭 바가 데스크톱에서 공간을 다시 차지했다.
- 검색 영역도 제목/설명/힌트/종목태그가 세로로 중복되어 1366px에서 차트가 약 571px 아래부터 시작했다.
- `static/css/comparison_compact_v40_1.css`에서 데스크톱 레거시 탭 바를 숨기고 검색 입력 + 선택 종목 태그를 작업바 형태로 압축했다.
- 섹터 빠른선택은 44px 한 줄로 기본 접힘 상태이며 `빠른 종목 추가 펼치기`로 언제든 접근 가능하다.
- `static/js/comparison_compact_v40_1.js`가 접근 가능한 펼침/접힘 상태를 관리한다.
- 마지막 장식성 4px 상단 margin을 제거하되 44px 입력/버튼 크기는 줄이지 않았다.
- 1366×900 비교 차트 위치 검증이 360px 기준을 통과했다.

## 추가/변경 파일

- `static/css/detail_ui_v40.css`
- `static/css/comparison_ui_v40.css`
- `static/css/comparison_compact_v40_1.css`
- `static/css/news_status_v40_1.css`
- `static/js/detail_visibility_v40_1.js`
- `static/js/comparison_compact_v40_1.js`
- `static/js/news_status_v40_1.js`
- `static/js/home_watchlist_boot_v32c.js`
- `static/js/release_flow_v40.js`
- `tests/app_release_stage12.cjs`

## 호환성

- 관심목록 localStorage 키/JSON 형식 변경 없음.
- 비교목록 localStorage 키/JSON 형식 변경 없음.
- 최근 종목/종목명 저장 형식 변경 없음.
- 개인화 뉴스 backend/provider 계약 변경 없음.
- 기사 본문/이미지 재배포 정책 변경 없음.
- 기능 소유 메타는 `newsVersion = v40`, 후속 안정화는 `newsPatch = v40.1`로 별도 기록한다.

## 최종 CI 검증

GitHub Actions `App Regression Check` run #188 (`34734589379`)에서 다음이 모두 성공했다.

- Python syntax
- Frontend JavaScript syntax
- API and frontend regressions
- Static cache shape
- App UX and market invariants
- mobile smoke
- Stage12 Playwright scenarios
  - 360/384/430px YTD 실제 날짜 요청
  - 360/384/430px 비교 차트 첫 화면 위치
  - single detail no-hang
  - empty/default/full compare state
  - missing/0/NaN/Infinity 숫자 표시
  - A→B race + close-after-late-response
  - 20-watchlist personalized news + non-blocking market hydrate
  - responsive Home and comparison
  - keyboard + storage failure warning

> Playwright Chromium 에뮬레이션 결과이며 모바일 실기기 검증으로 기록하지 않는다.

## 배포 전 체크포인트

1. 이 문서 커밋까지 포함한 PR CI가 다시 녹색인지 확인한다.
2. PR #11을 `main`에 병합한다.
3. Render가 병합 commit을 자동 배포했는지 확인하고, 자동 배포가 시작되지 않으면 수동 deploy를 1회 실행한다.
4. Render revision과 `main` commit이 일치하는지 확인한다.
5. 운영 `/health`와 주요 화면을 확인한 뒤 릴리스를 완료한다.

## 롤백

Stage12 merge commit 전체를 revert하면 된다. 기존 localStorage 형식을 변경하지 않았으므로 rollback 뒤에도 기존 관심목록/비교목록을 그대로 읽을 수 있다.
