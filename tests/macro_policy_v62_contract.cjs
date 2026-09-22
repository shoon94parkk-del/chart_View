const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const macro = fs.readFileSync('static/js/macro.js', 'utf8');
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

test('macro asset is cache-busted', () => {
  assert.match(html, /\/static\/js\/macro\.js\?v=20260922v62a/);
});
