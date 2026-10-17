"""GOLD v2.09 trade manager for the Signal Desk (same rules as EA GOLD_DAYTRADE v2.09 + DT209_GOLD_MAX2_HALF020.set).
Input: today's engine signals (engine206.run_day, skipped ones removed) + today's closed minute bars. Output: the trades he
should hold (legs), their state, and a time-ordered list of ACTIONS for the page (no Telegram).

Rules (tested: MT4 his run 2020-26, trades win ~80%, ~73% green days; Python mirror sim10.py):
- ONE direction at a time. A signal the same way while trades are open: ADD if fewer than 2 open and not in the same minute
  as an open trade's entry, else HOLD (do nothing).
- Opposite engine signals never reach here (the engine skips signals against the day's earlier trades), except against a
  range-fade FILL trade: then CLOSE ALL and open the other way (REVERSE) - same as the EA.
- Every trade: size 1 (desk size), stop = 0.5 x 14-day average daily range from the signal price (buy: below the bid,
  sell: above the ask). CLOSE HALF when profit = 0.20 x stop distance, then MOVE STOP TO ENTRY on the rest.
  The rest runs to its stop (entry) or the day-end close.
- FILL: if no engine signal by then, the broker 10:00-11:59 range; the first break within 6 hours is faded (break up = SELL,
  break down = BUY), entered at the next minute's open.
Prices: bars are Bid. Buys fill at Ask (= bid + spread) and exit at Bid; sells fill at Bid and exit at Ask."""
import numpy as np

SP = 0.5          # Capital.com gold spread ($/oz) - same as the engine's S['Spread']
K = 0.20          # close half at K x stop distance (Split_At_x_Stop)
EX = 0.0          # extra $ beyond the half level (Split_Extra_Dollars)
STOPX = 0.5       # stop = STOPX x 14-day range for every signal (Signal_Stop_Target, Stop_Other = 0)
FILLX = 0.5       # stop for the fill trade (Fill_Stop_x_DailyATR)
NMAX = 2          # Max_Same_Way_Trades
FILL_FROM, FILL_MIN, FILL_HOURS = 10 * 60, 120, 6


def fill_event(T, O, H, L, day, eod):
    """Range-fade fill for broker day `day` from today's minute bars. Returns (bar index of entry, dir) or None."""
    m = ((T - day.astype('datetime64[m]')) / np.timedelta64(1, 'm')).astype(int)
    rng = np.where((m >= FILL_FROM) & (m < FILL_FROM + FILL_MIN))[0]
    if len(rng) == 0: return None
    b = rng[-1]; hi, lo = H[rng].max(), L[rng].min()
    for j in range(b + 1, len(T)):
        if m[j] >= FILL_FROM + FILL_MIN + FILL_HOURS * 60 or T[j] >= eod: return None
        if H[j] > hi: return (j + 1, -1) if j + 1 < len(T) else ('pending', -1)
        if L[j] < lo: return (j + 1, 1) if j + 1 < len(T) else ('pending', 1)
    return None


