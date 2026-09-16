const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');

test('chart tab resize has a timer fallback for throttled animation frames', () => {
  const source = fs.readFileSync('static/js/ux_v3.js', 'utf8');
  const template = fs.readFileSync('templates/index.html', 'utf8');

  assert.match(source, /const resize = \(\) => window\.dispatchEvent\(new Event\('resize'\)\)/);
  assert.match(source, /setTimeout\(resize, 80\)/);
  assert.match(template, /chartview_release_bundle\.js\?v=20260916v12/);
});
