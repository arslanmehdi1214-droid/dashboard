"""S&P 500 (US500) PAPER engine for the Signal Desk - "version A" (MT4-proven 22 Oct 2026: his run SP500_DAYTRADE v1.00, .US500Cash M1 every
tick, spread 0.8 pt, 2020-01-01..2026-09-30: 2,330 trades, net $16,398 at $100 risk per leg, net/DD 6.23, worst day -$310; Python $16,437).
Broker clock = New York + 7 h (bid prices). One ladder per day:
  EVENTS  (a) Nasdaq desk picks (the Nasdaq engine's day picks: first core signal + a filler before it) copied to the S&P at the NEXT minute,
              same side, only when that S&P minute is in US hours 16:30-21:59 broker;
          (b) S&P book: 16:40 opening move (open 16:40 - open 16:00 beyond 0.05 x range -> follow);
              yesterday high/low sweep by 0.1 x range from 09:00 and from 13:00 broker (scan to 19:00), back inside within 30 min -> reverse,
              entry the next minute;
              day move since the open >= 0.8 x range at the first bar from 17:00 -> follow, entry the next minute (this idea is in the book
              twice - as "follow" and as "reversed fade" - so it adds two legs, exactly as tested).
  LADDER  the day's first event sets the side; later events the same side add a leg (max 3 legs); the other side is ignored.
          Same-minute events are taken in the research order (minute, side, source). No entries in the day-end minute or from 22:25 broker.
  EXIT    stop = 0.75 x the 14-day average daily range (high-low of the 14 previous broker days) from the entry; no half-close;
          everything closes at the open of the first bar at/after 22:30 broker (3:30 pm New York); if no such bar, at the day's last close.
Results: points per leg after a 0.8 pt cost (never less than Capital.com's live spread)."""
import numpy as np, pandas as pd

SM = 0.75; LEGS = 3; MOM_K = 0.05; SWEEP_X = 0.1; SWEEP_W = 30; K4_X = 0.8
X_MIN = 22 * 60 + 30; LAST_MIN = X_MIN - 5; US_LO = 16 * 60 + 30; US_HI = 22 * 60; END_H = 19
COST = 0.8

def eod_minutes(day): return 22 * 60 + 50 if pd.Timestamp(day).dayofweek == 4 else 23 * 60

def day_ctx(hist, day):
    """hist: minute bars (index broker time, o h l c) BEFORE `day`. Returns (A, prev high, prev low) like the research base:
    A = mean high-low of the 14 previous broker days (weekdays with bars)."""
    h = hist[hist.index < day]; h = h[h.index.dayofweek < 5]
    g = h.groupby(h.index.normalize()); hi = g.h.max(); lo = g.l.min()
    rng = (hi - lo).iloc[-14:]
    if len(rng) < 14: return np.nan, np.nan, np.nan
    return float(rng.mean()), float(hi.iloc[-1]), float(lo.iloc[-1])

def _first_bar(hm, minute):
    p = int(np.searchsorted(hm, minute)); return p if p < len(hm) else -1
def _exact(hm, minute):
    p = int(np.searchsorted(hm, minute)); return p if p < len(hm) and hm[p] == minute else -1

def book_events(b, A, pH, pL):
    """S&P book events of one day. b: today's bars. Returns list of (entry_index, side, name)."""
    O, H, L, C = (b[c].values.astype(float) for c in 'ohlc'); hm = (b.index.hour * 60 + b.index.minute).values; n = len(O); E = []
    if n == 0 or not np.isfinite(A): return E
    i0, i1 = _exact(hm, 960), _exact(hm, 1000)                                   # 16:00 and 16:40 bars
    ref = O[i0] if i0 >= 0 else None
    if ref is None:                                                              # no 16:00 bar: the research's filler bar = last close before it
        p = int(np.searchsorted(hm, 960)) - 1
        if p >= 0 and hm[p] >= 960 - 90: ref = C[p]
    if i1 < 0:                                                                   # no 16:40 bar (no ticks): enter at the first bar within 5 min after
        p = int(np.searchsorted(hm, 1000))
        if p < n and hm[p] <= 1005: i1 = p
    if ref is not None and i1 >= 0:
        mv = O[i1] - ref
        if mv != 0 and abs(mv) > MOM_K * A: E.append((i1, int(np.sign(mv)), 'S&P 9:40 am New York opening move'))
    for tb, lab in ((9, '10am'), (13, '2pm')):                                   # yesterday high/low sweep -> reverse
        i = _first_bar(hm, tb * 60)
        if i < 0 or not np.isfinite(pH): continue
        ie = _first_bar(hm, END_H * 60); ie = n if ie < 0 else ie
        up, dn = pH + SWEEP_X * A, pL - SWEEP_X * A; j = -1; sd = 0
        for q in range(i, ie):
            hu, hd = H[q] >= up, L[q] <= dn
            if hu and hd: j = q; sd = 0; break
            if hu: j = q; sd = 1; break
            if hd: j = q; sd = -1; break
        if j < 0 or sd == 0: continue
        lvl = pH if sd > 0 else pL
        for jj in range(j + 1, min(j + SWEEP_W, ie)):
            if (sd > 0 and C[jj] < lvl) or (sd < 0 and C[jj] > lvl):
                if jj + 1 < n: E.append((jj + 1, -sd, f'S&P yesterday {"high" if sd > 0 else "low"} swept ({lab} scan), back inside -> reverse'))
                break
    i = _first_bar(hm, 17 * 60)
    if i >= 0 and abs(O[i] - O[0]) >= K4_X * A and i + 1 < n:                   # day move since the open at 17:00 -> follow (twice, as tested)
        s = int(np.sign(O[i] - O[0]))
        E.append((i + 1, s, 'S&P big day move by 10 am New York -> follow')); E.append((i + 1, s, 'S&P big day move by 10 am New York -> follow (2nd leg)'))
    return E

