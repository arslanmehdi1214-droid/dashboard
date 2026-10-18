"""NASDAQ 100 PAPER signals for the page - ONE version since 18 Oct 2026: US100 = simple signals (Nasdaq prices only, nq_set.json) with the
v1.01 EXITS (nq_engine.manage_v101; MT4-proven on these signals' trades, his run 18 Oct). The full version (US100F) was removed from the page
(same trades so far, worse with the v1.01 exits); its old journal docs/journal_nqf.json is left untouched.
Original note: (no phone alerts, no real money). Called by run.py after gold, USDJPY and WTI, every minute.
Replays today's Capital.com US Tech 100 minutes through the Nasdaq walk-forward set (nq_engine.py + nq_set.json = the 2026 set,
re-picked each January on all earlier years; parity with the research trades: 194 of 194 days of 2026, same minute, side and price)
and keeps a paper journal, judged after ~3 months (pass = right way first >= 52.5% and profit factor >= 1.10 after the spread).
Files: docs/nq_min/YYYY-MM.npz (finished days of minute bars, broker clock, bid; seeded from HistData to 2026-09-30, then extended with
Capital.com minutes), docs/journal_nq.json (every paper trade), docs/data.json -> markets.US100 (the page)."""
import os, glob, json, time, requests, numpy as np, pandas as pd
import feeds as F, nq_engine as N
DEADLINE = time.time() + 240          # loop.py resets this every minute; the Nasdaq part never holds up gold

HERE = os.path.dirname(os.path.abspath(__file__))
MIN = os.path.join(HERE, 'docs', 'nq_min'); JOUR = os.path.join(HERE, 'docs', 'journal_nq.json')
PORTAL = os.path.join(HERE, 'docs', 'data.json')
EPIC = os.environ.get('CAPITAL_EPIC_NQ', 'US100')
MIN_SPREAD = 1.8                      # the paper result never uses less than 1.8 index points (Capital.com US Tech 100 page)
PASS = dict(green=55.0, pf=1.10, months=3)
RULES = 'v1.01'                       # journal days are tagged; the card's record counts only the current rules
BACKTEST = dict(direction='—', days='58.7% green / 95.3% traded', perday='1.32', win='64.9%', pf='1.24', net='+$102,485 at $1,000 risk per full trade',
                source='MT4 replay with the v1.01 exits (his run 18 Oct, spread 1.8 pts), 2020-01-01..2026-09-30, 2,327 trades; worst day -$2,039')
BACKTEST_F = dict(direction='53.2%', days='97%', perday='1.33', win='—', pf='1.17', net='+10.1 pts per weekday',
                  source='Python walk-forward 2020-2026 (signals re-picked each January, never seen when picked), 1.8 pt spread; '
                         'MT4 replay of the same trades (his run): 2,308 trades, PF 1.16, net +17,109 pts')
VARIANTS = [dict(code='US100', name='Nasdaq 100', S=N.SET, jour=JOUR, stats=BACKTEST,
                 what='Tracks whether live Nasdaq signals do as well as the v1.01 backtest. Decision after about 3 months.')]
REMOVED = ['US100F']                  # cards taken off the page on 18 Oct 2026

def loadj(p, d):
    try: return json.load(open(p))
    except Exception: return d
def dumpj(o, p, **kw):
    tmp = p + '.tmp'
    with open(tmp, 'w') as f: json.dump(o, f, **kw)
    os.replace(tmp, p)
def dubai(t): return F.broker_to_dubai(pd.Timestamp(t)).strftime('%-I:%M %p').lower()

def load_hist():
    fr = []
    for f in sorted(glob.glob(os.path.join(MIN, '*.npz'))):
        z = np.load(f); fr.append(pd.DataFrame({'o': z['o'], 'h': z['h'], 'l': z['l'], 'c': z['c']}, index=pd.DatetimeIndex(z['t'].astype('datetime64[m]'))))
    if not fr: raise RuntimeError('docs/nq_min history missing')
    return pd.concat(fr).sort_index()

def save_day(bars):
    """Add one finished broker day of minute bars to its month file."""
    per = bars.index[0].strftime('%Y-%m'); f = os.path.join(MIN, per + '.npz')
    old = load_month(f); d = pd.concat([old, bars[['o', 'h', 'l', 'c']]]) if old is not None else bars[['o', 'h', 'l', 'c']]
    d = d[~d.index.duplicated(keep='last')].sort_index()
    tmp = f + '.part'
    with open(tmp, 'wb') as fh:
        np.savez_compressed(fh, t=d.index.values.astype('datetime64[m]').astype(np.int64), o=d.o.values, h=d.h.values, l=d.l.values, c=d.c.values)
    os.replace(tmp, f)
