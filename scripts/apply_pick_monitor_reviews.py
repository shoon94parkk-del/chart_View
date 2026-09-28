from __future__ import annotations

import argparse
import copy
import json
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MONITOR = ROOT / "static/data/pick_monitor.json"
DEFAULT_HISTORY = ROOT / "static/data/pick_monitor_history.json"
DEFAULT_REVIEWS = ROOT / "static/data/pick_monitor_reviews.json"

KST = timezone(timedelta(hours=9))
STATUS_LABELS = {
    "PENDING_REVIEW": "검토 대기",
    "KEEP": "유지",
    "WATCH": "경계",
    "SELL_REVIEW": "매도검토",
    "EXIT": "종료",
}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_kst_iso() -> str:
    return datetime.now(KST).replace(microsecond=0).isoformat()


def parse_day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def valid_post_pick_evidence(pick: dict[str, Any], review: dict[str, Any]) -> list[dict[str, Any]]:
    pick_day = parse_day(pick.get("pickDate"))
    result = []
    for item in review.get("evidence", []):
        if not isinstance(item, dict) or item.get("verified") is not True:
            continue
        published = parse_day(item.get("publishedAt"))
        if pick_day and published and published < pick_day:
            continue
        if not item.get("sourceUrl") or not item.get("fact"):
            continue
        result.append(copy.deepcopy(item))
    return result


def derive_status(pick: dict[str, Any], review: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    if pick.get("status") == "EXIT":
        return "EXIT", []
    evidence = valid_post_pick_evidence(pick, review)
    if review.get("completed") is not True or not evidence:
        return "PENDING_REVIEW", evidence

    negative = [item for item in evidence if item.get("direction") == "negative"]
    major = [item for item in negative if item.get("materiality") == "major"]
    independent = {
        str(item.get("independentKey") or item.get("category") or item.get("sourceUrl"))
        for item in negative
    }
    if major or len(independent) >= 2:
        return "SELL_REVIEW", evidence
    if negative:
        return "WATCH", evidence
    return "KEEP", evidence


def apply_reviews(
    monitor: dict[str, Any],
    history: dict[str, Any],
    reviews: dict[str, Any],
    *,
    timestamp: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    timestamp = timestamp or now_kst_iso()
    monitor_out = copy.deepcopy(monitor)
    history_out = copy.deepcopy(history)
    review_map = {
        str(row.get("pickId")): row
        for row in reviews.get("reviews", [])
        if isinstance(row, dict) and row.get("pickId")
    }
    events = [e for e in history_out.get("events", []) if isinstance(e, dict)]
    changed = False

    for pick in monitor_out.get("picks", []):
        if not isinstance(pick, dict):
            continue
        review = review_map.get(str(pick.get("pickId")))
        if not review:
            continue
        previous = str(pick.get("status") or "PENDING_REVIEW")
        status, evidence = derive_status(pick, review)
        if previous == "EXIT":
            status = "EXIT"

        review_key = str(review.get("reviewedAt") or reviews.get("updated") or timestamp)
        existing_key = str((pick.get("monitor") or {}).get("reviewKey") or "")
        if status == previous and review_key == existing_key:
            continue

        pick["status"] = status
        pick["statusLabel"] = STATUS_LABELS[status]
        pick["needsUserReview"] = status == "SELL_REVIEW"
        pick["monitor"] = {
            **(pick.get("monitor") or {}),
            "lastReviewedAt": review.get("reviewedAt") or reviews.get("updated") or timestamp,
            "lastReviewedTradeDate": review.get("reviewTradeDate"),
            "reviewKey": review_key,
            "thesisChecks": review.get("thesisChecks") or {},
            "evidence": evidence,
            "reason": review.get("summary") or "최신 근거를 기준으로 투자논리를 재점검했습니다.",
        }
        if status != previous:
            events.append({
                "eventType": "STATUS_CHANGED",
                "pickId": pick.get("pickId"),
                "at": timestamp,
                "from": previous,
                "to": status,
                "reviewKey": review_key,
                "reason": pick["monitor"]["reason"],
            })
        else:
            events.append({
                "eventType": "REVIEW_REFRESHED",
                "pickId": pick.get("pickId"),
                "at": timestamp,
                "status": status,
                "reviewKey": review_key,
            })
        changed = True

    if changed:
        monitor_out["generatedAt"] = timestamp
        monitor_out["reviewSourceUpdated"] = reviews.get("updated")
        history_out["updated"] = timestamp
        history_out["events"] = events
    return monitor_out, history_out, changed


def validate(monitor: dict[str, Any]) -> list[str]:
    errors = []
    for pick in monitor.get("picks", []):
        if not isinstance(pick, dict):
            continue
        status = pick.get("status")
        if status not in STATUS_LABELS:
            errors.append(f"invalid status: {pick.get('pickId')}={status}")
        if status == "EXIT" and not (pick.get("decision") or {}).get("finalizedByUser"):
            errors.append(f"EXIT without user confirmation: {pick.get('pickId')}")
        if status == "SELL_REVIEW":
            evidence = (pick.get("monitor") or {}).get("evidence") or []
            negatives = [item for item in evidence if item.get("direction") == "negative"]
            major = any(item.get("materiality") == "major" for item in negatives)
            independent = {
                str(item.get("independentKey") or item.get("category") or item.get("sourceUrl"))
                for item in negatives
            }
            if not major and len(independent) < 2:
                errors.append(f"SELL_REVIEW lacks required evidence: {pick.get('pickId')}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply verified research evidence to Chart View PICK monitoring state.")
    parser.add_argument("--monitor", type=Path, default=DEFAULT_MONITOR)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    monitor = load_json(args.monitor, {"picks": []})
    history = load_json(args.history, {"events": []})
    reviews = load_json(args.reviews, {"reviews": []})

    if args.check:
        errors = validate(monitor)
        if errors:
            raise SystemExit("\n".join(errors))
        print(f"pick review state valid: {len(monitor.get('picks', []))} picks")
        return 0

    monitor_out, history_out, changed = apply_reviews(monitor, history, reviews)
    errors = validate(monitor_out)
    if errors:
        raise SystemExit("\n".join(errors))
    dump_json(args.monitor, monitor_out)
    dump_json(args.history, history_out)
    print(f"pick reviews {'applied' if changed else 'unchanged'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
