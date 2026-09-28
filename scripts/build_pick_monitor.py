from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RANKINGS = ROOT / "static/data/ai_daily_rankings.json"
DEFAULT_MONITOR = ROOT / "static/data/pick_monitor.json"
DEFAULT_HISTORY = ROOT / "static/data/pick_monitor_history.json"

SCHEMA_VERSION = 1
ALLOWED_STATUSES = {"PENDING_REVIEW", "KEEP", "WATCH", "SELL_REVIEW", "EXIT"}
STATUS_LABELS = {
    "PENDING_REVIEW": "검토 대기",
    "KEEP": "유지",
    "WATCH": "경계",
    "SELL_REVIEW": "매도검토",
    "EXIT": "종료",
}
POLICY = {
    "automaticExitAllowed": False,
    "userConfirmationRequiredForExit": True,
    "technicalOnlyCanTriggerSellReview": False,
    "sellReviewEvidenceRule": "one_major_fact_or_two_independent_weakening_signals",
    "priceDropAloneCanTriggerSellReview": False,
}

KST = timezone(timedelta(hours=9))


def now_kst_iso() -> str:
    return datetime.now(KST).replace(microsecond=0).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical_code(row: dict[str, Any]) -> str:
    code = str(row.get("code") or "").strip()
    if code:
        return code
    return str(row.get("symbol") or "").split(".")[0].strip()


def pick_id(trade_date: str, row: dict[str, Any]) -> str:
    return f"{trade_date}:{canonical_code(row)}"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def thesis_from_row(row: dict[str, Any]) -> dict[str, Any]:
    monitoring = row.get("monitoring") if isinstance(row.get("monitoring"), dict) else {}
    reason = str(row.get("reason") or "").strip()
    pillars = [str(x).strip() for x in _as_list(monitoring.get("thesisPillars") or monitoring.get("pillars")) if str(x).strip()]
    invalidation = [str(x).strip() for x in _as_list(monitoring.get("invalidationCriteria")) if str(x).strip()]
    catalysts = [str(x).strip() for x in _as_list(monitoring.get("catalysts")) if str(x).strip()]
    key_metrics = [str(x).strip() for x in _as_list(monitoring.get("keyMetrics")) if str(x).strip()]
    if not pillars and reason:
        pillars = [reason]
    detailed = bool(monitoring and pillars and invalidation)
    return {
        "summary": str(monitoring.get("summary") or reason),
        "pillars": pillars,
        "invalidationCriteria": invalidation,
        "catalysts": catalysts,
        "keyMetrics": key_metrics,
        "source": "publication_monitoring" if monitoring else "legacy_reason",
        "completeness": "detailed" if detailed else "legacy_baseline",
    }


def base_record(trade_date: str, row: dict[str, Any]) -> dict[str, Any]:
    status = "PENDING_REVIEW"
    return {
        "pickId": pick_id(trade_date, row),
        "code": canonical_code(row),
        "symbol": row.get("symbol"),
        "name": row.get("name"),
        "pickDate": trade_date,
        "rank": row.get("rank"),
        "pickPrice": row.get("close"),
        "changePctAtPick": row.get("changePct"),
        "scoreAtPick": row.get("totalScore"),
        "gradeAtPick": row.get("grade"),
        "originalThesis": thesis_from_row(row),
        "status": status,
        "statusLabel": STATUS_LABELS[status],
        "needsUserReview": False,
        "monitor": {
            "lastReviewedAt": None,
            "lastReviewedTradeDate": None,
            "thesisChecks": {},
            "evidence": [],
            "reason": "기존 PICK 기준선 등록 완료. 최신 팩트 검증 전 상태입니다.",
        },
        "decision": {
            "finalizedByUser": False,
            "exitDate": None,
            "exitPrice": None,
        },
    }


def _prefer_new_thesis(old: dict[str, Any], new: dict[str, Any]) -> bool:
    return old.get("completeness") != "detailed" and new.get("completeness") == "detailed"


