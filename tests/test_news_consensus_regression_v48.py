from __future__ import annotations

import time

import consensus_service as consensus
from news_summary_service import _finance_korean_fallback


def test_news_fallback_keeps_funding_meaning_and_amount():
    text = (
        "Nscale’s reported pursuit of about $3.5 billion in pre-IPO financing matters to more than its prospective shareholders. "
        "Dell Technologies Inc. and Nokia Oyj already have commercial and investment ties to the AI infrastructure company. "
        "Better funding could help their customer execute, but it would not automatically become either supplier’s revenue."
    )
    summary = _finance_korean_fallback(text, "Nscale’s Funding Talks Put Dell and Nokia’s AI Supply Relationships to the Test")
    assert "$3.5 billion" in summary
    assert "자금조달" in summary
    assert "Dell" in summary and "Nokia" in summary
    assert "매출" in summary
    assert "관련 내용을 다루고 있습니다" not in summary
    assert "주요 수치는" not in summary


def test_news_fallback_keeps_ciena_arista_comparison_meaning():
    text = (
        "If you own Ciena (CIEN) or Arista Networks, you own one idea: AI is driving fast growth in network traffic, and both sell the equipment that carries it. "
        "Both raised their revenue outlooks in their latest reports, and both say they could ship more if supply loosened. "
        "Then the pair splits. Ciena's case rests on orders it cannot yet fill, while Arista already keeps about 43 cents of every sales dollar as operating profit."
    )
    summary = _finance_korean_fallback(text, "Ciena's Backlog Or Arista's Margins: Which Should Carry Your AI Network Bet?")
    assert "Ciena" in summary and "Arista" in summary
    assert "매출 전망" in summary
    assert "43" in summary and "영업이익" in summary
    assert "관련 내용을 다루고 있습니다" not in summary


def test_consensus_weekend_cache_is_served_without_live_call(monkeypatch):
    consensus._mem_cache.clear()
    row = {
        "ticker": "AAPL",
        "name": "Apple",
        "currency": "USD",
        "periods": {"0y": {"earnings": {"avg": 1.0}}},
        "asOf": "2026-09-12T01:31:00+00:00",
    }
    monkeypatch.setattr(consensus, "_disk_payload", lambda: {
        "generatedAt": "2026-09-12T01:31:00+00:00",
        "quotes": {"AAPL": row},
    })
    monkeypatch.setattr(consensus, "_history_payload", lambda: {"history": {"AAPL": {}}})
    monkeypatch.setattr(consensus, "_cache_age_seconds", lambda payload: 52 * 3600)

    def fail_live(symbol):
        raise AssertionError(f"live Yahoo should not be called for weekend cache: {symbol}")

    monkeypatch.setattr(consensus, "fetch_live_consensus", fail_live)
    result = consensus.fetch_consensus("AAPL")
    assert result["periods"]["0y"]["earnings"]["avg"] == 1.0
    assert result["cacheMode"] == "stale"
    assert consensus.DISK_MAX_AGE >= 72 * 3600
