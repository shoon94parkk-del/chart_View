from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_home_summary_v54_is_loaded_with_fresh_cache_key():
    html = read("templates/index.html")
    assert "/static/js/home_summary_v54.js?v=20260916v54" in html


def test_home_watchlist_is_limited_to_four_with_more_link():
    js = read("static/js/home_summary_v54.js")
    assert "const HOME_WATCHLIST_VISIBLE = 4" in js
    assert "cards.slice(HOME_WATCHLIST_VISIBLE)" in js
    assert "더보기 →" in js


def test_home_pick_cards_remove_rank_and_reflow_grid():
    js = read("static/js/home_summary_v54.js")
    assert ".ai-daily-rank" in js
    assert ".remove()" in js
    assert "grid-template-areas:'name score' 'price arrow'" in js
    assert "grid-template-areas:'name score arrow' 'price score arrow'" in js
