"""S&P 500 (US500) PAPER signals for the page - version A (sp_engine.py; MT4-proven 22 Oct 2026, his run SP500_DAYTRADE v1.00:
2,330 trades 2020-01..2026-09, net $16,398 at $100 risk per leg, net/DD 6.23, worst day -$310). No phone alerts, no real money.
Called by run.py after the Nasdaq page, every minute. The day's Nasdaq picks come from docs/nq_picks.json (written by nq_run the same minute).
Files: docs/sp_min/YYYY-MM.npz (finished days of minute bars, broker clock, bid; if missing, the first run seeds the last 4 weeks from
Capital.com minutes, then each new day is added), docs/journal_sp.json (every paper trade), docs/data.json -> markets.US500 (the page)."""
import os, glob, json, time, requests, numpy as np, pandas as pd
import feeds as F, sp_engine as S
DEADLINE = time.time() + 240          # loop.py resets this every minute; the S&P part never holds up gold

HERE = os.path.dirname(os.path.abspath(__file__))
MIN = os.path.join(HERE, 'docs', 'sp_min'); JOUR = os.path.join(HERE, 'docs', 'journal_sp.json')
PORTAL = os.path.join(HERE, 'docs', 'data.json'); PICKS = os.path.join(HERE, 'docs', 'nq_picks.json')
EPIC = os.environ.get('CAPITAL_EPIC_SP', 'US500')
MIN_SPREAD = S.COST                   # the paper result never uses less than 0.8 index points per leg (as in the MT4 test)
PASS = dict(green=40.0, pf=1.15, months=3)
RULES = 'v1.00'
BACKTEST = dict(direction='—', days='43% profit days / 85% traded', perday='1.39', win='52.5%', pf='1.30', net='+$16,398 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.00 (his run 22 Oct, spread 0.8 pt), 2020-01-01..2026-09-30, 2,330 legs; worst day -$310; net/DD 6.23')

def loadj(p, d):
    try: return json.load(open(p))
    except Exception: return d
def dumpj(o, p, **kw):
    tmp = p + '.tmp'
    with open(tmp, 'w') as f: json.dump(o, f, **kw)
    os.replace(tmp, p)
def dubai(t): return F.broker_to_dubai(pd.Timestamp(t)).strftime('%-I:%M %p').lower()

def load_month(f):
    if not os.path.exists(f): return None
    z = np.load(f); return pd.DataFrame({'o': z['o'], 'h': z['h'], 'l': z['l'], 'c': z['c']}, index=pd.DatetimeIndex(z['t'].astype('datetime64[m]')))
def load_hist():
    fr = [load_month(f) for f in sorted(glob.glob(os.path.join(MIN, '*.npz')))]
    fr = [x for x in fr if x is not None]
    if not fr: raise RuntimeError('docs/sp_min history missing')
    return pd.concat(fr).sort_index()
def save_day(bars):
    os.makedirs(MIN, exist_ok=True); per = bars.index[0].strftime('%Y-%m'); f = os.path.join(MIN, per + '.npz')
    old = load_month(f); d = pd.concat([old, bars[['o', 'h', 'l', 'c']]]) if old is not None else bars[['o', 'h', 'l', 'c']]
    d = d[~d.index.duplicated(keep='last')].sort_index(); tmp = f + '.part'
    with open(tmp, 'wb') as fh:
        np.savez_compressed(fh, t=d.index.values.astype('datetime64[m]').astype(np.int64), o=d.o.values, h=d.h.values, l=d.l.values, c=d.c.values)
    os.replace(tmp, f)

EPIC_NOW = [EPIC]; _TRIED = [False]
def find_epic(feed):
    """Look up the US 500 epic in Capital.com's market list (used only if the default name is refused)."""
    r = requests.get(f'{feed.base}/api/v1/markets', headers=feed.h, timeout=20, params={'searchTerm': 'US 500'}); r.raise_for_status()
    for mkt in r.json().get('markets', []):
        nm = str(mkt.get('instrumentName', '')).lower()
        if ('us 500' in nm or 's&p' in nm) and 'future' not in nm:
            EPIC_NOW[0] = mkt['epic']; print('S&P epic found:', EPIC_NOW[0]); return
    raise RuntimeError('US 500 not found in Capital.com markets - set CAPITAL_EPIC_SP')

def minutes(feed, start_b, end_b):
    """Capital.com US 500 minute bars between two broker times: index broker time, Bid o/h/l/c + spread (ask close - bid close)."""
    if feed.h is None: feed.login()
    to_utc = lambda b: (pd.Timestamp(b) - pd.Timedelta(hours=7)).tz_localize(F.NY, ambiguous=False, nonexistent='shift_forward').tz_convert('UTC').tz_localize(None)
    t0, end = to_utc(start_b), to_utc(end_b); out = []
    while t0 < end:
        if time.time() > DEADLINE: raise TimeoutError('S&P time budget used up - next run continues')
        t1 = min(end, t0 + pd.Timedelta(minutes=900))
        r = requests.get(f'{feed.base}/api/v1/prices/{EPIC_NOW[0]}', headers=feed.h, timeout=20,
                         params={'resolution': 'MINUTE', 'max': 1000, 'from': t0.strftime('%Y-%m-%dT%H:%M:%S'), 'to': t1.strftime('%Y-%m-%dT%H:%M:%S')})
        if r.status_code == 200:
            for p in r.json().get('prices', []):
                ask = (p.get('closePrice') or {}).get('ask')
                out.append((p['snapshotTimeUTC'], p['openPrice']['bid'], p['highPrice']['bid'], p['lowPrice']['bid'], p['closePrice']['bid'],
                            np.nan if ask is None else ask - p['closePrice']['bid']))
        elif r.status_code == 404 and 'epic' in r.text.lower() and not _TRIED[0]:
            _TRIED[0] = True; find_epic(feed); continue
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

