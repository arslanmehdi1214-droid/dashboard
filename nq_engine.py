"""Nasdaq 100 (US Tech 100) PAPER engine for the Signal Desk - the 2026 walk-forward set (re-picked each January in Python).
Signals = the research idea code itself (nq_a = normal hours, nq_b = every start hour shifted +10 h into the US session), run on a
rolling base of recent minute bars (broker clock = New York + 7 h, bid prices). Per day: the first CORE signal of the day is a trade;
a FILLER signal is a trade only if it fires before the day's first core signal (first filler of the day only); max 2 trades a day.
Fills (same as the research): market = the minute's open; break = at the level when the minute trades to it; fade/limit = at the level
only if the minute trades THROUGH it by max(0.25, 0.01 x range). Stop = 0.25 x 14-day average daily range from the fill level;
no target; close at the day end (23:00 broker, Fri 22:50). No entry in the day-end minute."""
import os, sys, io, json, contextlib, importlib, tempfile, pickle, numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = {'a': os.path.join(HERE, 'nq_a'), 'b': os.path.join(HERE, 'nq_b')}
MODS = ['core', 'comp', 'spxC'] + [f'fam{s}' for s in ('', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11')]
SET = json.load(open(os.path.join(HERE, 'nq_set.json')))
STOP_X = SET['stop']; TICK = 0.25; KEEP_DAYS = 300

def eod_minutes(day):
    return 22 * 60 + 50 if pd.Timestamp(day).dayofweek == 4 else 23 * 60

def build_base(m, out):
    """m: minute bars (index = broker time, columns o h l c), weekdays, sorted. Same layout as the research base (build_base_n.py)."""
    t = m.index.values.astype('datetime64[ns]'); O, H, L, C = (m[c].values.astype(float) for c in 'ohlc')
    tt = pd.DatetimeIndex(t); day = tt.normalize(); hr = tt.hour.values; mi = tt.minute.values
    dcode, duniq = pd.factorize(day)
    g = pd.DataFrame({'h': H, 'l': L, 'o': O, 'c': C, 'd': dcode}).groupby('d')
    DB = pd.DataFrame({'o': g.o.first(), 'h': g.h.max(), 'l': g.l.min(), 'c': g.c.last()})
    DB['rng'] = DB.h - DB.l; DB['atr'] = DB.rng.rolling(14).mean().shift(1); DB['ph'] = DB.h.shift(1); DB['pl'] = DB.l.shift(1)
    A = DB.atr.values[dcode]; PH = DB.ph.values[dcode]; PL = DB.pl.values[dcode]; DO = DB.o.values[dcode]
    dow = tt.dayofweek.values
    eod_t = (day + pd.to_timedelta(np.where(dow == 4, 22 * 60 + 50, 23 * 60), unit='m')).values
    EOD = np.searchsorted(t, eod_t); dlast = np.r_[np.where(np.diff(dcode) != 0)[0], len(t) - 1][dcode]; EOD = np.minimum(EOD, dlast)
    np.savez(os.path.join(out, 'base.npz'), O=O, H=H, L=L, C=C, V=np.zeros(len(O)), A=A, PH=PH, PL=PL, DO=DO, dcode=dcode, hr=hr, mi=mi, EOD=EOD,
             yr=tt.year.values, dow=dow)
    pickle.dump(dict(t=t), open(os.path.join(out, 'base_t.pkl'), 'wb'))
    lad = pd.DataFrame({'edir': np.zeros(len(duniq), int), 'et': pd.Series([pd.NaT] * len(duniq), dtype='datetime64[s]').values}, index=duniq)
    lad.to_pickle(os.path.join(out, 'lad.pkl'))
    return dict(O=O, H=H, L=L, C=C, A=A, EOD=EOD, t=tt, dcode=dcode, hm=hr * 60 + mi)

def _purge():
    for n in MODS: sys.modules.pop(n, None)

def ideas(pkg, base_dir):
    """Import the research idea code from one package on the base in base_dir; returns {name: function} (twins not included)."""
    _purge(); os.environ['NQ_BASE'] = base_dir; sys.path.insert(0, PKG[pkg])
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            mods = [importlib.import_module(n) for n in ('fam5', 'fam6', 'fam7', 'fam11', 'spxC')]
        ALL = {}
        for mod in mods[:4]:
            for dn in ('IDEAS', 'IDEAS2', 'IDEAS3', 'IDEAS4', 'IDEAS5', 'IDEAS6', 'IDEAS7', 'IDEAS8', 'IDEAS9', 'IDEAS10', 'IDEAS11'):
                if hasattr(mod, dn): ALL.update(getattr(mod, dn))
        for n, f in mods[4].IDEASC.items(): ALL['C ' + n] = f
        return ALL
    finally:
        sys.path.remove(PKG[pkg])

def s11_events(name, B):
    """S11 ideas made inside the research script s11.py (only the opening-drive family is used)."""
    w = name.split()                                   # 'S11 opening drive 5min >0.2 follow'
    mins = int(w[3].replace('min', '')); thr = float(w[4][1:])
    hm, dc = B['hm'], B['dcode']; starts = np.r_[0, np.where(np.diff(dc) != 0)[0] + 1]; ends = np.r_[starts[1:], len(dc)]; E = []
    def at(k, mn):
        s, e = starts[k], ends[k]; p = s + np.searchsorted(hm[s:e], mn)
        return p if p < e and hm[p] <= mn + 5 else -1
    for k in range(len(starts)):
        a = at(k, 990); i = at(k, 990 + mins)
        if a < 0 or i < 0: continue
        mv = (B['C'][i - 1] - B['O'][a]) / B['A'][i]
        if abs(mv) > thr: E.append((k, i, B['O'][i], int(np.sign(mv))))
    return E

def filled(j, px, d, B):
    """Research fill rule (wf.py fill_acc): True if the order fills inside minute j."""
    O, H, L, A = B['O'], B['H'], B['L'], B['A']; m = max(TICK, 0.01 * A[j])
    if px == O[j]: return True
    if px > O[j]: return H[j] >= px if d > 0 else H[j] >= px + m
    return L[j] <= px if d < 0 else L[j] <= px - m

def day_events(B, names, funcs_a, funcs_b, k_today):
    """All filled events of day k_today for every name: list of (j, order_in_set, name, d, px)."""
    out = []
    for oi, nm in enumerate(names):
        rev = nm.startswith('REV '); base = nm[4:] if rev else nm
        if base.startswith('US+10 '): f = funcs_b.get(base[6:])
        elif base.startswith('S11 '): f = (lambda b=base: s11_events(b, B))
        else: f = funcs_a.get(base)
        if f is None: raise KeyError('signal not found: ' + nm)
        for (k, j, px, d) in f():
            if int(k) != k_today: continue
            j = int(j); d = -int(d) if rev else int(d); px = float(px)
            if j >= B['EOD'][j]: continue                        # no entry in the day-end minute
            if filled(j, px, d, B): out.append((j, oi, nm, d, px))
    return out

def first_trade(ev):
    """Research ladder with cap 1 = the earliest event (ties: set order)."""
    return min(ev, key=lambda e: (e[0], e[1])) if ev else None

def manage(B, j, d, px, now_idx):
    """Stop / day-end exit of a trade entered in minute j, using minutes after j up to now_idx (inclusive)."""
    O, H, L, A, EOD = B['O'], B['H'], B['L'], B['A'], B['EOD']; stop = px - d * STOP_X * A[j]; e = EOD[j]
    full_day = B['t'][e].hour * 60 + B['t'][e].minute >= eod_minutes(B['t'][j])
    for m in range(j + 1, min(e, now_idx) + 1):
        if m == e and full_day: return stop, 'eod', O[m], B['t'][m]
        if d > 0:
            if O[m] <= stop: return stop, 'stop', O[m], B['t'][m]
            if L[m] <= stop: return stop, 'stop', stop, B['t'][m]
        else:
            if O[m] >= stop: return stop, 'stop', O[m], B['t'][m]
            if H[m] >= stop: return stop, 'stop', stop, B['t'][m]
    return stop, 'open', None, None

def run_day(m, day, now=None):
    """m: minute bars (broker time) of the last ~300 days INCLUDING today's closed minutes; returns today's paper trades."""
    day = pd.Timestamp(day).normalize(); m = m[(m.index < day + pd.Timedelta(days=1))]
    if now is not None: m = m[m.index + pd.Timedelta(minutes=1) <= now]
    if not len(m) or m.index[-1].normalize() != day: return []
    with tempfile.TemporaryDirectory() as td:
        B = build_base(m, td)
        k_today = int(B['dcode'][-1])
        if not np.isfinite(B['A'][-1]): return []
        names = SET['core'] + SET['fill']
        need_b = any(n.replace('REV ', '', 1).startswith('US+10 ') for n in names)
        fa = ideas('a', td); fb = ideas('b', td) if need_b else {}
        _purge()
        ev = day_events(B, names, fa, fb, k_today)
    nc = len(SET['core'])
    c = first_trade([e for e in ev if e[1] < nc]); f = first_trade([e for e in ev if e[1] >= nc])
    picks = ([c] if c else []) + ([f] if f and (c is None or f[0] < c[0]) else [])
    trades = []
    for (j, oi, nm, d, px) in sorted(picks):
        stop, st, ex, ext = manage(B, j, d, px, len(B['O']) - 1)
        trades.append(dict(t=B['t'][j], j=j, name=nm, role='core' if oi < nc else 'filler', dir=d, px=px, stop=float(stop),
                           A=float(B['A'][j]), status=st, exit=None if ex is None else float(ex), exit_t=ext))
    return trades
