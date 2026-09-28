from pathlib import Path

SOURCE = Path("scripts/generate_screener.py").read_text(encoding="utf-8")

def test_screener_exports_popular_technical_signals():
    assert "PERIOD='1y'" in SOURCE
    assert "(local.hour, local.minute)<(16, 0)" in SOURCE
    for field in [
        "'macdBullish':macd_bullish",
        "'macdCrossUp':macd_cross_up",
        "'goldenCross2060':golden_cross",
        "'trend2060':trend2060",
        "'high52':high52",
        "'distance52HighPct':distance52",
        "'near52High':near52",
        "'bbBreakout':bb_breakout",
    ]:
        assert field in SOURCE
