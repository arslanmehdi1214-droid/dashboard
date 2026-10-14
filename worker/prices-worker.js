// Signal Desk — live price relay (Cloudflare Worker, free plan)
// Reads Capital.com's own prices for the 4 desk markets and returns ONLY prices.
// Your Capital.com keys stay here as encrypted secrets; they never reach the desk page.
//
// Secrets to add in Cloudflare (Settings > Variables and Secrets), same values as the GitHub secrets:
//   CAPITAL_API_KEY, CAPITAL_IDENTIFIER, CAPITAL_API_PASSWORD
// Plain variable:  CAPITAL_DEMO = 1  (1 = demo server, like the desk now; 0 = live server)

const EPICS = ['GOLD', 'USDJPY', 'OIL_CRUDE', 'US100'];
const ALLOWED = ['https://arslanmehdi1214-droid.github.io', 'null']; // 'null' = opening the page from a file on your computer
const CACHE_SECONDS = 2;          // one Capital.com call serves every viewer for 2 seconds
let session = null;               // { cst, token, at } kept while the worker stays warm
let last = null;                  // { body, at } short memory cache (the Cache API does nothing on workers.dev)

function base(env) {
  return env.CAPITAL_DEMO === '0' ? 'https://api-capital.backend-capital.com' : 'https://demo-api-capital.backend-capital.com';
}

async function login(env) {
  const r = await fetch(base(env) + '/api/v1/session', {
    method: 'POST',
    headers: { 'X-CAP-API-KEY': env.CAPITAL_API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier: env.CAPITAL_IDENTIFIER, password: env.CAPITAL_API_PASSWORD, encryptedPassword: false }),
  });
  if (!r.ok) throw new Error('login ' + r.status);
  session = { cst: r.headers.get('CST'), token: r.headers.get('X-SECURITY-TOKEN'), at: Date.now() };
}

async function markets(env) {
  // Capital.com sessions expire after 10 minutes without use; renew at 8.
  if (!session || Date.now() - session.at > 8 * 60 * 1000) await login(env);
  let r = await fetch(base(env) + '/api/v1/markets?epics=' + EPICS.join(','), {
    headers: { 'X-SECURITY-TOKEN': session.token, CST: session.cst },
  });
  if (r.status === 401) { await login(env); r = await fetch(base(env) + '/api/v1/markets?epics=' + EPICS.join(','), { headers: { 'X-SECURITY-TOKEN': session.token, CST: session.cst } }); }
  if (!r.ok) throw new Error('markets ' + r.status);
  session.at = Date.now();
  const j = await r.json();
  const out = {};
  for (const m of j.marketDetails || []) {
    const s = m.snapshot || {}, epic = (m.instrument || {}).epic;
    if (!epic) continue;
    out[epic] = { bid: s.bid, ask: s.offer, mid: s.bid != null && s.offer != null ? (s.bid + s.offer) / 2 : null,
                  status: s.marketStatus, time: s.updateTime || null };
  }
  return out;
}

// Forex Factory week calendar (free). Fetched at most once an hour - their feed blocks frequent requests.
let cal = null;
async function calendar(req) {
  if (!cal || Date.now() - cal.at > 60 * 60 * 1000) {
    try {
      const r = await fetch('https://nfs.faireconomy.media/ff_calendar_thisweek.json', { headers: { 'User-Agent': 'Mozilla/5.0 (signal-desk)' } });
      if (r.ok) cal = { body: await r.text(), at: Date.now() };
    } catch (e) {}
  }
  return new Response(cal ? cal.body : '[]', { headers: cors(req) });
}

function cors(req) {
  const o = req.headers.get('Origin') || '';
  return { 'Access-Control-Allow-Origin': ALLOWED.includes(o) ? o : ALLOWED[0], 'Vary': 'Origin',
           'Content-Type': 'application/json', 'Cache-Control': 'no-store' };
}

export default {
  async fetch(req, env, ctx) {
    if (req.method === 'OPTIONS') return new Response(null, { headers: cors(req) });
    if (new URL(req.url).pathname === '/calendar') return calendar(req);
    if (last && Date.now() - last.at < CACHE_SECONDS * 1000) return new Response(last.body, { headers: cors(req) });
    try {
      const body = JSON.stringify({ at: new Date().toISOString(), source: 'Capital.com', prices: await markets(env) });
      last = { body, at: Date.now() };
      return new Response(body, { headers: cors(req) });
    } catch (e) {
      session = null;
      return new Response(JSON.stringify({ error: String(e.message || e) }), { status: 502, headers: cors(req) });
    }
  },
};
