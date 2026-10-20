"""DEMO AUTO-TRADER (20 Oct 2026). Copies the Signal Desk's trades onto the Capital.com DEMO account, every minute, inside loop.py.

How it works (one pass per minute, right after the desk engines ran):
  * reads docs/data.json (the desk's own trades for today, all markets)
  * NEW desk trade (status open, at most MAX_AGE_MIN old)  -> opens it on demo at market with the desk's stop.
      If the desk trade has a part-close level, it is opened as TWO positions: the "part" (desk part %) with a take-profit at the
      part-close level, and the "rest" with the same stop.
  * desk part done (half = true)                           -> part position closed (if the take-profit has not already done it)
  * desk stop changed (stop to entry, Nasdaq trail)        -> stop moved on every position of that trade
  * desk trade closed (stop / day end / day lock / reverse) -> every position of that trade closed
  * positions gone on Capital.com (their own stop/target)   -> marked closed here
  Desk trades older than MAX_AGE_MIN when first seen are NOT entered (no late entries at a worse price).

Safety: works ONLY on the demo server (CAPITAL_DEMO=1) and only when AUTOTRADE=1; touches ONLY positions it opened itself
(their deal ids are kept in autotrade_state.json); caps new positions per minute and open positions in total; any error is
logged and the desk carries on. Sizes: AUTOTRADE_RISK_USD dollars lost if a FULL-size trade hits its first stop (1/3-size
trades risk one third)."""
import os, json, time, datetime as dt, requests

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, 'autotrade_state.json')
LOG_FILE = os.path.join(HERE, 'autotrade_log.json')
PORTAL = os.path.join(HERE, 'docs', 'data.json')
DEMO_BASE = 'https://demo-api-capital.backend-capital.com'
CONFIG_FILE = os.path.join(HERE, 'autotrade_config.json')   # {"on": true, "risk_usd": 100, "max_age_min": 5, "split": true} - edit this file to switch off / resize
def _cfg():
    try:
        with open(CONFIG_FILE) as f: return json.load(f)
    except Exception: return {}
CFG = _cfg()
RISK_USD = float(os.environ.get('AUTOTRADE_RISK_USD', CFG.get('risk_usd', 100)))
MAX_AGE_MIN = float(os.environ.get('AUTOTRADE_MAX_AGE_MIN', CFG.get('max_age_min', 5)))
SPLIT = bool(CFG.get('split', True))
MAX_NEW_PER_PASS = 8          # new positions per minute, all markets
MAX_OPEN_TOTAL = 24           # positions open at once, all markets
MARKETS = {                   # desk code -> Capital.com epic, quote currency
    'GOLD': dict(epic='GOLD', quote='USD'),
    'USDJPY': dict(epic='USDJPY', quote='JPY'),
    'OIL': dict(epic='OIL_CRUDE', quote='USD'),
    'US100': dict(epic='US100', quote='USD'),
    'SILVER': dict(epic='SILVER', quote='USD'),
}
DUBAI = dt.timezone(dt.timedelta(hours=4))

def enabled():
    on = os.environ.get('AUTOTRADE', '1' if _cfg().get('on') else '0') == '1'      # re-read every minute: switching off works at once
    return on and os.environ.get('CAPITAL_DEMO', '1') == '1'

