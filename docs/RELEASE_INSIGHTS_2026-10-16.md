# 발표 정보·물가 그래프·DRAM 전월비 출시 기록 — 2026-10-16

상태: 구현·통합 기록 초안. **이번 출시의 최종 QA, main SHA, 운영 배포와 성능 결과는 아직 이 문서에 기록하지 않았다.** 아래 확인란은 출시 담당자가 실제 결과로 채운다.

## 출시 범위와 통합 기준

AFTERNS 조사에서 제안한 발표 중심 정보 구조를 기존 공시·수출·매크로·컨센서스 화면에 적용한다. 발표 날짜, 관측 대상 월, 수집·확인 시각과 원문을 구분하고 기존 자료로 돌아가는 동선을 보강한다. AFTERNS의 데이터·요약·인용문을 복제하지 않는다.

백엔드 작업 기준 `0d7f9b42b2563e8b0e292c3773d07f5367bf924c`에는 다음 main 변경을 병합해 포함했다.

- `92c1e5612e00102255ced511004c3266552c5c4b`: 반도체 전월 비교 기준의 중복 집계 수정.
- `c02878102a57d6aaab577e40378c8a1f579d68d5`: 기존 컨센서스 일일 캐시 갱신.

프런트는 **0.16 출시를 목표**로 한다. PR #134의 최근 조회 5종목, 관심 정렬 복원, 상세 문맥 및 질문·비교종목 저장 상태 개선을 이미 통합한 기준에서 이번 기능을 추가한다. 최종 package 버전과 프런트 main·운영 SHA는 출시 확인란에 기록한다.

PICK 선정·기록·점수·상태·노출 조건·사후 성과와 LAB 핵심 판단 코드는 변경하지 않는다. 기존 시세 공급자·캐시·수익률 계산·전략 기준과 면책 문구를 유지한다. 토스 콘솔 설정이나 추가 Toss API·SDK 메서드는 도입하지 않는다.

## DRAM 전월비: 같은 전월 원자료의 중복 제거

운영에서 확인한 2026년 9월 DRAM 수출액은 167.770억 달러, 독립 월별 이력의 8월은 157.331억 달러였다. 이 금액으로 계산한 전월비는 `+6.6%`지만 기존 개요에는 `-46.7%`가 표시됐다. 넓은 메모리 HSK `854232` 요청과 개별 DRAM·Flash·MCP 요청에 같은 전월 10자리 HSK 행이 겹쳐 들어와 기준 금액·중량이 두 번 집계된 것이 원인이었다.

통합한 수정은 전월 수집 단계에서 월·HS 식별자를 정규화해 같은 행을 한 번만 사용한다. 금액·중량이 서로 맞는 중복은 합치고, 값이 충돌하면 해당 선택 비교 묶음을 제공하지 않는다. 기존 다섯 병렬 요청, TTL, 캐시, 엔드포인트, 일반 집계 계산식을 유지한다. 현재 월 금액·YoY와 독립 월별 이력은 이 중복 비교 경로를 사용하지 않는다.

재현 수치·영향 범위·기존 개별 검증 기록은 [DRAM 감사 기록](DRAM_MOM_AUDIT_2026-10-16.md)에 있다. 이 문서의 운영 배포 확인은 별도이며, 배포 후 기존 캐시가 정상 갱신된 실제 응답에서 개요와 같은 HSK·월의 이력을 다시 비교한다.

## CPI·근원 CPI·PPI·근원 PPI

새 정적 캐시는 FRED가 제공하는 BLS 월별 지수로 네 계열을 구성한다. 기존 16개 매크로 결과·요약 계산을 유지하면서 `/api/macro`에 선택 정보인 `inflation`과 `releaseCalendar`를 덧붙인다. 요청 시 공식 공급자를 조회하지 않는다.

