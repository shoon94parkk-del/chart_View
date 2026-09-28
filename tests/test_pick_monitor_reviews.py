from scripts.apply_pick_monitor_reviews import apply_reviews, derive_status, validate


def pick(status="PENDING_REVIEW"):
    return {
        "pickId": "2026-09-20:123456",
        "pickDate": "2026-09-20",
        "status": status,
        "statusLabel": "검토 대기",
        "monitor": {},
        "decision": {"finalizedByUser": status == "EXIT"},
    }


def evidence(direction="positive", materiality="supporting", key="earnings", published="2026-09-21"):
    return {
        "verified": True,
        "publishedAt": published,
        "sourceUrl": "https://example.com/source",
        "sourceTitle": "source",
        "fact": "verified fact",
        "direction": direction,
        "materiality": materiality,
        "independentKey": key,
        "category": key,
    }


def review(items, completed=True):
    return {"completed": completed, "evidence": items}


def test_completed_review_without_negative_evidence_is_keep():
    status, items = derive_status(pick(), review([evidence()]))
    assert status == "KEEP"
    assert len(items) == 1


def test_one_nonmajor_negative_signal_is_watch():
    status, _ = derive_status(pick(), review([evidence("negative", "supporting", "consensus")]))
    assert status == "WATCH"


def test_two_independent_negative_signals_are_sell_review():
    status, _ = derive_status(pick(), review([
        evidence("negative", "supporting", "orders"),
        {**evidence("negative", "supporting", "customer"), "sourceUrl": "https://example.com/other"},
    ]))
    assert status == "SELL_REVIEW"


def test_one_major_verified_fact_is_sell_review():
    status, _ = derive_status(pick(), review([evidence("negative", "major", "customer_loss")]))
    assert status == "SELL_REVIEW"


def test_pre_pick_evidence_cannot_drive_status_change():
    status, items = derive_status(pick(), review([evidence(published="2026-09-19")]))
    assert status == "PENDING_REVIEW"
    assert items == []


def test_price_only_review_without_verified_evidence_stays_pending():
    status, _ = derive_status(pick(), {"completed": True, "priceDropPct": -30, "evidence": []})
    assert status == "PENDING_REVIEW"


def test_exit_is_never_overwritten_by_review_engine():
    monitor = {"picks": [pick("EXIT")]}
    history = {"events": []}
    reviews = {"updated": "2026-09-21T18:30:00+09:00", "reviews": [{
        "pickId": "2026-09-20:123456",
        "completed": True,
        "reviewedAt": "2026-09-21T18:30:00+09:00",
        "summary": "bad",
        "evidence": [evidence("negative", "major", "customer_loss")],
    }]}
    updated, _, _ = apply_reviews(monitor, history, reviews, timestamp="2026-09-21T18:31:00+09:00")
    assert updated["picks"][0]["status"] == "EXIT"
    assert validate(updated) == []