def load_month(f):
    if not os.path.exists(f): return None
    z = np.load(f); return pd.DataFrame({'o': z['o'], 'h': z['h'], 'l': z['l'], 'c': z['c']}, index=pd.DatetimeIndex(z['t'].astype('datetime64[m]')))

EPIC_NOW = [EPIC]; _TRIED = [False]
def find_epic(feed):
    """Look up the US Tech 100 epic in Capital.com's market list (used only if the default name is refused)."""
    r = requests.get(f'{feed.base}/api/v1/markets', headers=feed.h, timeout=20, params={'searchTerm': 'US Tech 100'})
    r.raise_for_status()
    for mkt in r.json().get('markets', []):
        if 'tech 100' in str(mkt.get('instrumentName', '')).lower() and 'future' not in str(mkt.get('instrumentName', '')).lower():
            EPIC_NOW[0] = mkt['epic']; print('Nasdaq epic found:', EPIC_NOW[0]); return
    raise RuntimeError('US Tech 100 not found in Capital.com markets - set CAPITAL_EPIC_NQ')

def minutes(feed, start_b, end_b):
    """Capital.com US Tech 100 minute bars between two broker times: index broker time, Bid o/h/l/c + spread (ask close - bid close)."""
    if feed.h is None: feed.login()
    to_utc = lambda b: (pd.Timestamp(b) - pd.Timedelta(hours=7)).tz_localize(F.NY, ambiguous=False, nonexistent='shift_forward').tz_convert('UTC').tz_localize(None)
    t0, end = to_utc(start_b), to_utc(end_b); out = []
    while t0 < end:
        if time.time() > DEADLINE: raise TimeoutError('Nasdaq time budget used up - next run continues')
        t1 = min(end, t0 + pd.Timedelta(minutes=900))
        r = requests.get(f'{feed.base}/api/v1/prices/{EPIC_NOW[0]}', headers=feed.h, timeout=20,
                         params={'resolution': 'MINUTE', 'max': 1000, 'from': t0.strftime('%Y-%m-%dT%H:%M:%S'), 'to': t1.strftime('%Y-%m-%dT%H:%M:%S')})
        if r.status_code == 200:
            for p in r.json().get('prices', []):
                ask = (p.get('closePrice') or {}).get('ask')
                out.append((p['snapshotTimeUTC'], p['openPrice']['bid'], p['highPrice']['bid'], p['lowPrice']['bid'], p['closePrice']['bid'],
                            np.nan if ask is None else ask - p['closePrice']['bid']))
        elif r.status_code == 404 and 'epic' in r.text.lower() and not _TRIED[0]:
            _TRIED[0] = True; find_epic(feed); continue                  # wrong epic name: look it up once, then retry
        elif r.status_code not in (400, 404):
            r.raise_for_status()
        t0 = t1; time.sleep(0.15)
    if not out: return pd.DataFrame(columns=['o', 'h', 'l', 'c', 'sp'], index=pd.DatetimeIndex([]), dtype=float)
    d = pd.DataFrame(out, columns=['t', 'o', 'h', 'l', 'c', 'sp']).drop_duplicates('t')
    d.index = F.utc_to_broker(pd.to_datetime(d.t)); d = d[d.index.dayofweek < 5]
    return d[['o', 'h', 'l', 'c', 'sp']].astype(float).sort_index()

def catch_up(feed, hist, day, get=None):
    """Add every finished weekday after the last stored day and before `day` (Capital.com minutes)."""
    get = get or minutes; last = hist.index[-1].normalize(); added = []
    while last + pd.Timedelta(days=1) < day:
        nxt = last + pd.Timedelta(days=1)
        if nxt.dayofweek < 5:
            b = get(feed, nxt, nxt + pd.Timedelta(days=1)); b = b[(b.index >= nxt) & (b.index < nxt + pd.Timedelta(days=1))]
            if len(b) >= 60: save_day(b); added.append(str(nxt.date()))
            else: added.append(str(nxt.date()) + ' (no prices - holiday)')
        last = nxt
    return added

def rwf(b, j, d, px, A):
    """Right way first: +0.3 x range before -0.3 x range, until the day end (None = not decided yet / never)."""
    a = 0.3 * A
    for k in range(j + 1, len(b)):
        up = (b.h.values[k] - px) if d > 0 else (px - b.l.values[k]); dn = (px - b.l.values[k]) if d > 0 else (b.h.values[k] - px)
        if up >= a and dn >= a: return None
        if up >= a: return 1
        if dn >= a: return 0
    return None