| 계열 | 전년 동월 대비: NSA 지수 | 전월 대비: SA 지수 | 정의 |
| --- | --- | --- | --- |
| CPI | `CPIAUCNS` | `CPIAUCSL` | CPI-U 전체 품목 |
| 근원 CPI | `CPILFENS` | `CPILFESL` | CPI-U 식품·에너지 제외 |
| PPI | `PPIFID` | `PPIFIS` | 생산자물가지수 최종수요 |
| 근원 PPI | `PPICOR` | `PPIFES` | 최종수요 중 식품·에너지 제외 |

전년비는 **비계절조정(NSA)** 지수의 정확히 12개월 전 값, 전월비는 **계절조정(SA)** 지수의 정확히 1개월 전 값과 비교한다. 근원 PPI를 식품·에너지·무역서비스 제외 변형과 섞지 않는다. PCE는 기존 이름·정의를 유지한다.

최초 확보 캐시는 2021-10~2026-09의 60개월이다. CPI·근원 CPI에는 공급 자료의 공백이 있어 각 전년비 59개, 전월비 58개가 있고 PPI 두 계열은 각각 60개다. CPI의 2025-10 전년비·전월비와 2025-11 전월비는 결측으로 보존한다. 인접 관측치를 당겨 전월 자료로 사용하거나, 결측을 0·보간값으로 채우지 않는다. 화면은 기간·YoY/MoM·단위·조정 기준·관측월·출처와 결측 상태를 드러낸다.

공식 발표 시각은 BLS 원문에서 관측월과 함께 확인한 경우에만 연결한다. `asOf`는 관측월, `publishedAt`은 확인한 공식 발표 시각, `collectedAt`·`checkedAt`은 수집·성공 확인 시각이다. FRED는 현재 빈티지이며 최초 발표 당시 값의 아카이브가 아니다. 겹치는 지수 값이 직전 성공 캐시와 달라졌을 때의 `revised`는 캐시 간 변경 관찰을 뜻한다. 공식 수정 플래그나 원래 발표값을 확인했다는 뜻으로 표시하지 않는다. 확인되지 않은 과거 발표일·수정 상태는 비워 둔다.

## 공식 경제 발표 일정

발표 일정은 BLS의 CPI·PPI 개별 공식 일정표에서 읽는다. 최초 확보분은 **28개 공식 일정**이며, 각 행에 대상 관측월, 공식 현지 날짜·시간, `America/New_York`, UTC 시각, 출처와 성공 확인 시각을 보존한다. KST 변환은 해당 날짜의 서머타임을 반영한다.

일정은 확인 당시의 자료이며 이후 공식 변경이 있을 수 있다. 읽기 단계에서 지난 일정을 제외한다. 날짜만 확인된 행에는 임의 시각을 넣지 않는다. 일정과 지수 수집 실패는 서로 구분하며, 실패한 계열·일정은 기존 성공 자료와 원래 확인 시각을 보존하거나 자료 없음으로 표시한다.

## 기업 실적: 확인된 컨퍼런스콜 일정부터 제공

새 `/api/earnings-events`는 별도 정적 캐시만 읽는다. `ticker`를 생략하면 제한된 전체 범위, 지정하면 해당 종목의 결과를 반환한다. 최초 확보 범위는 다음과 같다.

