"""GBP/USD crowd engine (GBP_CROWD v1.03 rules, MT4-proven 24 Oct 2026: his run 4, 3,810 trades 2011-2026, net $12,108.90 at 0.10 lot,
max DD $2,090.54, net/DD 5.79, all 4 periods positive, 95.3% of weekdays traded, profit days 49.2%; v1.02 = layers 1-3 only). Pure functions, no I/O - used by gbp_run.py (desk) and the parity tests.
Signal (weekly, CFTC Traders in Financial Futures, British Pound 096742; Tuesday report used from the Monday after = report date + 6 days):
  layer 1: leveraged funds' net/OI in the top / bottom 10% of the last 52 weeks -> fade them (SELL / BUY)
  layer 2: else small traders' (non-reportable) net/OI in the top / bottom 20% -> fade them
  layer 3: else small traders' 1-week change of net/OI in the top / bottom 25% -> fade it
  layer 4 (v1.03, daily): else EUR/GBP at 10:00 broker of the last 20 trading days BEFORE today: z of the newest > 1.5 -> BUY (pound cheap
           vs euro, snaps back), z < -1.5 -> SELL
  layer 5 (v1.03, weekly): else FOLLOW leveraged funds in EURO futures (CFTC TFF 099741): net/OI in the top 25% of 52 weeks -> BUY, bottom 25% -> SELL
Trade: one a day, entry at the first bar from 10:00 to 10:05 broker (New York + 7 h), stop 1.0 x the 14-day average daily range,
target 1.0 x stop, close 23:45 broker; a trade still open when the day has no 23:45 bar closes at the day's last price (v1.02 catch-up)."""
import numpy as np, pandas as pd

Q1, Q2, Q3 = 0.10, 0.20, 0.25
STOP_X, TGT_X, RANGE_DAYS = 1.0, 1.0, 14
ENTRY_MIN, ENTRY_LATE, CLOSE_MIN = 10 * 60, 5, 23 * 60 + 45
COST = 0.00015                                   # 1.5 pips (the research cost); the desk uses max(this, live spread)
LAYER_NAME = {1: 'Layer 1 · hedge funds crowded', 2: 'Layer 2 · small traders crowded', 3: 'Layer 3 · small traders jumped in',
              4: 'Layer 4 · pound stretched vs euro', 5: 'Layer 5 · euro hedge funds trend'}
Q5, EG_W, EG_Z = 0.25, 20, 1.5

def rank_pct(v, win=52, minp=26):
    """rolling 52-week percentile of the newest value = pandas rolling(52, min_periods=26).rank(pct=True) (average ties)."""
    v = np.asarray(v, float); out = np.full(len(v), np.nan)
    for i in range(len(v)):
        w = v[max(0, i - win + 1):i + 1]; w = w[np.isfinite(w)]
        if len(w) < minp or not np.isfinite(v[i]): continue
        out[i] = (np.sum(w < v[i]) + (np.sum(w == v[i]) + 1) / 2) / len(w)
    return out

def codes(W):
    """W: weekly DataFrame indexed by report date with oi, lev_l, lev_s, nr_l, nr_s. Returns a DataFrame with the percentiles and
    code = +-1 / +-2 / +-3 (sign = BUY / SELL, number = layer), 0 = no trade."""
    W = W.sort_index(); lev = (W.lev_l - W.lev_s) / W.oi; nr = (W.nr_l - W.nr_s) / W.oi
    lp, npc, ncp = rank_pct(lev.values), rank_pct(nr.values), rank_pct(nr.diff().values)
    f = lambda p, q: np.where(p >= 1 - q, -1, np.where(p <= q, 1, 0))
    t1, t2, t3 = f(lp, Q1), f(npc, Q2), f(ncp, Q3)
    c = np.where(t1 != 0, t1, np.where(t2 != 0, 2 * t2, 3 * t3))
    return pd.DataFrame(dict(lev=lev, nr=nr, levp=lp, nrp=npc, nrcp=ncp, code=c), index=W.index)

def code_for(C, day):
    """the code that applies on broker day `day`: latest report with report date + 6 days <= day. Returns (code, report date) or (0, None)."""
    if C is None or not len(C): return 0, None
    use = C.index + pd.Timedelta(days=6); i = int(use.searchsorted(pd.Timestamp(day), side='right')) - 1
    if i < 0: return 0, None
    return int(C.code.values[i]), C.index[i]

