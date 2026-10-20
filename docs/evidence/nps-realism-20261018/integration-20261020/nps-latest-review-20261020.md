# NPS 최신 커밋 통합 검토 — 2026-10-20

검토 대상: backend origin/main `1cab36a`, frontend origin/main `1fd9b1a`에 기존 현실성 모델 revision 2를 통합한 작업 트리. 주요 신규 커밋 `edcbe17`(재시도·push 갱신), `a4f7ab8`(목표 대응 KOSPI·정오 갱신 경고), `da289b6`(운영 기록)를 확인했다. 처음에는 읽기 전용 검토였으며, parent의 후속 지시에 따라 아래 backend 결함과 회귀를 이 에이전트가 수정했다. 수정 후 전체 검토의 독립 검증을 대신하는 보고서는 아니다.

## 발견 사항

**미해결 P1 없음. 아래 P2 3건은 수정 및 관련 회귀 통과.** 최종 수집·전체 pytest·브라우저·배포 검증은 parent가 수행한다.

### P2 — 소스 push가 같은 시장일의 모델 변경을 게시하지 못함 — 수정

기존 `.github/workflows/update-nps.yml` push 경로는 `quotes.py`·`config.json`만 열거해 신규 `realism.py` 수정 단독으로는 실행되지 않았다. 실행돼도 `FORCE_RECHECK`는 수동 dispatch의 force만 처리했다. `run()`의 두 조기 종료가 모델·출처·기준 변경 재계산을 막았다.

네트워크 없는 재현: 기존 marketDate/cutoff가 모두 Oct19면 force=False는 공급자 호출 전에 종료하고, True는 수집에 진입했다. cutoff Oct18/common session Oct16인 주말도 force=False는 filing/model 재계산 전에 종료하고 True는 진행했다.

수정: workflow `:16`은 `scripts/nps/**`를 감시하고 `:50`은 push 이벤트에 force를 켠다. schedule의 정상 중복 시장일 건너뛰기와 수동 force=false는 유지한다. `tests/test_nps_realism.py:166`의 실제 표현식 4개 이벤트 조합 및 모듈 경로 회귀는 **수정 전 2 failed / 3 passed → 수정 후 통과**했다.

### P2 — 선택 AGGG 비교의 결측이 중앙 추정 전체를 오래된 시장일에 묶음 — 수정

`common_session()`이 13개 수집 시계열 전체 교집합을 사용했다. BNDW를 쓰는 메인 추정에는 AGGG가 필요하지 않지만, AGGG Oct19 결측 하나로 다른 12개가 Oct19를 가져도 Oct16이 선택됐다. parent가 실제 수집의 AGGG Oct19 null을 확인했으며, 로컬에서도 동일 교집합 문제를 합성 가격으로 재현했다. Oct16을 이미 게시된 Oct19 위에 덮어쓰려는 시도는 기존 publish 보호가 거부했다.

수정: `scripts/nps_pipeline.py:34`·`:50`은 AGGG만 공통일 필수 집합에서 제외한다. 수집은 13개를 유지한다. `:73`의 선택 수집 예외 처리와 `:84`의 관측 기록은 실제 None/error/통화/출처를 보존한다. 비정상 NaN/무한대는 JSON의 null 관측으로 남기고 0이나 과거 가격으로 채우지 않는다. 출처 상세는 동일 기준일 가격 ‘미확인’을 표시한다. 다른 12개는 기준일·현재일 결측 및 잘못된 통화에서 계속 실패한다.

`scripts/nps/realism.py:47`·`:64`는 기준/시장일 양쪽 close·adjustedClose가 유한 양수이며 USD인 경우에만 비교 수익률을 만든다. 불가하면 `unhedgedProxyReturnPct:null`, `unhedgedProxyStatus:'unavailable'`, 실제 `unhedgedProxyDate`를 기록한다. `:84`는 그 비교만 제외하고 `sensitivity.unavailable`에 이유를 제공한다. 정상 자료와 실제 0% 수익은 available 및 기존 8개 비교를 유지한다.

가용성·누락·잘못된 통화·수집 예외·동일 중앙값·출처 및 JSON 게시 가능성을 다루는 최초 13개 회귀는 **수정 전 13 failed → 수정 후 통과**했다. 기존 핵심 시계열 회귀도 12개 전체로 확장했다. `summary.update`는 10:30/13:30/16:30 KST 재시도와 source push의 같은 시장일 강제 재계산을 설명한다.

### P2 — 오전에 빠진 선택 비교를 오후 재시도가 복구하지 못함 — 수정

선택 비교를 분리하기만 하면 오전에 중앙 Oct19/unavailable을 게시한 후 오후 실행은 같은 marketDate라서 다시 조기 종료된다.

