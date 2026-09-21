(() => {
  'use strict';

  const WATCHLIST_KEY = 'chartview-watchlist-v1';
  const SYNC_ID_KEY = 'chartview-profile-sync-id-v1';
  const MAX_WATCHLIST = 20;
  const ID_RE = /^[A-Za-z0-9_-]{6,32}$/;
  let saveTimer = null;
  let busy = false;

  function normalizeId(value) {
    const id = String(value || '').trim().toLowerCase();
    return ID_RE.test(id) ? id : '';
  }

  function readWatchlist() {
    try {
      const parsed = JSON.parse(localStorage.getItem(WATCHLIST_KEY) || '[]');
      if (!Array.isArray(parsed)) return [];
      const seen = new Set();
      return parsed.map((row) => {
        const symbol = String(row?.symbol || row?.ticker || '').trim().toUpperCase();
        if (!symbol || seen.has(symbol)) return null;
        seen.add(symbol);
        return { symbol, name: String(row?.name || symbol).trim() || symbol };
      }).filter(Boolean).slice(0, MAX_WATCHLIST);
    } catch (_) {
      return [];
    }
  }

  function writeWatchlist(rows) {
    const seen = new Set();
    const clean = (Array.isArray(rows) ? rows : []).map((row) => {
      const symbol = String(row?.symbol || row?.ticker || '').trim().toUpperCase();
      if (!symbol || seen.has(symbol)) return null;
      seen.add(symbol);
      return { symbol, name: String(row?.name || symbol).trim() || symbol };
    }).filter(Boolean).slice(0, MAX_WATCHLIST);
    localStorage.setItem(WATCHLIST_KEY, JSON.stringify(clean));
    return clean;
  }

  function activeId() {
    return normalizeId(localStorage.getItem(SYNC_ID_KEY) || '');
  }

  function setActiveId(id) {
    if (id) localStorage.setItem(SYNC_ID_KEY, id);
    else localStorage.removeItem(SYNC_ID_KEY);
  }

  function installStyles() {
    if (document.getElementById('profile-sync-v1-style')) return;
    const style = document.createElement('style');
    style.id = 'profile-sync-v1-style';
    style.textContent = `
      .profile-sync-v1{margin:12px 0 16px;padding:14px;border:1px solid #e5e8eb;border-radius:16px;background:#fff}
      .profile-sync-v1-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:10px}
      .profile-sync-v1-head strong{display:block;font-size:15px;line-height:1.35}
      .profile-sync-v1-head span{display:block;margin-top:3px;color:#6b7684;font-size:12px;line-height:1.4}
      .profile-sync-v1-row{display:flex;gap:8px;align-items:center}
      .profile-sync-v1 input{min-width:0;flex:1;height:44px;padding:0 12px;border:1px solid #dfe3e8;border-radius:12px;font:600 14px/1 system-ui,sans-serif;outline:none}
      .profile-sync-v1 input:focus{border-color:#3182f6;box-shadow:0 0 0 3px rgba(49,130,246,.12)}
      .profile-sync-v1 button{min-height:44px;border:0;border-radius:12px;padding:0 14px;font:700 13px/1 system-ui,sans-serif;cursor:pointer}
      .profile-sync-v1 [data-sync-connect]{background:#3182f6;color:#fff}
      .profile-sync-v1 [data-sync-disconnect]{background:#f2f4f6;color:#4e5968}
      .profile-sync-v1 button:disabled{opacity:.55;cursor:default}
      .profile-sync-v1-status{display:block;margin-top:9px;color:#4e5968;font-size:12px;line-height:1.4}
      .profile-sync-v1-status.ok{color:#067647}.profile-sync-v1-status.error{color:#d92d20}
      .profile-sync-v1-note{margin:8px 0 0;color:#8b95a1;font-size:11px;line-height:1.45}
      @media(max-width:520px){.profile-sync-v1-row{display:grid;grid-template-columns:1fr auto}.profile-sync-v1 [data-sync-disconnect]{grid-column:1/-1;width:100%}}
    `;
    document.head.appendChild(style);
  }

  function statusNode() {
    return document.querySelector('#profile-sync-v1 [data-sync-status]');
  }

  function setStatus(message, tone = '') {
    const node = statusNode();
    if (!node) return;
    node.textContent = message;
    node.className = `profile-sync-v1-status ${tone}`.trim();
  }

  function updateUi() {
    const root = document.getElementById('profile-sync-v1');
    if (!root) return;
    const id = activeId();
    const input = root.querySelector('[data-sync-id]');
    const connect = root.querySelector('[data-sync-connect]');
    const disconnect = root.querySelector('[data-sync-disconnect]');
    if (id && input && !input.matches(':focus')) input.value = id;
    if (connect) connect.textContent = id ? '불러오기' : '저장·불러오기';
    if (disconnect) disconnect.hidden = !id;
    if (id) setStatus(`${id} ID와 연결됨 · 관심종목 변경 시 자동 저장`, 'ok');
  }

  function mount() {
    installStyles();
    const summary = document.querySelector('.watchlist-v33-summary');
    if (!summary || document.getElementById('profile-sync-v1')) return false;
    const section = document.createElement('section');
    section.id = 'profile-sync-v1';
    section.className = 'profile-sync-v1';
    section.setAttribute('aria-label', '관심종목 기기 간 동기화');
    section.innerHTML = `
      <div class="profile-sync-v1-head">
        <div><strong>기기 간 관심종목 동기화</strong><span>회원가입 없이 동기화 ID 하나로 관심종목을 옮길 수 있어요.</span></div>
      </div>
      <div class="profile-sync-v1-row">
        <input type="text" inputmode="latin" autocomplete="off" autocapitalize="none" spellcheck="false"
          maxlength="32" placeholder="동기화 ID (6~32자)" aria-label="관심종목 동기화 ID" data-sync-id>
        <button type="button" data-sync-connect>저장·불러오기</button>
        <button type="button" data-sync-disconnect hidden>연결 해제</button>
      </div>
      <span class="profile-sync-v1-status" role="status" aria-live="polite" data-sync-status>영문·숫자·-·_ 조합 6~32자</span>
      <p class="profile-sync-v1-note">비밀번호 없는 간편 동기화입니다. ID를 아는 사람은 해당 관심종목 목록을 불러오거나 변경할 수 있으므로 개인정보에는 사용하지 마세요.</p>
    `;
    summary.insertAdjacentElement('afterend', section);

    const input = section.querySelector('[data-sync-id]');
    const connect = section.querySelector('[data-sync-connect]');
    const disconnect = section.querySelector('[data-sync-disconnect]');

    if (activeId()) input.value = activeId();

    connect.addEventListener('click', () => connectOrPull(input.value));
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') connectOrPull(input.value);
    });
    disconnect.addEventListener('click', () => {
      setActiveId('');
      input.value = '';
      updateUi();
      setStatus('이 기기에서 동기화 연결을 해제했습니다. 서버의 목록은 유지됩니다.');
    });
    updateUi();
    return true;
  }

  async function fetchProfile(id) {
    return fetch(`/api/profile-sync/${encodeURIComponent(id)}`, {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
  }

  async function saveProfile(id, quiet = false) {
    const cleanId = normalizeId(id);
    if (!cleanId) {
      if (!quiet) setStatus('ID는 6~32자의 영문, 숫자, -, _만 사용할 수 있어요.', 'error');
      return false;
    }
    const response = await fetch(`/api/profile-sync/${encodeURIComponent(cleanId)}`, {
      method: 'PUT',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ watchlist: readWatchlist() }),
    });
    if (!response.ok) {
      let message = '동기화 저장에 실패했습니다.';
      try { message = (await response.json()).detail || message; } catch (_) { }
      throw new Error(message);
    }
    setActiveId(cleanId);
    if (!quiet) {
      updateUi();
      setStatus(`${cleanId} ID에 현재 관심종목을 저장했습니다.`, 'ok');
    }
    return true;
  }

  async function connectOrPull(value) {
    if (busy) return;
    const id = normalizeId(value);
    if (!id) {
      setStatus('ID는 6~32자의 영문, 숫자, -, _만 사용할 수 있어요.', 'error');
      return;
    }
    busy = true;
    const root = document.getElementById('profile-sync-v1');
    root?.querySelectorAll('button,input').forEach((node) => { node.disabled = true; });
    setStatus('동기화 ID를 확인하는 중…');
    try {
      const response = await fetchProfile(id);
      if (response.status === 404) {
        await saveProfile(id, false);
        return;
      }
      if (!response.ok) {
        let message = '동기화 목록을 불러오지 못했습니다.';
        try { message = (await response.json()).detail || message; } catch (_) { }
        throw new Error(message);
      }
      const payload = await response.json();
      const remote = Array.isArray(payload.watchlist) ? payload.watchlist : [];
      writeWatchlist(remote);
      setActiveId(id);
      setStatus(`${id} ID의 관심종목 ${remote.length}개를 불러왔습니다.`, 'ok');
      window.setTimeout(() => window.location.reload(), 350);
    } catch (error) {
      setStatus(error?.message || '동기화 중 오류가 발생했습니다.', 'error');
    } finally {
      busy = false;
      root?.querySelectorAll('button,input').forEach((node) => { node.disabled = false; });
      updateUi();
    }
  }

  function queueAutoSave() {
    const id = activeId();
    if (!id) return;
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(async () => {
      try {
        await saveProfile(id, true);
        setStatus(`${id} ID에 관심종목 변경사항을 저장했습니다.`, 'ok');
      } catch (error) {
        setStatus(`자동 저장 실패 · ${error?.message || '네트워크를 확인해 주세요.'}`, 'error');
      }
    }, 700);
  }

  function init() {
    mount();
    window.setTimeout(mount, 400);
    window.setTimeout(mount, 1200);
    document.addEventListener('chartview:watchlist-change', queueAutoSave);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
