# Toss 시세 속도 검증과 완료 시세 조기 게시 · 2026-10-15

후속 요청에 따라 [동일 조건의 개선 전후 비교·추가 출시 검사·배포 승인 경계](QUOTE_SPEED_COMPARISON_2026-10-15.md)를 기록했다. 운영 배포 후 측정과 로컬 코드 비교를 구분한다.

## 현재 판정

기존 UI와 공급자·캐시를 유지하며, `/api/quotes`에서 먼저 완료된 Home 종목을 기존 공유 캐시에 즉시 게시하도록 수정했다. 다른 종목이 느려도 `/api/home-live`와 후속 일반 시세 요청은 완료된 값을 사용할 수 있다. 원래 묶음 JSON 응답은 계속 모든 종목을 기다린다. 따라서 이 변경을 해당 묶음의 응답 시간 단축이나 30~50ms 실시간 서비스 보장으로 설명하지 않는다.

**초안 PR의 출시 차단:** 전체 Python 검사는 770통과·1실패다. 실패는 이번 변경 전 최신 main `40daf4fd773e253839e23b9745ae6f34638b8c6b`에도 있는 PICK 원장 데이터 불일치이며, 원본 Git 파일만 복사한 별도 경로에서 같은 검사를 재현했다. 사용자의 PICK 변경 금지 범위에 따라 테스트·선정·원장·계산을 그대로 둔다. 이 상태를 전체 QA 통과 또는 배포 가능 상태로 표시하지 않는다.

## 실제 운영과 외부 주소 확인

- 프런트 운영: `9bd17dbe410065eb09a743c72506be36c2bc4d30`, 정적 사이트 `chart-view-toss.onrender.com`. 실제 자산 `/assets/index-CF9uo1sD.js`와 Render live 배포를 확인했다. 이전 개선 PR134는 아직 미병합이다.
- 백엔드 운영 및 작업 기준: `40daf4fd773e253839e23b9745ae6f34638b8c6b`. 기존 Chart View workspace의 Render 서비스는 free plan·virginia이며 실제 live 배포도 이 SHA다. 이 조사에서 서버를 중지하거나 유휴 상태로 만들지 않았다. 무료 서비스 재기동 시간은 측정하지 않았다.
- 제공된 `ais-dev-wfltcluoz4imw7oiomx2pb-286821798369.asia-northeast1.run.app`의 root, health, quotes, market-now와 quotes preflight는 모두 인증 쿠키 확인 경로로302 응답했다. 정상 리다이렉트 후 페이지도200 HTML의 Cookie check이며 권한 확인을 요청했다. 관찰한 응답에서 CORS 허용 헤더는 없었다. 보호된 실제 애플리케이션의 CORS 설정 자체를 단정할 수는 없다.
- 이 주소에서는 시세 JSON·종목 범위·통화·기준 시각·등락률·오류 계약을 검증할 수 없었다. 인증을 우회하거나 임의 토큰을 넣지 않았다. 전역 `VITE_CHARTVIEW_API_BASE` 교체는 모든 API를 옮기므로 적용하지 않았다.

재현 가능한 [Cloud Run 확인 결과](audits/2026-10-15-quote-speed/cloudrun-reachability.json), [서비스 설정](audits/2026-10-15-quote-speed/render-services.json), [기존 시세 응답](audits/2026-10-15-quote-speed/render-quotes.json)을 보존한다. 원래 raw HTTP 증거는 별도 연구 디렉터리에 보존하며 쿠키·인증 확인 페이지는 저장소에 넣지 않는다.

## 기존 운영의 관측값

같은 일반 시세 요청 `005930.KS,NVDA,AAPL`을 순차3회 읽었다. 응답 본문 완료 시간은2,634 /174 /157ms였다. 공유 캐시 hit/provider fallback 수는2/1 →3/0 →3/0이다. 이는 앱 메모리 캐시이며 `CF-Cache-Status`는 DYNAMIC이었다. 신규 공급자 조회가 있는 표본과 캐시 표본의 차이를 코드 개선율로 해석하지 않는다. Cloud Run은 JSON을 받지 못해 직접 비교할 수 없었다.

390×844 Chromium·실제 운영 웹·원격 실제 API·한국어 글꼴·프록시 relay 조건에서 각3회 측정했다. 새 context의 브라우저/앱 캐시는 비어 있고, 동일 세션 복귀는 more 화면을 거쳐 돌아온다. 성공 데이터가 표시된 시점만 집계했다.

| 화면의 주요 데이터 | 새 context 중앙값(범위) | 같은 세션 복귀 중앙값 |
|---|---:|---:|
| 홈 주요 콘텐츠 |501ms (491~1,196)|60ms|
| 관심종목 가격 |363ms (338~2,407)|20ms|
| 삼성전자 상세 가격 |877ms (696~987)|77ms|
| 수익률 비교 표 |417ms (402~1,018)|41ms|

이것은 기존 운영의 관측이며 패치 전후 비교가 아니다. 각3회 표본으로 실사용자 p95나 모바일 네트워크·Render cold start를 추정하지 않는다. [원 측정 요약](audits/2026-10-15-quote-speed/production-browser-summary.json)에 완료 기준과 환경을 포함한다.

## 재현한 원인과 수정 범위

분류: 기존 Home 캐시 조기 게시 계약에서 발견한 새 버그다. 10월13일의 background Home/market 조기 게시와 canonical singleflight·HTTP 연결 재사용은 이미 구현되어 있어 다시 만들지 않았다.