def seed(feed, day, get):
    """No stored history yet: fetch the last 4 weeks of finished weekdays from Capital.com (oldest first; a timeout keeps what was saved)."""
    for d in pd.bdate_range(day - pd.Timedelta(days=28), day - pd.Timedelta(days=1)):
        b = get(feed, d, d + pd.Timedelta(days=1)); b = b[(b.index >= d) & (b.index < d + pd.Timedelta(days=1))]
        if len(b) >= 60: save_day(b)

def picks_for(day):
    """Today's Nasdaq desk picks [(nasdaq minute, side)] from docs/nq_picks.json; ([], note) if the file is not for today."""
    p = loadj(PICKS, {})
    if p.get('day') != str(day.date()): return [], 'Nasdaq picks for today not written yet'
    return [(pd.Timestamp(t), int(s)) for t, s in p.get('picks', [])], None

def row(t, b, now, sp):
    st = t['status']
    res = None if t['pts'] is None else round(t['pts'], 1)
    live = None
    if st == 'open' and len(b):
        pxn = float(b.c.values[-1]); live = round(t['dir'] * (pxn - t['entry']) - sp, 1)
    return dict(time=dubai(t['t']), side='BUY' if t['dir'] == 1 else 'SELL', name=t['name'], src='Nasdaq' if t['src'] == 0 else 'S&P', leg=t['leg'],
                price=round(t['entry'], 1), entry=round(t['entry'], 1), stop=round(t['stop'], 1), stop0=round(t['stop0'], 1), stop_pts=round(t['sd'], 1),
                half_px=None, half=False, size='full', status=st,
                exit=None if t['exit'] is None else round(t['exit'], 1), exit_time=None if t['exit_t'] is None else dubai(t['exit_t']),
                res=res, res_sized=res, r=None if t['r'] is None else round(t['r'], 3), r_sized=None if t['r'] is None else round(t['r'], 3),
                live=live, spread=round(sp, 2))

def summary(J, day=None):
    D3 = [d for d in J.get('days', []) if d.get('rules') == RULES]
    if not D3: return dict(since=None, trades=0, rules=RULES)
    allt = [t for d in D3 for t in d['trades']]; rr = [t['res'] for t in allt if t.get('res') is not None]
    start = D3[0]['date']; end = str((day or pd.Timestamp(D3[-1]['date'])).date())
    wd = max(1, len(pd.bdate_range(start, end))); tdays = sum(1 for d in D3 if d['trades'])
    gp, gl = sum(p for p in rr if p > 0), -sum(p for p in rr if p < 0)
    return dict(since=pd.Timestamp(start).strftime('%d %b %Y'), weekdays=wd, trades=len(allt), days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                closed=len(rr), win=(round(100 * sum(p > 0 for p in rr) / len(rr), 1) if rr else None), pf=(round(gp / gl, 2) if gl > 0 else None),
                net=round(sum(rr), 1) if rr else None, rules=RULES, direction=None,
                green=round(100 * sum(1 for d in D3 if sum(t.get('res') or 0 for t in d['trades']) > 0) / wd, 1))

def jdays(J): return J.get('days', [])[-30:][::-1]

def base_card(A=None):
    note = ('14-day range ' + ('—' if A is None else f'{A:,.0f} pts') + ' · stop 0.75 x range' + ('' if A is None else f' (= {0.75 * A:,.0f} pts)') +
            ' · no half-close · the day\'s first signal sets BUY or SELL, later signals the same way add (max 3 trades) · signals: Nasdaq desk signals '
            'copied in US hours + S&P 9:40 am New York move, yesterday high/low sweep, big move by 10 am New York · close 10:30 pm broker = 11:30 pm Dubai '
            '(3:30 pm New York; 12:30 am Dubai in winter)')
    return dict(code='US500', name='S&P 500', symbol='US500 · Capital.com US 500', live=False, paper=True, status='Paper', version=RULES,
                unit='pts', dp=1, stats=BACKTEST, pass_bar=PASS, day_note=note,
                what_note='Tracks whether live S&P signals do as well as the v1.00 MT4 test. Decision after about 3 months.',
                cost_note='Results are index points per trade after 0.8 points of cost (Capital.com spread + slippage).',
                net_label='Net points (v1.00 rules)')

