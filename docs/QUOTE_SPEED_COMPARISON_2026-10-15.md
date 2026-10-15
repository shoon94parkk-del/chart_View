# 시세 개선 전후 속도 비교와 배포 상태 · 2026-10-15

기존 [시세 패치와 조사 기록](QUOTE_SPEED_CHECK_2026-10-15.md)에 이어, 같은 조건의 개선 전후 비교를 추가했다. 비교 대상은 main `40daf4fd773e253839e23b9745ae6f34638b8c6b`와 시세 패치 `3588790fff1fa8f4644c9172247400b1e64d6f71`다. 이후 문서·측정 스크립트 커밋은 런타임 변경에 포함되지 않는다.

## 동일 조건의 코드 비교

실제 Git revision을 각각 archive해 별도 프로세스에서 FastAPI ASGI 경로를 실행했다. 외부 네트워크와 앱 lifespan은 실행하지 않고 동일한 날짜·시세·지연을 가진 가상 공급자를 사용했다. 기본 executor 예약 시간은 측정에 포함하고, import와 최초 Home 읽기는 제외했다. 버전 순서를 교대로 바꾸며 3가지 조건을 각 버전8회, 총48회 실행했다. Home 읽기 간격은2ms이며 이는 캐시 게시 시점 확인을 위한 측정 해상도다.

| 조건 | 지표 | 개선 전 중앙값 | 개선 후 중앙값 |
|---|---|---:|---:|
| 일반 요청, 공급자40/400ms | 빠른 종목의 새 값을 Home에서 읽기 |405.96ms|46.69ms|
| 일반 요청, 공급자40/400ms | 전체 묶음 응답 완료 |404.25ms|405.21ms|
| fresh 요청, 공급자40/400ms | 빠른 종목의 새 값을 Home에서 읽기 |406.34ms|46.74ms|
| fresh 요청, 공급자40/400ms | 전체 묶음 응답 완료 |404.32ms|404.51ms|
| 모두40ms인 대조 조건 | 전체 묶음 응답 완료 |44.95ms|44.98ms|

빠른 종목의 공급자 완료부터 공유 캐시 게시까지의 지연은 약360ms에서0.2ms로 줄었다. 전체 묶음 응답 시간과 공급자 자체 조회 시간은 유지됐다. 48회 모두 중복 입력을 포함해 공급자 호출은3회였고, `fetchedAt`을 제외한 최종 응답의 값·순서·출처·시각·오류·조회 수·fresh 계약과 최종 Home 값은 전후 동일했다. 비Home 종목은 공유 Home 캐시에 들어가지 않았다. 대조 조건의 작은 차이는 로컬 잡음 범위로 본다.

공유 캐시 읽기 시간의 약88.5% 감소는 이 가상 지연 조건의 결과에 한정된다. 실제 홈 클라이언트는 `static/js/home_heatmap_v57.js`의5초 갱신 주기를 사용한다. 둘 다 다음 갱신 전에 끝나는40/400ms 조건에서는 사용자 화면의 개선이 없을 수 있다. 네트워크·Render 서버 기동·공급자 제한·화면 렌더링은 위 수치에 포함되지 않는다.

별도6회 비교에서는 빠른 공급자40ms·느린 공급자6초·Home 읽기0/5/10초 조건을 사용했다. 빠른 종목을 Home에서 읽는 중앙값은10,018.27ms →5,017.60ms, 전체 묶음은6,006.93ms →6,005.69ms였다. 느린 종목의 완료 전후를 갱신 주기가 가르는 경우, 먼저 완료된 값을 한 번 먼저 읽는 결과다. 이 고정 위상·가상 공급자 조건은 실제 기기 화면 측정이나 모든 사용자의 개선 예측에 해당하지 않는다. 갱신 시점이 달라지면 효과도 달라진다.

측정 스크립트와 전체 표본은 `scripts/benchmark_quote_publication.py`, `docs/audits/2026-10-15-quote-speed/comparison/`에 있다. 가상 공급자의 지연은 벤치마크에만 존재하며 제품에 고정 대기를 추가하지 않았다.

```sh
PYTHONDONTWRITEBYTECODE=1 python scripts/benchmark_quote_publication.py \
  --repo "$PWD" \
  --before 40daf4fd773e253839e23b9745ae6f34638b8c6b \
  --after 3588790fff1fa8f4644c9172247400b1e64d6f71 \
  --repetitions 8 --fast-ms 40 --slow-ms 400 --poll-ms 2 \
  --output-dir /tmp/chartview-quote-comparison

# 기존5초 갱신 주기의 조건부 효과: 버전별3회
PYTHONDONTWRITEBYTECODE=1 python scripts/benchmark_quote_publication.py \
  --repo "$PWD" \
  --before 40daf4fd773e253839e23b9745ae6f34638b8c6b \
  --after 3588790fff1fa8f4644c9172247400b1e64d6f71 \
  --repetitions 3 --fast-ms 40 --slow-ms 6000 --poll-ms 5000 \
  --cadence-check --output-dir /tmp/chartview-quote-comparison
```