# ---------------------------------------------------------------- Capital.com demo client
class Demo:
    def __init__(self, session_maker=None):
        self.base = DEMO_BASE                                       # hard-wired: never the live server
        self.key = os.environ['CAPITAL_API_KEY']; self.ident = os.environ['CAPITAL_IDENTIFIER']; self.pw = os.environ['CAPITAL_API_PASSWORD']
        self.h = None; self.rules = {}; self.http = requests.Session(); self.last_order = 0.0
    def login(self):
        r = self.http.post(self.base + '/api/v1/session', headers={'X-CAP-API-KEY': self.key, 'Content-Type': 'application/json'},
                           json={'identifier': self.ident, 'password': self.pw, 'encryptedPassword': False}, timeout=20)
        r.raise_for_status(); self.h = {'X-SECURITY-TOKEN': r.headers['X-SECURITY-TOKEN'], 'CST': r.headers['CST']}
    def req(self, method, path, **kw):
        if self.h is None: self.login()
        for attempt in (0, 1):
            r = self.http.request(method, self.base + path, headers=self.h, timeout=20, **kw)
            if r.status_code == 401 and attempt == 0: self.login(); continue
            return r
    def positions(self):
        r = self.req('GET', '/api/v1/positions'); r.raise_for_status()
        out = {}
        for p in r.json().get('positions', []):
            q = p.get('position', {}); m = p.get('market', {})
            out[q.get('dealId')] = dict(epic=m.get('epic'), size=q.get('size'), level=q.get('level'), direction=q.get('direction'),
                                        stop=q.get('stopLevel'), profit=q.get('profitLevel'), bid=m.get('bid'), offer=m.get('offer'))
        return out
    def market_rules(self, epic):
        if epic not in self.rules:
            r = self.req('GET', '/api/v1/markets/' + epic); r.raise_for_status(); j = r.json()
            dr = j.get('dealingRules', {}) or {}; ins = j.get('instrument', {}) or {}; sn = j.get('snapshot', {}) or {}
            mn = float((dr.get('minDealSize') or {}).get('value') or 0.01)
            inc = float((dr.get('minSizeIncrement') or {}).get('value') or mn)
            dp = sn.get('decimalPlacesFactor')
            self.rules[epic] = dict(min=mn, inc=inc, dp=int(dp) if dp is not None else 5, bid=sn.get('bid'), offer=sn.get('offer'),
                                    status=sn.get('marketStatus'), contract=max(1.0, _num(ins.get('contractSize'), 1.0)))
        return self.rules[epic]
    def _pace(self):                                               # opening orders: max one per 0.1 s (Capital.com limit) -> keep 0.25 s
        w = 0.25 - (time.time() - self.last_order)
        if w > 0: time.sleep(w)
        self.last_order = time.time()
    def confirm(self, ref):
        for _ in range(6):
            r = self.req('GET', '/api/v1/confirms/' + ref)
            if r.status_code == 200:
                j = r.json(); deals = j.get('affectedDeals') or []
                did = (deals[0].get('dealId') if deals else None) or j.get('dealId')
                return j.get('dealStatus'), did, j.get('level'), j.get('reason')
            time.sleep(0.4)
        return 'UNKNOWN', None, None, 'no confirm'
    def open(self, epic, direction, size, stop, profit=None):
        self._pace(); body = dict(epic=epic, direction=direction, size=size, guaranteedStop=False, stopLevel=stop)
        if profit is not None: body['profitLevel'] = profit
        r = self.req('POST', '/api/v1/positions', json=body)
        if r.status_code != 200: return 'REJECTED', None, None, f'http {r.status_code} {r.text[:160]}'
        return self.confirm(r.json().get('dealReference'))
    def set_stop(self, deal, stop, profit=None):
        body = dict(stopLevel=stop) if profit is None else dict(stopLevel=stop, profitLevel=profit)
        r = self.req('PUT', '/api/v1/positions/' + deal, json=body)
        return r.status_code == 200, r.text[:160]
    def close(self, deal):
        self._pace(); r = self.req('DELETE', '/api/v1/positions/' + deal)
        return r.status_code == 200, r.text[:160]

# ---------------------------------------------------------------- helpers
def _num(x, d):
    try: return float(x)
    except Exception: return d
def broker_day(now):
    """Broker day = New York time + 7 h (the desk's day)."""
    from zoneinfo import ZoneInfo
    return (now.astimezone(ZoneInfo('America/New_York')).replace(tzinfo=None) + dt.timedelta(hours=7)).strftime('%Y-%m-%d')
def load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return default
def save(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f: json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)
def now_dubai(): return dt.datetime.now(DUBAI)
def entry_time(txt, now):
    """Desk time '1:06 pm' (Dubai) -> the latest Dubai datetime at that clock time that is not in the future."""
    t = dt.datetime.strptime(txt.strip().upper(), '%I:%M %p').time()
    c = dt.datetime.combine(now.date(), t, tzinfo=DUBAI)
    return c if c <= now + dt.timedelta(minutes=1) else c - dt.timedelta(days=1)
def weight(code, e):
    s = e.get('size')
    if code == 'GOLD': return 1.0                                   # one-position gold: every leg is size 1
    if isinstance(s, (int, float)): return float(s)
    s = str(s).lower()
    return 1.0 if s in ('full', '1', '1.0') else (1 / 3 if s in ('third', '1/3', '⅓') else 1.0)
def key_of(code, e, day):
    return '|'.join(str(x) for x in (code, day, e.get('time'), e.get('side'), e.get('tag') or e.get('name') or e.get('sig') or ''))