기존 `/api/quotes`는 `to_thread` 작업을 모두 gather한 뒤 성공한 Home 종목들을 게시했다. 실제 ASGI 경로에서 한 공급자를 보류하면 다른 종목의 canonical 조회는 끝났어도 Home 응답에는 이전 가격이 남았다. 새 회귀는 이 상태에서 먼저 끝난 값이 보여야 한다고 검사하며, 수정 전4개 실패·6개 통과를 확인했다.

수정은 각 종목의 기존 `to_thread` 직후 event loop에서 기존 `_publish_home_quote`를 호출하는 것이다. 원래 batch 시작 시각을 전달해 더 최근 관측을 오래된 응답이 덮지 못하게 한다. gather와 최종 응답의 입력 순서·오류·조회 수·캐시 hit·값·제공처·시각은 유지하고, 완료 뒤의 중복 게시만 제거했다. 부분 성공이 최종 batch 완료를 뜻하지 않는다.

새 캐시·provider·pool·키·비용·CORS·API 라우터·갱신 주기를 추가하지 않았다. Home 화면의 기존 polling에서 앞서 게시된 값을 읽을 수 있으나 다음 화면 갱신까지의 기존 대기와 네트워크 시간은 남는다.

변경 파일:

- `main.py`: `/api/quotes` 내부 완료 시점 게시만 변경. 나머지 최상위 구문은 AST 비교로 동일함을 확인했다.
- `tests/test_home_quote_progress.py`: 실제 Home 읽기·일반/fresh 요청·동일 provider 횟수·전체 응답 순서·비Home·누락/오류/부적합 값·늦은 관측 보호10개 회귀.
- `tests/test_performance_isolation_contract.py`: 동일한 `to_thread`와 missing 집합을 검사하도록 변경된 내부 helper 위치를 반영. 실제 동작 검증을 추가했으며 기존 cache hit·fresh·provider count 검사를 유지했다.

PICK/LAB·거장 계산·공급자·선정/기록 데이터13개 파일과 나머지 main 구문의 [보호 범위 증거](audits/2026-10-15-quote-speed/protected-scope.json)를 남겼다. 최신 main의 KODEX200 사용자 선정 변경도 작업 기준에 그대로 보존했다.

## 검증과 남은 차단

| 검사 | 결과 |
|---|---|
| 기존 관련 회귀 baseline |45통과|
| 신규10개, 수정 전 |4실패·6통과|
| 신규10개, 수정 후 |10통과|
| 관련 통합 회귀 |55통과, 기존 deprecation warning75개|
| 전체 Python |770통과·1실패, 기존 warning79개|
| 필수 Node CI6파일 |52통과|
| Web 번들 freshness |통과, 프런트 파일 변경 없음|
| 독립 코드 리뷰 |중요 미해결 사항 없음. 리뷰어는 검사를 재실행하지 않음|

Python 실패는 `tests/test_pick_screener_contract.py::test_pick_ledger_contains_latest_daily_pick`다. 10월15일 daily 선정에는069500이 있으나 `ai_recommendations.json`의 같은 날짜 원장은 비어 있다. 프로젝트 기억의 rankings/ledger 정합성 계약과 원장 updater는 user_final_selection도 포함하므로 이를 ETF 제외 테스트로 바꾸지 않는다. ETF identity 검사는 screener 바깥 종목을 허용했지만 기존 updater는 equity screener에 없는 symbol을 여전히 거부한다. 선정 자료·원장 및 해당 검사를 이번 성능 작업에서 변경하지 않았다. 원본 입력 [해시](audits/2026-10-15-quote-speed/baseline-pick-inputs.json)를 보존한다.

그 밖의 관측도 해결된 것으로 주장하지 않는다.

- 동기 singleflight의 대기자가 기본 executor를 점유할 수 있다. 로컬의 기존7worker에서 같은 ticker를7회 보류하면 다른 ticker 시작이 막히는 통제 사례를 확인했다. 실제 운영 queue 근거가 없으므로 pool 확대나 새 owner 계층을 넣지 않았다.
- Naver의19시대 응답에는 afterMarket 문맥이 있으나 기존 backend는 OPEN을 regular_live로 표기했다. 선택된 top-level 가격의 정확한 세션 기준은 모호하다. 제공처 timestamp를 조회 시각으로 만든 것은 아니며, 별도의 after-market 가격을 임의 대체하지 않았다. [실제 provider 근거](audits/2026-10-15-quote-speed/naver-session.json)를 남기고 시세 값/PICK 출력은 유지했다.

```bash
python -m pytest -q
node --test tests/frontend.test.cjs tests/live_quotes_v56_contract.cjs tests/home_heatmap_v57_contract.cjs tests/macro_policy_v62_contract.cjs tests/server_live_cache_v66_contract.cjs tests/share_deeplink_v68_contract.cjs
python scripts/build_frontend_bundle.py --check
```

작업 브랜치는 `fix/publish-completed-quotes-20261015`다. 전체 Python의 기존 실패가 남아 있으므로 PR은 초안이며, main 병합·Render 배포·요금제/리전 변경은 수행하지 않는다. Toss UI를 수정하지 않아 새 AIT는 생성하지 않았다. 실제 운영 개선 효과는 향후 정확한 검증 main 배포 뒤 별도로 측정해야 한다.
