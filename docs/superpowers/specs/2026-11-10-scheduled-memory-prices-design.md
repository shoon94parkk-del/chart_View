# 방문과 독립적인 반도체 가격 수집

사용자는 사이트를 열지 않아도 반도체 가격을 자동 수집하고 이력을 누적하기를 요청했다. 분류는 new behavior이며, 기존 예약 작업이 없는 사실을 코드·workflow·최근 schedule 실행에서 확인했다.

현재 `/api/memory-prices`·`/api/memory-spot`은 요청 시6시간 캐시가 만료됐으면 공개 최신 원문을 읽고 Redis 또는 메모리에 자체 관측을 누적한다. 새 수집은 기존 무료 GitHub Actions를 사용한다. 별도 유료 cron/서버나 새 자격증명은 만들지 않는다.

접근: 단순 API 주기 호출은 서버 수면/6시간 캐시/지속 저장에 의존한다. 예약 작업 안에서 원문을 직접 수집하고 Git JSON으로 보존하며 기존 `published_data.py` 독자를 통해 배포 없이 읽는 방식을 선택한다. 기존 API v2·두 별칭·품목/가격군·날짜/단위는 유지한다.

- 매일19:35/20:35KST(10:35/11:35UTC) 예약과 수동 실행. GitHub 지연/누락 가능성이 있어 정확한 분 실행을 보장하지 않는다.
- 공개 최신2페이지를 기존 parser/fetcher로 수집한다. 유료 이력을 역수집하지 않는다. 현재 공개 API의 기존 이력은 초기 JSON에 보존한다.
- `static/data/memory_prices.json`에 provider sourceDate별 누적과 그룹별 마지막 검증값을 저장한다. 동일 날짜는 idempotent merge, 실패/역행은 마지막 정상값 보존, 전부 실패하면 파일 변경 없이 작업 실패.
- `generatedAt`/`collectedAt`은 실제 수집 시각이고 sourceDate/updatedAt은 공급자 기준 그대로다. HBM/MCP 대체값·미수집 날짜·0값을 만들지 않는다.
- 정상 API는 기존 GitHub published reader(45초 캐시)를 통해 저장 결과를 읽는다. 공개 원문을 사용자/홈/시세 요청에 추가하지 않는다. Git/CDN 역행·장애에서 마지막 검증 publication을 보존한다. Redis가 없어도 전체 저장 이력이 복구된다.
- Git의 데이터 커밋은 `[skip render]`로 반복 백엔드 재배포를 요구하지 않는다. 최초 코드 배포는 정확한 검사 main revision을 확인한다.

검증: 수치/날짜/결측/부분 실패/전체 실패/역행/동일 날짜/재시작 보존과 remote publication→기존 API 회귀. 실제 공개 원문 수집, 예약 workflow 수동 실행·commit, 재배포 없이 API가 새 publication을 읽는지 검증한다. 미래 schedule 실행 성공은 수동 실행 성공과 구분한다.
