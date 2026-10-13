# 2026-10-13 Home 지수·시세 대기 개선

완료한 canonical 시세를 기존 Home/market cache에 종목별로 먼저 게시하고, 일반 cold 지수 요청을 최대2초 후 실제 확보된 행·진행 상태로 반환한다. 초기 Home HTML transport가 무한 대기하거나 fallback으로 새 대기 예산을 얻는 문제는 별도 Toss 저장소에서5초 단일 deadline으로 수정한다. 새 API/provider/cache/worker pool/키/유료 서비스는 없다.

## 범위와 운영 관찰

관찰 당시 운영 main.py는 `9824a49e0e8410c35e8bf60880d623f38c4e1f97`, 구현 시작 main은 `71cb721375c4598b60897e12d0db04f5a2440fa7`이다. 두 main.py는 동일하다. 작업 중 사용자가 게시한 TOP10 UI/데이터 변경을 포함한 `fca5ee86d498334477a7ebf138943ea6d5dc3398`로 fast-forward했고, 해당 main.py도 동일했다. 이번 runtime 수정은 main.py뿐이며 Web UI/데이터 업데이트를 덮어쓰지 않는다.

사용자는 지수 표시까지20초를 관찰했다. 후속 운영 ordinary API는353ms, 최근 재시작/실패 이벤트0건이었다. Access log에는 요청 시작/handler 시간이 없어 그 사건의 정확한 큐·공급자·네트워크 원인은 확정할 수 없다. 과거의 정상 warm 샘플로 사용자의 지연을 부정하거나 제어 실험을 실제 사건의 원인 증명으로 제시하지 않는다.

기존 cold handler는 기본4개와 보조4개를 pool2에서 모두 기다린다. 각 공급자 fallback이 순차 timeout을 가질 수 있어 한 항목이 지연되면 이미 준비된 기본 지수도 반환하지 못했다. Home-live gather도 전체 완료 전에 빠른 개별 성공을 cache에 공개하지 않았다.

## 계약 보존

- 기존 canonical provider와 BACKGROUND2/BULK1, 정상 quote worker 수, 호출 횟수·TTL·startup warm을 유지한다.
- Home-live/market 각 coroutine의 완료 결과를 event loop에서 기존 cache에 먼저 게시한다. Gather/lock이 전체 cycle과 완료 상태를 소유하며 worker callback이 cache를 직접 바꾸지 않는다.
- 종목별 성공 완료 epoch를 사용한다. 원자료 `asOf/sessionDate/source`는 그대로이며 실패/invalid/older 응답은 새로운 가격이나 freshness가 되지 않는다. Foreground에서 받은 더 최신 관측이 늦은 background 응답보다 우선한다.
- Market cache의 transient task/Event가 동일 owner를 공유한다. 일반 cold 요청은 primary4개 terminal 또는2초까지 기다리고 실제 준비된 행/진행 상태를 반환한다. 다음 progress read는 기다리지 않는다. Pending ticker는 확정 errors로 합성하지 않는다.
- `fresh=true`는 같은 owner의8개 완료를 shield-await한다. Caller cancellation은 shared owner를 취소하지 않는다. 실제 owner cancel, 첫 turn 전 cancel 및 후속 owner와 이전 finally 경합을 보호한다.
- 전체 batch timestamp는8개 terminal 뒤에만 갱신한다. 완료 clock이 없는 progress의 `cacheAgeSec`는null이다. Pending partial/empty는 `Cache-Control:no-store`; 기존 full warm/SWR header는 유지한다.
- `/api/quotes`의 max20/full JSON/fresh canonical await 계약은 그대로다. 한 missing ticker가 해당 batch를 기다리게 할 수 있으므로 모든 관심종목 완료의2초 SLA는 아니다.
- 고정 `Server-Timing: market-ready;dur=…, market-handler;dur=…`로 일반 HTTP의 준비 대기와 처리시간을 구분한다. 개인 정보나 ticker를 header에 넣지 않는다.

## 전후 증거

[같은 HTTP harness 결과](audits/2026-10-13-home-data-wait/controlled-http.json): 실제 handler/cache AST를 base/current에서 추출하고 startup 없는 isolated FastAPI route를 ASGI HTTP로 호출했다. Fake provider 한 항목20초, 나머지3ms; 각 독립 instance pool2/호출8회는 동일하다.

| 20초 지연 항목 | 일반 첫 HTTP 이전 → 이후 | 이후 실제 준비된 primary |
|---|---:|---:|
| VIX 보조 | 20,092 → 61ms | 4개 |
| KOSPI 기본 | 20,069 → 2,003ms | 3개 |

8개 최종 완료는 모두 약20초로 유지된다. 네트워크·실제 공급자 SLA나 실제 사건의 원인 확정은 아니다. JSON source hash는 동결 main.py를 구분하며 repo 전체 SHA를 대신하지 않는다. 재현: `python docs/audits/2026-10-13-home-data-wait/controlled_market_wait.py --output /tmp/home-data-wait` (약80초, 외부 공급자 호출 없음). 명시 fresh 재시도는 full8 owner/기존5초 guard를 따르므로 즉시 공급자 재조회 보장은 없다.

변경 전 신규 회귀의 per-row12실패/7통과, cold2실패/1통과, bounded/pending3실패/6통과를 확인했다. 집중80개 통과. 최신 fca5ee8 위 동결 runtime에서 Python3.11.17 전체748개, Node 데이터 계약52개, Python/Web JS syntax, CI의 static cache shape 및 App UX/market invariants가 통과했다. 기존 deprecation warning5개는 숨기지 않는다.

PR CI와 정확한 main 운영 revision, 배포 뒤 실제 API/기존 운영 UI 검증은 별도 공개 기록으로 남긴다. Heatmap 불필요한 preload/스냅샷 게시, Consensus failure cooldown/큐 개선은 이번에 섞지 않는다.
