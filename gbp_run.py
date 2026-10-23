"""GBP/USD PAPER signals for the page - GBP_CROWD v1.02 rules (gbp_engine.py; MT4-proven 23 Oct 2026, his run 3: 3,320 trades
2011-01..2026-06, net $8,652.74 at 0.10 lot, max DD $2,090.54, net/DD 4.14, PF 1.12, all 4 periods positive). One trade a day at most,
manual (the demo auto-trader does NOT copy GBP/USD - his choice B, 23 Oct). No phone alerts, no real money.
Called by run.py every minute. Each run: (1) the weekly CFTC British Pound report (publicreporting.cftc.gov, free, no key) is re-read
at most once an hour and cached in docs/cftc_gbp.json - the desk keeps working on the cached report if the CFTC site is down;
(2) the 14-day average range from Capital.com hourly bars; (3) today's Capital.com minute bars (bid + spread) -> gbp_engine.trade();
(4) docs/journal_gbp.json (every paper trade) and docs/data.json -> markets.GBPUSD (the page)."""
import os, json, time, requests, numpy as np, pandas as pd
import feeds as F, gbp_engine as E
DEADLINE = time.time() + 240          # loop.py resets this every minute; the GBP part never holds up gold

HERE = os.path.dirname(os.path.abspath(__file__))
JOUR = os.path.join(HERE, 'docs', 'journal_gbp.json'); PORTAL = os.path.join(HERE, 'docs', 'data.json')
CFTC = os.path.join(HERE, 'docs', 'cftc_gbp.json')
CFTC_URL = 'https://publicreporting.cftc.gov/resource/gpe5-46if.json'
EPIC = os.environ.get('CAPITAL_EPIC_GBP', 'GBPUSD')
RULES = 'v1.02'
PASS = dict(pf=1.10, months=3)
BACKTEST = dict(direction='—', days='82% of weekdays traded, max 1 a day', perday='0.82', win='9.8% hit target · 51.4% closed in profit', pf='1.12',
                net='+$8,652.74 at 0.10 lot (net/DD 4.14)',
                source='MT4 test GBP_CROWD v1.02 (his run 3, 23 Oct, spread 1.8 pips), 2011-01..2026-06-19, 3,320 trades; max DD $2,090.54; worst day -$231.50; all 4 periods positive')

class FeedError(RuntimeError):
    pass

_DAILY = {}                            # today's daily-range table (kept between minutes inside one desk job)

def loadj(p, d):
    try: return json.load(open(p))
    except Exception: return d
def dumpj(o, p, **kw):
    tmp = p + '.tmp'
    with open(tmp, 'w') as f: json.dump(o, f, **kw)
    os.replace(tmp, p)
def dubai(t): return F.broker_to_dubai(pd.Timestamp(t)).strftime('%-I:%M %p').lower()

# ---------------- weekly CFTC report ----------------
def cftc_rows(get=None):
    """Cached weekly rows; refreshed from the CFTC site at most once an hour. Returns (rows, note)."""
    c = loadj(CFTC, {}); rows = c.get('rows') or []; note = None
    if time.time() - float(c.get('fetched', 0)) >= 3600 or not rows:
        try:
            if get is not None: new = get()
            else:
                r = requests.get(CFTC_URL, timeout=20, params={'$where': "cftc_contract_market_code='096742'", '$order': 'report_date_as_yyyy_mm_dd DESC', '$limit': 200,
                                 '$select': 'report_date_as_yyyy_mm_dd,open_interest_all,lev_money_positions_long,lev_money_positions_short,nonrept_positions_long_all,nonrept_positions_short_all'})
                r.raise_for_status()
                new = [dict(d=str(x['report_date_as_yyyy_mm_dd'])[:10], oi=float(x['open_interest_all']), lev_l=float(x['lev_money_positions_long']),
                            lev_s=float(x['lev_money_positions_short']), nr_l=float(x['nonrept_positions_long_all']), nr_s=float(x['nonrept_positions_short_all'])) for x in r.json()]
            if len(new) >= 60:
                rows = sorted({x['d']: x for x in rows + new}.values(), key=lambda x: x['d'])[-260:]
                dumpj(dict(fetched=time.time(), source=CFTC_URL, rows=rows), CFTC, indent=0)
            else: note = f'CFTC site returned only {len(new)} weeks - using the saved report'
        except Exception as e:
            note = f'CFTC site not reachable ({type(e).__name__}) - using the saved report'
            if rows: dumpj(dict(c, fetched=time.time() - 3000), CFTC, indent=0)      # retry in ~10 min, not every minute
    if not rows: raise FeedError('no CFTC report saved yet and the CFTC site is not reachable')
    return rows, note