def row(t, b, now, eod, spread):
    """One trade for the page. res = index points of the WHOLE trade at its v1.01 size (sells 1/3, the 25% part included), after the spread."""
    st = t['status']; sp = max(MIN_SPREAD, spread or 0.0); P = N.V101
    part_pts = P['part'] * t['dir'] * (t['half_px'] - t['entry']) if t['half'] else 0.0; rem = 1 - P['part'] if t['half'] else 1.0
    if st == 'open' and now >= eod and len(b):                  # day over without a close-time bar: close at the last price
        ex = float(b.c.values[-1]) + (0 if t['dir'] > 0 else sp)
        t = dict(t, status='eod', exit=ex, exit_t=b.index[-1], pts=t['w'] * (part_pts + rem * t['dir'] * (ex - t['entry']))); st = 'eod'
    res = None if t['pts'] is None else round(t['pts'], 1)
    j = int(np.searchsorted(b.index.values, np.datetime64(t['t'])))
    live = None
    if st == 'open' and len(b):
        pxn = float(b.c.values[-1]) + (0 if t['dir'] > 0 else sp); live = round(t['w'] * (part_pts + rem * t['dir'] * (pxn - t['entry'])), 1)
    return dict(time=dubai(t['t']), side='BUY' if t['dir'] == 1 else 'SELL', name=t['name'], role=t['role'], price=round(t['px'], 1), entry=round(t['entry'], 1),
                stop=round(t['stop'], 1), stop0=round(t['stop0'], 1), stop_pts=round(t['sd'], 1), half_px=round(t['half_px'], 1), half=bool(t['half']),
                half_time=None if t['half_t'] is None else dubai(t['half_t']), size=t['size'], status=st,
                exit=None if t['exit'] is None else round(t['exit'], 1), exit_time=None if t['exit_t'] is None else dubai(t['exit_t']),
                res=res, res_sized=res, r=None if t['r'] is None else round(t['r'], 3), r_sized=None if t['r'] is None else round(t['r'] * t['w'], 3),
                live=live, rwf=rwf(b, j, t['dir'], t['px'], t['A']), spread=round(sp, 2))

def summary(J, day=None):
    """Paper record of the CURRENT rules only (v1.01 days); older days (old exits, 12-16 Oct) stay in the journal but are not mixed in."""
    D3 = [d for d in J.get('days', []) if d.get('rules') == RULES]
    if not D3: return dict(since=None, trades=0, rules=RULES)
    J = dict(start=D3[0]['date'], days=D3)
    allt = [t for d in J.get('days', []) for t in d['trades']]
    dec = [t['rwf'] for t in allt if t.get('rwf') is not None]; rr = [t['res'] for t in allt if t.get('res') is not None]
    end = str((day or pd.Timestamp(J['days'][-1]['date'])).date()) if J.get('days') else J['start']
    wd = max(1, len(pd.bdate_range(J['start'], end))); tdays = sum(1 for d in J['days'] if d['trades'])
    gp, gl = sum(p for p in rr if p > 0), -sum(p for p in rr if p < 0)
    return dict(since=pd.Timestamp(J['start']).strftime('%d %b %Y'), weekdays=wd, trades=len(allt), decided=len(dec),
                direction=(round(100 * sum(dec) / len(dec), 1) if dec else None), days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                closed=len(rr), win=(round(100 * sum(p > 0 for p in rr) / len(rr), 1) if rr else None), pf=(round(gp / gl, 2) if gl > 0 else None),
                net=round(sum(rr), 1) if rr else None, rules=RULES,
                green=round(100 * sum(1 for d in J['days'] if sum(t.get('res') or 0 for t in d['trades']) > 0) / wd, 1))

def jdays(J): return J.get('days', [])[-30:][::-1]

def base_card(A=None, V=None):
    V = V or VARIANTS[0]
    note = ('14-day range ' + ('—' if A is None else f'{A:,.0f} pts') + ' · stop: buys ½ range, sells ¼ range · sells ⅓ size · close 25% at +0.5 x risk, '
            'then the rest at the entry · day lock +3R/+1.5R · max 2 trades a day · close 11:00 pm broker (Fri 10:50 pm) = 12:00 am Dubai, 1:00 am in winter')
    return dict(code=V['code'], name=V['name'], symbol='US100 · Capital.com US Tech 100', live=False, paper=True, status='Paper', version=V['S'].get('version', ''),
                unit='pts', dp=1, stats=V['stats'], pass_bar=PASS, day_note=note,
                what_note=V['what'],
                cost_note="Results are index points for the whole trade at its v1.01 size (sells ⅓, the 25% part included), after Capital.com's spread (at least 1.8 points).",
                net_label='Net points (v1.01 rules)')

