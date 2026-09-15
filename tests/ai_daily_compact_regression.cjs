const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('daily TOP3 starts compact and reveals reasons with accessible controls', () => {
  const source = fs.readFileSync('static/js/ai_daily_widget.js', 'utf8');
  assert.match(source, /<details class="ai-daily-card"><summary aria-label=/);
  assert.match(source, /추천 사유 보기/);
  assert.match(source, /class="ai-daily-detail"/);
  assert.match(source, /\.ai-daily-card\[open\] \.ai-daily-arrow/);
});
