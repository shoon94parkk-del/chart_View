# Home 공급자 중복·연결 비용 개선

홈 데이터 대기 개선 첫 운영본(front02cb311/backend78021)은 실제 데이터5종을 통과했으나 같은 Home/Heatmap harness에서 지수4개1.8/8.6/4.2초, 관심3개3.7/13.9/4.2초의 cold-browser 표본이 나왔다. 초기 네 요청이5초에 취소된 뒤 기존 polling으로 회복한 표본도 있었다. 당시 CPU는0.15 core 한도에 도달했고 메모리는약47%, 재시작·실패 이벤트0이었다. 정확한 최초 사용자20초 요청이나 단일 함수 원인을 확정하지 않는다. [첫 운영 표본](audits/2026-10-13-home-provider-contention/first-release-live-timing.json)을 남기고 숫자 표시가 충분히 빨라졌다는 결론을 보류했다.

## 기존 보호 복구

기존 `market_service.fetch_quote_snapshot`은 singleflight를 적용했지만 한국 Naver 교체 경로는 이를 우회했다. 기존5초 캐시를 동시에 놓친 같은 ticker의 Home/watch/heatmap 요청이 중복될 수 있었다. 한국 index/stock의 공통 provider owner에 기존 `request_coalescing.singleflight`를 적용한다. normalize한 ticker로 합치고 cache put은 owner만 수행하며 각 caller에는 별도 dict를 반환한다. 비교·밸류에이션도 동일한 한국 경로를 사용한다. 기존cache/TTL/fallback/출처·asOf/regular-close 계약은 유지한다.

실제 canonical 함수의 동시 cache miss 회귀는 수정 전3개 실패, 수정 후 통과했다. 6개 동시 stock/index 조회의 provider call은6→1, quote/compare/valuation3개는3→1이었다. 가짜 외부 provider를 붙인 중복 작업 제어 검사이며 운영 응답 시간 개선율이 아니다. 기존5초 만료, caller 값 격리, 실패 후 다시 조회, 다른 ticker 병렬 동작도 검증한다.

## 연결 재사용

Yahoo Chart/Naver GET이 매번 만들던 Session 대신 스레드별 standardRequestsSession을 재사용한다. caller의URL/header/params/timeout, 환경proxy/CA 검증, default retry0을 유지한다. response cache나 새provider/pool/키를 만들지 않는다. Yahoo auth/crumb 경로는 이번 변경에 포함하지 않는다. 실제localhost socket 재사용, 스레드 격리, cookiehost범위·Authorization비보존, HTTP/JSON/timeout오류, intraday→dailyfallback 회귀를 추가했다.

## 검증·배포

[로컬 검증](audits/2026-10-13-home-provider-contention/local-qa.json): Python761, 신규 통합focus23, 필수NodeCI52, release/bootbundlecheck·문법·CIstatic/marketinvariants가 통과했다. 독립 검토 차단 사항0이다. 테스트HTTPmock은 새transport seam을 대상으로 변경하고 기존assertion을 유지했다. 추가로 실행한 오래된JSregex18개는baseline/current모두12통과·6실패다. 해당UI와검사파일은변경하지 않았으며 필수CI52와 구분한다.

새 자동수집macro/Guru/Home/fullheatmap JSON을 포함한8e053을base로 보존한다. 프런트02cb311과 package0.15.1은 유지한다. 정확한 mainCI·Renderrevision·실제가격/출처·같은harness재측정은 후속운영기록으로 연결한다. 공급자poolBG2/BULK1/default, TTL과 정상pollingcadence를 늘리지 않았고 새API/키/유료인프라는 없다.

다음 우선순위는 히트맵 직접진입의 미사용Home market/bootstrap 요청과 snapshot게시 실패 상태다. 기존풀의 index우선순위나 실패cooldown은 queue대기 근거를 확보한 뒤 별도판단한다.