def sync_payloads(
    rankings: dict[str, Any],
    monitor: dict[str, Any] | None = None,
    history: dict[str, Any] | None = None,
    *,
    timestamp: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    timestamp = timestamp or now_kst_iso()
    monitor = copy.deepcopy(monitor or {})
    history = copy.deepcopy(history or {})
    prior = {
        str(row.get("pickId")): row
        for row in monitor.get("picks", [])
        if isinstance(row, dict) and row.get("pickId")
    }
    events = [e for e in history.get("events", []) if isinstance(e, dict)]
    event_keys = {(e.get("eventType"), e.get("pickId")) for e in events}
    picks: list[dict[str, Any]] = []
    changed = False

    for day in rankings.get("days", []):
        trade_date = str(day.get("tradeDate") or "")
        if not trade_date:
            continue
        for row in day.get("top3", []):
            if not isinstance(row, dict):
                continue
            fresh = base_record(trade_date, row)
            pid = fresh["pickId"]
            old = prior.get(pid)
            if old:
                merged = copy.deepcopy(old)
                for key in ("code", "symbol", "name", "pickDate", "rank", "pickPrice", "changePctAtPick", "scoreAtPick", "gradeAtPick"):
                    merged[key] = fresh[key]
                if _prefer_new_thesis(merged.get("originalThesis") or {}, fresh["originalThesis"]):
                    merged["originalThesis"] = fresh["originalThesis"]
                    changed = True
                    if ("THESIS_BASELINE_ENRICHED", pid) not in event_keys:
                        events.append({
                            "eventType": "THESIS_BASELINE_ENRICHED",
                            "pickId": pid,
                            "at": timestamp,
                            "source": "ai_daily_rankings.json",
                        })
                        event_keys.add(("THESIS_BASELINE_ENRICHED", pid))
                status = str(merged.get("status") or "PENDING_REVIEW")
                if status not in ALLOWED_STATUSES:
                    status = "PENDING_REVIEW"
                    merged["status"] = status
                    changed = True
                merged["statusLabel"] = STATUS_LABELS[status]
                picks.append(merged)
            else:
                picks.append(fresh)
                changed = True
                if ("PICK_REGISTERED", pid) not in event_keys:
                    events.append({
                        "eventType": "PICK_REGISTERED",
                        "pickId": pid,
                        "at": timestamp,
                        "status": "PENDING_REVIEW",
                        "source": "ai_daily_rankings.json",
                    })
                    event_keys.add(("PICK_REGISTERED", pid))

    picks.sort(key=lambda row: (str(row.get("pickDate") or ""), int(row.get("rank") or 99), str(row.get("code") or "")))
    if len(picks) != len(prior) or [p.get("pickId") for p in picks] != [p.get("pickId") for p in monitor.get("picks", []) if isinstance(p, dict)]:
        changed = True

    generated_at = timestamp if changed or not monitor.get("generatedAt") else monitor.get("generatedAt")
    monitor_out = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "source": "static/data/ai_daily_rankings.json",
        "sourceUpdated": rankings.get("updated"),
        "policy": POLICY,
        "picks": picks,
    }
    history_out = {
        "schemaVersion": SCHEMA_VERSION,
        "updated": timestamp if changed or not history.get("updated") else history.get("updated"),
        "events": events,
    }
    return monitor_out, history_out, changed


def validate(rankings: dict[str, Any], monitor: dict[str, Any], history: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = {
        pick_id(str(day.get("tradeDate") or ""), row)
        for day in rankings.get("days", [])
        if day.get("tradeDate")
        for row in day.get("top3", [])
        if isinstance(row, dict)
    }
    actual_rows = [row for row in monitor.get("picks", []) if isinstance(row, dict)]
    actual = {str(row.get("pickId")) for row in actual_rows}
    missing = sorted(expected - actual)
    if missing:
        errors.append("missing monitor picks: " + ", ".join(missing))

    if monitor.get("policy") != POLICY:
        errors.append("monitor policy drift")

    for row in actual_rows:
        status = str(row.get("status") or "")
        if status not in ALLOWED_STATUSES:
            errors.append(f"invalid status {status!r}: {row.get('pickId')}")
        if status == "EXIT" and not (row.get("decision") or {}).get("finalizedByUser"):
            errors.append(f"EXIT without user finalization: {row.get('pickId')}")
        thesis = row.get("originalThesis") or {}
        if not thesis.get("summary") and not thesis.get("pillars"):
            errors.append(f"missing thesis baseline: {row.get('pickId')}")

    seen: set[tuple[Any, Any]] = set()
    for event in history.get("events", []):
        key = (event.get("eventType"), event.get("pickId"))
        if key in seen and event.get("eventType") in {"PICK_REGISTERED", "THESIS_BASELINE_ENRICHED"}:
            errors.append(f"duplicate history event: {key}")
        seen.add(key)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize PICK monitoring baseline from published Chart View PICK history.")
    parser.add_argument("--rankings", type=Path, default=DEFAULT_RANKINGS)
    parser.add_argument("--monitor", type=Path, default=DEFAULT_MONITOR)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    rankings = load_json(args.rankings, {"days": []})
    monitor = load_json(args.monitor, {})
    history = load_json(args.history, {"events": []})

    if args.check:
        errors = validate(rankings, monitor, history)
        if errors:
            raise SystemExit("\n".join(errors))
        print(f"pick monitor valid: {len(monitor.get('picks', []))} picks")
        return 0

    monitor_out, history_out, changed = sync_payloads(rankings, monitor, history)
    errors = validate(rankings, monitor_out, history_out)
    if errors:
        raise SystemExit("\n".join(errors))
    dump_json(args.monitor, monitor_out)
    dump_json(args.history, history_out)
    print(f"pick monitor {'updated' if changed else 'unchanged'}: {len(monitor_out['picks'])} picks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
