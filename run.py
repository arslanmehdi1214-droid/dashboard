"""Runs every minute (GitHub Actions, via loop.py). GOLD v2.15 from 22 Oct 2026 (= v2.11 + day lock 2R/0.5R + real-yield size 1.5 + strong-family size 1.5 + add a 3rd trade when every open trade is up 1.25x its stop; desk209.V215_FROM; MT4 his run passed 21 Oct). Before: GOLD v2.11 (20 Oct 2026; = v2.10 with NO half-close / no stop to entry, desk209.SPLIT=False). Was v2.10 (18 Oct 2026; = v2.09 + no 2nd trade in the same minute): today's gold minute bars -> the EA's signals
(engine206.py, v2.06 signal set) -> the v2.10 trade rules (desk209.py: one direction, max 2 trades, half close at 0.20 x stop,
stop to entry, rest to the day-end close, range-fade fill). Writes the page + the live journal, including the ACTIONS list
(OPEN / ADD / HOLD / CLOSE HALF / STOP / REVERSE / CLOSE ALL). Desk only - no Telegram (his rule, 18 Oct).
It never trades. You place the trades yourself."""
import os, sys, json, requests, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine206 as E, inputs206 as I, feeds as F, desk209 as DK

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = float(os.environ.get('ALERT_SIZE_OZ', '0.1'))
STATE = os.path.join(HERE, 'sent.json'); PORTAL = os.path.join(HERE, 'docs', 'data.json')
JOURNAL = os.path.join(HERE, 'docs', 'journal.json'); INPUTS = os.path.join(HERE, 'docs', 'inputs.json')
BACKTEST_V210 = dict(direction='—', days='72–73% green', perday='1.7', win='79–81%', pnl='—', source='MT4 backtest v2.10, his run 2020–2026 (worst day −2.1R)')
BACKTEST = dict(direction='—', days='49% green (53% of trade days)', perday='1.5', win='0% hit target · 51% closed in profit', pnl='—', source='MT4 backtest v2.15, his run 21 Oct 2020–2026 ($247/day 2020–22, $263/day 2023–26 at $1,000 risk; worst day −$4,681)')
BACKTEST_V211 = dict(direction='—', days='45–46% green', perday='1.5', win='47–50%', pnl='—', source='MT4 backtest v2.11, his runs 20 Oct 2020–2026 ($162/day 2020–22, $189/day 2023–26 at $1,000 risk; worst day −3.6R)')

def dubai(t): return F.broker_to_dubai(pd.Timestamp(t)).strftime('%-I:%M %p').lower()
def eod_of(day):
    """Broker day -> its day-end close (broker time). Falls back to the old rule if engine206.py is an older copy."""
    d = pd.Timestamp(day); f = getattr(E, 'close_minutes', None)
    return d + pd.Timedelta(minutes=f(d) if f else (22 * 60 + 50 if d.dayofweek == 4 else 23 * 60))
def send(text):
    """DESK ONLY (his rule, 18 Oct 2026): nothing goes to Telegram any more; the message is shown on the page instead."""
    print('[desk only] ' + text.replace('\n', ' | ')); return True
    tok, chat = os.environ.get('TELEGRAM_BOT_TOKEN'), os.environ.get('TELEGRAM_CHAT_ID')
    if not tok or not chat: print('[no Telegram keys] ' + text.replace('\n', ' | ')); return True
    try:
        r = requests.post(f'https://api.telegram.org/bot{tok}/sendMessage', data={'chat_id': chat, 'text': text}, timeout=20)
    except Exception as e:
        print('telegram not sent:', type(e).__name__); return False        # retried next run (not marked as sent)
    print('telegram', r.status_code, text.splitlines()[0]); return r.status_code == 200
def dumpj(obj, p, **kw):
    """Write JSON atomically (temp file + rename), so a cancelled job never leaves a half-written file."""
    tmp = p + '.tmp'
    with open(tmp, 'w') as f: json.dump(obj, f, **kw)
    os.replace(tmp, p)
def loadj(p, d):
    try: return json.load(open(p))
    except Exception: return d

def daily_bars(h1, day):
    """Broker-day bars from hourly bars (index = broker time), days before `day` only."""
    d = h1[h1.index < day]
    g = d.groupby(d.index.normalize())
    return pd.DataFrame({'o': g.o.first(), 'h': g.h.max(), 'l': g.l.min(), 'c': g.c.last()})

