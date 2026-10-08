# 거장 자료 부족·원계정·수집 회귀 수정 — 2026-10-08

기준 commit `e8132f984fb64ad19d43e01c20eba87838e8324b`, 작업 브랜치 `fix/guru-data-coverage-20261008`. 기존 선정 조건을 유지하면서 실제 수집/가공 결함 네 가지를 수정했다. 아래는 **로컬 저장 자료·테스트에서 확인한 결과**이며 PR/공식 DART 재수집/운영 배포의 완료 기록은 후속 증거로 추가한다.

## 확인한 결함과 최소 수정

| 결함 | 수정 및 보호 |
|---|---|
| 명시적인 총 Basic EPS가 누락되고, 계속/중단영업 EPS 또는 금액 계정이 총 EPS로 선택됨 | canonical Basic ID와 명시적인 기본(희석)/비표준 기본주당순손익 라벨을 좁게 인정한다. 우선/희석 전용/계속·중단/총 EPS가 아닌 IFRS ID를 거부한다. IS/CIS·중복·receipt·KRW·연간기간 검증을 유지 |
| 전체 기업행동 조회가 고정 20페이지에서 끝나거나 불완전한 pagination을 verified로 받아들임 | 선언된 마지막 페이지까지 기존 shared request/deadline/020 예산 안에서 확인한다. 전체 수·페이지·corp·receipt·수신일·중복·조회기간을 검증하고, 불완전/오류는 unknown/ProviderError로 유지 |
| 같은 financial checkedAt의 재수집 실패가 workflow merge에서 사라져 이전 후보가 다시 선정됨 | 같은 원재무 근거에 연결된 더 최신 `lastAttemptAt`/`refreshError`만 보존한다. 다른 receipt/연간자료·오래되거나 시간대 없는 시도는 붙이지 않는다. 검증된 새 성공과 독립 action 검증도 기존 규칙으로 보호 |
| Yahoo batch의 공통 날짜 index에서 상장 전 전체 NaN padding 때문에 실제 충분한 일봉이 탈락함 | 첫 실제 관측 전 Close/High/Low/Volume이 모두 NaN인 행만 제외한다. 부분 결측·관측 이후 공백·잘못된 가격 범위·기준일 누락은 계속 거부한다. 실제 253일 최소/273일 최대·동일 가격일 검증 유지 |

삼성전자 기업행동 `unknown`이 실제로 20페이지 제한 때문에 발생했는지는 아직 확정하지 않았다. 21페이지 fake provider 회귀는 고정 상한 결함을 입증하지만 실제 삼성 공시 페이지 수를 입증하지 않는다. 공식 재수집으로 원인을 확인해야 하며, `events=[]`를 검증된 무행동으로 바꾸지 않는다.

## 실제 저장 자료 보강과 독립 대조

가격 기준일 **2026-10-07**, 로컬 snapshot **`96bf0f872bbc824f049b`**. 일봉은 실제 공급자 요청 후 저장한 자료이며 EPS는 기존 원공시를 수정된 parser로 순수 재정규화한 결과다. 새 연간 공시 수집 완료와 구분한다.

- 유효 일봉 **2,129→2,174, +45개**. 기존 유효 2,129개 행은 모두 보존했다.
- 스크리너 동일날 종가와 0.1% 이내 일치하는 비교 이력 **2,047→2,089, +42개**. 가격 비교 대상 2,252개는 유지했고 자료 범위는 **90.897%→92.762%**다. 기존 90% 관문을 낮추지 않았다.
- 새 45개 중 3개는 가격 확인 조건을 통과하지 않아 비교 대상에 넣지 않았다. 당일 거래량 0인 bar를 새로운 종가 source로 승격하지 않았다.
- EPS **11개 기업의 21개 연도 관측 복원**, **40개 기업의 86개 오인 관측 무효화**. 원보고서/receipt/기간/통화/값과 대조했고 non-EPS 계정·원 reports·financial checkedAt·기업행동·수집 상태를 변경하지 않았다.
- 독립 source 대조 **2,948 assertions 통과, 문제 0개**. 날짜·중복·양수 가격·고저/거래량·이력 길이·KIND 식별·원 URL·EPS 원계정·same-version 지표/선정 조건을 확인했다.

| 전략 | 선정 전→후 | 현재 평가 | 현재 자료 부족 |
|---|---:|---:|---:|
| 버핏 |54→54|1,949|473|
| 린치 |42→41|1,260|1,162|
| 오닐 |1→1|1,197|1,225|
| 미너비니 |81→82|2,089|333|
| 그린블라트 ROA/PER 대안 |3→3|1,472|905|

린치는 대원강업이 추가되었고 HK이노엔·우주일렉트로는 올바른 총 EPS 확인 부족으로 제외되었다. 후보 수를 늘리기 위해 오인 계정을 남기지 않았다.

