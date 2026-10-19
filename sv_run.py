"""SILVER v1.8 PAPER signals for the page (no phone alerts, no real money). Called by run.py after the other markets, every minute.
Rules = sv_engine.py (SILVER_DAYTRADE v1.8, HONEST live entries: an agreement completed by a compression break enters at the break price,
not the open of that minute; U4 news trade only if it comes before any U1 agreement that day). Parity: the engine re-creates all 1,050
research trades 2009-Sep 2026 (time, side, size, source) on his MT4 data (validate.py, 19 Oct 2026).
Voters: gold v2.06 engine signals (engine206ns = the research 'noskip' engine, signals not against the day's earlier trades), fast gold->silver
catch-up, compression breakout. Prices: Capital.com SILVER and GOLD minute bars (bid), broker clock = New York + 7 h.
Files: docs/sv_min/{SILVER,GOLD}_YYYY-MM.npz (finished days of Capital.com minute bars; the first run fetches the last ~5 weeks),
daily measures (14-day range, squeeze, ADX, band width) come from Capital.com hourly bars (460 days),
docs/journal_sv.json (every paper trade), docs/data.json -> markets.SILVER (the page)."""
import os, glob, json, time, requests, numpy as np, pandas as pd
import feeds as F, sv_engine as E
DEADLINE = time.time() + 240          # loop.py resets this every minute

HERE = os.path.dirname(os.path.abspath(__file__))
MIN = os.path.join(HERE, 'docs', 'sv_min'); JOUR = os.path.join(HERE, 'docs', 'journal_sv.json')
PORTAL = os.path.join(HERE, 'docs', 'data.json'); INPUTS = os.path.join(HERE, 'docs', 'inputs.json')
CAL = os.path.join(HERE, 'docs', 'calendar.json')
EPIC = {'SILVER': os.environ.get('CAPITAL_EPIC_SV', 'SILVER'), 'GOLD': os.environ.get('CAPITAL_EPIC', 'GOLD')}
SEARCH = {'SILVER': 'Silver', 'GOLD': 'Gold'}
MIN_SPREAD = 0.05                     # his Capital.com quote 19 Oct 2026: 57.698 / 57.748
OZ = 50                               # 0.01 lot of silver = 50 oz (page value; check against the broker's contract size)
KEEP_DAYS = 32                        # minute history used: 20-day correlation needs 15-20 earlier days
RULES = 'v1.8h'
PASS = dict(months=3, band='3-month net at 0.01 lot (50 oz) inside the backtest 5-95% band: -$87 .. +$227 (median +$8)')
BACKTEST = dict(direction='—', days='11.8% green / 21.7% traded', perday='0.22', win='54.3%', pf='1.26', net='+$26 per weekday at $1,000 risk (+$1.09 at 0.01 lot = 50 oz)',
                source='Python, honest entries (break price), Capital.com $0.05 spread = 8.66 bp, 2018-Mar 2026, 466 trades; 2010-17 +$15 per weekday, '
                       'PF 1.13; Apr-Sep 2026 -$4,343 (24 trades). MT4 v1.8 run (his, 19 Oct) used the old open-price entries.')


def loadj(p, d):
    try: return json.load(open(p))
    except Exception: return d
def dumpj(o, p, **kw):
    tmp = p + '.tmp'
    with open(tmp, 'w') as f: json.dump(o, f, **kw)
    os.replace(tmp, p)
def dubai(t): return F.broker_to_dubai(pd.Timestamp(t)).strftime('%-I:%M %p').lower()


# ---------------- minute history (one file per market per month) ----------------
def load_month(f):
    if not os.path.exists(f): return None
    z = np.load(f); return pd.DataFrame({'o': z['o'], 'h': z['h'], 'l': z['l'], 'c': z['c']}, index=pd.DatetimeIndex(z['t'].astype('datetime64[m]')))