def main(feed=None, get=None, now=None):
    now = now or F.broker_now(); day = now.normalize()
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    for c in REMOVED: mk.pop(c, None)
    if now.dayofweek >= 5:
        for V in VARIANTS:
            J = loadj(V['jour'], dict(start=None, days=[])); prev = mk.get(V['code']) or {}
            mk[V['code']] = dict({k: v for k, v in prev.items() if k not in ('status', 'note')}, **base_card(None, V), state='closed', message='Market closed for the weekend.',
                                 entries=[], journal=summary(J), jdays=jdays(J), feed_error=False)
        dumpj(old, PORTAL, indent=1); print('Nasdaq: weekend'); return
    get = get or minutes
    if feed is None:
        if not os.environ.get('CAPITAL_API_KEY'): raise RuntimeError('Nasdaq paper needs the Capital.com prices')
        feed = F.Capital()
    hist = load_hist()
    added = catch_up(feed, hist, day, get)
    if added: hist = load_hist()
    b = get(feed, day, now); b = b[(b.index >= day) & (b.index + pd.Timedelta(minutes=1) <= now)]      # today's closed minute bars only
    eod = day + pd.Timedelta(minutes=N.eod_minutes(day))
    allm = pd.concat([hist[hist.index < day].iloc[-N.KEEP_DAYS * 1500:], b[['o', 'h', 'l', 'c']]])
    spread = float(np.nanmedian(b.sp.values)) if len(b) and np.isfinite(b.sp.values).any() else None
    last = float(b.c.iloc[-1]) if len(b) else None; first = float(b.o.iloc[0]) if len(b) else None
    spark = []
    if len(b):
        g5 = b[['o', 'h', 'l', 'c']].resample('5min').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'}).dropna()   # 5-min candles for the page: [time, close, open, high, low]
        spark = [[F.broker_to_dubai(t).strftime('%-I:%M %p').lower(), round(float(r.c), 1), round(float(r.o), 1), round(float(r.h), 1), round(float(r.l), 1)] for t, r in g5.iterrows()]
    errs = []
    for V in VARIANTS:                                   # each version on its own: one failing never stops the other
        try:
            mk[V['code']] = variant(V, allm, b, day, now, eod, spread, last, first, spark, hist, added)
        except Exception as e:
            errs.append((V, e))
    for V, e in errs: mark_failed(mk, V, e)
    dumpj(old, PORTAL, indent=1)
    print(f'Nasdaq paper: {now} broker | bars {len(b)} | history to {hist.index[-1].date()} | added {added} | failed {[V["code"] for V, _ in errs]}')

def variant(V, allm, b, day, now, eod, spread, last, first, spark, hist, added):
    J = loadj(V['jour'], dict(start=None, days=[]))
    trades = N.run_day(allm, day, now, S=V['S'], exits='v1.01', sp=max(MIN_SPREAD, spread or 0.0)) if len(b) else []
    rows = [row(t, b, now, eod, spread) for t in trades]
    if J.get('start') is None: J['start'] = str(day.date())
    A = trades[0]['A'] if trades else None
    J['days'] = sorted([d for d in J['days'] if d['date'] != str(day.date())] +
                       [dict(date=str(day.date()), rules=RULES, label=day.strftime('%a %d %b'), side=(rows[0]['side'] if rows else None), trades=rows,
                             final=bool(now >= eod))], key=lambda d: d['date'])
    J['summary'] = summary(J, day)
    dumpj(J, V['jour'], indent=1)
    if rows:
        op = [r for r in rows if r['status'] == 'open']; state = rows[-1]['side'].lower()
        locked = bool(trades and trades[-1].get('locked_day'))
        msg = (f"{len(rows)} paper trade{'s' if len(rows) > 1 else ''} today ({len(op)} running). Each closes 25% at its part level, then the rest at the entry; "
               f"everything closes at the {dubai(eod)} Dubai close. At most 2 trades a day." + (" Day lock hit: no more trades today." if locked else ''))
    elif now >= eod: state, msg = 'none', 'No paper trade today.'
    else: state, msg = 'waiting', 'Waiting for the first signal.'
    return dict(base_card(A, V), state=state, message=msg, price=last, change=(None if last is None or first is None else round(last - first, 1)),
                entries=rows, spark=spark, journal=J['summary'], jdays=jdays(J), feed_error=False, epic=EPIC_NOW[0], close_at=dubai(eod),
                history_note=f"history to {hist.index[-1].date()} ({hist.index.normalize().nunique()} days)" + (f" · added {', '.join(added)}" if added else ''))

def mark_failed(mk, V, e):
    c = mk.get(V['code']) or {}
    c.update(base_card(None, V)); c.setdefault('entries', []); c.setdefault('state', 'waiting'); c['feed_error'] = True
    c['message'] = f"Nasdaq paper update failed at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({type(e).__name__}: {str(e)[:120]}) — shows the last good update; retries every minute."
    mk[V['code']] = c

def fail(e):
    """Keep the last good Nasdaq cards and say what failed."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    for c in REMOVED: mk.pop(c, None)
    for V in VARIANTS: mark_failed(mk, V, e)
    dumpj(old, PORTAL, indent=1)
