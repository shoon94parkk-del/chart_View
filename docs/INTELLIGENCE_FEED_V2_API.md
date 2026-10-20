# 감사 인텔리전스 피드 v2 조회 API (Read-only, opt-in)

`GET /api/intelligence/feed/v2` — 3인 독립 분석 → 감사 통과(PASS)한 PICK만
노출하는 별도 피드. v1(`GET /api/intelligence/feed`, PR #160) 엔드포인트와는
독립적이다: 별도 모듈(`intelligence_feed_v2_service.py`), 별도 환경변수,
별도 라우트, 상호 스키마 거부(schema 1 ↔ 2).

## 계약 (intel-os `docs/FEED_V2_CONTRACT.md` / intel-os PR #11)

- `schema_version: 2`, `kind: "market_research"`,
  `publication_status: "AUDITED_PICKS"` 고정.
- `picks`는 비어 있을 수 없음. 각 pick은 `audit_status == "PASS"` +
  `fact_pack_hash` + `audit_hash` 필수. 문자열 "PASS"만으로는 게시 불가
  (해시 누락 시 거부).
- `evidence_urls`는 전부 `https://`만 허용. `thesis` 200자 이내.
- 직렬화 문서 전체의 **키 이름**에 `api_key/apikey/secret/password/token/
  account_id/private_key/db_path/dsn` 포함 시 게시 거부 (값이 아니라 키 이름
  기준 — 파이프라인 유출 신호로 보고 strip이 아니라 refuse).
- `as_of`/`generated_at`은 timezone-aware, 미래 시각 거부(1분 skew 허용).
- `source`는 서버가 항상 `"three_agent_audited"`로 스탬프.

### 선택 확장 필드 (P5 — 서버 계산값만)

Toss v2 UI가 표시하는 추가 필드. 전부 선택(optional)이며, allowlist에
포함되려면 타입·범위 검증을 통과해야 한다. 검증 실패 시 문서 전체가
거부된다 (fail-closed) — 프런트는 점수·수익률을 임의 생성하지 않으며,
서버도 검증되지 않은 값을 전달하지 않는다.

| 필드 | 규칙 |
|---|---|
| `research_score` | 유한 숫자, 0~100. 발굴 단계 조사 우선도 |
| `judgment_score` | 유한 숫자, 0~100. 3인 토론·감사 통과 후 최종 판단 점수 |
| `agent_claims` | 객체. 키는 `mer`/`nonggu`/`meng`만, 각 값은 1~500자 문자열. 서버가 토론 기록에서 사전 생성한 핵심 주장 |
| `performance` | 객체. `return_pct`/`mdd_pct`/`excess_benchmark_pct` (유한 숫자), `benchmark` (≤32자), `as_of` (tz-aware ISO). 서버에서 종가 기준으로 사전 계산된 값만. 최소 1개 필드 필수 |

원천: intel-os `integration/feed_v2.py` (`docs/FEED_V2_CONTRACT.md`).
피드 파일에 실리는 확장 필드는 전부 원장(결정 원장 payload ·
`pick_performance` 스냅샷)에 기록된 서버 계산값이다.

## 서버 동작

- 입력은 `MARKET_INTELLIGENCE_FEED_V2_PATH` 환경변수(절대경로)의 로컬 파일뿐.
  미설정·상대경로·파일 없음·검증 실패 시 기본 **503**.
- 파일 크기 상한 512 KiB. 외부 fetch·DB 조회·LLM 호출 없음.
- ETag: sha256(canonical JSON) 앞 32 hex, `"..."` 인용.
  `If-None-Match` 일치 시 304. `Cache-Control: public, max-age=60`.
- Stale: `generated_at`이 `MARKET_INTELLIGENCE_FEED_V2_STALE_AFTER`(기본 6시간)
  보다 오래되면 `X-Feed-Stale: true` 헤더를 붙인다. 과거 스냅샷을 현재 분석처럼
  위장하지 않음 — `as_of`/`generated_at`은 항상 그대로 노출.
- 실패(OSError/ValueError/설정 누락 등)는 전부 503으로 통일.

## 신뢰 모델

- 원장 검증(PICK 원장 → 결정 원장 → 감사 영수증)은 intel-os 게시자
  (`integration/feed_v2.py::build_feed_v2_verified`)가 수행. 이 호스트는
  원장·DB·private repo에 접근하지 않는다.
- 서버는 문서를 allowlist로 재검증·재조립한다. 알 수 없는 필드는 제거하고,
  금지 키 이름이 하나라도 있으면 전체 문서를 거부한다.
- 운영 활성화는 별도 승인 필요. 기본 비활성(503)이 정상 상태.

## 테스트

`python -m unittest tests.test_intelligence_feed_v2 -v`
(v1/v2 분리·allowlist·미검증 PICK 거부·ETag/304·stale 표시·기본 503).