| 종목 | 확인한 공식 일정 | 한국 시각 | 출처 |
| --- | --- | --- | --- |
| 삼성전자 | 3Q26 Earnings Conference Call, 2026-10-29 10:00 KST | 2026-10-29 10:00 | [Samsung IR Events](https://www.samsung.com/global/ir/ir-events-presentations/events/) |
| Apple | FY26 Q4 results conference call, 2026-11-02 17:00 ET | 2026-11-03 07:00 | [Apple IR](https://investor.apple.com/investor-relations/default.aspx), [공식 RSS](https://investor.apple.com/rss/Event.aspx?LanguageId=1) |

두 일정은 **컨퍼런스콜 시각**이다. 실제 실적 자료의 공개 시각은 확인되지 않았으므로 이벤트의 `publishedAt`은 null, 실적 발표의 장전·장후 구분은 unknown으로 유지한다. 원문 공지 자체의 게시 시각은 별도의 `source.publishedAt`이다. Apple RSS의 채널 날짜는 콜 시각으로 사용하지 않으며, 확인 당시 404인 상세 링크 대신 확인한 IR·RSS 링크를 제공한다.

추적 범위는 AAPL·NVDA·005930.KS·000660.KS 네 종목이다. NVIDIA 공식 이벤트 RSS는 유효한 빈 피드였고, SK하이닉스 공식 일정은 이번 수집에 포함하지 않았다. 따라서 확인된 다음 콜은 두 종목이며 나머지는 이유를 표시한다. 과거 콜, 성공 확인 후 7일을 넘긴 일정, 시간대·공식 출처가 검증되지 않은 행은 다음 일정으로 제공하지 않는다. 실패 후 보존한 일정은 성공 확인 시각을 새로 찍지 않는다.

**예상·실제·발표 후 반응 비교는 조건부 미제공**이다. 읽기 전용 Yahoo 대표 종목 확인에서 EPS와 회계 기준 메타데이터는 있었지만, 발표 전 예상의 불변 스냅샷 시각, 실제 자료 공개 시각과 발표를 반영하는 정규장 종가 쌍을 확보하지 못했다. 같은 회계기간·같은 기준의 예상과 실제를 검증한 뒤에만 비교를 제공한다. 현재 예상치를 과거 예상치로 소급하거나, 회계기간 종료일을 발표일로 쓰거나, 일반 기간 수익률을 실적 반응으로 표시하지 않는다. 이번에는 실제 EPS만의 별도 공식 기간·기준 검증도 완료하지 않아 숫자·서프라이즈·beat/miss·가격 반응을 내보내지 않는다.

## 파일·수집·요청 경로

| 파일 | 역할 |
| --- | --- |
| `inflation_release_service.py` | 선택 물가·경제 일정 정적 캐시 읽기, 지난 일정 제외 |
| `scripts/generate_inflation_release_cache.py` | FRED 8개 SA/NSA 지수, BLS 2개 일정·2개 발표 원문 수집과 의미 검증 |
| `static/data/inflation_release_cache.json` | 독립 물가 이력·공식 일정 캐시 |
| `earnings_event_service.py` | 공식 콜 출처·시각 검증, KST 변환, 만료·결측 처리 |
| `scripts/generate_earnings_event_cache.py` | Apple·Samsung·NVIDIA 공식 공개 페이지 3개 확인 |
| `static/data/earnings_event_cache.json` | 확인된 콜·종목별 수집 상태와 원문 지문 |
| `main.py` | 기존 매크로 응답에 선택 자료 연결, 독립 콜 API 등록, Home 매크로의 기존 범위 유지 |
| `.github/workflows/update-macro-cache.yml` | 기존 작업과 독립된 물가·일정 수집 job 추가 |
| `.github/workflows/update-earnings-events.yml` | 하루 한 번·수동 실행 가능한 독립 콜 수집 workflow |
| `tests/test_inflation_release_cache.py` | 지수·기간·발표일·일정·실패 보존 검증 |
| `tests/test_earnings_event_service.py`, `tests/test_earnings_event_collector.py` | 공식 콜 시각·출처·만료·실패 보존 검증 |
| `tests/test_release_reading_api.py` | 기존 매크로·Home 계약 및 정적 콜 API 검증 |

물가 수집은 최대 4개 worker로 12개 공식 공개 URL을 확인하고 요청 timeout은 25초다. 독립 job의 상한은 5분이다. 기존 16개 매크로 수집 job의 상한을 늘리지 않는다. 콜 수집은 실행당 공개 페이지 3개, 재시도·리디렉션 추적 없음, 요청 timeout 12초, job 상한 3분이다. 새 유료 키·서비스·인프라는 필요하지 않다.

Home 응답에는 새 그래프 이력·경제 일정·콜 payload를 싣지 않는다. 기존 Home 매크로 필드와 요약을 유지한다. 새 기업 일정 API는 컨센서스 화면의 선택 지연 로드로 사용하며 Home 진입 호출을 추가하지 않는다. 실패한 선택 자료가 기존 유효한 차트·매크로·시세를 지우거나 첫 화면을 기다리게 하지 않는다.

수집 workflow의 캐시 커밋은 운영 게시 완료와 구분한다. 백엔드에 해당 파일을 게시하려면 검증한 정확한 main revision의 기존 Render 배포 절차를 따른다. 공급자 조회·새로 고침을 서버 요청 경로로 옮기지 않는다.

## 재현 명령

아래 명령은 출시 담당자가 실행 결과를 기록하기 위한 절차다. 이 목록 자체는 실행·성공 기록이 아니다. 저장소 요구사항과 pytest/httpx/yfinance가 준비된 Python 환경을 사용한다.

```sh
# 공급자 없이 저장 자료·계산·API 계약 확인
python -m pytest -q tests/test_export_semiconductor_mom_dedup.py tests/test_inflation_release_cache.py tests/test_earnings_event_service.py tests/test_earnings_event_collector.py tests/test_release_reading_api.py

# 전체 백엔드·기존 Web 계약과 생성 자산 확인
python -m pytest -q
node --test tests/frontend.test.cjs tests/live_quotes_v56_contract.cjs tests/home_heatmap_v57_contract.cjs tests/macro_policy_v62_contract.cjs tests/server_live_cache_v66_contract.cjs tests/share_deeplink_v68_contract.cjs
python scripts/build_frontend_bundle.py --check
python scripts/build_boot_bundle.py --check

# 공식 공급자 조회 후 각각의 독립 JSON 캐시 갱신
python scripts/generate_inflation_release_cache.py
python scripts/generate_earnings_event_cache.py
```

프런트 저장소에서는 최종 main 기준 `npm test`, `npm run build`, 관련 모바일 브라우저/E2E 확인과 `npm run build:ait` 결과를 기록한다. 네이티브 환경 확인은 브라우저 에뮬레이션과 구분한다.

배포 후에는 `/health` revision, `/api/macro`의 기존 16개 결과·요약과 선택 자료, `/api/earnings-events?ticker=AAPL`, 같은 기간의 수출 개요·월별 이력을 확인한다. 운영 모바일에서 실제 데이터·원문 이동·연구 복귀·결측·재방문 동선과 Home 호출·성능을 확인한다. Render의 live 상태만으로 완료로 판정하지 않는다.

## 검증 기록 및 배포 확인 위치

- 로컬 백엔드 전체 Python **815 passed**, 기존 Node 계약 **52 passed**, 두 생성 번들 최신성 확인 성공. 독립 검토에서 미해결 Critical/High 없음. 잘못된 일정 타입은 해당 선택 일정만 제외하는 회귀 테스트로 보강했다.
- 최종 main SHA·PR·Render 배포·운영 확인은 이 문서를 포함한 커밋을 배포한 뒤 PR의 검증 댓글에 기록한다. 배포 후 문서만 바꾸어 검증 SHA를 다시 변경하지 않는다.
- 프런트 최종 버전 / main SHA / PR / 테스트·빌드·AIT 결과: **미기록**.
- Render 배포 ID·시각 / 실제 `/health` revision / 정적 자산 정합성: **미기록**.
- 운영 DRAM 개요·같은 HSK 월별 이력 / 물가·공식 일정 / 기업 콜 API 확인: **미기록**.
- 모바일 Chromium·WebKit 브라우저 확인 / Home 요청·성능 전후 측정: **미기록**.
- 실제 iOS·Android Toss Sandbox: **미검증**. 웹 미리보기·AIT 빌드 성공과 별도로 기록한다.
- 추가 Toss 콘솔·API·SDK 메서드: **도입 없음**.