def run(signals, day, m1, now, atr, eod, label=None):
    """signals: engine trades (dict t, dir, tag, px). day: np.datetime64[D]. m1: dict t,o,h,l,c (closed bars, broker time).
    atr: 14-day average daily range. eod: np.datetime64[m] day-end close. Returns (legs, actions)."""
    T = np.asarray(m1['t'], dtype='datetime64[m]'); O, H, L, C = (np.asarray(m1[k], float) for k in ('o', 'h', 'l', 'c'))
    legs, act = [], []
    if len(T) == 0 or atr <= 0: return legs, act
    jidx = lambda t: int(np.searchsorted(T, np.datetime64(t, 'm'), side='left'))
    ev = [(jidx(s['t']), s['dir'], 's', float(s['px']), s['tag'], np.datetime64(s['t'], 'm')) for s in signals]
    ev = [e for e in ev if e[0] < len(T)]
    fe = fill_event(T, O, H, L, day, eod)
    if fe and fe[0] != 'pending' and (not ev or ev[0][0] > fe[0]):
        ev.append((fe[0], fe[1], 'f', float(O[fe[0]]), 'FILL range fade', T[fe[0]]))
    ev.sort(key=lambda e: (e[0], 0 if e[2] == 'f' else 1))
    side = lambda d: 'BUY' if d > 0 else 'SELL'
    openl = lambda: [g for g in legs if g['status'] in ('open', 'half')]

    def add(t, kind, d, text, px=None): act.append(dict(t=t, kind=kind, side=side(d), text=text, price=px))

    def new_leg(j, d, kind, p0, tag, t):
        sd = (FILLX if kind == 'f' else STOPX) * atr
        if d > 0: e = p0 + SP; sl = (e - sd) if kind == 'f' else (p0 - sd)
        else: e = p0; sl = (e + sd) if kind == 'f' else (p0 + SP + sd)
        risk = abs(e - sl); hp = e + d * (K * risk + EX)
        g = dict(j=j, t=t, dir=d, tag=tag, kind=kind, entry=round(e, 2), stop0=round(sl, 2), stop=round(sl, 2), risk=round(risk, 2),
                 half_px=round(hp, 2), status='open', half_t=None, exit=None, exit_t=None, pnl_oz=None, time_txt=('from ' + label(t)) if label else '#%d' % (len(legs) + 1))
        legs.append(g); return g

    def close_leg(g, px, t, why):
        d = g['dir']; full = 0.5 if g['status'] == 'half' else 1.0
        banked = 0.5 * d * (g['half_px'] - g['entry']) if g['status'] == 'half' else 0.0
        g.update(exit=round(px, 2), exit_t=t, status=why, pnl_oz=round(banked + full * d * (px - g['entry']), 2))

    def walk(j0, j1):
        """Stops and half-closes on bars j0..j1-1 (bars after each trade's entry bar)."""
        for j in range(j0, j1):
            if T[j] >= eod: return
            for g in openl():
                if j <= g['j']: continue
                d = g['dir']
                if (d > 0 and L[j] <= g['stop']) or (d < 0 and H[j] + SP >= g['stop']):
                    px = min(g['stop'], O[j]) if d > 0 else max(g['stop'], O[j] + SP)
                    be = g['status'] == 'half'
                    close_leg(g, px, T[j], 'stop at entry' if be else 'stop hit')
                    add(T[j], 'STOP', d, (f"{side(d)} {g['time_txt']}: stop at entry hit at {px:.2f} - the rest is closed, half was banked"
                                          if be else f"{side(d)} {g['time_txt']}: STOP HIT at {px:.2f} - trade closed"), round(px, 2))
                    continue
                if g['status'] == 'open' and ((d > 0 and H[j] >= g['half_px']) or (d < 0 and L[j] + SP <= g['half_px'])):
                    g.update(status='half', half_t=T[j], stop=g['entry'])
                    add(T[j], 'HALF', d, f"CLOSE HALF of your {side(d)} {g['time_txt']} now at {g['half_px']:.2f}, then MOVE STOP of the rest to {g['entry']:.2f} (entry)", g['half_px'])

    cur = 0
    for (j, d, kind, p0, tag, t) in ev:
        walk(cur, j); cur = j                    # bars before this event
        if T[min(j, len(T) - 1)] >= eod: break
        op = openl()
        if op and op[0]['dir'] == d:
            same_min = any(g['t'] == t for g in op)
            if len(op) < NMAX and not same_min:
                g = new_leg(j, d, kind, p0, tag, t)
                add(t, 'ADD', d, f"ADD {side(d)} (2nd trade) now ~{g['entry']:.2f} | stop {g['stop']:.2f} | close half at {g['half_px']:.2f} | signal {tag}", g['entry'])
            else:
                add(t, 'HOLD', d, f"HOLD - new {side(d)} signal ({tag}) but {'a trade was opened this minute' if same_min else '2 trades are already open'}: do nothing")
            continue
        if op:   # opposite signal against an open (fill) trade: close all, turn round
            px = p0 if op[0]['dir'] > 0 else p0 + SP
            for g in op: close_leg(g, px, t, 'reversed')
            add(t, 'REVERSE', d, f"REVERSE - close ALL your {side(-d)} trades now (~{px:.2f}) and {side(d)} instead", round(px, 2))
        g = new_leg(j, d, kind, p0, tag, t)
        add(t, 'OPEN', d, f"OPEN {side(d)} now ~{g['entry']:.2f} | stop {g['stop']:.2f} ({g['risk']:.1f} away) | close half at {g['half_px']:.2f} | signal {tag}", g['entry'])
    walk(cur, len(T))
    after = np.datetime64(now, 'm') >= eod
    if after:
        op = openl()
        if op:
            k = int(np.searchsorted(T, eod, side='left')); k = min(max(k - 1, 0), len(T) - 1)
            for g in op: close_leg(g, C[k] if g['dir'] > 0 else C[k] + SP, eod, 'day end')
            add(eod, 'CLOSE_ALL', op[0]['dir'], f"END OF DAY - CLOSE ALL your gold trades now ({len(op)} open)")
    act.sort(key=lambda a: a['t'])
    return legs, act
