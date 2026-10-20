"""WTI_DAYTRADE v1.05 rules (= v1.04 + the day's FIRST trade, if a SELL, is FULL size when P['first_sell_full'] is set: last EIA Cushing report = build AND yesterday's close < close 5 trading days earlier; his MT4 run 20 Oct 2026)
(v1.04 = v1.03 + part-close 25% instead of 50%) as a PAPER engine for the Signal Desk - same logic as the EA / its line-by-line Python port
(wti_ea_port.py: 4,300 of 4,300 MT4 trades 2020-2026 same minute and direction). Prices are Bid; broker clock = New York + 7 h.
History = finished broker days: [date 'YYYY-MM-DD', open, high, low, close, settle] where settle = open of the first bar 21:30-21:35.
Rules:
 - range A = mean (high - low) of the 14 previous days; trade only if A exists and the previous day is <= 3 calendar days back.
 - 7 level families, each gives at most ONE trade a day (its first touched level), break direction, scanned from its start bar
   to the close bar (first bar >= 20:00 broker):
   1 yesterday's settlement (start 16:00-16:05)   2-4 day open +/- 0.5 / 0.7 / 1.0 x yesterday's range (start: the day's 2nd bar)
   5 yesterday's high / low (start 7:00-7:05)     6 last week's high / low (start 2:00-2:05)
   7 nearest whole dollar below / above the 10:00 price (only if >= 0.15 x A away; start 10:00-10:05)
   A level counts only if the start-bar open is >= 0.05 x A away. Touch = a bar trades THROUGH the level by 1 cent;
   signal price = the level (or the bar open if it opened beyond) + the MT4-like slip (1.3-2.5 cents by the minute's range),
   which reproduced his MT4 fills (direction 53.0% 2020-26).
 - LADDER: the day's first trade either way; later trades only the same way; same minute + same way = one trade.
 - v1.03 ENTRY TIMES: no new trade from 16:30 broker, except ONE first trade until 19:00 on a day with no trade yet.
 - v1.03 EXITS: stop buys 1.0 x A, sells 0.75 x A; half-close at +0.05 (buys) / +0.15 (sells) x the trade's risk, then the rest's stop
   goes to the entry price; day lock: once the day is +2R, close all if it falls back to +1R (no more trades); everything closes at 20:00
   broker (Fridays too) at the close bar's open.
 - v1.03 SIZE: first trade 1/3, buys 1/3, later sells full while the day is in profit (R, marked at the signal price), else 1/3.
 - Right way first = +0.3 A before -0.3 A from the signal price, until the close bar (same bar both = undecided)."""
import numpy as np, pandas as pd

KEEP_DAYS = 60
SLIP = True                     # False only for the parity test against the no-slip EA port
EDG = (0.05, 0.10, 0.20, 0.40); SLP = (0.013, 0.017, 0.020, 0.023, 0.025)   # MT4-like slip by the signal minute's range (calibrated on his MT4 run 1: 53.0%)
RWF_X, MIN_DIST, ROUND_GAP = 0.3, 0.05, 0.15
# ---- v1.03 exits / times / sizes (same inputs as the EA WTI_DAYTRADE v1.03, his MT4 runs 18 Oct 2026)
BUY_STOP, SELL_STOP = 1.00, 0.75          # x 14-day range
BUY_HALF, SELL_HALF = 0.05, 0.15          # close PART at +k x the trade's risk, then the rest's stop goes to the entry price
PART = 0.25                               # v1.04: part closed at that level (v1.03 = 0.5)
LOCK_PEAK, LOCK_FLOOR = 2.0, 1.0          # day up +2R -> close all if it falls back to +1R; no more trades that day
LAST_ENTRY, LATE_FIRST, CLOSE_HM = 16 * 60 + 30, 19 * 60, 20 * 60      # broker minutes
MIN_SP = 0.02
FAM_NAME = {'settle': "Yesterday's settlement", 'open+-0.5': 'Open ± ½ range', 'open+-0.7': 'Open ± 0.7 range', 'open+-1.0': 'Open ± 1 range',
            'yday': "Yesterday's high/low", 'lastweek': "Last week's high/low", 'round1': 'Whole dollar'}

def close_hm(day):
    return CLOSE_HM                                                     # v1.03: 20:00 broker every day (Fridays too)

def daily_from_minutes(t, o, h, l, c):
    """One finished broker day of minute bars (broker times) -> [open, high, low, close, settle]."""
    t = pd.DatetimeIndex(t); hm = t.hour * 60 + t.minute
    s = np.flatnonzero((hm >= 21 * 60 + 30) & (hm <= 21 * 60 + 35))
    return [float(o[0]), float(np.max(h)), float(np.min(l)), float(c[-1]), (float(o[s[0]]) if len(s) else None)]

