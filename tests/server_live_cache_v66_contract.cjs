const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const main = fs.readFileSync('main.py', 'utf8');
const heat = fs.readFileSync('static/js/home_heatmap_v57.js', 'utf8');
const visitor = fs.readFileSync('static/js/visitor_v66.js', 'utf8');
const html = fs.readFileSync('templates/index.html', 'utf8');
const admin = fs.readFileSync('templates/admin_usage.html', 'utf8');

test('Home clients read Render memory instead of triggering provider quote fetches', () => {
  assert.match(heat, /LIVE_ENDPOINT = '\/api\/home-live'/);
  assert.match(heat, /fetch\(LIVE_ENDPOINT/);
  assert.doesNotMatch(heat, /\/api\/quotes\?tickers=/);
  assert.match(main, /async def _home_live_worker/);
  assert.match(main, /active_home > 0/);
  assert.match(main, /HOME_LIVE_ACTIVE_REFRESH_SEC = 5\.0/);
});

test('anonymous heartbeat is global and privacy-light', () => {
  assert.match(html, /\/static\/js\/visitor_v66\.js\?v=20260922v66a/);
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

test('daily unique count persists in Render Key Value with memory fallback', () => {
  const requirements = fs.readFileSync('requirements.txt', 'utf8');
  assert.match(requirements, /redis>=5\.0\.0/);
  assert.match(main, /CHARTVIEW_ANALYTICS_REDIS/);
  assert.match(main, /async def _persist_daily_visitor/);
  assert.match(main, /chartview:visitors:/);
  assert.match(main, /await client\.sadd/);
  assert.match(main, /await client\.scard/);
  assert.match(main, /analyticsBackend/);
});

test('heartbeat response does not expose visitor counts publicly', () => {
  const start = main.indexOf('@app.post("/api/activity")');
  const end = main.indexOf('@app.get("/api/home-live")', start);
  const block = main.slice(start, end);
  assert.doesNotMatch(block, /activeVisitors/);
  assert.doesNotMatch(block, /activeHomeVisitors/);
  assert.match(block, /"heartbeatSec": VISITOR_HEARTBEAT_SEC/);
});