def eur_codes(W):
    """W: weekly EURO FX TFF rows (oi, lev_l, lev_s) by report date -> levp + code +1 (funds long euro: BUY GBP/USD) / -1 / 0 (layer 5 follows them)."""
    W = W.sort_index(); lev = (W.lev_l - W.lev_s) / W.oi; p = rank_pct(lev.values)
    return pd.DataFrame(dict(lev=lev, levp=p, code=np.where(p >= 1 - Q5, 1, np.where(p <= Q5, -1, 0))), index=W.index)

def eg_side(vals):
    """vals = EUR/GBP at 10:00 broker on the trading days BEFORE today, oldest first. Uses the newest 20 (= pandas rolling(20) z of
    yesterday's value). Returns (+1 BUY / -1 SELL / 0, z)."""
    v = np.asarray(vals, float)[-EG_W:]
    if len(v) < EG_W or not np.isfinite(v).all(): return 0, np.nan
    sd = v.std(ddof=1)
    if not sd > 0: return 0, np.nan
    z = (v[-1] - v.mean()) / sd
    return (1 if z > EG_Z else -1 if z < -EG_Z else 0), float(z)

def decide(gcode, eg, ecode):
    """v1.03 order: GBP layers 1-3, else layer 4 (EUR/GBP), else layer 5 (euro funds). Returns code +-1..+-5 or 0."""
    if gcode: return int(gcode)
    if eg: return 4 * int(eg)
    return 5 * int(ecode)

def avg_range(daily, day):
    """14-day average daily high-low of the weekdays BEFORE `day` (daily: index broker dates, columns h, l). NaN if fewer than 14 days."""
    d = daily[(daily.index < pd.Timestamp(day)) & (daily.index.dayofweek < 5)]
    if len(d) < RANGE_DAYS: return np.nan
    return float((d.h - d.l).iloc[-RANGE_DAYS:].mean())

def trade(b, day, code, A, now=None, cost=COST):
    """b = the day's closed minute bars (index broker time, columns o h l c, bid). Returns a trade dict or None.
    status: open / target / stopped / eod (23:45 close) / close_now (day over, no 23:45 bar = catch-up close)."""
    if code == 0 or not np.isfinite(A) or A <= 0 or not len(b): return None
    day = pd.Timestamp(day); t0 = day + pd.Timedelta(minutes=ENTRY_MIN); te = day + pd.Timedelta(minutes=CLOSE_MIN)
    a = int(b.index.searchsorted(t0))
    if a >= len(b) or b.index[a] - t0 > pd.Timedelta(minutes=ENTRY_LATE): return None    # no bar 10:00-10:05 -> no trade (as the EA)
    s = 1 if code > 0 else -1; en = float(b.o.values[a]); sd = STOP_X * A
    st, tg = en - s * sd, en + s * TGT_X * sd
    e = int(b.index.searchsorted(te))                                                      # first bar at/after 23:45 (exit at its open)
    H, L = b.h.values[a:e], b.l.values[a:e]
    hs = (L <= st) if s > 0 else (H >= st); ht = (H >= tg) if s > 0 else (L <= tg)
    js = int(np.argmax(hs)) if hs.any() else 10**9; jt = int(np.argmax(ht)) if ht.any() else 10**9
    out = dict(t=b.index[a], dir=s, layer=abs(code), entry=en, sd=sd, A=A, stop=st, target=tg, exit=None, exit_t=None, status='open', pips=None)
    if js < 10**9 or jt < 10**9:
        j = min(js, jt); out.update(status='stopped' if js <= jt else 'target', exit=st if js <= jt else tg, exit_t=b.index[a + j])
    elif e < len(b):
        out.update(status='eod', exit=float(b.o.values[e]), exit_t=b.index[e])
    elif now is not None and pd.Timestamp(now) >= day + pd.Timedelta(days=1):                # day over without a 23:45 bar
        out.update(status='close_now', exit=float(b.c.values[-1]), exit_t=b.index[-1])
    if out['exit'] is not None: out['pips'] = (s * (out['exit'] - en) - cost) * 1e4
    return out