def weekly(rows):
    W = pd.DataFrame(rows); W.index = pd.to_datetime(W.pop('d')); return E.codes(W[['oi', 'lev_l', 'lev_s', 'nr_l', 'nr_s']].astype(float))

# ---------------- prices ----------------
def to_utc(b): return (pd.Timestamp(b) - pd.Timedelta(hours=7)).tz_localize(F.NY, ambiguous=False, nonexistent='shift_forward').tz_convert('UTC').tz_localize(None)

def prices(feed, res, start_b, end_b, step):
    """Capital.com GBP/USD bars between two broker times: index broker time, Bid o/h/l/c + spread (ask close - bid close)."""
    if feed.h is None: feed.login()
    t0, end = to_utc(start_b), to_utc(end_b); out = []
    while t0 < end:
        if time.time() > DEADLINE: raise TimeoutError('GBP time budget used up - next run continues')
        t1 = min(end, t0 + step)
        r = requests.get(f'{feed.base}/api/v1/prices/{EPIC}', headers=feed.h, timeout=20,
                         params={'resolution': res, 'max': 1000, 'from': t0.strftime('%Y-%m-%dT%H:%M:%S'), 'to': t1.strftime('%Y-%m-%dT%H:%M:%S')})
        if r.status_code == 200:
            for p in r.json().get('prices', []):
                ask = (p.get('closePrice') or {}).get('ask')
                out.append((p['snapshotTimeUTC'], p['openPrice']['bid'], p['highPrice']['bid'], p['lowPrice']['bid'], p['closePrice']['bid'],
                            np.nan if ask is None else ask - p['closePrice']['bid']))
        elif r.status_code not in (400, 404): r.raise_for_status()
        t0 = t1; time.sleep(0.15)
    if not out: return pd.DataFrame(columns=['o', 'h', 'l', 'c', 'sp'], index=pd.DatetimeIndex([]), dtype=float)
    d = pd.DataFrame(out, columns=['t', 'o', 'h', 'l', 'c', 'sp']).drop_duplicates('t')
    d.index = F.utc_to_broker(pd.to_datetime(d.t)); d = d[d.index.dayofweek < 5]
    return d[['o', 'h', 'l', 'c', 'sp']].astype(float).sort_index()

def minutes(feed, start_b, end_b): return prices(feed, 'MINUTE', start_b, end_b, pd.Timedelta(minutes=900))
def daily(feed, day):
    """weekday high/low per broker day from hourly bars of the last 35 days (before today)."""
    h = prices(feed, 'HOUR', day - pd.Timedelta(days=35), day, pd.Timedelta(hours=900))
    h = h[h.index < day]
    if not len(h): return pd.DataFrame(columns=['h', 'l'])
    return h.groupby(h.index.normalize()).agg(h=('h', 'max'), l=('l', 'min'))

def feed_check(b, now):
    """None if today's closed bars look fresh, else the reason (01:00-23:30 broker only)."""
    hm = now.hour * 60 + now.minute
    if hm < 60 or hm > 23 * 60 + 30: return None
    if not len(b): return 'no price bars received for today'
    age = now - (b.index[-1] + pd.Timedelta(minutes=1))
    if age > pd.Timedelta(minutes=5): return f'newest closed price bar ({dubai(b.index[-1])} Dubai) is {age.total_seconds() / 60:.0f} min old'
    return None

