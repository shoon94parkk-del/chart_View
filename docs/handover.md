# Chart View 개발 인수인계

최종 갱신: 2026-09-12

## 운영 경로

- 운영 URL: https://chart-view-bsg6.onrender.com
- 저장소: https://github.com/shoon94parkk-del/chart_View
- 기본 브랜치: `main`
- Render 진입점: 루트 `main.py`
- 실행 명령: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- 실제 템플릿/정적 자산: 루트 `templates/`, `static/`
- `toss_stock_app/`는 과거 사본이다. 현재 Render 진입점으로 사용하지 않는다.

## V35 변경 목적

1. 같은 화면에 있는 데이터의 수집 시각과 원자료 기준일을 구분한다.
2. 밸류에이션 필드의 실제 선택 소스와 계산 방식을 API에서 전달한다.
3. 비교 차트를 조정주가 일봉 기준으로 통일한다.
4. EPS·주가 변화율 차이를 `%p`로 표시하고 단정적인 ‘미반영’ 표현을 없앤다.
5. 투자판단은 서로 다른 판단 축 수를 사용하고 데이터 존재 비율을 신뢰도처럼 표시하지 않는다.
6. 역사적 밸류를 공시 시점 근사 재구성치로 명확히 표시한다.
7. 종목발굴·관심종목에서 진입한 종목을 요약 카드의 활성 대상으로 맞춘다.
8. 앱 셸이 준비되기 전 구형 메뉴가 잠깐 노출되는 현상을 줄인다.

## 검증 명령

```bash
python -m pytest -q
node --test tests/frontend.test.cjs
python -m py_compile main.py market_service.py valuation_band_service.py consensus_service.py scripts/*.py
```

배포 후에는 GitHub Actions의 App Regression Check, Live Render Smoke Test, Production Mobile Verification 결과와 `/health`의 `revision`이 배포 커밋과 일치하는지 확인한다.

## 후속 작업

- 실제 공시일을 구할 수 있는 데이터 경로를 조사해 역사적 밸류의 45일 가정을 종목별 공시일로 교체한다.
- 공급자 예상 PER/EPS가 FY1·FY2·NTM 중 어느 기간인지 신뢰할 수 있게 식별되는 경우에만 구체적인 회계기간을 표시한다.
- 업종 분류의 품질을 확인한 뒤 절대 임계값과 업종·자기 과거 비교를 함께 제공한다.
- 최초 앱 셸을 템플릿에 정적으로 포함시키는 구조 통합은 별도 단계로 진행한다.
- V별 패치 파일과 일회성 워크플로는 참조 여부와 복구 경로를 확인한 뒤 정리한다. 일괄 삭제하지 않는다.

## 변경 원칙

- 코드 기능 변경과 정기 데이터 캐시 커밋을 구분한다.
- 화면 수치에는 값뿐 아니라 단위, 기준일, 소스, 기간을 함께 추적한다.
- 브라우저 저장 관심종목은 계정 동기화 데이터로 표현하지 않는다.
- 배포가 확인되기 전 완료로 기록하지 않는다.
