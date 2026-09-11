from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'static/js/home_brief_v8.js'
CSS = ROOT / 'static/css/home_brief_v8.css'
LOGOS = ROOT / 'static/logos'


def download_text(url: str) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': 'ChartView/1.0'})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode('utf-8')


def save_logo(name: str, url: str, fill: str | None = None) -> None:
    text = download_text(url)
    if '<svg' not in text:
        raise RuntimeError(f'{name}: invalid svg')
    if fill and '<path ' in text and 'fill=' not in text.split('<path ', 1)[1].split('>', 1)[0]:
        text = text.replace('<path ', f'<path fill="{fill}" ', 1)
    (LOGOS / name).write_text(text, encoding='utf-8')


def write_logos() -> None:
    LOGOS.mkdir(parents=True, exist_ok=True)
    save_logo('samsung.svg', 'https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/samsung.svg', '#1428A0')
    save_logo('skhynix.svg', 'https://raw.githubusercontent.com/gilbarbara/logos/main/logos/sk-hynix.svg')
    save_logo('nvidia.svg', 'https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/nvidia.svg', '#76B900')
    save_logo('apple.svg', 'https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/apple.svg', '#111111')
    save_logo('meta.svg', 'https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/meta.svg', '#0866FF')
    save_logo('tesla.svg', 'https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/tesla.svg', '#E82127')
    save_logo('google.svg', 'https://raw.githubusercontent.com/gilbarbara/logos/main/logos/google-icon.svg')
    microsoft = '''<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Microsoft"><rect x="4" y="4" width="43" height="43" fill="#F25022"/><rect x="53" y="4" width="43" height="43" fill="#7FBA00"/><rect x="4" y="53" width="43" height="43" fill="#00A4EF"/><rect x="53" y="53" width="43" height="43" fill="#FFB900"/></svg>'''
    (LOGOS / 'microsoft.svg').write_text(microsoft, encoding='utf-8')