# ---------------- page rows / journal ----------------
def row(t, now_px, cost):
    s = t['dir']; st = t['status']; dp = 5
    live = None if st != 'open' or now_px is None else round((s * (now_px - t['entry']) - cost) * 1e4, 1)
    nxt = None
    if st == 'open':
        nxt = (f"Hold · stop {t['stop']:.5f} · target {t['target']:.5f} (close the WHOLE trade there) · no half-close, no stop move · "
               f"closes at {dubai(t['t'].normalize() + pd.Timedelta(minutes=E.CLOSE_MIN))} Dubai")
    return dict(time=dubai(t['t']), side='BUY' if s == 1 else 'SELL', name=E.LAYER_NAME[t['layer']], layer=t['layer'],
                price=round(t['entry'], dp), entry=round(t['entry'], dp), stop=round(t['stop'], dp), stop0=round(t['stop'], dp), stop_pips=round(t['sd'] * 1e4, 1),
                half_px=round(t['target'], dp), half=(st == 'target'), part=1.0, size='full', status=st,
                exit=None if t['exit'] is None else round(t['exit'], dp), exit_time=None if t['exit_t'] is None else dubai(t['exit_t']),
                pips=None if t['pips'] is None else round(t['pips'], 1), res=None if t['pips'] is None else round(t['pips'], 1),
                res_sized=None if t['pips'] is None else round(t['pips'], 1), r=None if t['pips'] is None else round(t['pips'] / (t['sd'] * 1e4), 3),
                live=live, spread=round(cost * 1e4, 2), next=nxt)

def summary(J, day=None):
    D3 = [d for d in J.get('days', []) if d.get('rules') == RULES]
    if not D3: return dict(since=None, trades=0, rules=RULES)
    allt = [t for d in D3 for t in d['trades']]; rr = [t['pips'] for t in allt if t.get('pips') is not None]
    start = D3[0]['date']; end = str((day or pd.Timestamp(D3[-1]['date'])).date())
    wd = max(1, len(pd.bdate_range(start, end))); tdays = sum(1 for d in D3 if d['trades'])
    gp, gl = sum(p for p in rr if p > 0), -sum(p for p in rr if p < 0)
    return dict(since=pd.Timestamp(start).strftime('%d %b %Y'), weekdays=wd, trades=len(allt), days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                closed=len(rr), win=(round(100 * sum(t.get('status') == 'target' for t in allt) / len(rr), 1) if rr else None),
                inprofit=(round(100 * sum(p > 0 for p in rr) / len(rr), 1) if rr else None), pf=(round(gp / gl, 2) if gl > 0 else None),
                net=round(sum(rr), 1) if rr else None, rules=RULES, direction=None,
                green=round(100 * sum(1 for d in D3 if sum(t.get('pips') or 0 for t in d['trades']) > 0) / wd, 1))

def jdays(J): return J.get('days', [])[-30:][::-1]

def base_card(A=None, rep=None, code=0):
    rp = '—' if rep is None else pd.Timestamp(rep).strftime('%a %d %b')
    lay = {0: 'no layer on - no trade this week', 1: 'layer 1 (hedge funds crowded)', 2: 'layer 2 (small traders crowded)', 3: 'layer 3 (small traders jumped in)'}[abs(code)]
    note = (f"This week: {'BUY' if code > 0 else 'SELL' if code < 0 else 'NO TRADE'} days · {lay} · CFTC report of {rp} · 14-day range "
            + ('—' if A is None else f'{A * 1e4:.0f} pips') + ' · stop 1.0 x range, target 1.0 x stop (close the whole trade there), no half-close · '
            'one trade a day at 10:00 broker (11:00 am Dubai in summer, 12:00 pm in winter) · everything closes at 23:45 broker '
            '(12:45 am Dubai in summer, 1:45 am in winter)')
    return dict(code='GBPUSD', name='GBP/USD', symbol='GBPUSD · Capital.com GBP/USD', live=False, paper=True, status='Paper', version=RULES,
                unit='pips', dp=5, stats=BACKTEST, pass_bar=PASS, day_note=note,
                what_note='Tracks whether live GBP/USD signals do as well as the v1.02 MT4 test. You place the trade by hand on the demo (the auto-trader leaves GBP/USD alone). Decision after about 3 months.',
                cost_note='Results are pips per trade after the spread (at least 1.5 pips). 0.01 lot = 1,000 units = $0.10 per pip.',
                net_label='Net pips (v1.02 rules)')