def load_hist(mk, since=None):
    fr = [load_month(f) for f in sorted(glob.glob(os.path.join(MIN, f'{mk}_*.npz')))]
    fr = [x for x in fr if x is not None]
    if not fr: return pd.DataFrame(columns=['o', 'h', 'l', 'c'], index=pd.DatetimeIndex([]), dtype=float)
    d = pd.concat(fr).sort_index()
    return d if since is None else d[d.index >= since]
def save_day(mk, bars):
    per = bars.index[0].strftime('%Y-%m'); f = os.path.join(MIN, f'{mk}_{per}.npz')
    old = load_month(f); d = pd.concat([old, bars[['o', 'h', 'l', 'c']]]) if old is not None else bars[['o', 'h', 'l', 'c']]
    d = d[~d.index.duplicated(keep='last')].sort_index(); tmp = f + '.part'
    with open(tmp, 'wb') as fh:
        np.savez_compressed(fh, t=d.index.values.astype('datetime64[m]').astype(np.int64), o=d.o.values, h=d.h.values, l=d.l.values, c=d.c.values)
    os.replace(tmp, f)

_TRIED = set()
def find_epic(feed, mk):
    r = requests.get(f'{feed.base}/api/v1/markets', headers=feed.h, timeout=20, params={'searchTerm': SEARCH[mk]}); r.raise_for_status()
    for m in r.json().get('markets', []):
        nm = str(m.get('instrumentName', '')).lower()
        if nm.startswith(SEARCH[mk].lower()) and 'future' not in nm and 'etf' not in nm:
            EPIC[mk] = m['epic']; print(mk, 'epic found:', EPIC[mk]); return
    raise RuntimeError(f'{SEARCH[mk]} not found in Capital.com markets')

def minutes(feed, mk, start_b, end_b):
    """Capital.com minute bars between two broker times: index broker time, bid o/h/l/c + spread (ask close - bid close)."""
    if getattr(feed, 'h', None) is None: feed.login()
    to_utc = lambda b: (pd.Timestamp(b) - pd.Timedelta(hours=7)).tz_localize(F.NY, ambiguous=False, nonexistent='shift_forward').tz_convert('UTC').tz_localize(None)
    t0, end = to_utc(start_b), to_utc(end_b); out = []
    while t0 < end:
        if time.time() > DEADLINE: raise TimeoutError('silver time budget used up - next run continues')
        t1 = min(end, t0 + pd.Timedelta(minutes=900))
        r = requests.get(f'{feed.base}/api/v1/prices/{EPIC[mk]}', headers=feed.h, timeout=20,
                         params={'resolution': 'MINUTE', 'max': 1000, 'from': t0.strftime('%Y-%m-%dT%H:%M:%S'), 'to': t1.strftime('%Y-%m-%dT%H:%M:%S')})
        if r.status_code == 200:
            for p in r.json().get('prices', []):
                ask = (p.get('closePrice') or {}).get('ask')
                out.append((p['snapshotTimeUTC'], p['openPrice']['bid'], p['highPrice']['bid'], p['lowPrice']['bid'], p['closePrice']['bid'],
                            np.nan if ask is None else ask - p['closePrice']['bid']))
        elif r.status_code == 404 and 'epic' in r.text.lower() and mk not in _TRIED:
            _TRIED.add(mk); find_epic(feed, mk); continue
        elif r.status_code not in (400, 404):
            r.raise_for_status()
        t0 = t1; time.sleep(0.15)
    if not out: return pd.DataFrame(columns=['o', 'h', 'l', 'c', 'sp'], index=pd.DatetimeIndex([]), dtype=float)
    d = pd.DataFrame(out, columns=['t', 'o', 'h', 'l', 'c', 'sp']).drop_duplicates('t')
    d.index = F.utc_to_broker(pd.to_datetime(d.t)); d = d[d.index.dayofweek < 5]
    return d[['o', 'h', 'l', 'c', 'sp']].astype(float).sort_index()