def prep(hist, day):
    """Levels input for `day` from finished history rows (oldest first). Returns None when the EA would not trade the day."""
    day = pd.Timestamp(day).normalize()
    H = [r for r in hist if pd.Timestamp(r[0]) < day]
    if len(H) < 15: return None
    prev = H[-1]; pd_ = pd.Timestamp(prev[0])
    if (day - pd_).days > 3: return None
    rng = [r[2] - r[3] for r in H[-14:]]; A = float(np.mean(rng))
    wk = day.to_period('W'); lw = [r for r in H if pd.Timestamp(r[0]).to_period('W') == wk - 1]
    return dict(A=A, yhi=prev[2], ylo=prev[3], yrange=prev[2] - prev[3], settle=prev[5],
                lwh=(max(r[2] for r in lw) if lw else np.nan), lwl=(min(r[3] for r in lw) if lw else np.nan))

def run_day(P, t, O, H, L, C, now=None, spread=None, final=False):
    """P = prep(...); t/O/H/L/C = today's minute bars so far (broker times, closed bars only). Returns the day's ladder trades with their
    state as of `now` (default: end of the bars). A trade is reported only once its signal bar has closed. final=True (the broker day is over):
    a day with no close bar (holiday early close) closes open trades at the last bar's close, like the EA port."""
    if P is None or len(t) == 0: return []
    t = pd.DatetimeIndex(t); O, H, L, C = (np.asarray(x, float) for x in (O, H, L, C)); n = len(t)
    hm = (t.hour * 60 + t.minute).values; day = t[0].normalize(); lim = close_hm(day)
    eod = int(np.searchsorted(hm, lim)); has_close = eod < n           # index of the close bar if it already exists
    end = min(eod, n)                                                   # signals are scanned up to (not incl.) the close bar
    def at(x, slack=5):
        p = int(np.searchsorted(hm, x)); return p if p < n and hm[p] <= x + slack else -1
    A = P['A']; fams = []
    a = at(16 * 60); fams.append(('settle', a, [P['settle']] if P['settle'] is not None else []))
    for x in (0.5, 0.7, 1.0): fams.append((f'open+-{x}', 1, [O[0] + x * P['yrange'], O[0] - x * P['yrange']]))
    fams.append(('yday', at(7 * 60), [P['yhi'], P['ylo']]))
    fams.append(('lastweek', at(2 * 60), [P['lwh'], P['lwl']]))
    a = at(10 * 60)
    if a >= 0:
        p0 = O[a]; fl, ce = np.floor(p0), np.ceil(p0)
        fams.append(('round1', a, [fl if p0 - fl > ROUND_GAP * A else np.nan, ce if ce - p0 > ROUND_GAP * A else np.nan]))
    EV = []
    for fi, (nm, a, lvls) in enumerate(fams):
        if a < 0 or a >= end: continue
        best = None
        for lv in lvls:
            if lv is None or not np.isfinite(lv): continue
            side = 1 if O[a] > lv else -1
            if abs(O[a] - lv) < MIN_DIST * A: continue
            for m in range(a, end):
                if (side > 0 and L[m] <= lv - 0.01) or (side < 0 and H[m] >= lv + 0.01):
                    if best is None or m < best[0]: best = (m, lv, -side)
                    break
        if best:
            m, lv, d = best; px = max(lv, O[m]) if d > 0 else min(lv, O[m])
            r = H[m] - L[m]; j = 0
            while j < 4 and r > EDG[j]: j += 1
            EV.append((m, fi, d, px + (d * SLP[j] if SLIP else 0.0), nm, lv))
    EV.sort(key=lambda r: (r[0], r[1]))
    def SPm(m):
        x = None if spread is None else spread[m]
        return max(MIN_SP, float(x)) if x is not None and np.isfinite(x) else MIN_SP
    bym = {}
    for ev in EV: bym.setdefault(ev[0], []).append(ev)
    legs = []; banked = 0.0; peak = 0.0; off = False; ddir = 0; lastm = -1; lastd = 0; off_i = None
    def mark(g, bid):                                   # leg result in R x its size, at a bid price
        px = bid if g['dir'] > 0 else bid + g['sp']
        return g['w'] * (g['bank'] + g['q'] * g['dir'] * (px - g['e']) / g['sd'])
    def close_leg(g, bid, q_i, why):
        nonlocal banked
        px = bid if g['dir'] > 0 else bid + g['sp']
        g['bank'] += g['q'] * g['dir'] * (px - g['e']) / g['sd']; g['q'] = 0.0; g['on'] = False
        g['exit'], g['exit_i'], g['why'] = float(bid), q_i, why; banked += g['w'] * g['bank']
    m0 = EV[0][0] if EV else n
    for m in range(m0, n):
        if m == eod:                                                    # 20:00 broker close: everything out at the close bar's open
            for g in legs:
                if g['on']: close_leg(g, O[m], m, 'eod')
            break
        for (mm, fi, d, px, nm, lv) in bym.get(m, []):
            if off: continue
            if hm[m] >= LAST_ENTRY and not (len(legs) == 0 and hm[m] < LATE_FIRST): continue
            if ddir != 0 and d != ddir: continue
            if m == lastm and d == lastd: continue
            sd = (BUY_STOP if d > 0 else SELL_STOP) * A; sp = SPm(m)
            st = banked + sum(mark(g, px) for g in legs if g['on'])
            w = ((1.0 if (d < 0 and P.get('first_sell_full')) else 1 / 3) if len(legs) == 0 else ((1.0 if st > 0 else 1 / 3) if d < 0 else 1.0))   # v1.05 first sell
            if d > 0: w = min(w, 1 / 3)
            e = px + sp if d > 0 else px                                   # buy fills at the ask, sell at the bid
            stop_b = px - sd if d > 0 else px + sd                          # stop in BID terms (sell stop = ask + sd)
            rk = sd + sp; k = BUY_HALF if d > 0 else SELL_HALF
            hp = e + d * k * rk                                             # half level in the order's own price (buy: bid, sell: ask)
            legs.append(dict(i=m, t=t[m], dir=d, px=float(px), level=float(lv), fam=nm, name=FAM_NAME[nm], sd=sd, sp=sp, e=e, w=w,
                             stop0=float(stop_b), stop=float(stop_b), half_px=float(hp if d > 0 else hp - sp), half=False, bank=0.0, q=1.0,
                             on=True, exit=None, exit_i=None, why=None, late=bool(hm[m] >= LAST_ENTRY), first=(len(legs) == 0)))
            if ddir == 0: ddir = d
            lastm, lastd = m, d
        for g in legs:                                                  # bar m: stop first (gap-aware), then the half-close
            if not g['on'] or m <= g['i']: continue
            d = g['dir']
            if (d > 0 and L[m] <= g['stop']) or (d < 0 and H[m] >= g['stop']):
                b = min(g['stop'], O[m]) if d > 0 else max(g['stop'], O[m])
                close_leg(g, b, m, 'be' if g['half'] else 'stopped'); continue
            if not g['half'] and ((d > 0 and H[m] >= g['half_px']) or (d < 0 and L[m] <= g['half_px'])):
                g['bank'] += PART * d * ((g['half_px'] if d > 0 else g['half_px'] + g['sp']) - g['e']) / g['sd']; g['q'] = 1.0 - PART; g['half'] = True
                g['half_t'] = t[m]; g['stop'] = float(g['e'] if d > 0 else g['e'] - g['sp'])      # rest's stop = entry price (bid terms)
        tot = banked + sum(mark(g, C[m]) for g in legs if g['on']); peak = max(peak, tot)
        if not off and peak >= LOCK_PEAK and tot <= LOCK_FLOOR:
            for g in legs:
                if g['on']: close_leg(g, C[m], m, 'day lock')
            off = True; off_i = m
    if final and not has_close:
        for g in legs:
            if g['on']: close_leg(g, C[n - 1], n - 1, 'eod')
    out = []
    for g in legs:
        m, d, px = g['i'], g['dir'], g['px']
        rwf = None; tg = RWF_X * A; last = min(eod, n - 1) if has_close else n - 1; decided = False
        for q in range(m + 1, last + 1):
            up = (H[q] - px) if d > 0 else (px - L[q]); dn = (px - L[q]) if d > 0 else (H[q] - px)
            if up >= tg and dn >= tg: decided = True; break
            if up >= tg: rwf = 1; decided = True; break
            if dn >= tg: rwf = 0; decided = True; break
        res = None if g['on'] else round(g['bank'] * g['sd'], 4)          # $ per barrel for a FULL-size trade, spread included
        out.append(dict(i=m, t=t[m], dir=d, px=px, level=g['level'], fam=g['fam'], name=g['name'], stop=g['stop'], stop0=g['stop0'],
                        half_px=g['half_px'], half=g['half'], part=PART, first=g['first'], late=g['late'], size='full' if g['w'] == 1.0 else '1/3',
                        status=('open' if g['on'] else g['why']), exit=g['exit'], exit_t=(None if g['exit_i'] is None else t[g['exit_i']]),
                        res=res, R=(None if g['on'] else round(g['bank'], 4)), rwf=rwf, rwf_final=decided or has_close or final, A=A, spread=g['sp']))
    return out