def main(feed=None, get=None, getd=None, cget=None, now=None):
    global DEADLINE; DEADLINE = time.time() + 75     # own 75 s time budget per market
    now = now or F.broker_now(); day = now.normalize()
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    J = loadj(JOUR, dict(start=None, days=[]))
    rows_c, cnote = cftc_rows(cget); C = weekly(rows_c)
    code, rep = E.code_for(C, day)
    if now.dayofweek >= 5:
        prev = mk.get('GBPUSD') or {}
        nxt_code, nxt_rep = E.code_for(C, day + pd.Timedelta(days=7 - day.dayofweek))
        mk['GBPUSD'] = dict({k: v for k, v in prev.items() if k not in ('status', 'note')}, **base_card(None, nxt_rep, nxt_code), state='closed',
                            message=f"Market closed for the weekend. Next week: {'BUY' if nxt_code > 0 else 'SELL' if nxt_code < 0 else 'no trade'} days (CFTC report of {'—' if nxt_rep is None else pd.Timestamp(nxt_rep).strftime('%d %b')}).",
                            entries=[], journal=summary(J), jdays=jdays(J), feed_error=False, cftc_note=cnote)
        dumpj(old, PORTAL, indent=1); print('GBP: weekend'); return
    get = get or minutes; getd = getd or daily
    if feed is None:
        if not os.environ.get('CAPITAL_API_KEY'): raise RuntimeError('GBP paper needs the Capital.com prices')
        feed = F.Capital()
    if _DAILY.get('day') != str(day.date()) or len(_DAILY.get('d', [])) < E.RANGE_DAYS:   # daily ranges fetched once a day (hourly bars)
        _DAILY.update(day=str(day.date()), d=getd(feed, day))
    dd = _DAILY['d']; A = E.avg_range(dd, day)
    b = get(feed, day, now); b = b[(b.index >= day) & (b.index + pd.Timedelta(minutes=1) <= now)]
    bad = feed_check(b, now)
    if bad: raise FeedError(bad)
    sp = float(np.nanmedian(b.sp.values)) if len(b) and np.isfinite(b.sp.values).any() else 0.0
    cost = max(E.COST, sp)
    jd = next((d for d in J['days'] if d['date'] == str(day.date())), None)
    if jd and jd.get('trades') and jd.get('frozen'):                       # a trade already shown keeps its entry, stop and target
        fz = jd['frozen']; code = int(fz['code']); A = float(fz['A'])
    t = E.trade(b[['o', 'h', 'l', 'c']], day, code, A, now=now, cost=cost)
    last = float(b.c.iloc[-1]) if len(b) else None; first = float(b.o.iloc[0]) if len(b) else None
    rows = [row(t, last, cost)] if t else []
    t_in = day + pd.Timedelta(minutes=E.ENTRY_MIN); t_out = day + pd.Timedelta(minutes=E.CLOSE_MIN)
    if J.get('start') is None: J['start'] = str(day.date())
    nd = dict(date=str(day.date()), rules=RULES, label=day.strftime('%a %d %b'), side=(rows[0]['side'] if rows else None), trades=rows,
              final=bool(t is None and now >= t_in + pd.Timedelta(minutes=E.ENTRY_LATE + 1)) or bool(t and t['status'] != 'open'),
              code=int(code), report=None if rep is None else str(pd.Timestamp(rep).date()))
    if t: nd['frozen'] = dict(code=int(code), A=float(A))
    J['days'] = sorted([d for d in J['days'] if d['date'] != str(day.date())] + [nd], key=lambda d: d['date'])
    J['summary'] = summary(J, day); dumpj(J, JOUR, indent=1)
    spark = []
    if len(b):
        g5 = b[['o', 'h', 'l', 'c']].resample('5min').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'}).dropna()
        spark = [[F.broker_to_dubai(x).strftime('%-I:%M %p').lower(), round(float(r.c), 5), round(float(r.o), 5), round(float(r.h), 5), round(float(r.l), 5)] for x, r in g5.iterrows()]
    side = 'BUY' if code > 0 else 'SELL' if code < 0 else None
    if rows:
        r0 = rows[0]; state = r0['side'].lower()
        st0 = r0['status']
        if st0 == 'open': msg = (f"PAPER {r0['side']} at {r0['price']:.5f} ({r0['time']} Dubai). Stop {r0['stop']:.5f}, target {r0['half_px']:.5f} - "
                                 f"close the WHOLE trade at the target; otherwise it closes at {dubai(t_out)} Dubai.")
        elif st0 == 'target': msg = f"Target hit at {r0['exit_time']} Dubai: {r0['pips']:+.1f} pips. Done for today."
        elif st0 == 'stopped': msg = f"Stop hit at {r0['exit_time']} Dubai: {r0['pips']:+.1f} pips. Done for today."
        elif st0 == 'eod': msg = f"Closed at the day end ({r0['exit_time']} Dubai): {r0['pips']:+.1f} pips."
        else: msg = f"Day ended without a {dubai(t_out)} price - closed at the last price: {r0['pips']:+.1f} pips."
    elif side is None: state, msg = 'none', 'No GBP/USD trade this week: no positioning layer is at an extreme in the latest CFTC report.'
    elif now < t_in: state, msg = 'waiting', f"Today is a {side} day ({E.LAYER_NAME[abs(code)].split(' · ')[1]}). The trade opens at {dubai(t_in)} Dubai (10:00 broker)."
    elif not np.isfinite(A): state, msg = 'none', 'No trade: fewer than 14 days of price history for the average range.'
    else: state, msg = 'none', f'No trade today: no price bar between {dubai(t_in)} and {dubai(t_in + pd.Timedelta(minutes=E.ENTRY_LATE))} Dubai.'
    if cnote: msg += f' ({cnote}.)'
    mk['GBPUSD'] = dict(base_card(A if np.isfinite(A) else None, rep, code), state=state, message=msg, price=last,
                        change=(None if last is None or first is None else round(last - first, 5)), entries=rows, spark=spark, journal=J['summary'], jdays=jdays(J),
                        feed_error=False, epic=EPIC, close_at=dubai(t_out), open_at=dubai(t_in), signal=side, layer=abs(int(code)), cftc_note=cnote,
                        report=None if rep is None else str(pd.Timestamp(rep).date()), range_pips=None if not np.isfinite(A) else round(A * 1e4, 1),
                        cftc=dict(levp=None if rep is None else round(float(C.loc[rep, 'levp']), 3), nrp=None if rep is None else round(float(C.loc[rep, 'nrp']), 3),
                                  nrcp=None if rep is None else round(float(C.loc[rep, 'nrcp']), 3)))
    dumpj(old, PORTAL, indent=1)
    print(f'GBP paper: {now} broker | bars {len(b)} | code {code} report {None if rep is None else pd.Timestamp(rep).date()} | A {A * 1e4 if np.isfinite(A) else None} pips | trade {None if not t else t["status"]}')

def fail(e):
    """Keep the last good GBP/USD card and say what failed."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {}); c = mk.get('GBPUSD') or {}
    c.update({k: v for k, v in base_card().items() if k not in ('day_note',)}); c.setdefault('day_note', base_card()['day_note'])
    c.setdefault('entries', []); c.setdefault('state', 'waiting'); c['feed_error'] = True
    c['message'] = f"GBP/USD paper update failed at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({type(e).__name__}: {str(e)[:120]}) — shows the last good update; retries every minute."
    mk['GBPUSD'] = c; dumpj(old, PORTAL, indent=1)
