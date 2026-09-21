(() => {
  'use strict';

  function selectedCount() {
    const tags = document.getElementById('ticker-tags');
    if (!tags) return 0;
    return tags.querySelectorAll('.ticker-tag').length;
  }

  function updateSelectionStatus() {
    const status = document.getElementById('app-selection-status');
    if (!status) return;
    status.textContent = `선택 ${selectedCount()}/6`;
    const manage = document.querySelector('[data-mobile-compare-open]');
    if (manage) manage.textContent = `비교 ${selectedCount()}/6 · 관리`;
    const summary = document.querySelector('.mobile-compare-summary');
    const tags = [...document.querySelectorAll('#ticker-tags .ticker-tag')];
    if (summary) {
      const labels = tags.map(tag => (tag.querySelector('.tag-name')?.textContent || tag.childNodes[0]?.textContent || '').trim()).filter(Boolean);
      // Use persisted names when tag markup has no separate name node.
      const items = window.ChartViewState?.getCompare().items || [];
      const names = window.ChartViewState?.getNames() || {};
      summary.textContent = items.length ? items.slice(0,3).map(x => names[x] || x).join(' · ') + (items.length > 3 ? ` 외 ${items.length - 3}개` : '') : labels.join(' · ') || '종목을 추가해 비교해 보세요';
    }
  }

  function enhanceUtilityHeader() {
    const header = document.querySelector('.header');
    const search = document.querySelector('#global-filter .global-search') || document.querySelector('.header .global-search');
    if (!header || !search || header.dataset.utilityReady === '1') return false;

    header.dataset.utilityReady = '1';
    header.classList.add('app-utility-header');
    header.querySelector('.title')?.remove();

    const top = document.createElement('div');
    top.className = 'app-utility-top';
    top.innerHTML = `
      <div class="app-utility-copy">
        <strong><span class="header-desktop-title">종목 검색</span><span class="header-mobile-title">종목분석</span></strong>
        <span>검색한 종목을 차트 · 밸류 · 투자판단에서 함께 봅니다</span>
      </div>
      <span id="app-selection-status" class="app-selection-status">선택 0/6</span>
      <button type="button" class="mobile-compare-open" data-mobile-compare-open aria-haspopup="dialog">비교 0/6 · 관리</button>`;
    header.appendChild(top);
    const summary = document.createElement('button');
    summary.type = 'button';
    summary.className = 'mobile-compare-summary';
    summary.setAttribute('aria-label', '선택한 비교종목 관리');
    header.appendChild(summary);
    header.appendChild(search);
    search.classList.add('app-header-search');

    const label = search.querySelector('.search-label');
    if (label) label.hidden = true;

    const hint = search.querySelector('.search-hint');
    if (hint) hint.textContent = '한국 종목 · 6자리 코드 · 해외 티커 · 최대 6종목';

    const input = search.querySelector('#unified-input');
    if (input) input.placeholder = '종목명 · JYP · 005930 · AAPL';

    const tags = document.getElementById('ticker-tags');
    if (tags) {
      const observer = new MutationObserver(updateSelectionStatus);
      observer.observe(tags, { childList: true, subtree: true });
    }
    installComparisonManager(header);
    updateSelectionStatus();
    return true;
  }

  function installComparisonManager(header) {
    const dialog = document.createElement('dialog');
    dialog.className = 'mobile-compare-dialog';
    dialog.setAttribute('aria-labelledby', 'mobile-compare-title');
    dialog.innerHTML = `<div class="mobile-compare-dialog-head"><h2 id="mobile-compare-title">비교종목 관리</h2><button type="button" data-compare-close aria-label="비교종목 관리 닫기">✕</button></div>
      <div class="mobile-compare-dialog-body">
        <p>차트에 표시할 종목을 최대 6개 선택하세요. 관심종목 목록은 바뀌지 않습니다.</p>
        <label for="mobile-compare-search">종목 검색</label>
        <input type="search" id="mobile-compare-search" placeholder="종목명 · 코드 · 티커" autocomplete="off">
        <p data-compare-message role="status" aria-live="polite"></p>
        <div data-compare-results></div>
        <h3>선택 종목 <span data-compare-count></span></h3><div data-compare-draft></div>
        <details><summary>추천 종목</summary><div data-compare-recommendations></div></details>
      </div><div class="mobile-compare-dialog-foot"><button type="button" data-compare-cancel>취소</button><button type="button" data-compare-apply>적용</button></div>`;
    document.body.appendChild(dialog);
    let draft = [], names = {}, timer, controller, request = 0, returnFocus, closingHistory = false;
    const input = dialog.querySelector('input');
    const message = dialog.querySelector('[data-compare-message]');
    const results = dialog.querySelector('[data-compare-results]');
    const list = dialog.querySelector('[data-compare-draft]');
    const say = text => { message.textContent = text; };
    const row = (symbol, name, remove = false) => {
      const item = document.createElement('div'); item.className = 'mobile-compare-row';
      const text = document.createElement('span');
      const title = document.createElement('strong'); title.textContent = name || symbol;
      const code = document.createElement('small'); code.textContent = symbol;
      text.append(title, code);
      const button = document.createElement('button'); button.type = 'button';
      const selected = draft.includes(symbol);
      button.textContent = remove ? '제거' : selected ? '선택됨' : '추가';
      button.disabled = !remove && selected;
      button.setAttribute('aria-label', `${name || symbol} ${remove ? '비교에서 제거' : '비교에 추가'}`);
      button.addEventListener('click', () => {
        if (remove) draft = draft.filter(x => x !== symbol);
        else {
          if (draft.length >= 6) { say('최대 6개까지 비교할 수 있어요. 한 종목을 제외해 주세요.'); return; }
          draft.push(symbol); names[symbol] = name || symbol;
        }
        say(remove ? `${name || symbol} 제외. 적용을 누르면 반영됩니다.` : `${name || symbol} 선택. 적용을 누르면 반영됩니다.`);
        const lostFocus = list.contains(button) || button.closest('[data-compare-recommendations]');
        renderDraft();
        if (lostFocus) (list.querySelector('button') || input).focus({ preventScroll: true });
        results.querySelectorAll('button').forEach(b => { b.disabled = draft.includes(b.dataset.symbol); b.textContent = b.disabled ? '선택됨' : '추가'; });
      });
      button.dataset.symbol = symbol;
      item.append(text, button); return item;
    };
    const renderDraft = () => {
      dialog.querySelector('[data-compare-count]').textContent = `${draft.length}/6`;
      list.replaceChildren(...draft.map(symbol => row(symbol, names[symbol], true)));
      if (!draft.length) list.textContent = '선택한 종목이 없습니다. 검색하거나 추천 종목에서 추가하세요.';
      const picks = [['005930.KS','삼성전자'],['000660.KS','SK하이닉스'],['AAPL','애플'],['NVDA','엔비디아']];
      dialog.querySelector('[data-compare-recommendations]').replaceChildren(...picks.map(([symbol,name]) => row(symbol,name)));
    };
    const cleanup = () => {
      clearTimeout(timer); controller?.abort(); request += 1;
      document.body.classList.remove('compare-dialog-open');
      returnFocus?.focus({ preventScroll: true });
    };
    const close = () => {
      if (!dialog.open) return;
      dialog.close(); cleanup();
      if (history.state?.cvCompareDialog) { closingHistory = true; history.back(); }
    };
    const open = event => {
      if (!window.ChartViewState || dialog.open || closingHistory) return;
      returnFocus = event.currentTarget;
      draft = [...window.ChartViewState.getCompare().items];
      names = { ...window.ChartViewState.getNames() };
      input.value = ''; results.replaceChildren(); say(''); renderDraft();
      document.body.classList.add('compare-dialog-open');
      dialog.showModal();
      history.pushState({ ...history.state, cvCompareDialog: true }, '', location.href);
      dialog.querySelector('[data-compare-close]').focus();
    };
    header.querySelector('[data-mobile-compare-open]').addEventListener('click', open);
    header.querySelector('.mobile-compare-summary').addEventListener('click', open);
    dialog.querySelectorAll('[data-compare-close],[data-compare-cancel]').forEach(button => button.addEventListener('click', close));
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
    window.addEventListener('popstate', event => {
      if (closingHistory) { closingHistory = false; event.stopImmediatePropagation(); return; }
      if (dialog.open && !event.state?.cvCompareDialog) {
        event.stopImmediatePropagation(); dialog.close(); cleanup();
      }
    }, true);
    dialog.querySelector('[data-compare-apply]').addEventListener('click', () => {
      const state = window.ChartViewState;
      if (!state.safeWrite(state.KEYS.names, names).ok || !state.setCompare(draft).ok) {
        say('저장하지 못했습니다. 기존 목록을 확인하고 다시 시도해 주세요.'); return;
      }
      updateSelectionStatus(); close();
    });
    input.addEventListener('input', () => {
      clearTimeout(timer); controller?.abort(); const seq = ++request;
      const query = input.value.trim(); results.replaceChildren();
      if (!query) { say(''); return; }
      say('종목을 찾고 있습니다.');
      timer = setTimeout(async () => {
        controller = new AbortController();
        try {
          const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`, { signal: controller.signal });
          if (!response.ok) throw new Error('search');
          const data = await response.json();
          if (seq !== request || !dialog.open) return;
          const rows = (Array.isArray(data.results) ? data.results : []).filter(x => x && String(x.symbol || '').trim()).slice(0,8);
          results.replaceChildren(...rows.map(x => row(String(x.symbol || '').toUpperCase(), x.name)));
          say(rows.length ? `${rows.length}개 검색 결과` : '검색 결과가 없습니다. 종목명이나 정확한 티커를 확인해 주세요.');
        } catch (error) { if (seq === request && error.name !== 'AbortError') say('검색하지 못했습니다. 검색어를 다시 입력해 주세요.'); }
      }, 180);
    });
  }

  function init() {
    if (enhanceUtilityHeader()) return;
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      if (enhanceUtilityHeader() || attempts >= 20) clearInterval(timer);
    }, 100);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