미너비니 신규 **국도화학의 자체 일봉은 baseline과 동일**하다. 실제 peer 이력 42개 복원으로 기존 cohort에서 RS 중간백분위가 **69.6873473376→70.0095739588**이 되어 기준 70을 통과했다. 이 회사의 새 일봉 수집이나 기준 완화로 설명하면 부정확하다. 기존 미너비니 후보는 모두 유지했다. 현재 후보 합계 181은 전략행 수이며 서로 다른 기업 181개라는 뜻은 아니다.

가격 부족 79개에 기존 일봉을 quote fallback으로 넣는 대안은 채택하지 않았다. 79개 모두 기준일 Volume=0이고 일부는 마지막 실제 거래가 오래되었다. 그 값을 현재 종가로 승격하면 미너비니가 81→86으로 늘어나는 가짜 선정 반례가 재현된다. 전량 거절하고 기존 날짜/가격 source 계약을 유지했다.

## 검사와 재현 근거

현재 로컬 전체 pytest **627개 통과**(기존 dependency 경고 6개), Node 계약 **38개 통과**, 거장 대상 회귀 **175개 통과**. release/boot bundle check도 통과했다. 대상 회귀와 독립 자료 대조는 전체 pytest 수에 추가해 하나의 테스트 수로 합산하지 않는다. 이 문서 담당자는 저장된 실행 log와 source diff를 대조했으며 해당 검사를 별도로 다시 실행하지 않았다.

관련 코드: `guru_financials.py`, `scripts/generate_guru_screening.py`, `scripts/generate_guru_market.py`, `scripts/merge_guru_cache.py`. 회귀: `tests/test_guru_financials.py`, `test_guru_collection.py`, `test_guru_market_collection.py`, `test_guru_refresh_merge.py`. 기존 workflow에 `symbols` input과 collector 회귀에 필요한 `yfinance` 테스트 의존성만 연결했다. 방문 API에서 provider 재수집을 시작하지 않는다.

로컬 증거: `/workspace/scratch/chartview-guru-coverage-fix-20261008/`의 `backend-full-pytest.log`, `backend-node.log`, `guru-targeted-tests.log`, `market-backfill.log`, `recomputed-screening.log`, `data-review/source-data-report.md`, `source-data-audit.json`, `final_source_audit.py`, `collector-review/REVIEW.md`, padding 및 unsafe-fallback 반례. scratch는 새 머신으로 자동 이관되지 않는다. 지속 가능한 보호는 커밋된 회귀와 GitHub Actions artifact다.

## 공식 재수집·CI·배포: 아직 미완료

root는 PR/CI/main 반영 후 기존 **Update Guru Screening**에서 삼성전자 `005930.KS`와 실제 financial-refresh flag가 있는 10개 기업, 합계 11개 기업만 재확인할 예정이다. 계획은 `collect=true`, `symbols=<확인한 11개 KIND ticker>`, `max_companies=11`, `max_requests=500`, 기존 시간 상한 1200초, `collect_extensions=false`다. 10개 기업은 전략별 사유의 중복을 제거한 수이며 그린블라트의 8개는 부분집합이다. 아직 공식 action 결과·실제 요청 수·삼성 action 상태/원페이지 수·갱신 snapshot을 완료로 기록하지 않는다.

CLI의 `--symbols`는 `--collect`와 현재 KIND 종목을 요구한다. 선택 종목만 기존 24시간 cooldown을 건너뛰어 재검증하며, 기존 shared request/time/020 예산을 유지한다. selected full review는 무관한 전체 incremental 공시 scan을 추가하지 않는다. 나머지 저장 universe/원재무 근거는 유지하고 cached parser 재정규화와 provider 재수집을 구분한다. 기존 Actions의 DART Secret만 사용하며 키를 출력·복사하거나 새 Secret/LLM API/유료 서비스/배포 hook을 만들지 않는다.

공식 자료 갱신 후 final main의 pytest/Node/bundle/관련 CI를 확인하고 기존 Render 백엔드 서비스에 정확한 tested main만 게시한다. 실제 `/health.revision`, HTML/JS/CSS 자산, CDN·결과·근거의 snapshotVersion, 현재 버전 근거 200/잘못된 버전 409와 Toss 화면을 확인해야 운영 완료다. 수집 성공과 서버 게시 성공은 서로 다른 단계다.

## 남은 자료와 이관

원공시 없는 총 EPS·연간/단일분기·기업행동 불명확, 실제 253일 부족·종가 불일치·기업유형 미지원·비12월 결산은 계속 insufficient/unsupported로 둔다. 공식 자료가 있어도 선정 기준에 미달하면 미선정을 유지한다. 원자료를 합성하거나 알려진 과거 값을 오늘 관측으로 바꾸지 않는다. 전체 daily 자료 게시/서버 배포 자동 연결과 Toss native release는 별도 미완료다.

