# Chart View 개발 인수인계

최종 갱신: 2026-09-13

## 운영 경로

- 운영 URL: https://chart-view-bsg6.onrender.com
- 저장소: https://github.com/shoon94parkk-del/chart_View
- 기본 브랜치: `main`
- Render 진입점: 루트 `main.py`
- 실행 명령: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- 실제 템플릿/정적 자산: 루트 `templates/`, `static/`
- `toss_stock_app/`는 과거 사본이다. 현재 Render 진입점으로 사용하지 않는다.

## 앱 출시 준비 Stage 1 + Stage 2 (PR #11)

상세 설계·재현·테스트·복구 기록은 `docs/app-release-stage12.md`를 우선 읽는다.

### 현재 상태 소유권

- 비교목록·숫자 정규화·화면 snapshot: `static/js/app_state_v40.js`
- 단일 종목 상세·history·요청 취소: `static/js/single_detail_v40.js`
- 비교 수익률 차트: 기존 `static/js/chart.js` 엔진 유지
- 관심목록 저장/목록 UI: 기존 `static/js/watchlist_v30.js`, 저장 형식 유지
- 개인화 뉴스 UI: `static/js/personalized_news_v40.js`
- 개인화 뉴스 서버: `news_service_v37.py`
- 화면 완성/접근성: `static/js/release_ui_v40.js`, `static/js/release_flow_v40.js`
- 비교 화면 압축 스타일: `static/css/comparison_ui_v40.css`
- 공통 Stage 1+2 스타일: `static/css/release_ui_v40.css`
- 활성 자산 로더: `static/js/home_watchlist_boot_v32c.js`

### 중요 호환 규칙

- `chartview-watchlist-v1`, `chartview-selected-tickers-v1`, `chartview-ticker-names-v1`, `chartview-recents-v1` localStorage 형식을 바꾸지 않는다.
- 비교목록 key가 **없을 때만** 기본 비교목록을 적용한다. 사용자가 저장한 `[]`은 빈 목록으로 유지한다.
- 단일 상세를 연다고 비교목록을 변경하지 않는다.
- 비교 버튼 상태는 `비교 중 / 비교에 추가 / 비교목록 관리`만 사용한다.
- 상세 요청은 AbortController + detail sequence로 보호한다. A→B 전환이나 닫기 뒤 A의 늦은 응답이 DOM을 쓰게 만들지 않는다.
- V39.3의 `clarity_v39_3.js`와 V36 `personalization_v36.js`, V38 `personalized_news_v38.js`는 새 활성 로딩 경로에서 제외됐다. 과거 CSS는 시각 호환 때문에 일부 유지한다.
- 뉴스는 관심종목 최대 20개 전체를 조회하며, 서버 provider 동시 호출은 제한한다. 기사 텍스트가 5거래일 미니차트보다 먼저 표시돼야 한다.
- ROE/배당률은 값 크기로 단위를 추정해 임의로 100배하지 않는다. null/빈 문자열/NaN/Infinity와 실제 0을 구분한다.

### 검증

기존 명령에 더해 PR CI에서 아래 브라우저 테스트를 실행한다.

```bash
python -m pytest -q
node --test tests/frontend.test.cjs
node tests/mobile_smoke.cjs
node tests/app_release_stage12.cjs
```

`tests/app_release_stage12.cjs`는 Playwright 격리 context에서 상세 멈춤 외부 timeout, A→B 역순 응답, 닫기 후 늦은 응답, 저장된 빈 비교목록, 6개 한도, 결측값/0, 20종목 뉴스/부분실패/미니차트 지연, 360/390/430 긴 가격, 모바일/데스크톱 차트 위치, 다크모드·키보드·저장 실패를 검사한다.

Playwright 모바일 viewport 결과는 실기기 검증으로 표현하지 않는다.

## V35 변경 목적(역사 기록)

1. 같은 화면에 있는 데이터의 수집 시각과 원자료 기준일을 구분한다.
2. 밸류에이션 필드의 실제 선택 소스와 계산 방식을 API에서 전달한다.
3. 비교 차트를 조정주가 일봉 기준으로 통일한다.
4. EPS·주가 변화율 차이를 `%p`로 표시하고 단정적인 ‘미반영’ 표현을 없앤다.
5. 투자판단은 서로 다른 판단 축 수를 사용하고 데이터 존재 비율을 신뢰도처럼 표시하지 않는다.
6. 역사적 밸류를 공시 시점 근사 재구성치로 명확히 표시한다.
7. 종목발굴·관심종목에서 진입한 종목을 요약 카드의 활성 대상으로 맞춘다.
8. 앱 셸이 준비되기 전 구형 메뉴가 잠깐 노출되는 현상을 줄인다.

## 후속 작업

- 실제 공시일을 구할 수 있는 데이터 경로를 조사해 역사적 밸류의 45일 가정을 종목별 공시일로 교체한다.
- 공급자 예상 PER/EPS가 FY1·FY2·NTM 중 어느 기간인지 신뢰할 수 있게 식별되는 경우에만 구체적인 회계기간을 표시한다.
- 뉴스 번역/사건 군집/새 투자 점수는 Stage 1 안정성 범위와 분리한다.
- 계정 동기화, 알림, 공유, PWA, 앱스토어 패키징은 별도 제품 단계다.
- 최초 앱 셸을 템플릿에 정적으로 포함시키는 구조 통합은 별도 단계로 진행한다.
- V별 패치 파일과 일회성 워크플로는 참조 여부와 복구 경로를 확인한 뒤 정리한다. 일괄 삭제하지 않는다.

## 변경 원칙

- 코드 기능 변경과 정기 데이터 캐시 커밋을 구분한다.
- 화면 수치에는 값뿐 아니라 단위, 기준일, 소스, 기간을 함께 추적한다.
- 브라우저 저장 관심종목은 계정 동기화 데이터로 표현하지 않는다.
- 배포가 확인되기 전 완료로 기록하지 않는다.
- 운영 완료는 Render `live`만으로 판단하지 않고 main SHA/revision과 화면 동작을 함께 확인한다.
