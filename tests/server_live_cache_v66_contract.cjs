const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const main = fs.readFileSync('main.py', 'utf8');
const heat = fs.readFileSync('static/js/home_heatmap_v57.js', 'utf8');
const visitor = fs.readFileSync('static/js/visitor_v66.js', 'utf8');
const html = fs.readFileSync('templates/index.html', 'utf8');
const boot = fs.readFileSync('static/js/chartview_boot_bundle.js', 'utf8');
const admin = fs.readFileSync('templates/admin_usage.html', 'utf8');

test('Home clients read Render memory instead of triggering provider quote fetches', () => {
  assert.match(heat, /LIVE_ENDPOINT = '\/api\/home-live'/);
  assert.match(heat, /fetch\(LIVE_ENDPOINT/);
  assert.doesNotMatch(heat, /\/api\/quotes\?tickers=/);
  assert.match(main, /async def _home_live_worker/);
  assert.match(main, /is_active_home/);
  assert.match(main, /HOME_LIVE_ACTIVE_REFRESH_SEC = 5\.0/);
  assert.match(main, /HOME_LIVE_FIRST_VISITOR_GRACE_SEC = 5\.0/);
});

test('anonymous heartbeat is global and privacy-light', () => {
  assert.match(html, /\/static\/js\/chartview_boot_bundle\.js\?v=/);
  assert.match(boot, /\/\* --- static\/js\/visitor_v66\.js --- \*\//);
  assert.match(visitor, /chartview-anon-visitor-v66/);
  assert.match(visitor, /\/api\/activity/);
  assert.match(visitor, /HEARTBEAT_MS = 20_000/);
  assert.doesNotMatch(visitor, /geolocation|email|phone|name/);
});

test('usage dashboard is token protected and not linked from public UI', () => {
  assert.match(main, /CHARTVIEW_ADMIN_TOKEN/);
  assert.match(main, /X-ChartView-Admin/);
  assert.match(main, /secrets\.compare_digest/);
  assert.match(admin, /Chart View 사용 현황/);
  assert.match(admin, /sessionStorage/);
  assert.doesNotMatch(html, />Chart View 사용 현황</);
});

test('automated browser visits are not counted as users', () => {
  assert.match(visitor, /if \(navigator\.webdriver\) return/);
});


test('closed markets remain demand-refreshed without deploy-time provider fanout', () => {
  assert.match(main, /HOME_LIVE_CLOSED_REFRESH_SEC = 300\.0/);
  assert.match(main, /def _all_home_markets/);
  assert.match(main, /all_markets = _all_home_markets\(\)/);
  assert.match(main, /for market, tickers in all_markets\.items\(\)/);
  assert.match(main, /interval = HOME_LIVE_ACTIVE_REFRESH_SEC if market in open_markets else HOME_LIVE_CLOSED_REFRESH_SEC/);
  assert.doesNotMatch(main, /asyncio\.create_task\(_refresh_home_live\(_all_home_markets\(\)\)\)/);
});

test('heatmap client cache is invalidated with the reliability release', () => {
  assert.match(heat, /chartview-home-heatmap-v68/);
  assert.match(heat, /chartview-watchlist-quotes-v35/);
  assert.match(html, /\/static\/js\/chartview_boot_bundle\.js\?v=/);
  assert.match(boot, /\/\* --- static\/js\/home_heatmap_v57\.js --- \*\//);
});


test('bundled market cache is invalidated for session-correct quotes', () => {
  const bundle = fs.readFileSync('static/js/chartview_release_bundle.js', 'utf8');
  assert.match(bundle, /chartview-market-now-v23/);
  assert.doesNotMatch(bundle, /chartview-market-now-v22/);
  assert.match(html, /chartview_release_bundle\.js\?v=[^"\\s]+/);
});
