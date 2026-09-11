from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding='utf-8')
    if new in text:
        print(f'{label}: already applied')
        return
    if old not in text:
        raise SystemExit(f'{label}: target not found')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')
    print(f'{label}: applied')


home = ROOT / 'static/js/home_brief_v8.js'
replace_once(
    home,
    """    const chartTab = document.getElementById('chart-tab');\n    const anchor = chartTab?.querySelector('.date-section');\n    if (!chartTab || !anchor) return;""",
    """    const chartTab = document.getElementById('chart-tab');\n    const anchor = chartTab?.querySelector('.chart-section');\n    if (!chartTab || !anchor) return;""",
    'brief anchor',
)
replace_once(
    home,
    "    anchor.insertAdjacentElement('beforebegin', section);",
    "    anchor.insertAdjacentElement('afterend', section);",
    'brief placement',
)
replace_once(
    home,
    "<div><span class=\"stock-brief-kicker\">한눈에 판단</span><h2>선택 종목 요약</h2><p>차트·밸류·실적을 따로 열기 전에 핵심 상태부터 확인합니다.</p></div>",
    "<div><span class=\"stock-brief-kicker\">한눈에 판단</span><h2>선택 종목 요약</h2><p>수익률 흐름을 먼저 확인한 뒤 밸류·실적 상태를 이어서 봅니다.</p></div>",
    'brief copy',
)

uxv3 = ROOT / 'static/js/ux_v3.js'
replace_once(
    uxv3,
    "/static/js/home_brief_v8.js?v=20260911v18",
    "/static/js/home_brief_v8.js?v=20260911v19",
    'home asset version',
)

uxpatch = ROOT / 'static/js/ux_patch.js'
replace_once(
    uxpatch,
    "/static/js/ux_v3.js?v=20260911v18",
    "/static/js/ux_v3.js?v=20260911v19",
    'ux v3 version',
)

template = ROOT / 'templates/index.html'
replace_once(
    template,
    "/static/js/ux_patch.js?v=20260911v18",
    "/static/js/ux_patch.js?v=20260911v19",
    'root asset version',
)

print('stock analysis order v19 ready')
