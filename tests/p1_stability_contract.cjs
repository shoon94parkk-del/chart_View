const fs = require('fs');
const assert = require('assert');

function read(path) { return fs.readFileSync(path, 'utf8'); }

const chart = read('static/js/chart.js');
assert(chart.includes('normalizeChartDate'), 'chart dates must be normalized');
assert(chart.includes('종목별 기준일 상이'), 'mixed-market trade dates must be explicit');
assert(chart.includes('KST 조회'), 'fetch time must identify KST');

const quick = read('static/js/watchlist_quick_add_v48.js');
assert(quick.includes("button.textContent !== label"), 'quick-add DOM writes must be idempotent');
assert(quick.includes("closest?.('[data-watch-quick-add]')"), 'observer must ignore self changes');

const home = read('static/js/home_summary_v54.js');
assert(home.includes("more.textContent !== '더보기 →'"), 'home summary text writes must be idempotent');

const screener = read('static/js/screener.js');
assert(screener.includes('validateCustomFilters'), 'screener must validate custom ranges');
assert(screener.includes('RSI 최소는 최대보다 클 수 없습니다.'), 'reversed RSI range must explain the error');
assert(screener.includes('갱신 실패 ·'), 'stale screener data must be labelled');

const ledger = read('static/js/ai_pick_ledger_v52.js');
assert(ledger.includes("String(value).trim() === ''"), 'empty PICK returns must stay missing');
assert(ledger.includes('추천 건별 단순 평균 수익률'), 'PICK average must describe its calculation');
assert(ledger.includes('미평가 제외'), 'PICK KPI must disclose missing-value policy');

const watch = read('static/js/watchlist_v30.js');
assert(watch.includes('quoteMetaText'), 'watchlist quote freshness must share one formatter');
assert(watch.includes('tradeDateLabel'), 'watchlist must expose trade date');

console.log('P1 stability contracts passed');