def rnd_size(x, rules):
    inc = rules['inc'] or 0.01; n = int(x / inc + 1e-9) * inc
    return round(n, 6)
def rnd_px(x, rules): return None if x is None else round(float(x), max(0, min(8, rules['dp'])))

# ---------------------------------------------------------------- one pass
_API = [None]
def run_once(api=None, portal=PORTAL, now=None):
    if not enabled(): return 'off'
    now = now or now_dubai(); stamp = now.strftime('%a %d %b %I:%M %p').replace(' 0', ' ')
    st = load(STATE_FILE, {'trades': {}}); log = load(LOG_FILE, [])
    def note(market, what, detail, ok=True):
        log.append(dict(t=stamp, market=market, action=what, detail=detail, ok=ok)); print('AUTOTRADE', market, what, detail, 'ok' if ok else 'FAILED')
    try:
        D = load(portal, {}); mk = D.get('markets', {})
        if api is None:
            if _API[0] is None: _API[0] = Demo()
            api = _API[0]
        live = api.positions()                                     # what is really open on the demo account
        T = st['trades']
        # 1) positions that disappeared (their own stop / take-profit on Capital.com)
        for k, tr in T.items():
            for role in ('part', 'rest'):
                d = tr.get(role)
                if d and d.get('open') and d['id'] not in live:
                    d['open'] = False; d['closed_by'] = 'Capital.com stop/target'; note(tr['market'], f'{role} closed on demo', k)
        closes, opens, moves = [], [], []; today = broker_day(now)
        seen = set(); read_ok = set()
        for code, cfg in MARKETS.items():
            m = mk.get(code) or {}
            if m.get('feed_error') in (True, 'True'): continue        # desk not sure of its prices: change nothing this minute
            day = today; read_ok.add(code)
            for e in m.get('entries') or []:
                k = key_of(code, e, day); seen.add(k); tr = T.get(k); status = e.get('status')
                if tr is None:
                    age = (now - entry_time(e['time'], now)).total_seconds() / 60
                    if status == 'open' and age <= MAX_AGE_MIN: opens.append((code, cfg, e, k))
                    else: T[k] = dict(market=code, state='not entered', why=f'desk trade seen {age:.0f} min after entry, status {status}', at=stamp)
                    continue
                if tr.get('state') != 'open': continue
                if status != 'open':                                   # desk closed it (stop, day end, day lock, reverse, close_now)
                    closes.append((k, tr, f'desk: {status}'))
                    continue
                if e.get('half') and tr.get('part') and tr['part'].get('open'):
                    closes.append((k, dict(tr, rest=None), 'desk: part close'))
                want = e.get('stop')
                if want is not None and abs(float(want) - float(tr.get('stop', want))) > 1e-9: moves.append((k, tr, float(want)))
        # trades we still hold from an EARLIER desk day (the day-end close was missed): close them
        # ... or whose desk row has vanished for 3 minutes in a row (the desk re-drew its day): close them too
        for k, tr in T.items():
            if tr.get('state') != 'open' or k in seen: 
                if tr.get('missing'): tr['missing'] = 0
                continue
            if k.split('|')[1] < today: closes.append((k, tr, 'left over from an earlier day'))
            elif tr['market'] in read_ok:
                tr['missing'] = tr.get('missing', 0) + 1
                if tr['missing'] >= 3: closes.append((k, tr, 'desk row gone 3 minutes'))
        # 2) closes first (so a reverse never meets the old position)
        for k, tr, why in closes:
            for role in ('part', 'rest'):
                d = tr.get(role)
                if d and d.get('open'):
                    ok, msg = api.close(d['id']) if d['id'] in live else (True, 'already gone')
                    if ok: T[k][role]['open'] = False; T[k][role]['closed_by'] = why
                    note(tr['market'], f'close {role}', f'{k} ({why}) {"" if ok else msg}', ok)
            if not any((T[k].get(r) or {}).get('open') for r in ('part', 'rest')): T[k]['state'] = 'closed'
        # 3) stop moves
        for k, tr, want in moves:
            if T[k].get('state') != 'open': continue
            rules = api.market_rules(MARKETS[tr['market']]['epic']); s = rnd_px(want, rules); ok_all = True
            for role in ('part', 'rest'):
                d = T[k].get(role)
                if d and d.get('open'):
                    ok, msg = api.set_stop(d['id'], s, d.get('tp'))
                    ok_all &= ok
                    if not ok: note(tr['market'], f'move stop {role} FAILED', f'{k} to {s}: {msg}', False)
            if ok_all: T[k]['stop'] = want; note(tr['market'], 'stop moved', f'{k} to {s}')
        # 4) opens
        n_open = sum(1 for tr in T.values() for r in ('part', 'rest') if (tr.get(r) or {}).get('open'))
        for code, cfg, e, k in opens[:MAX_NEW_PER_PASS]:
            if n_open >= MAX_OPEN_TOTAL: T[k] = dict(market=code, state='not entered', why='too many open positions', at=stamp); note(code, 'skip', k, False); continue
            rules = api.market_rules(cfg['epic'])
            px = float(e['price']); stop0 = float(e.get('stop0') or e['stop']); dist = abs(px - stop0)
            if dist <= 0: T[k] = dict(market=code, state='not entered', why='zero stop distance', at=stamp); continue
            usd_per_unit = (dist / px if cfg['quote'] == 'JPY' else dist) * rules['contract']
            size = RISK_USD * weight(code, e) / usd_per_unit
            part = float(e.get('part', 0.5)) if (SPLIT and e.get('half_px') is not None and not e.get('half')) else 0.0
            p_size = rnd_size(size * part, rules) if part > 0 else 0.0
            r_size = rnd_size(size - p_size, rules)
            if p_size < rules['min'] or r_size < rules['min']:          # too small to split: one position, part handled by the stop move
                p_size = 0.0; r_size = max(rnd_size(size, rules), rules['min'])
            side = 'BUY' if e['side'] == 'BUY' else 'SELL'; stop = rnd_px(e['stop'], rules); tp = rnd_px(e.get('half_px'), rules)
            T[k] = dict(market=code, state='open', side=side, stop=float(e['stop']), desk_price=px, opened_at=stamp, risk_usd=round(RISK_USD * weight(code, e), 2))
            for role, sz, prof in (('part', p_size, tp), ('rest', r_size, None)):
                if sz <= 0: continue
                stt, did, lvl, why = api.open(cfg['epic'], side, sz, stop, prof)
                if stt == 'ACCEPTED' and did:
                    T[k][role] = dict(id=did, size=sz, level=lvl, tp=prof, open=True); n_open += 1
                    note(code, f'OPEN {side} {role}', f'{k} size {sz} at {lvl} stop {stop}' + (f' target {prof}' if prof else ''))
                else:
                    note(code, f'open {role} REJECTED', f'{k} size {sz} stop {stop}: {stt} {why}', False)
            if not any((T[k].get(r) or {}).get('open') for r in ('part', 'rest')): T[k]['state'] = 'not entered'; T[k]['why'] = 'rejected by Capital.com'
        if opens:                                                   # same-direction positions must stay separate (else switch "split" off)
            after = api.positions(); mine = {d['id'] for tr in T.values() for r in ('part', 'rest') for d in [tr.get(r)] if d and d.get('open')}
            for k2, tr in T.items():
                for r in ('part', 'rest'):
                    d = tr.get(r)
                    if d and d.get('open') and d['id'] not in after: note(tr['market'], f'CHECK {r} not on account right after opening', k2, False)
            epics = {c['epic'] for c in MARKETS.values()}
            for did, p in after.items():
                if p.get('epic') in epics and did not in mine: note('ALL', 'untracked position on demo (not ours / merged?) - left alone', f"{p.get('epic')} {p.get('direction')} {p.get('size')}", False)
        for code, cfg, e, k in opens[MAX_NEW_PER_PASS:]:
            T[k] = dict(market=code, state='not entered', why='too many new trades in one minute', at=stamp)
        # keep 4 days of state, 400 log lines
        cut = (now - dt.timedelta(days=4)).strftime('%Y-%m-%d')
        st['trades'] = {k: v for k, v in T.items() if v.get('state') == 'open' or k.split('|')[1] >= cut}
        st['risk_usd'] = RISK_USD; st['open_positions'] = sum(1 for tr in st['trades'].values() for r in ('part', 'rest') if (tr.get(r) or {}).get('open'))
        save(STATE_FILE, st); save(LOG_FILE, log[-400:])
        return 'ok'
    except Exception as ex:
        note('ALL', 'error', f'{type(ex).__name__}: {str(ex)[:200]}', False); _API[0] = None
        try: save(STATE_FILE, st); save(LOG_FILE, log[-400:])
        except Exception: pass
        return 'error'
