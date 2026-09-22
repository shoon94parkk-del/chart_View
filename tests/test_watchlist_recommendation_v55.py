from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_recommendation_watchlist_module_exists_and_is_loaded():
    module = ROOT / 'static/js/recommendation_watchlist_v55.js'
    assert module.exists()
    html = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
    assert '/static/js/recommendation_watchlist_v55.js?v=20260917v56' in html


def test_watchlist_keeps_one_month_return_contract():
    watchlist = (ROOT / 'static/js/watchlist_v30.js').read_text(encoding='utf-8')
    overlay = (ROOT / 'static/js/recommendation_watchlist_v55.js').read_text(encoding='utf-8')

    assert '관심종목 · 1달 수익률' in watchlist
    assert '현재가와 1달 수익률' in watchlist
    assert '수익률 높은순' in watchlist
    assert '수익률 낮은순' in watchlist

    for token in ('#home-watchlist-v30', '#watchlist-tab', 'data-home-watch-return', 'data-watch-return'):
        assert token not in overlay


def test_chartview_pick_uses_recommendation_close_to_current_price():
    js = (ROOT / 'static/js/recommendation_watchlist_v55.js').read_text(encoding='utf-8')

    assert 'ai_recommendations.json' in js
    assert 'recommendedPrice' in js
    assert 'recommendedDate' in js
    assert 'currentPrice' in js
    assert 'returnPct' in js
    assert 'current / base - 1' in js
    assert '#ai-daily-section' in js
    assert '.ai-daily-price' in js
    assert '추천' in js and '현재' in js
    assert '.ai-daily-rank' in js


def test_watchlist_add_is_immediate_and_refreshes_only_new_symbol():
    js = (ROOT / 'static/js/watchlist_v30.js').read_text(encoding='utf-8')
    toggle = js.split('function toggleWatchlist(symbol, name)', 1)[1].split('function formatPrice', 1)[0]
    render = js.split('function render({ refreshQuotes = false } = {})', 1)[1].split('function applyQuote', 1)[0]
    loader = js.split('async function loadQuoteRows(rows, force = false)', 1)[1].split('function retryFailedQuotes', 1)[0]

    assert 'render({ refreshQuotes: false })' in toggle
    assert 'setTimeout(() => hydrateAddedWatchlistRow(row), 0)' in toggle
    assert 'loadQuotes(false)' not in toggle
    assert 'if (refreshQuotes) loadQuotes(false)' in render
    assert 'async function hydrateAddedWatchlistRow(row)' in js
    assert '/api/quotes?tickers=' in js
    assert '/api/compare?tickers=' in js
    assert 'const targets = dedupe((rows || []).filter' in loader
    assert 'return loadQuoteRows([...watchlist], force)' in loader


def test_watchlist_entry_is_cache_first_and_does_not_start_full_refresh():
    js = (ROOT / 'static/js/watchlist_v30.js').read_text(encoding='utf-8')
    quick = (ROOT / 'static/js/watchlist_quick_add_v48.js').read_text(encoding='utf-8')

    assert 'const RETURN_FRESH_MS = 12 * 60 * 60 * 1000' in js
    assert 'const ENTRY_REFRESH_THROTTLE_MS = 60 * 1000' in js
    assert 'function render({ refreshQuotes = false } = {})' in js
    assert 'render({ refreshQuotes: false })' in js
    assert 'async function refreshCurrentQuotesQuietly()' in js
    assert 'async function refreshReturnsQuietly()' in js
    assert 'function refreshWatchlistOnEntry()' in js
    assert 'window.__refreshWatchlistOnEntry = refreshWatchlistOnEntry' in js
    assert 'requestIdleCallback(runReturns' in js
    assert 'setTimeout(() => window.__refreshWatchlistOnEntry?.(), 0)' in quick
    assert "tab.querySelector('[data-watch-refresh]')?.addEventListener('click', () => loadQuotes(true))" in js
