from pathlib import Path
import json


def replace_required(path: str, old: str, new: str) -> None:
    p = Path(path)
    s = p.read_text(encoding='utf-8')
    if old not in s:
        raise SystemExit(f'pattern not found in {path}: {old[:100]!r}')
    p.write_text(s.replace(old, new), encoding='utf-8')

# 1) Generator also writes a tiny freshness metadata file.
replace_required(
    'scripts/generate_screener.py',
    'OUT = Path("static/data/screener.json")\nBATCH_SIZE = 80',
    'OUT = Path("static/data/screener.json")\nMETA_OUT = Path("static/data/screener_meta.json")\nBATCH_SIZE = 80',
)
replace_required(
    'scripts/generate_screener.py',
    '    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")\n    print(f"Saved {len(rows)} stocks -> {OUT} ({OUT.stat().st_size / 1024:.1f} KB)")',
    '    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")\n    meta_payload = {key: payload[key] for key in ("updated", "tradeDate", "count", "universeCount", "source")}\n    META_OUT.write_text(json.dumps(meta_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")\n    print(f"Saved {len(rows)} stocks -> {OUT} ({OUT.stat().st_size / 1024:.1f} KB); meta -> {META_OUT}")',
)
replace_required(
    '.github/workflows/update-screener.yml',
    '          git add static/data/screener.json',
    '          git add static/data/screener.json static/data/screener_meta.json',
)

# Seed metadata from the already-fresh current JSON so no regeneration is needed now.
payload = json.loads(Path('static/data/screener.json').read_text(encoding='utf-8'))
meta = {key: payload.get(key) for key in ('updated', 'tradeDate', 'count', 'universeCount', 'source')}
Path('static/data/screener_meta.json').write_text(json.dumps(meta, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

# 2) Screener tab: tiny no-store meta lookup, then cache the large JSON by trade date.
p = Path('static/js/screener.js')
s = p.read_text(encoding='utf-8')
needle = "  async function loadData() {\n"
if needle not in s:
    raise SystemExit('screener loadData anchor not found')
helper = """  async function screenerDataUrl() {\n    try {\n      const response = await fetch('/static/data/screener_meta.json', { cache: 'no-store' });\n      if (!response.ok) throw new Error(`meta HTTP ${response.status}`);\n      const meta = await response.json();\n      const version = meta.tradeDate || meta.updated || 'latest';\n      return `/static/data/screener.json?v=${encodeURIComponent(version)}`;\n    } catch (_) {\n      return `/static/data/screener.json?v=${Date.now()}`;\n    }\n  }\n\n"""
s = s.replace(needle, helper + needle, 1)
old = """    loadingPromise = fetch('/static/data/screener.json', { cache: 'no-store' })\n      .then((response) => {\n        if (!response.ok) throw new Error(`HTTP ${response.status}`);\n        return response.json();\n      })"""
new = """    loadingPromise = screenerDataUrl()\n      .then((url) => fetch(url, { cache: 'force-cache' }))\n      .then((response) => {\n        if (!response.ok) throw new Error(`HTTP ${response.status}`);\n        return response.json();\n      })"""
if old not in s:
    raise SystemExit('screener fetch block not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

# 3) Home data-status reads only the tiny uncached metadata file.
replace_required(
    'static/js/ux_patterns_v12.js',
    "fetch('/static/data/screener.json', { cache: 'force-cache' }).then((r) => r.ok ? r.json() : null).catch(() => null),",
    "fetch('/static/data/screener_meta.json', { cache: 'no-store' }).then((r) => r.ok ? r.json() : null).catch(() => null),",
)

# 4) Lazy Korean search and stock brief also key their large-file cache by the latest trade date.
replace_required(
    'static/js/ux_patch.js',
    "universePromise = fetch('/static/data/screener.json', { cache: 'force-cache' })\n        .then((res) => {\n          if (!res.ok) throw new Error(`screener HTTP ${res.status}`);\n          return res.json();\n        })",
    "universePromise = fetch('/static/data/screener_meta.json', { cache: 'no-store' })\n        .then((res) => res.ok ? res.json() : null)\n        .then((meta) => fetch(`/static/data/screener.json?v=${encodeURIComponent(meta?.tradeDate || meta?.updated || 'latest')}`, { cache: 'force-cache' }))\n        .then((res) => {\n          if (!res.ok) throw new Error(`screener HTTP ${res.status}`);\n          return res.json();\n        })",
)
replace_required(
    'static/js/home_brief_v8.js',
    "screenerPromise = fetch('/static/data/screener.json', { cache: 'force-cache' })\n        .then((r) => r.ok ? r.json() : { stocks: [] })",
    "screenerPromise = fetch('/static/data/screener_meta.json', { cache: 'no-store' })\n        .then((r) => r.ok ? r.json() : null)\n        .then((meta) => fetch(`/static/data/screener.json?v=${encodeURIComponent(meta?.tradeDate || meta?.updated || 'latest')}`, { cache: 'force-cache' }))\n        .then((r) => r.ok ? r.json() : { stocks: [] })",
)

# 5) Cache bust changed scripts in the loader chain.
replace_required('static/js/ux_patch.js', '/static/js/screener.js?v=20260911v13', '/static/js/screener.js?v=20260912v29')
replace_required('static/js/ux_patch.js', '/static/js/ux_patterns_v12.js?v=20260911v12', '/static/js/ux_patterns_v12.js?v=20260912v29')
replace_required('static/js/ux_patch.js', '/static/js/ux_v3.js?v=20260911v26', '/static/js/ux_v3.js?v=20260912v29')
replace_required('static/js/ux_v3.js', '/static/js/home_brief_v8.js?v=20260911v26', '/static/js/home_brief_v8.js?v=20260912v29')
replace_required('templates/index.html', '/static/js/ux_patch.js?v=20260912v28', '/static/js/ux_patch.js?v=20260912v29')