def regime_today(feed, h1, day, now):
    """1 / 0 / None and the correlation; needs the broker's 00:00 hourly FX bars (closed at 1:00 broker)."""
    if now < day + pd.Timedelta(hours=1): return None, None
    try:
        fx = {}
        for p in I.W:
            b = feed.h1(days=45, epic=p); b = b[b.index.hour == 0]
            fx[p] = {t.date(): float(c) for t, c in zip(b.index.normalize(), b.c)}
        g = h1[h1.index <= now]; opens = g.groupby(g.index.normalize()).o.first()
        return I.dollar_regime([(t.date(), float(o)) for t, o in opens.items()], fx)
    except Exception as e:
        print('regime not computed:', type(e).__name__, e); return None, None

RY_FILE = os.path.join(HERE, 'docs', 'realyield.json')   # v2.15: US 10-yr real yield (Treasury daily real yield curve = FRED DFII10)
RY_URL = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all?type=daily_treasury_real_yield_curve&field_tdr_date_value={y}&page&_format=csv'
def realyield(day):
    """v2.13 sizing input for broker day `day`: change of the 10-yr real yield on its latest date <= day - 2 calendar days (vs the previous
    date). Refreshes docs/realyield.json from treasury.gov at most once an hour while that date is missing. None = unknown (no yield size)."""
    import time
    R = loadj(RY_FILE, dict(rows=[], last_try=0)); need = (day - pd.Timedelta(days=2)).normalize()
    have = pd.Timestamp(R['rows'][-1][0]) if R['rows'] else pd.Timestamp('2000-01-01')
    if have < need - pd.Timedelta(days=4) or (have < need and time.time() - R.get('last_try', 0) > 3600):
        R['last_try'] = time.time(); rows = {r[0]: r[1] for r in R['rows']}
        for y in sorted({need.year - 1, need.year}):
            try:
                r = requests.get(RY_URL.format(y=y), timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
                if r.status_code != 200: continue
                lines = r.text.strip().splitlines(); hd = [h.strip('"') for h in lines[0].split(',')]; c = hd.index('10 YR')
                for ln in lines[1:]:
                    v = ln.split(',')
                    if len(v) > c and v[c].strip():
                        m_, d_, y_ = v[0].split('/'); rows[f'{y_}-{int(m_):02d}-{int(d_):02d}'] = float(v[c])
            except Exception as e: print('real yield fetch failed', y, type(e).__name__)
        R['rows'] = sorted(rows.items())[-400:]; dumpj(R, RY_FILE)
    prev = [r for r in R['rows'] if pd.Timestamp(r[0]) <= need]
    if len(prev) < 2 or pd.Timestamp(prev[-1][0]) < need - pd.Timedelta(days=6): return None
    return round(prev[-1][1] - prev[-2][1], 4)

def fmt(e):
    side = 'BUY' if e['dir'] == 1 else 'SELL'
    if e['kind'] == 'ENTRY':
        return (f"GOLD {side} now  ({'first trade' if e['first'] else 'add, same direction'} · {e['tag']})\n"
                f"Signal price {e['px']:.2f} | stop {e['stop']:.2f} ({abs(e['px'] - e['stop']):.1f} away) | no target\n"
                f"Size {SIZE:.2f} oz | hold until the stop or the day-end close at {dubai(eod_of(pd.Timestamp(e['t']).normalize()))} Dubai | {dubai(e['t'])} Dubai")
    if e['kind'] == 'STOP':
        return f"GOLD {side} ({e['tag']}, entered {dubai(e['t0'])}): stop hit at {e['px']:.2f} | {dubai(e['t'])} Dubai"
    if e['kind'] == 'EOD':
        return f"GOLD END OF DAY: close ALL open gold trades now ({e.get('n', '')} from today's signals) | {dubai(e['t'])} Dubai"
    if e['kind'] == 'SKIP':
        return f"GOLD: first {side} signal skipped by the dollar filter ({e['tag']}) - waiting for the next one | {dubai(e['t'])} Dubai"
    return str(e)

STATUS = {'open': 'open', 'half': 'open', 'stop hit': 'stopped', 'stop at entry': 'be', 'day end': 'eod', 'reversed': 'reversed', 'day lock': 'lock'}
def row(g, k=0):
    """One v2.10 trade (desk209 leg) -> page/journal row. price = his fill (Ask for buys, Bid for sells)."""
    st = STATUS.get(g['status'], g['status']); half = g.get('half_t') is not None
    nxt = None
    if st == 'open':
        nxt = (f"Half banked at {g['half_px']:.2f} · stop is at entry {g['entry']:.2f} · hold the rest to the stop or the day-end close"
               if half else (f"Close HALF at {g['half_px']:.2f}, then move the stop to entry {g['entry']:.2f} · stop now {g['stop']:.2f}" if g.get('half_px') is not None
               else f"Hold to the stop {g['stop']:.2f} or the day-end close · no half-close" + (f" · size x{g.get('size_x', 1):g}" if g.get('size_x', 1) != 1 else "")))
    return dict(time=dubai(g['t']), side='BUY' if g['dir'] == 1 else 'SELL', tag=g['tag'], price=g['entry'], stop=g['stop'],
                stop0=g['stop0'], half_px=g['half_px'], half=half, half_time=(dubai(g['half_t']) if half else None), size=SIZE,
                status=st, first=(k == 0), exit=g['exit'], exit_time=(dubai(g['exit_t']) if g['exit_t'] is not None else None),
                pnl=(None if g['pnl_oz'] is None else round(g['pnl_oz'] * g.get('size_x', 1.0), 2)), pnl_oz=g['pnl_oz'], size_x=g.get('size_x', 1.0), rwf=None, next=nxt)
def act_rows(acts):
    return [dict(time=dubai(a['t']), kind=a['kind'], side=a['side'], text=a['text']) for a in acts]

def compute(h1, m1, day, now, inp):
    """The EA's trades for broker day `day` as of `now` (same steps for today and for a missed day)."""
    D1 = daily_bars(h1, day)
    D = E.Daily(D1.index.values.astype('datetime64[D]'), D1.o.values, D1.h.values, D1.l.values, D1.c.values)
    hh = h1[h1.index <= now]
    Hh = E.Hourly(hh.index.values.astype('datetime64[m]'), hh.h.values, hh.l.values, hh.c.values)
    dayst = np.datetime64(day.date(), 'D')
    one_am = dayst.astype('datetime64[m]') + np.timedelta64(60, 'm')
    reg = inp.get('regime')
    einp = dict(d5=inp['d5'], d1=inp['d1'], vix=inp['vix'], tnx=inp['tnx'], attn=inp.get('attn', 0),
                regime=lambda t: (reg if (reg is not None and t >= one_am) else 0))
    mm = dict(t=m1.index.values.astype('datetime64[m]'), o=m1.o.values, h=m1.h.values, l=m1.l.values, c=m1.c.values)
    sig = E.run_day(dayst, D, Hh, mm, einp) if len(m1) else []
    taken = [t for t in sig if not t.get('skipped')]; skipped = [t for t in sig if t.get('skipped')]
    ry = None
    if dayst >= DK.V215_FROM:
        try: ry = realyield(day)
        except Exception as e: print('real yield failed', type(e).__name__, e)
    legs, acts = DK.run(taken, dayst, mm, np.datetime64(now, 'm'), D.atr(0), np.datetime64(eod_of(day), 'm'), label=dubai, ry=ry) if len(m1) else ([], [])
    return legs, acts, skipped, D

def missed_days(J, now, cache):
    """Past broker days (last 9 days, inputs still cached) that never got their day-end run."""
    today = str(now.normalize().date())
    return [d for d in J.get('days', []) if not d.get('final') and d['date'] < today and d['date'] in cache
            and (now.normalize() - pd.Timestamp(d['date'])).days <= 9]

def finish_missed_days(feed, h1, now):
    """CATCH-UP: a past broker day whose day-end run never happened (e.g. GitHub down at midnight) is replayed to its end and
    written to the journal as final; if trades were still open at the day-end close, one Telegram tells him to close them."""
    J = loadj(JOURNAL, None)
    if not J: return
    today = str(now.normalize().date()); cache = loadj(INPUTS, {}); state = loadj(STATE, {}); changed = False
    for d in missed_days(J, now, cache):
        try:
            day = pd.Timestamp(d['date']); inp = dict(cache[d['date']])
            m1 = feed.m1_today(day); m1 = m1[m1.index < day + pd.Timedelta(days=1)]
            if not len(m1) or m1.index.max() < day + pd.Timedelta(hours=22):          # minutes do not reach the day end: try later
                print('missed day', d['date'], 'not caught up: minute bars end', (m1.index.max() if len(m1) else None)); continue
            if inp.get('regime') is None:
                reg, corr = regime_today(feed, h1, day, day + pd.Timedelta(hours=23))
                if reg is not None: inp.update(regime=reg, corr=corr)
            was_open = any(t.get('status') in ('open', 'close_now') for t in d.get('trades', []))
            legs, acts, skipped, _ = compute(h1, m1, day, day + pd.Timedelta(hours=23, minutes=59), inp)
            rows = [row(g, k) for k, g in enumerate(legs)]
        except Exception as e:
            print('missed day', d['date'], 'not caught up:', type(e).__name__, e); continue
        d.update(side=(rows[0]['side'] if rows else None), trades=rows, skipped=len(skipped), final=True, caught_up=str(now))
        changed = True
        if was_open or any(r['status'] == 'eod' for r in rows):
            k = f"MISSED_EOD|{d['date']}"; sent = set(state.get(today, []))
            if k not in sent and send(f"GOLD: the day-end close for {day.strftime('%a %d %b')} was missed (the signal server was down). "
                                      f"If any gold trade from that day is still open, close it now. | {dubai(now)} Dubai"):
                sent.add(k); state[today] = sorted(sent)
        print('caught up missed day', d['date'], len(rows), 'trades')
    if changed:
        dumpj(J, JOURNAL, indent=1); dumpj(state, STATE, indent=0)

def summary(J, day):
    allt = [t for d in J['days'] for t in d['trades']]
    dec = [t['rwf'] for t in allt if t.get('rwf') is not None]
    pnl = [t['pnl'] for t in allt if t.get('pnl') is not None]
    wd = max(1, len(pd.bdate_range(J['start'], str(day.date()))))
    tdays = sum(1 for d in J['days'] if d['trades'])
    return dict(since=pd.Timestamp(J['start']).strftime('%d %b %Y'), trades=len(allt),
                direction=(round(100 * sum(dec) / len(dec), 1) if dec else None), decided=len(dec),
                days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                avg_pnl=(round(sum(pnl) / len(pnl), 2) if pnl else None), closed=len(pnl),
                total_pnl_01=(round(sum(p * 0.1 for p in pnl), 2) if pnl else None))

def write_summary():
    J = loadj(JOURNAL, None)
    if J and J.get('days'):
        J['summary'] = summary(J, pd.Timestamp(J['days'][-1]['date'])); dumpj(J, JOURNAL, indent=1)
        old = loadj(PORTAL, {}); g = (old.get('markets') or {}).get('GOLD')
        if g is not None: g['journal'] = J['summary']; dumpj(old, PORTAL, indent=1)

def main():
    now = F.broker_now(); day = now.normalize(); test = '--test' in sys.argv
    if now.dayofweek >= 5 and not test:
        if missed_days(loadj(JOURNAL, {}), now, loadj(INPUTS, {})):
            try: feed, src = F.get_feed(); finish_missed_days(feed, feed.h1(days=460), now); write_summary()
            except Exception as e: print('weekend catch-up skipped:', type(e).__name__, e)
        old = loadj(PORTAL, {}); g = (old.get('markets') or {}).get('GOLD')
        if g: g.update(state='closed', message='Market closed for the weekend'); dumpj(old, PORTAL, indent=1)
        print('weekend'); return
    feed, src = F.get_feed()
    h1 = feed.h1(days=460)
    try: finish_missed_days(feed, h1, now)
    except Exception as e: print('catch-up skipped:', type(e).__name__, e)
    m1 = feed.m1_today(day); m1 = m1[m1.index + pd.Timedelta(minutes=1) <= now]          # closed minute bars only
    # daily outside values (cached per broker day; retried every 30 minutes if something was missing)
    cache = loadj(INPUTS, {}); key = str(day.date()); inp = cache.get(key)
    retry = inp is not None and any(inp.get(k) == 9 for k in ('d1', 'd5', 'vix', 'tnx')) and \
        (now - pd.Timestamp(inp.get('fetched', '2000-01-01'))) > pd.Timedelta(minutes=30)
    if inp is None or retry:
        inp = I.daily_inputs(day.date()); inp['fetched'] = str(now)
    if inp.get('regime') is None:
        reg, corr = regime_today(feed, h1, day, now)
        if reg is not None: inp.update(regime=reg, corr=corr)
    cache = {k: v for k, v in cache.items() if k >= str((day - pd.Timedelta(days=10)).date())}; cache[key] = inp
    dumpj(cache, INPUTS, indent=1)
    reg = inp.get('regime')
    taken, acts, skipped, D = compute(h1, m1, day, now, inp)      # taken = v2.10 trades (desk209 legs)
    eod = eod_of(day)                                   # day-end close (22:50 broker on Fridays and in US winter time)
    # ---- actions: shown on the page only; a NEW action is recorded in sent.json so loop.py pushes the page at once
    state = loadj(STATE, {}); sent = set(state.get(key, []))
    for a in acts:
        k = f"A|{a['kind']}|{pd.Timestamp(a['t']).isoformat()}|{a['text'][:48]}"
        if k not in sent: print('ACTION', dubai(a['t']), a['text']); sent.add(k)
    if test:
        last = float(m1.c.iloc[-1]) if len(m1) else float('nan')
        send(f"GOLD v2.06 signal system TEST OK [{src}]\nLast price {last:.2f} | broker day {day.date()} | daily range {D.atr(0):.1f}\n"
             f"Dollar 1d/5d {inp.get('dollar_1d')}/{inp.get('dollar_5d')} · VIX {inp.get('vix_5d')} · US10y {inp.get('tnx_5d')} · dollar-driven {reg} · low attention {inp.get('attn')}\n"
             f"Trades today so far: {len(taken)} | {dubai(now)} Dubai\n"
             f"CHECK: daily bars {D.n} ({str(D.t[0]) if D.n else '-'} .. {str(D.t[-1]) if D.n else '-'}) | hourly bars {len(h1)} | ADX {D.adx():.1f} | "
             f"dollar-driven corr {inp.get('corr')} | input notes {inp.get('notes')}")
    state = {k2: v for k2, v in state.items() if k2 >= str((day - pd.Timedelta(days=5)).date())}; state[key] = sorted(sent)
    dumpj(state, STATE, indent=0)
    write_pages(now, day, m1, taken, skipped, inp, reg, src, eod, D.atr(0), acts)
    print(f'{now} broker | {src} | trades today {len(taken)} | skipped {len(skipped)} | inputs {inp}')

def write_pages(now, day, m1, taken, skipped, inp, reg, src, eod, datr, acts=()):
    rows = [row(g, k) for k, g in enumerate(taken)]
    if now >= eod: rows = [dict(r, status='close_now') if r['status'] == 'open' else r for r in rows]
    # page only: after the close, trades the desk booked at the day-end price are still open in his account until he closes them
    page_rows = [dict(r, status='close_now') if (now >= eod and r['status'] == 'eod') else r for r in rows]
    # ---- journal (one record per broker day, replaced on every run of that day)
    J = loadj(JOURNAL, dict(start=str(day.date()), days=[]))
    days = [d for d in J['days'] if d['date'] != str(day.date())]
    if now.dayofweek < 5:
        days.append(dict(date=str(day.date()), label=day.strftime('%a %d %b'), side=(rows[0]['side'] if rows else None),
                         trades=rows, skipped=len(skipped), final=bool(now >= eod)))
    J['days'] = sorted(days, key=lambda d: d['date'])
    J['summary'] = summary(J, day)
    dumpj(J, JOURNAL, indent=1)
    # ---- page data
    old = loadj(PORTAL, {}); others = {k: v for k, v in (old.get('markets') or {}).items() if k != 'GOLD'}
    V211 = np.datetime64(day.date(), 'D') >= DK.V211_FROM               # v2.11 rules (no half-close) from the switch day
    V215 = np.datetime64(day.date(), 'D') >= DK.V215_FROM               # v2.15 rules from their switch day
    last_sig = now >= day + pd.Timedelta(hours=19)
    if now.dayofweek >= 5: state, msg = 'closed', 'Market closed for the weekend'
    elif rows:
        side = rows[0]['side']; state = side.lower()
        msg = (f"{side} day — up to 2 {side} trades (a 3rd only when every open trade is up 1.25x its stop). Each runs to its stop or the day-end close at {dubai(eod)} Dubai. Day lock: once today reaches +2R, close all if it falls back to +0.5R." if V215 else
               f"{side} day — up to 2 {side} trades. Each runs to its stop or the day-end close at {dubai(eod)} Dubai (no half-close)." if V211 else
               f"{side} day — up to 2 {side} trades. Close HALF at the ½ level, then move the stop to entry; the rest runs to its stop or the day-end close at {dubai(eod)} Dubai.")
    elif skipped and not last_sig: state, msg = 'blocked', 'The first signal was skipped by the dollar filter — watching for the next one.'
    elif last_sig: state, msg = 'none', 'No trade today — no signal (new signals stop at 8 pm Dubai).'
    else: state, msg = 'waiting', 'Waiting for the first signal (signals can come until 8 pm Dubai).'
    spark = []
    if len(m1):
        g5 = m1[['o', 'h', 'l', 'c']].resample('5min').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'}).dropna()   # 5-min candles for the page: [time, close, open, high, low]
        spark = [[dubai(t), round(float(r.c), 2), round(float(r.o), 2), round(float(r.h), 2), round(float(r.l), 2)] for t, r in g5.iterrows()]
    last = float(m1.c.iloc[-1]) if len(m1) else None; first = float(m1.o.iloc[0]) if len(m1) else None
    hist = []
    for d in J['days'][-15:][::-1]:
        tr = d['trades']
        hist.append(dict(date=d['date'], label=d['label'], state=(d['side'] or 'none').lower() if tr else 'none', entries=len(tr),
                         stopped=sum(t['status'] == 'stopped' for t in tr), eod=sum(t['status'] in ('eod', 'close_now') for t in tr),
                         running=sum(t['status'] == 'open' for t in tr), rw=sum(1 for t in tr if t.get('rwf') == 1),
                         rd=sum(1 for t in tr if t.get('rwf') is not None),
                         pnl=(round(sum(t['pnl'] for t in tr if t.get('pnl') is not None), 2) if any(t.get('pnl') is not None for t in tr) else None)))
    gold = dict(code='GOLD', name='Gold', symbol='XAU/USD', live=True, version=('v2.15' if V215 else 'v2.11' if V211 else 'v2.10'), actions=act_rows(acts), actions_day=str(day.date()), feed_error=False, state=state, message=msg, price=last, close_at=dubai(eod),
                change=(None if last is None or first is None else round(last - first, 2)), size=SIZE, datr=round(datr, 2),
                open_now=sum(r['status'] in ('open', 'close_now') for r in page_rows), entries=page_rows, spark=spark, history=hist,
                inputs=dict(dollar_1d=inp.get('dollar_1d'), dollar_5d=inp.get('dollar_5d'), vix_5d=inp.get('vix_5d'), tnx_5d=inp.get('tnx_5d'),
                            dollar_driven=(None if reg is None else bool(reg)), corr=inp.get('corr'), low_attention=bool(inp.get('attn', 0)),
                            notes=inp.get('notes', [])),
                stats=(BACKTEST if V215 else BACKTEST_V211 if V211 else BACKTEST_V210), journal=J['summary'])
    data = dict(updated=F.broker_to_dubai(now).strftime('%a %d %b · %-I:%M %p').replace('AM', 'am').replace('PM', 'pm'),
                source=src, markets=dict(GOLD=gold, **others))
    dumpj(data, PORTAL, indent=1)

def safe_main():
    """Never crash the page: if a price source fails, say so on the page and keep the last good data."""
    import traceback
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        try:
            old = loadj(PORTAL, {}); g = (old.get('markets') or {}).get('GOLD')
            if g is not None:
                now = F.broker_now()
                g['message'] = (f"Price feed problem at {F.broker_to_dubai(now).strftime('%-I:%M %p').lower()} Dubai "
                                f"({type(e).__name__}) - the page shows the last good update; it retries every minute.")
                g['feed_error'] = True
                dumpj(old, PORTAL, indent=1)
        except Exception:
            traceback.print_exc()
    try:                                    # USDJPY paper page (separate from gold; a yen failure never touches the gold card)
        import yen_run
        yen_run.main()
    except Exception as e:
        traceback.print_exc()
        try:
            import yen_run; yen_run.fail(e)
        except Exception:
            traceback.print_exc()
    try:                                    # WTI paper page (separate; a WTI failure never touches the gold or USDJPY cards)
        import wti_run
        wti_run.main()
    except Exception as e:
        traceback.print_exc()
        try:
            import wti_run; wti_run.fail(e)
        except Exception:
            traceback.print_exc()
    try:                                    # Nasdaq paper page (separate; a Nasdaq failure never touches the other cards)
        import nq_run
        nq_run.main()
    except Exception as e:
        traceback.print_exc()
        try:
            import nq_run; nq_run.fail(e)
        except Exception:
            traceback.print_exc()
    try:                                    # Silver paper page (v1.8 honest rules; a silver failure never touches the other cards)
        import sv_run
        sv_run.main()
    except Exception as e:
        traceback.print_exc()
        try:
            import sv_run; sv_run.fail(e)
        except Exception:
            traceback.print_exc()

if __name__ == '__main__':
    safe_main()