수정: `scripts/nps_pipeline.py:416`에서 이전 AGGG 상태가 unavailable이면 두 조기 종료를 우회해 재확인한다. available로 복구하면 다음 동일 시장일 실행은 기존 종료 동작으로 돌아간다. 날짜가 더 오래된 중앙 추정을 새 게시물 위에 쓰는 publish 거부는 유지한다. `tests/test_nps_realism.py:268`은 cutoff==marketDate 및 주말 cutoff 두 경로에서 unavailable→available 복구, 중앙 inputs/result 불변, 복구 후 중복 건너뛰기를 검증한다. `:283`은 복구 재시도 중 오래된 시장일 덮어쓰기를 거부하고 파일을 그대로 보존한다. 이 3개 회귀는 **수정 전 3 failed → 수정 후 통과**했다.

## 최신 UI·데이터 경로 검토

- 목표 ±0.5%p 구간은 통계적 오차·예측 구간이 아니라 현재 다른 자산 추정액을 유지할 때 20.3~21.3%에 대응하는 지수 구간이다. parent가 `npsAllocationView.js:49`의 표시를 ‘비중 20.3~21.3% 대응’으로 정리했고 조건부 계산 설명을 유지한 것을 확인했다.
- 현실성 fixture에서 목표 20.3/20.8/21.3%의 역산 지수는 각각 4951.783196/5105.779539/5261.732633이었다. 각 지수를 다시 주 계산에 넣으면 해당 비중과 일치했다(최대 오차 3.55e-15%p). 이는 Oct16 fixture에 대한 계산 검증이며 현재 시장 수치가 아니다.
- KST 정오 유예를 실제 함수로 확인했다. Friday Oct16은 토·일·월 및 화요일 정오 전에는 정상이고 화요일 정오 후에는 예상 Monday Oct19보다 오래돼 경고가 켜진다. 공휴일 달력은 없다. 공휴일로 공통 종가가 이전 날짜에 머물면 경고가 나타날 수 있으며, 이를 실시간 가격 또는 새로운 보유수량으로 주장하지 않는다.
- `npsAllocationData.js`는 공개 raw CDN과 기존 `/static/data/nps/...` fallback을 사용한다. 최근 `/api/published-data/{filename}`의 flat allowlist는 NPS 자료를 포함하지 않으며 NPS 경로를 바꿀 필요가 없다. 문서의 raw CDN 최대 약 5분 전파 지연과 화면의 5분 게시 확인 의미를 유지한다.
- 최신 upstream 중앙 게시물은 Oct19 `fa14da10ba84ec87`이다. 역사적 Oct16 revision 2 `e93a82d9da4a54a8`을 최신 summary로 복원하면 안 된다. parent는 최종 수집으로 새 Oct19 revision 2 게시물을 만들고 있다.

## 산식 통합 점검

이번 변경은 중앙 자산 산식을 바꾸지 않는다. 선택 비교가 빠져도 같은 정상 12개 입력에서 inputs/result가 완전히 같다는 회귀가 통과했다. 채권 ETF 총수익률에 금리 가격손실·쿠폰을 다시 더하거나 빼지 않는다. 13F 직접 평가와 잔여 ACWI, 환율 적용, 단기자금 이자·순유입 원금·헤지 캐리는 기존 revision 2 분리를 유지한다. 사모 NAV의 중앙 0은 미관측 가정이고 경제가치 시나리오는 별도다. 상세 금융 근거와 기존 63개 Python/JS 산식 비교는 `/workspace/nps-realism-research/final-review.md`를 참고한다.

## 실행 검증

최종 backend 명령:

```sh
PYTHONDONTWRITEBYTECODE=1 uv run --with-requirements requirements.txt --with pytest --with httpx --with yfinance python -m pytest -q -p no:cacheprovider tests/test_nps_pipeline.py tests/test_nps_realism.py
```

결과 **57 passed in 2.09s**, exit 0. 모든 공급자 응답은 단위검사에서 주입하며 외부 대량 수집은 수행하지 않았다. 처음 기본 Python에서 pytest 부재로 실패해 pytest 설치/uv 환경을 사용했다. 이 환경 실패는 red 회귀 결과에 포함하지 않았다.

최신 커밋 통합 직후 frontend 기존 NPS/realism Node **16 passed** 및 위 역산/주말 검증을 별도로 실행했다. 이후 parent의 선택 비교 UI·가용성 validator 변경에 대한 최신 frontend 전체 QA 결과는 parent 기록을 따른다. 전체 backend pytest·fresh collection·브라우저·release 결과를 이 보고서가 주장하지 않는다.

이 에이전트의 제품 수정 범위는 `.github/workflows/update-nps.yml`, `scripts/nps_pipeline.py`, `scripts/nps/realism.py`, `tests/test_nps_realism.py`다. git stash/merge/commit·배포는 하지 않았다.