def nasdaq_events(b, picks):
    """picks: [(nasdaq minute Timestamp, side), ...] -> S&P entry at the NEXT minute (must exist), US hours only."""
    idx = b.index; hm = (idx.hour * 60 + idx.minute).values; E = []
    for t, s in picks:
        p = int(idx.searchsorted(pd.Timestamp(t) + pd.Timedelta(minutes=1)))
        if p < len(idx) and idx[p] == pd.Timestamp(t) + pd.Timedelta(minutes=1) and US_LO <= hm[p] < US_HI:
            E.append((p, int(s), 'Nasdaq signal copied'))
    return E

def legs_of_day(b, A, pH, pL, picks, day, day_done=True):
    """The day's ladder: list of dict(j, dir, src, name, leg). day_done=False (live, 22 Oct fix): until a bar at/after the close time
    exists, the latest closed bar is not the day-end bar (a signal on it is no longer held back a minute). Full days: unchanged."""
    hm = (b.index.hour * 60 + b.index.minute).values; n = len(b)
    eodm = eod_minutes(day); eod_i = _first_bar(hm, eodm); eod_i = (n - 1 if day_done else n) if eod_i < 0 else eod_i
    ev = [(j, s, 1, nm) for j, s, nm in book_events(b, A, pH, pL)] + [(j, s, 0, nm) for j, s, nm in nasdaq_events(b, picks)]
    ev.sort(key=lambda x: (x[0], x[1], x[2]))
    out = []; side = 0
    for j, s, src, nm in ev:
        if j >= eod_i or hm[j] >= LAST_MIN: continue
        if side == 0: side = s
        if s == side and len(out) < LEGS: out.append(dict(j=j, dir=s, src=src, name=nm, leg=len(out) + 1))
    return out

def manage(b, legs, A, day, sp=COST, now_done=True):
    """Walk each leg through today's closed bars. status: open / stopped / eod. r = result in units of the stop after the cost."""
    O, H, L, C = (b[c].values.astype(float) for c in 'ohlc'); hm = (b.index.hour * 60 + b.index.minute).values; n = len(O)
    eodm = eod_minutes(day); out = []
    for g in legs:
        j, s = g['j'], g['dir']; en = float(g.get('entry', O[j])); sd = float(g.get('sd', SM * A)); stp = en - s * sd; st = 'open'; ex = None; ext = None   # frozen legs keep entry/stop
        for m in range(j, n):
            if m > j and hm[m] >= X_MIN: st, ex, ext = 'eod', O[m], m; break
            if hm[m] >= eodm and m > j: st, ex, ext = 'eod', O[m], m; break
            if s > 0 and L[m] <= stp: st, ex, ext = 'stopped', stp, m; break
            if s < 0 and H[m] >= stp: st, ex, ext = 'stopped', stp, m; break
        if st == 'open' and now_done and n: st, ex, ext = 'eod', C[n - 1], n - 1
        pts = None if ex is None else s * (ex - en) - sp
        out.append(dict(g, t=g.get('t', b.index[j]), entry=float(en), stop=float(stp), stop0=float(stp), sd=float(sd), A=float(g.get('A', A)), status=st,
                        exit=None if ex is None else float(ex), exit_t=None if ext is None else b.index[ext], pts=pts,
                        r=None if pts is None else pts / sd, r_now=(s * (C[n - 1] - en) - sp) / sd if n else None))
    return out

def run_day(hist, today, day, picks, sp=COST, day_over=False):
    """hist: bars before `day` (>= 15 days); today: today's CLOSED bars; picks: Nasdaq desk picks of `day`. Returns managed legs."""
    A, pH, pL = day_ctx(hist, day)
    if not np.isfinite(A) or not len(today): return []
    legs = legs_of_day(today, A, pH, pL, picks, day, day_done=day_over)
    return manage(today, legs, A, day, sp, now_done=day_over)