def catch_up(feed, mk, day, get):
    """Add every finished weekday after the last stored day and before `day`."""
    os.makedirs(MIN, exist_ok=True)
    hist = load_hist(mk); added = []
    last = hist.index[-1].normalize() if len(hist) else day - pd.Timedelta(days=KEEP_DAYS + 8)     # first run: ~5 weeks back
    while last + pd.Timedelta(days=1) < day:
        nxt = last + pd.Timedelta(days=1)
        if nxt.dayofweek < 5:
            b = get(feed, mk, nxt, nxt + pd.Timedelta(days=1)); b = b[(b.index >= nxt) & (b.index < nxt + pd.Timedelta(days=1))]
            if len(b) >= 60: save_day(mk, b); added.append(f'{mk} {nxt.date()}')
            else: added.append(f'{mk} {nxt.date()} (no prices - holiday)')
        last = nxt
    return added


# ---------------- inputs ----------------
def news_times(day):
    """US high-impact releases (Forex Factory calendar the desk already keeps), broker time."""
    out = []
    for e in loadj(CAL, []):
        try:
            if e.get('country') != 'USD' or e.get('impact') != 'High': continue
            t = pd.Timestamp(e['date'])
            t = t.tz_convert('UTC').tz_localize(None) if t.tzinfo else t
            b = F.utc_to_broker(pd.DatetimeIndex([t]))[0]
            if day - pd.Timedelta(days=1) <= b < day + pd.Timedelta(days=1): out.append(b)
        except Exception: continue
    return np.array(out, dtype='datetime64[m]')

def gold_signals(feed, day, now, gm):
    """Today's gold v2.06 engine signals (research 'noskip' engine, not against, not skipped). gm = today's closed gold minutes."""
    import engine206ns as G
    h1 = feed.h1(days=460)
    D1 = h1[h1.index < day]; g = D1.groupby(D1.index.normalize())
    D1 = pd.DataFrame({'o': g.o.first(), 'h': g.h.max(), 'l': g.l.min(), 'c': g.c.last()})
    D = G.Daily(D1.index.values.astype('datetime64[D]'), D1.o.values, D1.h.values, D1.l.values, D1.c.values)
    hh = h1[h1.index <= now]; Hh = G.Hourly(hh.index.values.astype('datetime64[m]'), hh.h.values, hh.l.values, hh.c.values)
    inp = loadj(INPUTS, {}).get(str(day.date()))
    if not inp: return [], [], 'gold inputs for today not ready yet (gold card writes them first)'
    dayst = np.datetime64(day.date(), 'D'); one_am = dayst.astype('datetime64[m]') + np.timedelta64(60, 'm'); reg = inp.get('regime')
    einp = dict(d5=inp['d5'], d1=inp['d1'], vix=inp['vix'], tnx=inp['tnx'], attn=inp.get('attn', 0),
                regime=lambda t: (reg if (reg is not None and t >= one_am) else 0))
    mm = dict(t=gm.index.values.astype('datetime64[m]'), o=gm.o.values, h=gm.h.values, l=gm.l.values, c=gm.c.values)
    sig = G.run_day(dayst, D, Hh, mm, einp) if len(gm) else []
    sig = [s for s in sig if not s.get('skipped') and not s.get('against')]
    return [s['t'] for s in sig], [s['dir'] for s in sig], None


