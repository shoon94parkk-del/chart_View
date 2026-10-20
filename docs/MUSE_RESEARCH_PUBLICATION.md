# Muse → Chart View Toss 공개 연구 연동

2026-10-20. 종목별 연구 요약을 공개 게시하면 Toss `/debates/`가 재배포 없이 읽는다. 감사 PICK v2 등록·추천 원장·실제 매매와는 별도다. 분석은 Muse가 실행하며 조회나 CI가 LLM을 실행하지 않는다.

## Muse가 해야 할 일

1. 현재 분석 작업이 끝나면 세 에이전트의 **공개 가능한 주장·근거 요약**을 내보낸다. 비공개 원문, 내부 추론, 보유 목록이라는 표시, 수량·평단·계좌·개인 메모를 복사하지 않는다. 티커는 일반 종목 연구의 식별자로만 사용한다.
2. 기존 `tools/export_debates.py`의 승인 manifest와 공개 projection을 사용한다. 이 exporter는 intel-os PR12 기반이며 [호환 PR16](https://github.com/shoon94parkk-del/investment-intelligence-os/pull/16)에 새 선택 필드·3인 완료·안전한 records/shadow 경로·직접 게시 옵션을 구현했다. Muse는 두 기반을 현재 실행 브랜치에 통합해야 한다. 이 서버/앱은 private repo를 읽거나 다운로드하지 않는다.
3. 종목별 `summary`와 `updated_at`을 채운다. 새 자동 게시에서는 두 필드가 필수다. 완료는 mer/nonggu/meng의 phase1 세 개와 attack/rebuttal/final을 모두 기록했을 때만 `COMPLETED`로 쓴다. 진행 중 공개 자료는 `PARTIAL`, 중단은 `BLOCKED`다. 완료·게시 검증이 감사 승인이나 PICK을 뜻하지 않아 `audit_verified`는 false다.
4. 실제 분석 기준일은 `date`, 결과 수정 시각은 `updated_at`, 내보낸 시각은 `generated_at`으로 구분한다. 시간은 Z 또는 +09:00 같은 시간대를 포함하고 updated_at <= generated_at이어야 한다. 동일 id를 수정할 때 updated_at이 기존 결과보다 실제로 늦어야 한다.
5. 아래 검증/게시 명령을 분석 완료 후 실행한다. GitHub 기존 `gh` 인증과 대상 workflow 실행 권한이 필요하다. 새 키를 채팅/문서/JSON에 넣지 않는다. CLI는 시스템 로캘에 관계없이 JSON stdin을 UTF-8로 보낸다.

## JSON 계약

기존 schema1 `debate_archive`를 유지한다. legacy 기록은 선택 필드 없이 읽지만 새 게시 도구는 summary/updated_at을 요구한다. 다음은 형식 설명이며 실제 결과로 게시할 샘플이 아니다.

```json
{
  "schema_version": 1,
  "kind": "debate_archive",
  "publication_status": "EXPLICITLY_APPROVED",
  "generated_at": "2026-10-20T16:00:00+09:00",
  "debates": [{
    "id": "research-000000",
    "ticker": "000000",
    "company": "공개 연구 기업명",
    "date": "2026-10-20",
    "topic": "종목별 사업·가치·위험 검토",
    "summary": "뮤즈가 작성한 핵심 판단과 남은 불확실성. 최대 600자.",
    "updated_at": "2026-10-20T15:59:00+09:00",
    "status": "PARTIAL",
    "verdict": "UNKNOWN",
    "audit_verified": false,
    "phases": [{
      "role": "mer",
      "stage": "phase1",
      "title": "독립 분석 공개 요약",
      "text": "공개 가능한 주장·근거·한계 요약",
      "source_path": "records/debates/example/mer.md"
    }]
  }]
}
```

- 같은 종목의 현재 결과는 research-005930 같은 고정 id를 재사용하고 실제 date/updated_at으로 갱신한다. 의도한 별도 과거 기록만 새 id를 쓴다. private 원본 이력은 게시 아카이브와 분리해 유지한다.
- id: 영문/숫자/밑줄/하이픈3–80자. ticker: 영대문자/숫자/점/하이픈/^1–18자. company1–100자, topic최대240자.
- status: COMPLETED/PARTIAL/BLOCKED. verdict: BUY/HOLD/WAIT/SELL/UNKNOWN. HOLD는 연구의 유지 판단이며 WAIT와 구분한다. 현재 매매 지시가 아니라 해당 연구의 기록상 판단이다.
- role: mer/nonggu/meng/other. stage: phase1/attack/rebuttal/final/audit/context.
- phase: title1–160자, text1–16,000자. source_path는 records/debates 또는 records/shadow 아래 .md 경로이며 링크나 원문 다운로드 권한이 아니다. 새 게시물은 Toss와 동일한 ASCII 영문/숫자/밑줄/점/하이픈/슬래시,260자 미만, 연속된 .. 없음 규칙을 따른다.
- 입력/누적 아카이브 최대30건, 종목당24phase, 전체4MiB. 초과 시 기존 결과를 삭제하지 않고 게시를 거절한다. 역사 보관/페이지 분리는 후속 작업이다.
- 게시 전에 모든 문자열과 키의 개인정보/비밀 패턴을 검사하고 출력은 allowlist로 재구성한다. 패턴 검사는 의미상 개인정보를 완전히 판별하지 못하므로 공개용 작성·검토를 대체하지 않는다.

## 실제 명령

공유 저장소 `shoon94parkk-del/chart_View`의 최신 main에서, FastAPI 의존성이 있는 Python 환경을 사용한다. 입력은 이미 검토한 **공개 projection 파일**이다.

```bash
python -m scripts.dispatch_debate_publication --archive /local/public-debates.json --check
python -m scripts.dispatch_debate_publication --archive /local/public-debates.json
```

선택: 실제 운영 집계도 준비되면 `--shadow /local/public-shadow.json`을 함께 넣는다. `NOT_STARTED`는 실제 프로세스가 안 돈다는 판정이 아니라 정기 로그 미연결 상태다. 스모크 실행은 정기14일 집계와 분리한다. 타임스탬프/횟수를 추정해서 채우지 않는다.

위 명령은 검증 후 `Publish approved intelligence summaries` workflow를 main에서 실행한다. workflow는 동일 입력 재실행 시 무변경이고, 최신 main에 종목 id별로 병합한 뒤 fast-forward push한다. 충돌 시 최신 main에서 재검증·재병합하며, 오래된 동일 id나 상충하는 동일 시각 결과는 거절한다. workflow 실행 성공과 원격 JSON 게시를 확인한 뒤 게시 완료로 기록한다.

GitHub dispatch는 인코딩한 전체 inputs를60KB 이하로 제한한다. 초과하면 공개 요약을 줄이거나 다음 **검토된 git 게시** 경로를 사용한다. 4MiB를 dispatch로 보내려 하지 않는다.

```bash
python -m scripts.publish_debate_archive --archive /local/public-debates.json --check
python -m scripts.publish_debate_archive --archive /local/public-debates.json
git add static/data/intelligence_debates_public.json
git commit -m 'data: publish approved three-agent research'
git push
```

다른 데이터와 충돌하면 최신 main을 받아 같은 입력을 다시 병합·검증한다. 강제 push하지 않는다. 기존 review/branch 보호 규칙은 유지한다.

## 앱과 서버가 제공하는 부분

- 공개 URL: `https://raw.githubusercontent.com/shoon94parkk-del/chart_View/main/static/data/intelligence_debates_public.json`
- 서버: `GET /api/published-data/intelligence_debates_public.json`; Shadow는 같은 경로의 `intelligence_shadow_status.json`.
- 기존 `/api/intelligence/debates`와 `/api/intelligence/shadow/status`의 운영자 지정 local-file gate는 그대로다. 이 연결은 별도의 검증된 공개 파일 경로를 사용한다.
- 화면을 열면 bootstrap을 보여주고 독립 게시물을 확인한다. 열린/보이는 동안60초마다, 수동 갱신과 화면 복귀 시 재확인한다. workflow·네트워크·GitHub CDN 지연이 더해지므로 분석 완료 시각부터60초 이내 보장을 뜻하지 않는다.
- 최신 정상 결과는 오래된 CDN/배포 fallback으로 되돌리지 않는다. 자료 기준일·게시 시각·확인 지연을 구분하며, 상세 토론은 사용자가 펼쳐서 본다.
- 개인 보유 목록과 서버 인증 연동은 없다. 기존 Toss 익명키는 기기 저장 분리용이므로 비공개 서버 접근 권한으로 사용하지 않는다.

## 아직 Muse가 채울 것

실제 보유 종목별 공개용 분석 결과, 요약, 분석 기준일/수정 시각, 공개 검토 manifest, 완료 상태와 최종 판단, 실제 Shadow 운영 로그. 이 구현은 분석을 가짜로 채우거나 새 분석이 이미 끝났다고 표시하지 않는다. 개인에게만 보이는 전체 포트폴리오 보고서는 별도의 서버 인증/비공개 저장 설계가 필요하다.

## 2026-10-20 구현 검증

- 새 검증/게시/역행 방지/입력 경계는 RED 실패를 먼저 확인하고 수정했다. 대상34개와29subtests 통과.
- 의존성이 없는 기본 Python으로 전체 검사를 시작한 첫 시도는43개 import 수집 오류였다. 테스트 의존성을 갖춘 uv Python3.11에서 다시 실행하여 **1,130개와43subtests 통과**, 기존 경고5개를 확인했다. 별도 Web Node21개와 생성 번들 최신성 검사도 통과했다.
- 독립 검토의 대기열 누락·자유문 비밀/계좌 표시·clock-skew 동일 revision 문제를 수정했다. `queue: max`는 현재 GitHub 공식 문서에서 확인했으며 최대100개 대기 한도다. 게시 timestamp는 기존보다 최소1ms 증가한다.
- 위는 구현 및 로컬 검증이며, main CI/실제 workflow/운영 배포 증거는 후속 기록에서 확정한다. 기존 공개 seed 외에 실제 새 종목 분석을 게시하지 않았다.

## Muse 한 명령 게시 옵션

PR12와 호환 PR16을 실행 브랜치에 통합하면 Backend clone 없이 다음을 호출할 수 있다. 기본 export는 로컬만 저장하며, 아래 선택 옵션이 있을 때만 공개 workflow를 요청한다. 실제 공개 요약/manifest 검토와 완료 후 호출은 Muse 쪽 작업이다.

```bash
python -m tools.export_debates --manifest /local/approved-manifest.json --out /local/public-debates.json --owner-approved --publish-chartview
```

Producer의 원격 검사는 계정 환경 제약으로 실행하지 못한 상태이며 상세는 비공개 PR16에 기록했다. 로컬24개 대상 검사와 전체1,011개 실행(기존 live E2E skip1개), 독립 검토는 확인했다. 활성 Muse 실행 환경이나 스케줄을 이 서버 작업이 바꾸지 않았다.

추가 검증에서는 UTF-8 stdin과 Toss 비호환 경로의4건 실패를 먼저 재현했고, 수정 후 Python3.11 전체1,133개·43subtests가 통과했다. 생성 Web bundle 최신성과 독립 검토도 확인했다. main 통합·정확한 운영 revision은 별도로 대조한다.
