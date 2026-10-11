# 2026-10-11 백엔드 성능 점검 — 거장 근거 캐시

- 프로젝트: `github:shoon94parkk-del/chart_View`
- 측정 기준 커밋: `fcf8038b4d12c01de8447ebc34d79955240c52ab`
- 작업 브랜치: `perf/guru-cache-20261011`
- 분류: 기존 근거 조회 경로에서 새로 확인한 성능 버그. 공급자·시세·선정 규칙 변경 없음.

## 확인한 병목과 변경

`guru_service.py`는 evidence 파일의 경로·`mtime_ns`·크기·inode를 캐시 키로 사용한다. 그런데 요청의 `version`이 캐시의 `snapshotVersion`과 다르면, 파일이 같아도 잠금 안에서 전체 파일을 다시 읽고 JSON을 파싱했다. 따라서 이미 게시가 끝난 과거 버전이나 게시 시차로 인한 정상적인 409 요청이 반복될 때에도 같은 파싱 비용이 발생했다.

측정에 사용한 `guru_evidence.json`은 4,141,596바이트이고 snapshotVersion은 `f02782944aae036e73e1`이다. 기존 파일 키가 달라졌을 때만 다시 읽도록 조건 하나를 수정했다. 요청 버전과 게시 버전의 비교는 캐시 조회 후 그대로 수행한다. 기존 잠금과 파일 변경 감지는 유지하며 다른 캐시나 제공처 경로를 추가하지 않는다.

정상 버전은 같은 근거를 반환하고, 과거 버전은 기존 `409 / snapshot_changed / currentVersion`을 유지한다. 근거 없는 종목 404, 파일을 사용할 수 없을 때 503, 유효하지 않은 티커 400도 유지한다. 같은 크기·수정시각으로 원자 교체된 파일은 inode로 감지하며, 같은 snapshotVersion 안에서 파일이 바뀌어도 다시 읽는다.

## 공급자 없는 로컬 전후 측정

CPython 3.12.14에서 저장된 실제 evidence와 직접 handler 호출로 측정했다. 정상 버전으로 한 번 캐시를 준비한 뒤 정상 버전 5회, 과거 버전 5회를 순차 호출하고 `Path.read_text` 횟수를 센 동일 harness 결과다. `main` 앱·startup을 실행하거나 HTTP·제공처를 호출하지 않았다. 아래 시간은 로컬 처리 비용이며 운영 응답 시간이나 브라우저 속도 개선을 뜻하지 않는다.

| 경로 | 이전 중앙값 | 변경 후 중앙값 | 5회 요청의 이전/이후 파일 읽기 |
|---|---:|---:|---:|
| 정상 버전 warm 조회 | 0.003ms | 0.002ms | 0 / 0 |
| 과거 버전 409 | 35.047ms | 0.003ms | 5 / 0 |

개별 5회 값·측정 방법·프로젝트·기준 SHA는 [이전 증거](audits/2026-10-11-performance/guru-cache-before.json)와 [변경 후 증거](audits/2026-10-11-performance/guru-cache-after.json)에 보존한다. 검증 목적은 실행 시간 임계값이 아니라 변경 없는 파일의 반복 파싱이 제거됐다는 점이다.

다른 작은 오프라인 점검에서 Home bootstrap은 5회 중앙값 0.344ms, Home insights는 cold 30.515ms / warm 2.247ms였다. Toss 소스에서 `homeInsights`는 실제 호출을 찾지 못했다. Bootstrap 캐시를 새로 추가하거나 현재 시세 캐시의 신선도를 낮출 근거로 사용하지 않는다. 기존 gzip 설정의 screener 파일은 2,115,922바이트에서 376,043바이트로 줄어 압축이 이미 적용되어 있음을 확인했다.

## 회귀 검증

`tests/test_guru_service.py`에 다음 4개 실행 케이스를 추가했다.

- 캐시가 비어 있을 때 과거 버전을 반복 요청해도 파일은 한 번만 읽고 올바른 409를 유지한다.
- 정상 버전으로 캐시를 준비한 뒤 다른 과거 버전을 반복해도 재읽기 없이 올바른 409를 유지한다.
- 크기·수정시각이 같은 파일 원자 교체를 inode로 감지해 새 버전 근거를 반환하고 이전 버전에는 새 currentVersion을 알린다.
- 같은 snapshotVersion의 파일 내용 갱신을 감지해 새 근거를 반환한다.

코드 변경 전 새 반복 조회 케이스 2개가 실패했고 전체 대상은 8통과/2실패였다. 변경 후 기존 제공처 없는 조회·400/404/409/503·파일 교체 검사와 함께 10개가 0.18초에 통과했다. `git diff --check`도 통과했다. 실행 환경은 `/workspace/scratch/backend-perf/venv`이며 기존 라이브러리를 공유하고 pytest와 requests를 설치했다.

## 메모리 관측의 해석

Render 사건 `evt-db5hcvu8bjmc7397b4kg`은 **2026-10-11T04:54:23.700278Z**에 이전 인스턴스 `srv-dao4a50473hc73bclej0-f8m6f`가 `oomKilled`로 종료되었고 `memoryLimit`이 **512Mi**였음을 확인한다. 원문 사건 증거는 Toss 성능 감사의 `render-deploy-event-before.json`에 보존한다. 이는 실제 OOM 종료 기록이며, 아래 95.4% 메모리 관측은 다른 인스턴스에서 수집한 값이다. 같은 과정이나 같은 원인으로 단정하지 않는다.