## 운영 배포 전 기준 측정

운영 프런트는 `9bd17dbe410065eb09a743c72506be36c2bc4d30`, 백엔드는 `40daf4fd773e253839e23b9745ae6f34638b8c6b`다. Chromium390×844·동일 proxy relay·실제 API·각3회 조건으로 측정했다. 새 context는 브라우저/앱 캐시가 빈 상태이고, 재진입은 같은 세션에서 more 화면을 거쳐 돌아온 경우다. 서버의 유휴/재기동을 유도하지 않았다.

| 화면의 주요 데이터 완료 | 새 context 중앙값(범위) | 같은 세션 재진입 중앙값 |
|---|---:|---:|
| 홈 |460ms (406–1,271)|74ms|
| 관심종목 가격 |336ms (326–2,155)|20ms|
| 삼성전자 상세 가격 |654ms (627–886)|66ms|
| 차트 수익률 비교 표 |369ms (364–450)|41ms|

각 화면3/3이 정상 데이터를 표시했다. 이것은 배포 전 기준값이며 개선 후 운영 측정값은 아직 없다. 최초 시장 호출에 공급자 작업이 있는 표본과 캐시 표본을 섞어 개선율로 계산하지 않는다.

별도의 warm API 측정은 각 경로1회 예열 후5회 순차 호출했다. `/api/home-live` 중앙값214.232ms, `/api/quotes?tickers=005930.KS,NVDA,AAPL` 중앙값136.644ms였고 모두200이다. 시세 묶음5회 모두 공유 캐시3건·공급자 조회0건이다. 측정 전후 health SHA는 동일했다. 시장·네트워크·캐시 변화는 통제하지 않았으므로 운영 표본5개로 p95·SLA·코드 인과 효과를 추정하지 않는다. 재측정은 `scripts/measure_live_quote_latency.py --expected-sha <full-sha> --output <file>`로 수행한다.

## 출시 검사와 승인 경계

사용자의 이번 요청으로 배포 권한은 확인됐다. 다만 기존의 PICK 기록 변경 금지와 모든 기존 회귀 통과 조건은 유지한다.

| 검사 | 결과 |
|---|---|
| 동일 조건 ASGI 비교 |48회 및5초 주기6회, 응답·최종 Home 동일성 통과|
| 새로 실행한 시세 관련 Python6파일 |52통과, 기존 warning11개|
| 새로 실행한 전체 Python |770통과·1실패, 기존 warning79개|
| 필수 Node6파일 |52통과|
| Web 번들 freshness |통과|
| Live backend contract smoke |통과|
| 현재 운영 exact SHA·자산3개·거장5개 결과/근거·409 보호 |기존 운영 revision에서 통과|
| 패치3588790의 GitHub 모바일7개 job 및 번들 build |통과|
| Android/iPhone 실제 Toss Sandbox |미검증|

단일 실패는 기존 main에서도 재현되는 `test_pick_ledger_contains_latest_daily_pick`이다. 10월15일 확정 선정에는069500이 있으나 같은 날짜의 성과 원장에는 없다. 검사·PICK 선정·기준·기록·계산·UI·API 노출은 변경하지 않았다. `docs/CODEX_HANDOFF.md:70`과 `.github/workflows/app-check.yml`의 전체 Python CI 통과 후 배포 조건을 유지하며 초안 PR을 통과로 표시하지 않는다.

누락1건만 덧붙이는 [미적용 수정안](https://github.com/shoon94parkk-del/chart_View/pull/151#issuecomment-6190297364)을 제시했다. 원장 기존41건과 기존 metadata는 유지하고 이미 커밋된 선정일 종가87,025원을 사용한다. 선정일과 screener 기준일이 같아 기존 공식으로 당일 수익률은0%다. 이 안은 사용자의 PICK 기록 변경 금지에 대한 한정된 예외가 있어야 적용할 수 있다. 기존 updater의 ETF 갱신 거부는 별도 한계로 남으며 이1건 추가로 향후 자동 갱신까지 해결됐다고 주장하지 않는다.

배포는 이 예외 확인을 기다리는 상태다. main 병합·Render 재배포·프런트 배포·요금제/리전 변경은 수행하지 않았다. 백엔드 변경이므로 새 AIT도 생성하지 않았다. 실제 운영의 개선 후 결과는 정확한 검증 main 배포 및 `/health` revision 확인 뒤 같은 조건으로 측정해야 한다.
