import copy

from scripts.build_pick_monitor import POLICY, sync_payloads, validate


def rankings(reason="growth", price=100, monitoring=None):
    row = {
        "rank": 1,
        "code": "123456",
        "symbol": "123456.KQ",
        "name": "테스트",
        "close": price,
        "changePct": -15.0,
        "totalScore": 88,
        "grade": "사용자 확정",
        "scores": {"technical": 24},
        "reason": reason,
    }
    if monitoring is not None:
        row["monitoring"] = monitoring
    return {"updated": "2026-09-28T18:30:00+09:00", "days": [{"tradeDate": "2026-09-28", "top3": [row]}]}


def test_new_pick_is_registered_as_pending_not_sell_review():
    monitor, history, changed = sync_payloads(rankings(), {}, {"events": []}, timestamp="2026-09-28T18:40:00+09:00")
    assert changed is True
    row = monitor["picks"][0]
    assert row["status"] == "PENDING_REVIEW"
    assert row["originalThesis"]["summary"] == "growth"
    assert row["pickPrice"] == 100
    assert monitor["policy"] == POLICY
    assert history["events"][0]["eventType"] == "PICK_REGISTERED"


def test_price_drop_alone_never_changes_existing_status():
    base, history, _ = sync_payloads(rankings(price=100), {}, {"events": []}, timestamp="2026-09-28T18:40:00+09:00")
    base["picks"][0]["status"] = "KEEP"
    base["picks"][0]["statusLabel"] = "유지"
    newer = rankings(price=50)
    monitor, _, _ = sync_payloads(newer, base, history, timestamp="2026-09-29T18:40:00+09:00")
    assert monitor["picks"][0]["status"] == "KEEP"
    assert monitor["picks"][0]["pickPrice"] == 50


def test_sell_review_state_survives_baseline_sync():
    base, history, _ = sync_payloads(rankings(), {}, {"events": []}, timestamp="2026-09-28T18:40:00+09:00")
    base["picks"][0]["status"] = "SELL_REVIEW"
    base["picks"][0]["statusLabel"] = "매도검토"
    monitor, _, _ = sync_payloads(rankings(), base, history, timestamp="2026-09-29T18:40:00+09:00")
    assert monitor["picks"][0]["status"] == "SELL_REVIEW"


def test_detailed_publication_data_enriches_legacy_thesis_once():
    base, history, _ = sync_payloads(rankings(), {}, {"events": []}, timestamp="2026-09-28T18:40:00+09:00")
    detailed = rankings(monitoring={
        "summary": "HBM tester growth",
        "thesisPillars": ["customer adoption", "repeat demand"],
        "invalidationCriteria": ["customer qualification fails"],
        "catalysts": ["mass production"],
        "keyMetrics": ["HBM revenue mix"],
    })
    monitor, history2, changed = sync_payloads(detailed, base, history, timestamp="2026-09-29T18:40:00+09:00")
    assert changed is True
    assert monitor["picks"][0]["originalThesis"]["completeness"] == "detailed"
    assert sum(e["eventType"] == "THESIS_BASELINE_ENRICHED" for e in history2["events"]) == 1

    monitor2, history3, _ = sync_payloads(detailed, monitor, history2, timestamp="2026-09-30T18:40:00+09:00")
    assert sum(e["eventType"] == "THESIS_BASELINE_ENRICHED" for e in history3["events"]) == 1
    assert monitor2["picks"][0]["originalThesis"] == monitor["picks"][0]["originalThesis"]


def test_exit_requires_user_finalization():
    base, history, _ = sync_payloads(rankings(), {}, {"events": []}, timestamp="2026-09-28T18:40:00+09:00")
    bad = copy.deepcopy(base)
    bad["picks"][0]["status"] = "EXIT"
    bad["picks"][0]["decision"]["finalizedByUser"] = False
    errors = validate(rankings(), bad, history)
    assert any("EXIT without user finalization" in error for error in errors)


def _screener(trade_date, score, *, rsi=60.0, ret5=5.0, ret20=10.0):
    return {
        "tradeDate": trade_date,
        "stocks": [{
            "code": "123456",
            "symbol": "123456.KQ",
            "name": "테스트",
            "technicalScore": score,
            "rsi14": rsi,
            "ret5": ret5,
            "ret20": ret20,
            "change1d": 1.0,
        }],
    }


def test_technical_sell_signal_is_advisory_and_does_not_change_fundamental_status():
    monitor, history, _ = sync_payloads(
        rankings(),
        {},
        {"events": []},
        screener=_screener("2026-09-30", 24),
        timestamp="2026-09-30T18:40:00+09:00",
    )
    monitor["picks"][0]["status"] = "KEEP"
    monitor["picks"][0]["statusLabel"] = "유지"
    updated, _, changed = sync_payloads(
        rankings(),
        monitor,
        history,
        screener=_screener("2026-10-01", 20, rsi=74.0, ret5=18.0, ret20=35.0),
        previous_screener=_screener("2026-09-30", 24),
        timestamp="2026-10-01T18:40:00+09:00",
    )
    tech = updated["picks"][0]["technical"]
    assert changed is True
    assert updated["picks"][0]["status"] == "KEEP"
    assert tech["previousScore"] == 24
    assert tech["score"] == 20
    assert tech["dayDelta"] == -4
    assert tech["signal"] == "TECH_SELL_REVIEW"
    assert tech["severity"] == "red"
    assert tech["advisoryOnly"] is True


def test_score_drop_without_overheat_is_caution_not_red():
    monitor, history, _ = sync_payloads(
        rankings(),
        {},
        {"events": []},
        screener=_screener("2026-09-30", 24),
        timestamp="2026-09-30T18:40:00+09:00",
    )
    updated, _, _ = sync_payloads(
        rankings(),
        monitor,
        history,
        screener=_screener("2026-10-01", 20, rsi=58.0, ret5=3.0, ret20=8.0),
        previous_screener=_screener("2026-09-30", 24),
        timestamp="2026-10-01T18:40:00+09:00",
    )
    tech = updated["picks"][0]["technical"]
    assert tech["signal"] == "TECH_CAUTION"
    assert tech["severity"] == "orange"
