# 반도체 가격 자동 수집

## 변경 이유와 운영 계약

기존 `/api/memory-prices`와 `/api/memory-spot`은 방문 시 6시간 캐시가 만료되어야 TrendForce 공개 최신 표를 다시 읽었다. 별도 반도체 수집 예약은 없었으므로 방문하지 않는 날의 관측값 수집은 보장되지 않았다. 이번 변경은 사용자가 요청한 방문과 무관한 수집을 기존 GitHub Actions에 추가하는 새 동작이다.

`update-memory-prices.yml`은 매일 UTC 10:35와 11:35, 한국시간 19:35와 20:35에 실행하도록 설정한다. 두 번째 실행은 원문 지연이나 첫 실행 실패를 다시 확인한다. GitHub 예약 실행에는 지연이 있을 수 있으며 정확한 분 단위 실행을 보장하지 않는다. `workflow_dispatch`로 같은 작업을 수동 실행할 수 있다. 새 유료 서비스나 별도 토큰을 추가하지 않는다.

수집기는 기존 파서로 TrendForce의 공개 DRAM 및 NAND 최신 페이지 두 곳만 읽는다. `static/data/memory_prices.json`에 최신 5개 그룹과 최대 365개 원문 기준일의 이력을 함께 저장한다. 실제 공개 API에 이미 누적된 이력을 초기 자료로 보존한다. 같은 원문 날짜는 중복 없이 갱신하며 원문 날짜와 수집 시각을 구분한다. 주말이나 미갱신일에 가짜 관측 날짜를 만들지 않는다. 숫자 0과 값 없음도 구분한다.

부분 실패·불완전 표·날짜 역행 시 해당 그룹은 마지막 정상 값과 원문 날짜를 유지하고 실패 상태를 표시한다. 모든 그룹을 수집하지 못하면 파일을 교체하지 않고 작업을 실패시킨다. HBM/MCP/eMMC·UFS의 미공개 가격은 계속 제공 불가로 남긴다. GDDR 표의 공백 차이는 정규화하되 Gb와 GB는 구분한다.

데이터 커밋에는 `[skip render]`를 사용한다. 사이트는 기존 검증된 `published_data` reader의 짧은 캐시를 통해 최신 main 자료를 읽으므로 매일 재배포하지 않아도 새 데이터가 반영된다. 검증 실패나 오래된 CDN 응답은 마지막 정상 게시물로 되돌린다. 배포본에도 유효한 스냅샷을 포함한다. 공개 이력 전체를 Redis/프로세스 이력과 병합하므로 서버 재시작·빈 Redis에도 복원한다. 저장된 게시물이 전혀 없는 설치에서만 기존 지연 수집 fallback을 유지한다.

## 확인 방법

- Actions의 **Update Memory Prices** 실행 결과와 `memory_prices.json` 커밋을 확인한다.
- 수집만 검증: `python scripts/collect_memory_prices.py --check`.
- `/api/memory-prices`의 `collectionMode: scheduled`, `generatedAt`, `collectedAt`, `publicationSource`, 그룹별 `sourceDate`, 전체 `history`를 확인한다. `/api/memory-spot`도 같은 계약이다.
- 새 데이터 커밋 뒤 백엔드 배포 없이 API의 `generatedAt`이 바뀌는지 확인한다. `/health.revision`은 코드 배포 revision을 확인하는 별도 지표다.
- 원문 날짜가 그대로인 경우 수집 성공 시각만 바뀔 수 있다. 이는 새 가격 관측을 의미하지 않는다.

## 검증 및 게시 기록

로컬 전체 Python 검증은 1,354 passed / 29 skipped / 43 subtests passed이고 기존 deprecation warning 80건이 있다. 프런트 계약 52개, 메모리 전용 65개, Python 구문 및 기존 배포 번들 동기화 검사가 통과했다. 독립 검토에서 발견한 품목별 이력 날짜가 해당 그룹 기준일을 넘는 검증 누락을 재현하고 수정했다.

실제 원문 수집 CLI는 `2026-11-10T09:53:37Z`에 5개 그룹·15개 품목·21개 관측 기준일의 정상 저장을 확인했고 `--check`도 통과했다. CI, 정확한 코드 배포 revision, 실제 Actions 실행 및 재배포 없는 API 반영의 최종 영수증은 이 변경의 GitHub PR 설명에 기록한다. 향후 예약 시각의 실제 실행 여부는 해당 Actions 실행에서 확인한다.
