const API_ROOT = 'https://api.github.com';
const KST_OFFSET_MS = 9 * 60 * 60 * 1000;

function githubHeaders(token) {
  return {
    Accept: 'application/vnd.github+json',
    Authorization: `Bearer ${token}`,
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'chart-view-cloudflare-screener-watchdog'
  };
}

function kstParts(now = new Date()) {
  const shifted = new Date(now.getTime() + KST_OFFSET_MS);
  return {
    date: shifted.toISOString().slice(0, 10),
    weekday: shifted.getUTCDay(),
    hour: shifted.getUTCHours(),
    minute: shifted.getUTCMinutes()
  };
}

export function shouldCheckNow(now = new Date()) {
  const { weekday, hour, minute } = kstParts(now);
  if (weekday === 0 || weekday === 6) return false;
  const minutes = hour * 60 + minute;
  return minutes >= 16 * 60 && minutes <= 18 * 60;
}

async function githubRequest(fetchImpl, url, { token, method = 'GET', body } = {}) {
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetchImpl(url, {
        method,
        headers: githubHeaders(token),
        ...(body ? { body: JSON.stringify(body) } : {}),
        signal: controller.signal
      });
      if (response.ok) return response;
      const detail = (await response.text().catch(() => '')).slice(0, 300);
      lastError = Error(`GitHub API returned HTTP ${response.status}${detail ? `: ${detail}` : ''}`);
      if (response.status !== 429 && response.status < 500) break;
    } catch (error) {
      lastError = error;
    } finally {
      clearTimeout(timer);
    }
    if (attempt < 3) await new Promise(resolve => setTimeout(resolve, 500 * attempt));
  }
  throw lastError;
}

export function skipReason({ today, meta, runs }) {
  if (String(meta?.tradeDate || '') === today && Number(meta?.exactDateCoverage || 0) >= 0.90) {
    return `screener ${today} already published with sufficient coverage`;
  }
  for (const run of runs || []) {
    if (run.status === 'queued' || run.status === 'in_progress') return `screener run ${run.id} is ${run.status}`;
  }
  return '';
}

export async function dispatchScreener({ env, now = new Date(), fetchImpl = fetch, log = console.log }) {
  if (!shouldCheckNow(now)) return { dispatched: false, reason: 'outside KST weekday 16:00-18:00 window' };
  const token = String(env.GITHUB_ACTIONS_TOKEN || '').trim();
  if (!token) throw Error('GITHUB_ACTIONS_TOKEN secret is required.');
  const repository = env.GITHUB_REPOSITORY || 'shoon94parkk-del/chart_View';
  const workflow = env.GITHUB_WORKFLOW || 'update-screener.yml';
  const ref = env.GITHUB_REF_NAME || 'main';
  const today = kstParts(now).date;
  const encodedRepo = repository.split('/').map(encodeURIComponent).join('/');
  const metaUrl = `https://raw.githubusercontent.com/${encodedRepo}/${encodeURIComponent(ref)}/static/data/screener_meta.json?t=${now.getTime()}`;
  const runsUrl = `${API_ROOT}/repos/${encodedRepo}/actions/workflows/${encodeURIComponent(workflow)}/runs?per_page=10`;
  const [metaResponse, runsResponse] = await Promise.all([
    fetchImpl(metaUrl, { headers: { 'User-Agent': 'chart-view-cloudflare-screener-watchdog' } }).catch(() => null),
    githubRequest(fetchImpl, runsUrl, { token })
  ]);
  const meta = metaResponse?.ok ? await metaResponse.json().catch(() => null) : null;
  const runs = await runsResponse.json();
  const reason = skipReason({ today, meta, runs: runs.workflow_runs || [] });
  if (reason) {
    log(`No dispatch needed: ${reason}.`);
    return { dispatched: false, reason };
  }
  const dispatchUrl = `${API_ROOT}/repos/${encodedRepo}/actions/workflows/${encodeURIComponent(workflow)}/dispatches`;
  await githubRequest(fetchImpl, dispatchUrl, { token, method: 'POST', body: { ref } });
  log(`Dispatched ${repository}/${workflow}@${ref} for ${today}.`);
  return { dispatched: true, today };
}

export default {
  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(dispatchScreener({ env }).catch(error => console.error(`Chart View screener watchdog failed: ${error?.message || String(error)}`)));
  },
  async fetch() {
    return new Response('Chart View screener watchdog is active.', { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
  }
};