def patch_js() -> None:
    text = JS.read_text(encoding='utf-8')
    stock_block = '''  const HOME_MAJOR_STOCKS = [
    { symbol: '005930.KS', name: '삼성전자', logo: '/static/logos/samsung.svg', fallback: '삼성', logoClass: 'wide' },
    { symbol: '000660.KS', name: 'SK하이닉스', logo: '/static/logos/skhynix.svg', fallback: 'SK', logoClass: 'wide' },
    { symbol: 'NVDA', name: '엔비디아', logo: '/static/logos/nvidia.svg', fallback: 'NV' },
    { symbol: 'AAPL', name: '애플', logo: '/static/logos/apple.svg', fallback: 'A', logoClass: 'tall' },
    { symbol: 'MSFT', name: '마이크로소프트', logo: '/static/logos/microsoft.svg', fallback: 'MS', logoClass: 'square' },
    { symbol: 'META', name: '메타', logo: '/static/logos/meta.svg', fallback: 'M' },
    { symbol: 'TSLA', name: '테슬라', logo: '/static/logos/tesla.svg', fallback: 'T', logoClass: 'tall' },
    { symbol: 'GOOGL', name: '알파벳', logo: '/static/logos/google.svg', fallback: 'G', logoClass: 'square' },
  ];'''
    text, count = re.subn(r"  const HOME_MAJOR_STOCKS = \[\n.*?\n  \];", stock_block, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError('HOME_MAJOR_STOCKS block not replaced')

    old_logo = '''  function homeLogo(item) {
    const label = esc(item.fallback || String(item.name || item.symbol || '?').slice(0, 2));
    const color = item.fallbackColor ? ` style="color:${esc(item.fallbackColor)}"` : '';
    const fallback = `<span class="home16-logo-fallback"${color}>${label}</span>`;
    if (!item.logo) return `<span class="home16-logo">${fallback}</span>`;
    return `<span class="home16-logo"><img src="${esc(item.logo)}" alt="" loading="eager" decoding="async" onerror="this.remove()">${fallback}</span>`;
  }'''
    new_logo = '''  function homeLogo(item) {
    const label = esc(item.fallback || String(item.name || item.symbol || '?').slice(0, 2));
    const fallback = `<span class="home16-logo-fallback">${label}</span>`;
    if (!item.logo) return `<span class="home16-logo">${fallback}</span>`;
    const logoClass = item.logoClass ? ` logo-${esc(item.logoClass)}` : '';
    return `<span class="home16-logo"><img class="${logoClass.trim()}" src="${esc(item.logo)}" alt="${esc(item.name)} 로고" loading="eager" decoding="async" onerror="this.remove()">${fallback}</span>`;
  }'''
    if old_logo not in text:
        raise RuntimeError('homeLogo target not found')
    text = text.replace(old_logo, new_logo, 1)

    summary = '''  function marketSummaryHtml(macro) {
    const summary = typeof macro?.summary === 'string' ? macro.summary : macro?.summary?.text;
    const rawLevel = typeof macro?.summary === 'object' ? macro?.summary?.level : null;
    const level = ['green', 'yellow', 'red'].includes(rawLevel) ? rawLevel : 'yellow';
    const state = level === 'green'
      ? { label: '시장 우호적', desc: '위험 지표가 비교적 안정적입니다.' }
      : level === 'red'
        ? { label: '리스크 경계', desc: '방어적으로 확인할 구간입니다.' }
        : { label: '중립 · 주의', desc: '지표가 엇갈려 선별 접근이 필요합니다.' };
    const stale = Number(macro?.staleCount || 0);
    return `
      <section class="home-v8-block home16-summary-card home18-summary-${level}">
        <div class="home-block-head home16-head"><div><span>SUMMARY</span><h3>시장 한줄 요약</h3></div><button type="button" data-home-market>시장 자세히 →</button></div>
        <div class="home18-state-card">
          <div class="home18-traffic" aria-label="현재 시장 신호 ${esc(state.label)}">
            <i class="red ${level === 'red' ? 'active' : ''}"></i>
            <i class="yellow ${level === 'yellow' ? 'active' : ''}"></i>
            <i class="green ${level === 'green' ? 'active' : ''}"></i>
          </div>
          <div class="home18-state-copy"><span>현재 시장 상태</span><strong>${esc(state.label)}</strong><small>${esc(state.desc)}</small></div>
        </div>
        <p>${esc(summary || '주요 지수와 종목별 움직임을 확인해 주세요.')}</p>
        <div class="home16-summary-foot"><span class="${stale ? 'warn' : 'ok'}"></span>${stale ? `일부 매크로 지표 ${stale}개 갱신 지연` : '매크로 데이터 정상 갱신'}</div>
      </section>`;
  }'''
    text, count = re.subn(
        r"  function marketSummaryHtml\(macro\) \{.*?\n  \}\n\n  function selectedTickersNow",
        summary + '\n\n  function selectedTickersNow',
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError('marketSummaryHtml block not replaced')

    JS.write_text(text, encoding='utf-8')


def patch_css() -> None:
    text = CSS.read_text(encoding='utf-8')
    fallback_anchor = '.home16-logo-fallback{position:absolute;z-index:1;font-size:12px;letter-spacing:-.04em}\n'
    if '.home16-logo img+.home16-logo-fallback{display:none}' not in text:
        if fallback_anchor not in text:
            raise RuntimeError('fallback CSS anchor missing')
        text = text.replace(
            fallback_anchor,
            fallback_anchor
            + '.home16-logo img+.home16-logo-fallback{display:none}\n'
            + '.home16-logo img.logo-wide{width:86%;height:62%}\n'
            + '.home16-logo img.logo-tall{width:58%;height:72%}\n'
            + '.home16-logo img.logo-square{width:62%;height:62%}\n',
            1,
        )

    marker = '/* HOME V18: local brand logos + traffic-light market state */'
    if marker not in text:
        text += '''\n\n/* HOME V18: local brand logos + traffic-light market state */
.home18-state-card{display:flex;align-items:center;gap:12px;margin-bottom:10px;padding:12px 14px;border-radius:15px;background:#f7f9fa}
.home18-summary-green .home18-state-card{background:#effaf3}.home18-summary-yellow .home18-state-card{background:#fff8e8}.home18-summary-red .home18-state-card{background:#fff0f1}
.home18-traffic{display:flex;gap:5px;flex:0 0 auto;padding:7px 8px;border-radius:999px;background:#26313c;box-shadow:inset 0 0 0 1px rgba(255,255,255,.06)}
.home18-traffic i{display:block;width:11px;height:11px;border-radius:50%;opacity:.2}
.home18-traffic i.red{background:#ff4d57}.home18-traffic i.yellow{background:#ffc43d}.home18-traffic i.green{background:#31c96b}
.home18-traffic i.active{opacity:1;box-shadow:0 0 0 3px rgba(255,255,255,.12),0 0 9px rgba(0,0,0,.18)}
.home18-state-copy{min-width:0}.home18-state-copy span{display:block;color:#8b95a1;font-size:9px;font-weight:800}.home18-state-copy strong{display:block;margin-top:1px;color:#202632;font-size:15px;font-weight:900;letter-spacing:-.03em}.home18-state-copy small{display:block;margin-top:2px;color:#8b95a1;font-size:9px;line-height:1.35}
@media(max-width:720px){.home18-state-card{padding:11px 12px}.home18-state-copy strong{font-size:14px}}
'''
    CSS.write_text(text, encoding='utf-8')


def bust_assets() -> None:
    patches = {
        ROOT / 'static/js/ux_v3.js': [
            ('/static/css/home_brief_v8.css?v=20260911v16', '/static/css/home_brief_v8.css?v=20260911v18'),
            ('/static/js/home_brief_v8.js?v=20260911v17', '/static/js/home_brief_v8.js?v=20260911v18'),
        ],
        ROOT / 'static/js/ux_patch.js': [
            ('/static/js/ux_v3.js?v=20260911v17', '/static/js/ux_v3.js?v=20260911v18'),
        ],
        ROOT / 'templates/index.html': [
            ('/static/js/ux_patch.js?v=20260911v17', '/static/js/ux_patch.js?v=20260911v18'),
        ],
    }
    for path, reps in patches.items():
        text = path.read_text(encoding='utf-8')
        for old, new in reps:
            if old in text:
                text = text.replace(old, new)
            elif new not in text:
                raise RuntimeError(f'{path.name}: cache target missing: {old}')
        path.write_text(text, encoding='utf-8')


def main() -> None:
    write_logos()
    patch_js()
    patch_css()
    bust_assets()
    print('HOME V18 logos + market signal applied')


if __name__ == '__main__':
    main()