# ---------------- page rows ----------------
ST = {'stop': 'stopped', 'day end': 'eod', 'open': 'open'}
def row(S, x, m, sp, now_j, eod, now):
    d = x['dir']; px = x['px']; A = x['A']; w = x['w']
    ent = px + (sp if d > 0 else 0.0)                       # buys pay the ask
    st = m['status']
    if st == 'trail': st = 'be' if abs(m['exit'] - px) < 1e-9 else 'trail'
    else: st = ST.get(st, st)
    res = None; live = None
    if m['exit'] is not None:
        xo = m['exit'] + (0.0 if d > 0 else sp)              # sells buy back at the ask
        part = 0.5 * d * (m['tgt'] - ent) if m['half'] else 0.0
        res = part + (0.5 if m['half'] else 1.0) * d * (xo - ent)
    elif now_j is not None:
        pxn = float(S.C[now_j]) + (0.0 if d > 0 else sp)
        part = 0.5 * d * (m['tgt'] - ent) if m['half'] else 0.0
        live = round(w * (part + (0.5 if m['half'] else 1.0) * d * (pxn - ent)), 3)
    risk = abs(ent - m['stop0'])
    return dict(time=dubai(x['t']), side='BUY' if d > 0 else 'SELL', name=x['via'], role='first trade of the day', price=round(ent, 3),
                signal_price=round(px, 3), stop=round(m['stop'], 3), stop0=round(m['stop0'], 3), half_px=round(m['tgt'], 3), part=0.5, half=bool(m['half']),
                half_time=None if m['half_j'] is None else dubai(S.T[m['half_j']]), size=w, status=st,
                exit=None if m['exit'] is None else round(m['exit'] + (0.0 if d > 0 else sp), 3),
                exit_time=None if m['exit_j'] is None else dubai(S.T[m['exit_j']]),
                res=None if res is None else round(res, 3), res_sized=None if res is None else round(res * w, 3),
                r=None if res is None else round(res / risk, 3), r_sized=None if res is None else round(w * res / risk, 3),
                live=live, spread=round(sp, 3), corr20=None if x['corr'] is None else round(x['corr'], 3), A=round(A, 3))

def summary(J, day=None):
    D3 = [d for d in J.get('days', []) if d.get('rules') == RULES]
    if not D3: return dict(since=None, trades=0, rules=RULES)
    allt = [t for d in D3 for t in d['trades']]; rr = [t['res_sized'] for t in allt if t.get('res_sized') is not None]
    end = str((day or pd.Timestamp(D3[-1]['date'])).date()); wd = max(1, len(pd.bdate_range(D3[0]['date'], end)))
    gp, gl = sum(p for p in rr if p > 0), -sum(p for p in rr if p < 0)
    return dict(since=pd.Timestamp(D3[0]['date']).strftime('%d %b %Y'), weekdays=wd, trades=len(allt), days=round(100 * len(allt) / wd, 1),
                perday=round(len(allt) / wd, 2), closed=len(rr), win=(round(100 * sum(p > 0 for p in rr) / len(rr), 1) if rr else None),
                pf=(round(gp / gl, 2) if gl > 0 else None), net=round(sum(rr), 3) if rr else None, net_usd=round(sum(rr) * OZ, 2) if rr else None,
                green=round(100 * sum(1 for d in D3 if sum(t.get('res_sized') or 0 for t in d['trades']) > 0) / wd, 1), rules=RULES)

def jdays(J): return J.get('days', [])[-30:][::-1]

def base_card(A=None):
    note = ('14-day range ' + ('—' if A is None else f'${A:.2f}') + ' · ONE trade a day when 2 of 3 agree (gold signal, fast gold catch-up, '
            'compression break) · stop ½ range · close half at +1x risk, stop to entry, then trail ½ range · 2x size when gold and silver '
            'were loosely linked over 20 days · close 11:00 pm broker (Fri 10:50 pm)')
    return dict(code='SILVER', name='Silver', symbol='SILVER · Capital.com Silver (spot)', live=False, paper=True, status='Paper', version=RULES,
                unit='$/oz', dp=3, stats=BACKTEST, pass_bar=PASS, day_note=note,
                what_note='Forward test of silver v1.8 (honest entries) on live Capital.com prices. Checked after about 3 months against the backtest band.',
                cost_note=f"Results are $ per oz for the whole trade (half banked at +1R included) after Capital.com's spread (at least ${MIN_SPREAD:.2f}); "
                          f"x size (1 or 2); page money at 0.01 lot = {OZ} oz.",
                net_label='Net $/oz (v1.8 honest rules)')


