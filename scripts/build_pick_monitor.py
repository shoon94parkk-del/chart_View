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
DEFAULT_SCREENER = ROOT / "static/data/screener.json"

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

TECHNICAL_SIGNALS = {
    "TECH_SELL_REVIEW": {"label": "단기 매도 검토", "severity": "red"},
    "TECH_CAUTION": {"label": "단기 과열 경계", "severity": "orange"},
    "TECH_IMPROVING": {"label": "기술 흐름 개선", "severity": "green"},
    "TECH_NORMAL": {"label": "기술 중립", "severity": "neutral"},
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


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def technical_score_at_pick(row: dict[str, Any]) -> float | None:
    scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
    return _num(scores.get("technical"))


def _screener_index(payload: dict[str, Any] | None) -> tuple[str, dict[str, dict[str, Any]]]:
    payload = payload if isinstance(payload, dict) else {}
    trade_date = str(payload.get("tradeDate") or "")
    rows = {
        canonical_code(row): row
        for row in payload.get("stocks", [])
        if isinstance(row, dict) and canonical_code(row)
    }
    return trade_date, rows


def _technical_signal(day_delta: float | None, rsi: float | None, ret5: float | None, ret20: float | None) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if day_delta is not None and day_delta <= -3:
        reasons.append(f"기술점수 전일 대비 {day_delta:+.0f}점")
    if rsi is not None and rsi >= 70:
        reasons.append(f"RSI {rsi:.1f} 과열권")
    if ret5 is not None and ret5 >= 15:
        reasons.append(f"5일 수익률 {ret5:+.1f}% 급등")
    if ret20 is not None and ret20 >= 30:
        reasons.append(f"20일 수익률 {ret20:+.1f}% 급등")

    red = (
        (day_delta is not None and day_delta <= -3 and ((rsi is not None and rsi >= 70) or (ret20 is not None and ret20 >= 30) or (ret5 is not None and ret5 >= 15)))
        or ((rsi is not None and rsi >= 75) and (ret20 is not None and ret20 >= 30))
        or ((rsi is not None and rsi >= 80) and (ret20 is not None and ret20 >= 20))
    )
    caution = (
        (day_delta is not None and day_delta <= -3)
        or (rsi is not None and rsi >= 70)
        or ((day_delta is not None and day_delta < 0) and (ret20 is not None and ret20 >= 25))
    )
    improving = day_delta is not None and day_delta >= 2 and (rsi is None or rsi < 70)
    if red:
        return "TECH_SELL_REVIEW", reasons
    if caution:
        return "TECH_CAUTION", reasons
    if improving:
        return "TECH_IMPROVING", [f"기술점수 전일 대비 {day_delta:+.0f}점 개선"]
    return "TECH_NORMAL", reasons


def technical_snapshot(
    ranking_row: dict[str, Any],
    old_pick: dict[str, Any] | None,
    current_trade_date: str,
    current_row: dict[str, Any] | None,
    previous_trade_date: str,
    previous_row: dict[str, Any] | None,
) -> dict[str, Any] | None:
    old_technical = (old_pick or {}).get("technical") if isinstance((old_pick or {}).get("technical"), dict) else {}
    score_at_pick = technical_score_at_pick(ranking_row)
    if score_at_pick is None:
        score_at_pick = _num(old_technical.get("scoreAtPick"))

    current_score = _num((current_row or {}).get("technicalScore"))
    if current_score is None and current_trade_date == str(old_technical.get("tradeDate") or ""):
        current_score = _num(old_technical.get("score"))
    if current_score is None:
        current_score = score_at_pick
    if current_score is None and not old_technical:
        return None

    prior_date = ""
    prior_score: float | None = None
    if previous_row and previous_trade_date and previous_trade_date != current_trade_date:
        prior_date = previous_trade_date
        prior_score = _num(previous_row.get("technicalScore"))
    elif str(old_technical.get("tradeDate") or "") == current_trade_date:
        prior_date = str(old_technical.get("previousTradeDate") or "")
        prior_score = _num(old_technical.get("previousScore"))
    elif old_technical.get("tradeDate") and str(old_technical.get("tradeDate")) != current_trade_date:
        prior_date = str(old_technical.get("tradeDate") or "")
        prior_score = _num(old_technical.get("score"))

    day_delta = current_score - prior_score if current_score is not None and prior_score is not None else None
    rsi = _num((current_row or {}).get("rsi14"))
    ret5 = _num((current_row or {}).get("ret5"))
    ret20 = _num((current_row or {}).get("ret20"))
    change1d = _num((current_row or {}).get("change1d"))
    signal, reasons = _technical_signal(day_delta, rsi, ret5, ret20)
    meta = TECHNICAL_SIGNALS[signal]
    return {
        "tradeDate": current_trade_date or str(old_technical.get("tradeDate") or ranking_row.get("tradeDate") or ""),
        "scoreAtPick": score_at_pick,
        "score": current_score,
        "previousTradeDate": prior_date or None,
        "previousScore": prior_score,
        "dayDelta": day_delta,
        "deltaFromPick": current_score - score_at_pick if current_score is not None and score_at_pick is not None else None,
        "rsi14": rsi,
        "ret5": ret5,
        "ret20": ret20,
        "change1d": change1d,
        "signal": signal,
        "signalLabel": meta["label"],
        "severity": meta["severity"],
        "reasons": reasons,
        "advisoryOnly": True,
    }


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
    screener: dict[str, Any] | None = None,
    previous_screener: dict[str, Any] | None = None,
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
    current_trade_date, current_rows = _screener_index(screener)
    previous_trade_date, previous_rows = _screener_index(previous_screener)

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
                technical = technical_snapshot(
                    row,
                    old,
                    current_trade_date,
                    current_rows.get(fresh["code"]),
                    previous_trade_date,
                    previous_rows.get(fresh["code"]),
                )
                if technical is not None and merged.get("technical") != technical:
                    merged["technical"] = technical
                    changed = True
                picks.append(merged)
            else:
                technical = technical_snapshot(
                    row,
                    None,
                    current_trade_date,
                    current_rows.get(fresh["code"]),
                    previous_trade_date,
                    previous_rows.get(fresh["code"]),
                )
                if technical is not None:
                    fresh["technical"] = technical
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
        technical = row.get("technical") if isinstance(row.get("technical"), dict) else None
        if technical:
            signal = str(technical.get("signal") or "")
            if signal not in TECHNICAL_SIGNALS:
                errors.append(f"invalid technical signal {signal!r}: {row.get('pickId')}")
            if technical.get("advisoryOnly") is not True:
                errors.append(f"technical signal must remain advisory: {row.get('pickId')}")

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
    parser.add_argument("--screener", type=Path, default=DEFAULT_SCREENER)
    parser.add_argument("--previous-screener", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    rankings = load_json(args.rankings, {"days": []})
    monitor = load_json(args.monitor, {})
    history = load_json(args.history, {"events": []})
    screener = load_json(args.screener, {"stocks": []})
    previous_screener = load_json(args.previous_screener, {"stocks": []}) if args.previous_screener else None

    if args.check:
        errors = validate(rankings, monitor, history)
        if errors:
            raise SystemExit("\n".join(errors))
        print(f"pick monitor valid: {len(monitor.get('picks', []))} picks")
        return 0

    monitor_out, history_out, changed = sync_payloads(
        rankings,
        monitor,
        history,
        screener=screener,
        previous_screener=previous_screener,
    )
    errors = validate(rankings, monitor_out, history_out)
    if errors:
        raise SystemExit("\n".join(errors))
    dump_json(args.monitor, monitor_out)
    dump_json(args.history, history_out)
    print(f"pick monitor {'updated' if changed else 'unchanged'}: {len(monitor_out['picks'])} picks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