다른 Codex에서는 두 저장소의 최신 main·AGENTS/기억 문서·필수 QA를 읽는다. [전체 서버·도구·skill 복사용 시작 요청](https://github.com/shoon94parkk-del/chart-view-toss/blob/main/docs/CODEX_BOOTSTRAP_PROMPT.md)과 [이관 가이드](https://github.com/shoon94parkk-del/chart-view-toss/blob/main/docs/CODEX_TRANSFER.md)를 사용한다. 역할 지침·Git 기억을 재사용하되 e2e/claude-mem은 여전히 source-only이며 자동 MCP/worker/기억 수집 완료로 표현하지 않는다.

## 후속 실제 공식 수집·배포 확인

위 미완료 표시는 사전 검증 시점의 기록이다. 이후 [PR137](https://github.com/shoon94parkk-del/chart_View/pull/137)의 빌드·회귀·모바일 9개 검사를 통과해 main에 반영했다. [공식 수집37732042491](https://github.com/shoon94parkk-del/chart_View/actions/runs/37732042491)은 지정11회사만 **116요청, 오류0, complete**로 재검증했다. 데이터 commit **`40404bead3c724fb292b15cc90a661a6a1149320`**, snapshot **`b2ba5d2228cce4a89f35`**다. 선택 회사 외 캐시2,641개와 universe/market/quarters/screener는 동일하다. 보존 캐시2,652개와 활성 KIND universe2,651개의 분모를 혼동하지 않는다.

삼성전자와 정정공시 대상의 기업행동·EPS 비교 검증이 회복됐다. 이지스는 실제 정정 사업보고서 receipt `20261006000023`으로 갱신했다. 연간수치는 같고 추가 필요한 분기수집은0이다. 삼성의 실제 공시 페이지 수는 기록하지 않았으므로 고정20페이지가 삼성 unknown의 직접 원인이라고 단정하지 않는다.

| 전략 | 선정 | 평가 가능 | 자료 부족 |
|---|---:|---:|---:|
| 버핏 |54|1,949|473|
| 린치 |41|1,266|1,156|
| 오닐 |1|1,203|1,219|
| 미너비니 |82|2,089|333|
| 그린블라트 |3|1,480|897|

공식 단계는 자료 부족을 린치6/오닐6/그린8 줄였지만 추가 선정0이다. 독립 사후검사 **3,489개 통과**: 실제 원계정250개, 전체181후보 종가·근거와 미너비니82개 산술·조건을 대조했다. Actions Python3.11과 로컬3.12의7개 버핏 평균값은 최대7.11e-15 차이가 있어 산술을 작은 명시적 허용오차로 비교했다. 실제 게시 payload의 SHA256은 b2ba 버전과 정확히 일치하며 로컬 재생성으로 게시본을 덮지 않았다.

최종 데이터 pytest627/Node38/bundle 검사를 통과한 main40404be를 기존 수동 Render 경로로 게시했다. deploy **`dep-db3ijr6gekts73eulskg`**, live **2026-10-08 05:29:23 UTC**. 실제 health revision·HTML/JS/CSS 해시, 서버 JSON·공개 CDN·저장 원본 일치, 다섯 전략 근거200/이전 버전409를 확인했다. [최종 데이터 CI37732353574](https://github.com/shoon94parkk-del/chart_View/actions/runs/37732353574)의 check/7모바일/4운영 검사 **12개 모두 성공**했다. 이전 source-only main의 운영 검사만 데이터 갱신 후 취소하고 최종 SHA 전체 검사를 새로 실행했다.

Toss Android·작은 iPhone의 거장5전략/미국40히트맵 **4/4 통과**. 추가 실제 핵심검사5개 중 삼성 검색·시세/선정성과/PER3개는 통과했다. 수출2개와 별도 iPhone 수출복구1개는 관세청 `apis.data.go.kr` 연결 시간 초과/503으로 실패했다. 정상 오류 안내가 표시되지만 수출 기능 검증 완료로 기록하지 않는다. 검증된 전체 signed-balance snapshot이 없어 구형 정적 자료나 시험 fixture를 대입하지 않았다.

또한 기존 관세청 예외 문자열이 서비스키를 공개 오류에 포함하는 결함을 발견했다. 최소 수정은 공개 오류·캐시 메타·warning·로그에서 원문을 제외하고 고정 안내만 사용한다. 기존 오류 코드·stale 금액/날짜·부호 있는 수지·공급자 예산은 유지한다. 신규 보안 회귀19개, 기존 수출 회귀 포함54개가 통과했고 이 문서 시점에는 보안 수정 CI/재배포 확인이 진행 중이다. 원시 진단 trace/report의 공급자 query 키는 제거했다. 기존 키는 노출 가능성을 전제로 공공데이터포털에서 재발급 후 Render에 교체해야 한다; 실제 재발급·교체 완료는 주장하지 않는다.