별도 운영 기준 측정에서 Render 메모리는 512,344,060 / 536,870,900바이트(약 95.4%)였고, startup 약 333MB에서 15분 뒤 약 498MB 이상으로 증가한 관측이 있었다. 이 관측은 파싱 버그의 원인을 입증하지 않는다. 같은 파일의 재파싱 제거가 전체 증가량을 해결했다고 주장하지 않는다.

정적 구조 점검에서 evidence의 CPython 객체 그래프는 약 17.119MiB였다. 기존 재파싱은 이전 객체를 보유한 채 새 객체를 만들어 잠금 대기와 임시 할당을 유발할 수 있다. 이는 코드에서 확인한 반복 할당 구조이며 운영 메모리 증가량과의 인과관계는 미확인이다. 비교·시세·밸류에이션 메모리 캐시는 이미 각각 64/256/256개로 제한되어 있고 Home은 단일 교체 스냅샷을 사용한다. 메모리 점검 결과를 이유로 유효한 캐시나 SWR·시세 신선도 보호를 제거하지 않는다.

후속 관측 대상으로는 64개 제한 안에서도 `max`/10년/사용자 기간의 전체 관측점을 보관하는 compare 캐시, 만료된 미재방문 키를 지우지 않는 뉴스·관계·밴드·컨센서스·DART 캐시, thread/provider parser의 임시 할당이 있다. 비교 캐시의 합계 관측점·실제 키 개수·작업 시점과 메모리 값을 확인해야 원인 판단이 가능하다. 큰 `guru_financials.json`/`guru_market.json` 파일은 점검한 운영 요청 진입점에서 로드하지 않으므로 파일 크기만으로 원인을 주장하지 않는다. 이번 수정에는 캐시 축소·차트 관측점 삭제·executor 재설계를 포함하지 않는다.

## 전체 검증 및 배포 상태

운영 브라우저 성능 전후 측정이 끝났고 Python 3.11.17 전용 환경에서 전체 백엔드 suite 및 기존 Node·bundle·문법·데이터 계약 검증을 완료했다. 실제 개수와 실행 환경은 아래 최종 로컬 검증 기록에 있다. 최종 main CI와 해당 revision의 운영 배포/API 검증은 남아 있다. 생성된 Web 자산은 변경하지 않았다.

현재 설치된 Python 3.11.17 전용 환경에서 전체 검증을 재현하는 명령은 다음과 같다. 초기 전후 microbenchmark의 Python 3.12.14 환경과 전체 correctness 검증 환경은 구분한다.

```bash
uv pip install --python /workspace/scratch/backend-perf/venv311/bin/python -r requirements.txt pytest httpx yfinance
/workspace/scratch/backend-perf/venv311/bin/python -m pytest -q
/workspace/scratch/backend-perf/venv311/bin/python scripts/build_frontend_bundle.py --check
/workspace/scratch/backend-perf/venv311/bin/python scripts/build_boot_bundle.py --check
```

최종 완료에는 정확한 tested main SHA, 기존 CI, 해당 revision의 운영 `/health`, 같은 버전 실제 후보 근거 200 및 비현재 버전 409 검증이 필요하다. 새 LLM API·키·유료 인프라·서비스·배포 훅은 추가하지 않았다.

## 2026-10-11 최종 로컬 검증

운영 브라우저 성능 전후 측정이 끝난 뒤 Python 3.11.17을 설치하고 `/workspace/scratch/backend-perf/venv311`에 CI와 동일한 `requirements.txt` + pytest/httpx/yfinance를 설치했다. Node는 v24.19.0이다. 버전별 의존성 목록은 session 증거 `dependencies311.txt`에 보존했으며 기존 키·proxy 설정을 변경하지 않았다.

- Python 전체 suite: **718개 통과**, 11.96초. 실패 0개이며 기존 라이브러리/API 사용에 관한 deprecation 경고 5개가 있었다.
- `.github/workflows/app-check.yml`의 기존 6개 Node 계약 파일: **52개 통과**, 실패 0개.
- `build_frontend_bundle.py --check`, `build_boot_bundle.py --check`: 통과.
- 기존 CI 대상 Python 문법 및 모든 `static/js/*.js` Node 문법 검사: 통과.
- 기존 workflow의 Static cache shape 검사: **2,501종목 / 56컨센서스**, JYP 종목·주요 forward PER·16개 macro 구조 검사 통과.
- 기존 workflow의 App UX and market invariants 및 `git diff --check`: 통과.

전체 suite가 만든 미추적 `news_summary_cache.json`은 테스트 전 존재하지 않았으므로 session 증거 디렉터리로 이동했고 배포 변경에 포함하지 않는다. 원자료·정기 데이터 캐시를 재생성하지 않았다. 원본 검증 로그는 session의 `full-pytest311.txt`, `node-contracts.txt`, `static-cache-shape.txt`, `app-ux-market-invariants.txt`에 보존한다.

이 추가 기록은 로컬 검증 완료다. 최종 main CI 및 exact-revision 운영 배포/API 검증은 별도 게시 단계로 남아 있다.