def main(feed=None, get=None, now=None):
    now = now or F.broker_now(); day = now.normalize()
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    J = loadj(JOUR, dict(start=None, days=[]))
    if now.dayofweek >= 5:
        prev = mk.get('US500') or {}
        mk['US500'] = dict({k: v for k, v in prev.items() if k not in ('status', 'note')}, **base_card(), state='closed', message='Market closed for the weekend.',
                           entries=[], journal=summary(J), jdays=jdays(J), feed_error=False)
        dumpj(old, PORTAL, indent=1); print('S&P: weekend'); return
    get = get or minutes
    if feed is None:
        if not os.environ.get('CAPITAL_API_KEY'): raise RuntimeError('S&P paper needs the Capital.com prices')
        feed = F.Capital()
    try: hist = load_hist()
    except RuntimeError: seed(feed, day, get); hist = load_hist()
    added = catch_up(feed, hist, day, get)
    if added: hist = load_hist()
    b = get(feed, day, now); b = b[(b.index >= day) & (b.index + pd.Timedelta(minutes=1) <= now)]
    eod = day + pd.Timedelta(minutes=S.eod_minutes(day)); xt = day + pd.Timedelta(minutes=S.X_MIN)
    spread = float(np.nanmedian(b.sp.values)) if len(b) and np.isfinite(b.sp.values).any() else None
    sp = max(MIN_SPREAD, spread or 0.0)
    picks, pnote = picks_for(day)
    trades = S.run_day(hist[hist.index < day].iloc[-40 * 1500:], b[['o', 'h', 'l', 'c']], day, picks, sp=sp, day_over=bool(now >= eod)) if len(b) else []
    for t in trades:                                     # past the 3:30 pm New York close but no bar there yet: close at the last price
        if t['status'] == 'open' and now >= xt + pd.Timedelta(minutes=1) and len(b):
            ex = float(b.c.values[-1]); t.update(status='eod', exit=ex, exit_t=b.index[-1], pts=t['dir'] * (ex - t['entry']) - sp)
            t['r'] = t['pts'] / t['sd']
    rows = [row(t, b, now, sp) for t in trades]
    last = float(b.c.iloc[-1]) if len(b) else None; first = float(b.o.iloc[0]) if len(b) else None
    spark = []
    if len(b):
        g5 = b[['o', 'h', 'l', 'c']].resample('5min').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'}).dropna()
        spark = [[F.broker_to_dubai(t).strftime('%-I:%M %p').lower(), round(float(r.c), 1), round(float(r.o), 1), round(float(r.h), 1), round(float(r.l), 1)] for t, r in g5.iterrows()]
    if J.get('start') is None: J['start'] = str(day.date())
    J['days'] = sorted([d for d in J['days'] if d['date'] != str(day.date())] +
                       [dict(date=str(day.date()), rules=RULES, label=day.strftime('%a %d %b'), side=(rows[0]['side'] if rows else None), trades=rows,
                             final=bool(now >= eod))], key=lambda d: d['date'])
    J['summary'] = summary(J, day); dumpj(J, JOUR, indent=1)
    A = trades[0]['A'] if trades else S.day_ctx(hist[hist.index < day].iloc[-40 * 1500:], day)[0]
    if rows:
        op = [r for r in rows if r['status'] == 'open']; state = rows[0]['side'].lower()
        msg = (f"PAPER {rows[0]['side']} day: {len(rows)} trade{'s' if len(rows) > 1 else ''} today ({len(op)} running). Only {rows[0]['side']} signals count today "
               f"(max 3). Each trade keeps its stop, no half-close; everything closes at {dubai(xt)} Dubai (3:30 pm New York).")
    elif now >= xt: state, msg = 'none', 'No paper trade today.'
    else: state, msg = 'waiting', 'Waiting for the first signal (from 5:30 pm Dubai: 9:40 am New York move, Nasdaq signals; earlier: yesterday high/low sweep).'
    if pnote and now.hour * 60 + now.minute >= S.US_LO: msg += f' ({pnote}.)'
    mk['US500'] = dict(base_card(A if A == A else None), state=state, message=msg, price=last, change=(None if last is None or first is None else round(last - first, 1)),
                       entries=rows, spark=spark, journal=J['summary'], jdays=jdays(J), feed_error=False, epic=EPIC_NOW[0], close_at=dubai(xt),
                       history_note=f"history to {hist.index[-1].date()} ({hist.index.normalize().nunique()} days)" + (f" · added {', '.join(added)}" if added else ''))
    dumpj(old, PORTAL, indent=1)
    print(f'S&P paper: {now} broker | bars {len(b)} | picks {len(picks)} | legs {len(rows)} | history to {hist.index[-1].date()} | added {added}')

def fail(e):
    """Keep the last good S&P card and say what failed."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {}); c = mk.get('US500') or {}
    c.update(base_card()); c.setdefault('entries', []); c.setdefault('state', 'waiting'); c['feed_error'] = True
    c['message'] = f"S&P paper update failed at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({type(e).__name__}: {str(e)[:120]}) — shows the last good update; retries every minute."
    mk['US500'] = c; dumpj(old, PORTAL, indent=1)
