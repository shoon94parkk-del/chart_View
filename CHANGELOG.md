# 변경 이력

## 2026-09-21 · ID-based watchlist sync
- Added passwordless sync ID flow for moving watchlists between devices.
- Existing local-only behavior remains the default until a sync ID is connected.
- Added a small profile-sync API backed by PostgreSQL; only a hashed sync key and watchlist JSON are stored.
- Added validation, deduplication, 20-symbol limit, and regression coverage.
- Security note: this is intentionally not authentication; anyone who knows a sync ID can access that watchlist.


## 2026-09-21 · Audit final completion pass

- 홈 정보 순서를 시장 상태 → 내 관심종목 → 주요 종목 흐름으로 정리하고, 홈 보조 메타데이터의 지나치게 작은 글자를 보강했습니다.
- 단일 종목 수익률 차트에 시작·중간·종료 날짜를 표시하고, 선택 지점에서 원 가격과 기간 수익률을 함께 확인하도록 비교 API와 상세 UI를 확장했습니다.
- 상세 차트의 live status 및 관심/비교 버튼 접근성 이름을 보강하면서 기존 수익률 API 계약은 유지했습니다.
- 기존 Audit 문서에서 이미 끝난 항목은 재구현하지 않고 CV-03/CV-04/CV-06/CV-09의 남은 완료 기준을 중심으로 마무리했습니다.


## 2026-09-21 · Audit UX pass

- 데스크톱 주요 화면의 최대폭을 1120px 기준으로 정렬하고 홈 시장 카드의 2열 활용을 추가했습니다.
- 홈 주요 종목 로고를 작게 조정하고, 로고 실패 시 텍스트 fallback을 유지하면서 데스크톱 이전/다음 버튼과 좌우 방향키 탐색을 추가했습니다.
- 홈·관심목록의 조회 시각을 KST로 통일하고, 관심종목 백업/복원을 `목록 관리` 메뉴로 정리했습니다.
- PICK 홈 요약을 `최근 선정/오늘 선정`으로 구분하고, 추천 건별 평균 수익률의 평가 건수와 미평가 제외 정책을 화면에 표시했습니다.
- 단일 종목 상세의 예상 PER에 실제 제공 기간 메타데이터를 연결하고, 분석 요약을 `관찰된 사실 / 비교할 기준 / 확인이 필요한 점` 구조로 개편했습니다.
- 관심종목 조회 시각을 브라우저 위치와 무관하게 KST로 고정하고, 백업 복원은 기존 목록을 보존한 채 미리보기 후 중복 병합하도록 변경했습니다.
- 직접 기간 설정에 연결된 레이블, 인라인 오류 안내, 미래/역전 날짜 검증을 추가하고 기존 유효 차트를 보존하도록 정리했습니다.
- 상세 차트의 로딩/오류/거래 데이터 없음 상태를 분리하고 수익률 차트에 0% 기준선을 명확히 표시했습니다.
- 관심종목 정렬 문구와 비교 추가 용어를 명확히 하고 모바일 주요 컨트롤의 터치 높이/보조 텍스트 가독성을 보강했습니다.
- 운영 URL을 현재 Render 서비스인 https://chart-view-pkv8.onrender.com 으로 통일해 GitHub 운영 검증과 실제 배포를 다시 연결했습니다.\n- 뉴스 요약 품질 게이트는 번역문과 영문 제목을 단순 토큰 겹침으로 비교하지 않도록 수정하고, 구체적 수치·실적이 있는 짧은 한국어 요약을 정상 허용하도록 보완했습니다.


## V35 — 데이터 기준 및 판단 근거 정리 (2026-09-12)

- 비교 차트를 조정주가 일봉 기준으로 통일하고 실제 시작일·종료일·관측 수를 API에 추가.
- 밸류에이션 API에 필드별 소스·기준일·기간·계산 방식 메타데이터 추가.
- 확인하지 못한 예상 PER/EPS 회계기간을 일괄 ‘12M’으로 표시하지 않도록 수정.
- 거시지표의 수집 시각과 원자료 기준일을 분리 표시.
- EPS 변화율과 주가 수익률의 차이를 `%p`로 표시하고 단정적인 후보 명칭 수정.
- 투자판단 조건을 가치·수익성·전망·모멘텀 축별로 집계하고 필수 필드 제공 수를 표시.
- 역사적 밸류 화면을 공시 시점 근사 재구성치로 설명하고 마지막 유효일·제외 값을 표시.
- 새로 선택한 종목을 ‘한눈에 요약’ 활성 대상으로 연결.
- 앱 셸 준비 전 구형 메뉴 노출을 완화.
- 데이터 정의와 운영 인수인계 문서 추가.
