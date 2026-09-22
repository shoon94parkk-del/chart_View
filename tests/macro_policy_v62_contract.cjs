const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const macro = fs.readFileSync('static/js/macro.js', 'utf8');
const css = fs.readFileSync('static/css/style.css', 'utf8');
const main = fs.readFileSync('main.py', 'utf8');
const generator = fs.readFileSync('scripts/generate_macro_cache.py', 'utf8');
const html = fs.readFileSync('templates/index.html', 'utf8');
const workflow = fs.readFileSync('.github/workflows/update-macro-cache.yml', 'utf8');

test('policy rate uses target range plus daily EFFR, not monthly FEDFUNDS', () => {
  assert.match(generator, /"FEDTARGET"/);
  assert.match(generator, /dfedtarl/);
  assert.match(generator, /dfedtaru/);
  assert.match(generator, /"DFF"/);
  assert.match(generator, /"feed": "equibles:dff"/);
  assert.doesNotMatch(generator, /"FEDFUNDS":/);
  assert.match(workflow, /'FEDTARGET','DFF'/);
  assert.match(workflow, /len\(rows\) == 16/);
});

test('macro traffic light explicitly uses inflation and Fed stance', () => {
  assert.match(main, /PCEPI/);
  assert.match(main, /PCETRIM12M159SFRBDAL/);
  assert.match(main, /targetLower/);
  assert.match(main, /moveBp/);
  assert.match(main, /descriptive Fed-policy\/inflation\/labor\/financial-stress regime/);
  assert.match(main, /FOMC 결정을 예측하는 신호도 아닙니다/);
});

test('macro charts use local SVG sparklines and do not depend on chart library', () => {
  assert.match(macro, /function sparklineSvg/);
  assert.match(macro, /class="macro-sparkline"/);
  assert.doesNotMatch(macro, /LightweightCharts\.createChart/);
  assert.doesNotMatch(macro, /addLineSeries/);
  assert.match(macro, /FEDTARGET/);
  assert.match(macro, /bp 최근 변경/);
});

test('macro sparkline is physically clipped to its card', () => {
  assert.match(macro, /width="100%" height="100%"/);
  assert.match(macro, /overflow="hidden"/);
  assert.match(css, /\.mc-chart-wrapper[\s\S]*overflow:\s*hidden/);
  assert.match(css, /\.mc-mini-chart[\s\S]*height:\s*80px[\s\S]*overflow:\s*hidden/);
  assert.match(css, /\.mc-mini-chart-core[\s\S]*height:\s*120px/);
  assert.match(css, /\.macro-sparkline[\s\S]*width:\s*100%[\s\S]*height:\s*100%[\s\S]*overflow:\s*hidden/);
});

test('macro assets are cache-busted', () => {
  assert.match(html, /\/static\/css\/style\.css\?v=20260922v63a/);
  assert.match(html, /\/static\/js\/macro\.js\?v=20260922v63a/);
});