def main(feed=None, get=None, now=None, gsig=None):
    """gsig: optional function (feed, day, now, gold_minutes) -> (times, dirs, note) for tests."""
    now = now or F.broker_now(); day = now.normalize()
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    if now.dayofweek >= 5:
        J = loadj(JOUR, dict(start=None, days=[])); prev = mk.get('SILVER') or {}
        mk['SILVER'] = dict({k: v for k, v in prev.items() if k not in ('status', 'note')}, **base_card(None), state='closed',
                            message='Market closed for the weekend.', entries=[], journal=summary(J), jdays=jdays(J), feed_error=False)
        dumpj(old, PORTAL, indent=1); print('Silver: weekend'); return
    get = get or minutes; gsig = gsig or gold_signals
    if feed is None:
        if not os.environ.get('CAPITAL_API_KEY'): raise RuntimeError('Silver paper needs the Capital.com prices')
        feed = F.get_feed()[0]                          # loop.py: shared Capital.com session + hourly cache
    added = catch_up(feed, 'SILVER', day, get) + catch_up(feed, 'GOLD', day, get)
    since = day - pd.Timedelta(days=int(KEEP_DAYS * 1.5))
    hs, hg = load_hist('SILVER', since), load_hist('GOLD', since)
    b = get(feed, 'SILVER', day, now); b = b[(b.index >= day) & (b.index + pd.Timedelta(minutes=1) <= now)]     # closed minute bars only
    gb = get(feed, 'GOLD', day, now); gb = gb[(gb.index >= day) & (gb.index + pd.Timedelta(minutes=1) <= now)]
    spread = float(np.nanmedian(b.sp.values)) if len(b) and np.isfinite(b.sp.values).any() else MIN_SPREAD
    sp = max(MIN_SPREAD, spread)
    sv = pd.concat([hs[hs.index < day], b[['o', 'h', 'l', 'c']]]); gd = pd.concat([hg[hg.index < day], gb[['o', 'h', 'l', 'c']]])
    # day table: Capital.com hourly bars (460 days) built into broker days, + today so far from the minutes
    sh1 = feed.h1(days=460, epic=EPIC['SILVER']); sh1 = sh1[sh1.index < day]; g = sh1.groupby(sh1.index.normalize())
    DB = pd.DataFrame({'o': g.o.first(), 'h': g.h.max(), 'l': g.l.min(), 'c': g.c.last()})
    g = sv.groupby(sv.index.normalize()); dm = pd.DataFrame({'o': g.o.first(), 'h': g.h.max(), 'l': g.l.min(), 'c': g.c.last()})
    DB = pd.concat([DB, dm[~dm.index.isin(DB.index)]]).sort_index()            # hourly-built days + any minute day the hourly feed lacks (today)
    sv = sv[sv.index.normalize().isin(DB.index)]
    DT = E.day_table(DB)
    gg = gd.groupby(gd.index.normalize()); gdb = pd.DataFrame({'o': gg.o.first(), 'h': gg.h.max(), 'l': gg.l.min(), 'c': gg.c.last()})
    gh1 = feed.h1(days=460); d1 = gh1[gh1.index < day]; g1 = d1.groupby(d1.index.normalize())        # same hourly cache as the gold card
    gdb = pd.concat([pd.DataFrame({'o': g1.o.first(), 'h': g1.h.max(), 'l': g1.l.min(), 'c': g1.c.last()}), gdb[gdb.index >= day]]).sort_index()
    gA = E.gold_A(gdb)
    S = E.Span(sv.index.values, sv.o.values, sv.h.values, sv.l.values, sv.c.values, gd.index.values, gd.c.values, gA, DT)
    S.from_day = np.datetime64(day.date(), 'D')
    gt, gdir, gnote = gsig(feed, day, now, gb[['o', 'h', 'l', 'c']]) if len(gb) else ([], [], 'no gold minutes yet')
    X = E.signals(S, gt, gdir, news_times(day), honest=True)
    if len(X): X = X[pd.DatetimeIndex(X.t).normalize() == day]
    now_j = len(S.T) - 1 if len(b) else None
    eod = day + pd.Timedelta(minutes=(22 * 60 + 50) if day.dayofweek == 4 else 23 * 60)
    rows = []
    for _, x in X.iterrows():
        m = E.manage(S, int(x.j), int(x.dir), float(x.px), float(x.A), upto=now_j)
        if m['status'] == 'open' and now >= eod and now_j is not None:            # day over without a close-time bar
            m = dict(m, status='day end', exit=float(S.C[now_j]), exit_j=now_j)
        rows.append(row(S, x, m, sp, now_j, eod, now))
    J = loadj(JOUR, dict(start=None, days=[]))
    if J.get('start') is None: J['start'] = str(day.date())
    J['days'] = sorted([d for d in J['days'] if d['date'] != str(day.date())] +
                       [dict(date=str(day.date()), rules=RULES, label=day.strftime('%a %d %b'), side=(rows[0]['side'] if rows else None), trades=rows,
                             final=bool(now >= eod))], key=lambda d: d['date'])
    J['summary'] = summary(J, day); dumpj(J, JOUR, indent=1)
    last = float(b.c.iloc[-1]) if len(b) else None; first = float(b.o.iloc[0]) if len(b) else None
    spark = []
    if len(b):
        g5 = b[['o', 'h', 'l', 'c']].resample('5min').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'}).dropna()
        spark = [[F.broker_to_dubai(t).strftime('%-I:%M %p').lower(), round(float(r.c), 3), round(float(r.o), 3), round(float(r.h), 3), round(float(r.l), 3)] for t, r in g5.iterrows()]
    if rows:
        r0 = rows[0]; state = r0['side'].lower()
        msg = (f"Paper {r0['side']} at {dubai(X.t.iloc[0])} ({r0['name']} completed the 2-of-3 agreement, size {r0['size']}). "
               f"Half closes at {r0['half_px']:.3f}, then the stop moves to entry and trails; everything closes at {dubai(eod)} Dubai. One trade a day.")
    elif now >= eod: state, msg = 'none', 'No paper trade today (no 2-of-3 agreement).'
    else: state, msg = 'waiting', 'Waiting for 2 of 3 voters to agree (gold signal, fast gold catch-up, compression break).'
    if gnote: msg += f' · note: {gnote}'
    A = float(S.A[-1]) if len(S.A) and np.isfinite(S.A[-1]) else None
    mk['SILVER'] = dict(base_card(A), state=state, message=msg, price=last, change=(None if last is None or first is None else round(last - first, 3)),
                        entries=rows, spark=spark, journal=J['summary'], jdays=jdays(J), feed_error=False, epic=EPIC['SILVER'], close_at=dubai(eod),
                        gold_signals_today=len(gt), history_note=f"minutes from {sv.index[0].date()} ({sv.index.normalize().nunique()} days) · {DB.index.size} daily bars from {DB.index[0].date()}" + (f" · added {', '.join(added)}" if added else ''))
    dumpj(old, PORTAL, indent=1)
    print(f'Silver paper: {now} broker | bars {len(b)} gold {len(gb)} | gold signals {len(gt)} | trades {len(rows)} | added {added}')

def fail(e):
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {}); c = mk.get('SILVER') or {}
    if c.get('status') == 'NOT LIVE': c = {}
    c.update(base_card(None)); c.setdefault('entries', []); c.setdefault('state', 'waiting'); c['feed_error'] = True
    c['message'] = f"Silver paper update failed at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({type(e).__name__}: {str(e)[:120]}) — shows the last good update; retries every minute."
    mk['SILVER'] = c; dumpj(old, PORTAL, indent=1)
