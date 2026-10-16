# CPI/PPI 공식 수집 경로 보강 — 2026-10-16

기존 GitHub runner에서 FRED CSV 8종은 25초 읽기 시간 초과, BLS 일정·발표 HTML은 403을 반환했다. 캐시는 2026년 9월 관측값과 마지막 성공 확인 시각을 유지하며 `stale`로 게시했다. 이 상태를 새로 확인한 값으로 바꾸지 않는다.

격리한 [공식 소스 진단 실행](https://github.com/shoon94parkk-del/chart_View/actions/runs/38841507292)은 GitHub runner에서 다음 결과를 확인했다. 진단 커밋은 `16c0d43ac370a1e31ee2bc2c89141480690c3ec0`이며 제품 브랜치에 포함하지 않는다.

- 공식 BLS v2 `POST https://api.bls.gov/publicAPI/v2/timeseries/data/`: 한 요청, 키 없음, `2020–2026`, 8개 시리즈, HTTP 200 / `REQUEST_SUCCEEDED`, 0.545초.
- 모든 시리즈가 2020년 1월부터 2026년 9월까지 81개 월 행을 반환했다. CPI 4종의 유효값은 각각 80개, PPI 4종은 각각 81개다. 60개월 변화율과 전년 동월 기준값을 확보할 범위다.
- 공식 `https://www.bls.gov/schedule/news_release/bls.ics`: 한 요청, HTTP 200, 0.109초, 유효한 `VCALENDAR`, 80,672바이트.
- 앞선 관리 환경의 2025–2026 대조는 164/164개, runner의 전체 기간 대조는 **644/644개 유효 월 지수**가 저장한 공식 FRED CSV와 정확히 일치했다. 등록 키가 필요한 BLS catalog 이름은 요청하지 않았다. BLS가 수락한 ID와 전체 기간의 값 일치, 별도로 읽은 공식 FRED 정의·계절조정 표기를 함께 근거로 삼았다.

| 지표 | 전월비용 BLS SA | 전년 동월비용 BLS NSA | 공식 FRED 대응 |
|---|---|---|---|
| CPI-U 전체 | CUSR0000SA0 | CUUR0000SA0 | CPIAUCSL / CPIAUCNS |
| CPI-U 식품·에너지 제외 | CUSR0000SA0L1E | CUUR0000SA0L1E | CPILFESL / CPILFENS |
| PPI 최종수요 | WPSFD4 | WPUFD4 | PPIFIS / PPIFID |
| PPI 최종수요 식품·에너지 제외 | WPSFD49104 | WPUFD49104 | PPIFES / PPICOR |

수집기는 FRED를 먼저 확인한다. SA/NSA 쌍 중 하나라도 실패하거나 범위 검증을 통과하지 못하면 공식 BLS batch를 **최대 한 번** 요청한다. 현재 연도에서 6년 전부터 현재 연도까지의 8개 ID를 보내며, 시간 제한은 25초이고 키·재시도는 없다. BLS 결과는 실패한 지표 쌍에만 적용한다. 성공한 FRED 쌍을 바꾸거나 서로 다른 공급 경로의 SA/NSA를 한 쌍으로 섞지 않는다.

실제로 BLS를 사용한 행의 `source.name`, URL, SA/NSA ID도 BLS로 바뀐다. 원시 인덱스·누락·공식 footnote를 보존한다. CPI 2025년 10월의 `-`에는 공식 X 주석 “Data unavailable due to the 2025 lapse in appropriations”가 있다. 따라서 해당 월 변화율과 다음 달 MoM은 계속 null이다. 최신 PPI의 P 주석은 원발표 후 최대 4개월간 월별 수정 가능한 잠정 지수라고 명시한다. `observationStatus: preliminary`와 원문 주석을 API 메타데이터로 보존한다. 현재 프런트가 이 필드를 별도 배지로 표시하는 것은 아니다. 최신 관측에 공식 P 주석이 있는 경우에만 기존 정의 뒤에 “최근 값은 잠정치로 추후 수정될 수 있어요.”를 덧붙여 기존 정의 UI에서도 확인할 수 있게 한다. 근원 PPI의 원래 정의는 유지하며, 잠정 여부를 수정 발생 여부로 바꾸어 해석하지 않는다.

`checkedAt`와 `collectedAt`는 검증에 성공한 쌍만 갱신한다. 일부 또는 전체 BLS 결과가 없거나 잘못됐으면 그 지표의 마지막 유효 값과 성공 시각을 유지한다. YoY는 정확히 12개월 전 NSA 지수, MoM은 정확히 한 달 전 SA 지수를 사용한다. BLS API 확인 시각을 공식 발표 시각으로 쓰지 않는다. 발표 HTML을 읽지 못한 경우에도 같은 관측월에 대해 이미 검증한 `publishedAt`만 유지하며, 새 관측월 발표 시각은 null이다.

일정 HTML도 우선 경로다. 최초 GitHub runner 진단의 표준 라이브러리 urllib 요청은 ICS 200이었지만, 실제 수집기의 범용 requests 경로는 같은 ICS에서 403을 반환한 사례가 있다. ICS의 정확한 공식 URL에만 이미 확인한 urllib와 명시적 `Accept: text/calendar`를 사용한다. 앱 User-Agent는 동일하며, 프록시·기본 TLS 검증·환경과 FRED/공식 API 전송은 바꾸지 않는다. 이 경로도 실패하면 기존 일정과 확인 시각을 stale로 유지한다. 실패한 일정 종류가 있을 때만 공식 ICS를 한 번 확인한다. 파서는 명시된 UTC 또는 `US-Eastern`/`US/Eastern`/`America/New_York`를 사용하고 DST, 접힌 줄, 날짜만 있는 행을 구분한다. 시간대 없는 시간, 존재하지 않거나 중복되는 DST 현지 시각은 채택하지 않는다. 공식 UID가 같은 일정의 시간 변경은 이전 행을 교체한다. 취소 UID는 활성 행사와 별도로 reconciliation에 전달해 취소만 있는 피드에서도 이전 동일 UID 행을 제거한다. 취소 행은 DTSTART가 과거이거나 날짜만 있더라도 UID를 전달하며, 활성 행에만 지난 시각 필터를 적용한다. 같은 UID의 중복 또는 활성·취소 충돌은 피드 전체를 미확인으로 처리한다. UID가 없는 HTML 시드가 ICS의 명시적 발표일 달 안에서 충돌하면 과거 확정 일정으로 남기지 않고 목록에서 제외한다. 이 발표일 달은 충돌 범위를 좁히는 용도로만 쓰고 관측월을 추정하지 않는다. 그 범위 밖의 미래 행은 이전 확인 시각을 유지한다.

현재 ICS는 앞으로의 CPI/PPI 4개 행사만 포함하고 관측월을 명시하지 않는다. 관측월은 이전에 확인한 동일 종류·동일 시각 또는 동일 공식 UID의 행에서만 유지한다. 새 ICS 전용 행의 관측월은 null이다. 이번 자료에서는 4개 행만 새 확인 시각을 받으며, HTML에서 확인했던 나머지 24개 미래 행은 이전 확인 시각과 함께 보존해 일정 전체를 `partial`로 표시한다. 전체 일정의 `checkedAt`를 모든 행이 새로 확인된 것처럼 올리지 않는다.

보호 범위: 기존 16개 매크로 결과·요약·계산, Home 응답, 요청 시 공급자 호출 여부, PICK/LAB, 인프라와 키 설정을 바꾸지 않는다. 새 전송 경로는 기존 정적 수집기 안에서만 사용한다.

검증: 새 동작 테스트 RED→GREEN을 확인했다. `tests/test_inflation_release_cache.py`와 기존 `tests/test_macro_pce.py`의 대상 검사 41개, release/boot bundle `--check`를 통과했다. 전체 백엔드 CI와 최종 운영 SHA 검증은 통합 PR과 root의 release 기록으로 확인한다.
