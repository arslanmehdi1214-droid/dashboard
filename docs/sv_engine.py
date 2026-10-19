"""SILVER v1.8 signal engine (desk paper) - the SAME rules as SILVER_DAYTRADE.mq4 v1.8 (MT4 pass 19 Oct 2026, his run).
Built from the research code (silver_dt/sv: ens10.py, book1.py, uni1.py, comb1.py, reg2/reg3.py, famn fam8/fam9/fam10/fam11).

ENTRY (U1, ENS10a): 2 of 3 voters agree on a side -> trade at that moment, first agreement of the broker day only.
  G  = every gold v2.06 engine signal (noskip engine, signals not 'against' the day's earlier trades), mirrored on silver at the NEXT silver minute.
  F1 = fast catch-up: gold moved >= 0.30 x its 14-day range more than silver over the last 5 silver bars (01:15-22:00 broker) -> next minute; first per day.
  CP = strict compression breakout (34 fixed members: TTM squeeze KC 1.5/2.0, ADX<12, BB width <= 20th pct + break of 2/3/5-day range
       from 10am/11am/1pm, R11 with +0.1/0.2 x range buffer); the earliest member break of the day.
U4: on a day with no U1 trade, the 10-bar catch-up (gap >= 0.35) inside 120 bars after a US high-impact release.
U2: size 2 when the trailing 20-day 5-min gold/silver return correlation < 0.729695 (cut fixed on 2010-17), else 1.
U3 exit: stop 0.5 x 14-day range; half at +1R then stop to entry; trail 0.5 x range behind the best price; rest at the day-end close.
Day end = first minute at/after 23:00 broker (Fri 22:50). No entries 00:55-01:14 broker.

LIVE vs RESEARCH (honest live rules, measured in validate.py):
  research entered every trade at the OPEN of its list minute. For agreements completed by a CP break that minute is the minute the level
  breaks (the break happens inside it), so live the entry is the break price max(level, open) for buys / min(level, open) for sells.
  research dropped a U4 trade if a U1 agreement came LATER that day; live takes whichever comes first (one trade per day).
"""
import re
import numpy as np, pandas as pd

CUT = 0.729694869855824          # corr20 cut (1/3 quantile of 2010-17 days) - fixed
STOP, HALF_R, HALF_F, TRAIL = 0.5, 1.0, 0.5, 0.5
F1_L, F1_THR, U4_L, U4_THR, U4_WIN = 5, 0.30, 10, 0.35, 120
END_HR = 19                     # compression families stop looking for a break at 19:00 broker

MEMBERS = """P1 TTM squeeze (KC 1.5): break of 2-day range from 10am follow
P1 TTM squeeze (KC 1.5): break of 2-day range from 11am follow
P1 TTM squeeze (KC 1.5): break of 3-day range from 10am follow
P1 TTM squeeze (KC 1.5): break of 3-day range from 11am follow
P1 TTM squeeze (KC 1.5): break of 5-day range from 10am follow
P1 TTM squeeze (KC 1.5): break of 5-day range from 11am follow
P1 TTM squeeze (KC 2.0): break of 2-day range from 10am follow
P1 TTM squeeze (KC 2.0): break of 2-day range from 11am follow
P1 TTM squeeze (KC 2.0): break of 3-day range from 10am follow
P1 TTM squeeze (KC 2.0): break of 3-day range from 11am follow
P1 TTM squeeze (KC 2.0): break of 5-day range from 10am follow
P1 TTM squeeze (KC 2.0): break of 5-day range from 11am follow
Q1 ADX<12: break of 2-day range from 10am follow
Q1 ADX<12: break of 2-day range from 11am follow
Q1 ADX<12: break of 2-day range from 1pm follow
Q1 ADX<12: break of 3-day range from 10am follow
Q1 ADX<12: break of 3-day range from 11am follow
Q1 ADX<12: break of 3-day range from 1pm follow
R11 BB<=20%: break of 2-day range by +0.1ATR from 10am follow
R11 BB<=20%: break of 2-day range by +0.1ATR from 1pm follow
R11 BB<=20%: break of 2-day range by +0.2ATR from 10am follow
R11 BB<=20%: break of 2-day range by +0.2ATR from 1pm follow
R11 BB<=20%: break of 3-day range by +0.1ATR from 10am follow
R11 BB<=20%: break of 3-day range by +0.1ATR from 1pm follow
R11 BB<=20%: break of 3-day range by +0.2ATR from 10am follow
R11 BB<=20%: break of 3-day range by +0.2ATR from 1pm follow
R11 TTM: break of 2-day range by +0.1ATR from 10am follow
R11 TTM: break of 2-day range by +0.1ATR from 1pm follow
R11 TTM: break of 2-day range by +0.2ATR from 10am follow
R11 TTM: break of 2-day range by +0.2ATR from 1pm follow
R11 TTM: break of 3-day range by +0.1ATR from 10am follow
R11 TTM: break of 3-day range by +0.1ATR from 1pm follow
R11 TTM: break of 3-day range by +0.2ATR from 10am follow
R11 TTM: break of 3-day range by +0.2ATR from 1pm follow""".split('\n')
HOUR = {'10am': 9, '11am': 10, '1pm': 12}        # research label D(Tb): Tb=9 -> '10am'


def parse(m):
    n = int(re.search(r'break of (\d)-day', m).group(1)); tb = HOUR[re.search(r'from (\w+) follow', m).group(1)]
    b = re.search(r'by \+([\d.]+)ATR', m); buf = float(b.group(1)) if b else 0.0
    if m.startswith('P1'): cond, start = ('KC1.5' if 'KC 1.5' in m else 'KC2.0'), 25
    elif m.startswith('Q1'): cond, start = 'ADX12', 30
    else: cond, start = ('BB20' if 'BB<=20%' in m else 'KC1.5'), 30
    return dict(cond=cond, n=n, tb=tb, buf=buf, start=start, brkx=m.startswith('R11'))
MEM = [parse(m) for m in MEMBERS]


def sh(x, n=1):
    r = np.full(len(x), np.nan); r[n:] = x[:-n]; return r


def day_table(D):
    """D: broker-day bars (index = broker date, o h l c), every silver day ever traded, oldest first. -> per-day features (same formulas as famn)."""
    dhi, dlo, dcl = D.h.values.astype(float), D.l.values.astype(float), D.c.values.astype(float)
    rng = dhi - dlo
    A = pd.Series(rng).rolling(14).mean().shift(1).values
    ma20 = pd.Series(dcl).rolling(20).mean().values; sd20 = pd.Series(dcl).rolling(20).std().values
    tr = np.maximum(dhi - dlo, np.maximum(abs(dhi - np.r_[np.nan, dcl[:-1]]), abs(dlo - np.r_[np.nan, dcl[:-1]])))
    atr20 = pd.Series(tr).rolling(20).mean().values
    cond = {}
    for m in (1.5, 2.0):
        cond[f'KC{m}'] = np.nan_to_num(sh((ma20 + 2 * sd20 < ma20 + m * atr20) & (ma20 - 2 * sd20 > ma20 - m * atr20))).astype(bool)
    up = dhi - np.r_[np.nan, dhi[:-1]]; dn = np.r_[np.nan, dlo[:-1]] - dlo
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean()
    pdi = 100 * pd.Series(pdm).ewm(alpha=1 / 14, adjust=False).mean() / a; ndi = 100 * pd.Series(ndm).ewm(alpha=1 / 14, adjust=False).mean() / a
    adx = (100 * abs(pdi - ndi) / (pdi + ndi)).ewm(alpha=1 / 14, adjust=False).mean().values
    cond['ADX12'] = np.nan_to_num(sh(adx) < 12).astype(bool)
    bbw = pd.Series(dcl).rolling(20).std().values / pd.Series(dcl).rolling(20).mean().values
    bbp = sh(pd.Series(bbw).rolling(120, min_periods=60).apply(lambda x: (x[-1] >= x).mean(), raw=True).values)
    cond['BB20'] = np.nan_to_num(bbp <= 0.2).astype(bool)
    return dict(dates=D.index.values.astype('datetime64[D]'), dhi=dhi, dlo=dlo, A=A, cond=cond)


def gold_A(G):
    """gold broker-day bars -> 14 prior-day mean range per day (gold's own A)."""
    return pd.Series(pd.Series(G.h.values - G.l.values).rolling(14).mean().shift(1).values, index=G.index.values.astype('datetime64[D]'))


class Span:
    """A run of silver minutes (several whole days, the last one may be today so far) + aligned gold."""
    def __init__(self, st, so, sh_, sl, sc, gt, gc, gA_by_day, DT):
        self.T = st.astype('datetime64[m]'); self.O, self.H, self.L, self.C = so, sh_, sl, sc
        day = self.T.astype('datetime64[D]'); self.day = day
        self.k = np.searchsorted(DT['dates'], day)                         # row in the day table
        assert (DT['dates'][np.minimum(self.k, len(DT['dates']) - 1)] == day).all(), 'silver day missing from the day table'
        self.dc = np.r_[0, np.cumsum(day[1:] != day[:-1])]
        self.starts = np.r_[0, np.where(np.diff(self.dc) != 0)[0] + 1]; self.ends = np.r_[self.starts[1:], len(st)]
        tt = pd.DatetimeIndex(self.T); self.hr = tt.hour.values; self.mi = tt.minute.values; self.hm = self.hr * 100 + self.mi
        dow = tt.dayofweek.values
        self.A = DT['A'][self.k]
        eod_t = day.astype('datetime64[m]') + np.where(dow == 4, 22 * 60 + 50, 23 * 60).astype('timedelta64[m]')
        E = np.searchsorted(self.T, eod_t); dlast = (self.ends - 1)[self.dc]; self.EOD = np.minimum(E, dlast)
        self.isct = np.where(dow == 4, self.hm >= 2250, self.hm >= 2300)
        gt = gt.astype('datetime64[m]'); gi = np.searchsorted(gt, self.T, side='right') - 1
        self.gok = (gi >= 0) & ((self.T - gt[np.maximum(gi, 0)]) <= np.timedelta64(2, 'm'))
        self.gC = np.where(self.gok, gc[np.maximum(gi, 0)], np.nan)
        gday = gt[np.maximum(gi, 0)].astype('datetime64[D]')
        self.gA = np.where(self.gok, gA_by_day.reindex(gday).values, np.nan)
        same = gt[np.maximum(gi, 0)] == self.T
        self.gC_exact = np.where((gi >= 0) & same, gc[np.maximum(gi, 0)], np.nan)   # for the 5-min correlation (research aligned_x)
        self.DT = DT


def voters_G(S, gsig_t, gsig_d):
    """gold engine signals -> silver NEXT minute (research mir5)."""
    tt = np.asarray(gsig_t, dtype='datetime64[m]'); d = np.asarray(gsig_d, np.int64)
    if len(tt) == 0: return np.zeros(0, np.int64), np.zeros(0, np.int64)
    j = np.searchsorted(S.T, tt); jj = np.minimum(j, len(S.T) - 1)
    ok = (j < len(S.T)) & (np.abs(S.T[jj] - tt) <= np.timedelta64(2, 'm'))
    j = j[ok] + 1; d = d[ok]
    ok2 = (j < len(S.T)); j, d = j[ok2], d[ok2]
    ok3 = (j < S.EOD[j]) & np.isfinite(S.A[j]) & (S.A[j] > 0); j, d = j[ok3], d[ok3]
    key = j * 3 + d; _, u = np.unique(key, return_index=True); u = np.sort(u)
    return j[u], d[u]


def catchup(S, L_, thr, mask=None):
    """gold out-moved silver over the last L_ bars -> next minute (index based, same day, gold within 2 min). All trigger minutes."""
    idx = np.where((S.hm >= 115) & (S.hm <= 2200) & (mask if mask is not None else True))[0]
    idx = idx[(idx + 1 < S.EOD[idx]) & S.gok[idx]]
    q = idx - L_; ok = (q >= 0) & S.gok[np.maximum(q, 0)] & (S.dc[np.maximum(q, 0)] == S.dc[idx]); P = idx[ok]; Q = q[ok]
    gap = (S.gC[P] - S.gC[Q]) / S.gA[P] - (S.C[P] - S.C[Q]) / S.A[P]
    c = (np.abs(gap) >= thr) & np.isfinite(gap)
    return P[c] + 1, np.sign(gap[c]).astype(np.int64)


def first_per_day(S, j, d, key_minus1=False):
    k = S.dc[j - 1] if key_minus1 else S.dc[j]
    f = np.r_[True, k[1:] != k[:-1]] if len(k) else np.zeros(0, bool)
    return j[f], d[f]


def voters_CP(S):
    """earliest compression-member break per day (research famn brk/brkx + load_pool filters + first_of_day by member order). -> j, d, px"""
    DT = S.DT; out = []; frm = getattr(S, 'from_day', None)
    for s, e in zip(S.starts, S.ends):
        if frm is not None and S.day[s] < frm: continue          # live: only the days asked for (today)
        K = S.k[s]; best = None
        hr = S.hr[s:e]
        def bi(h):
            p = np.searchsorted(hr, h); return s + p if p < len(hr) else -1
        ie = bi(END_HR); ie = e if ie < 0 else ie
        for pr, M in enumerate(MEM):
            if K < M['start'] or not DT['cond'][M['cond']][K]: continue
            i = bi(M['tb'])
            if i < 0: continue
            up = DT['dhi'][max(0, K - M['n']):K].max(); dn = DT['dlo'][max(0, K - M['n']):K].min()
            if not M['brkx'] and not (np.isfinite(up) and np.isfinite(dn)): continue
            if M['brkx']: a = S.A[i]; up = up + M['buf'] * a; dn = dn - M['buf'] * a
            j, sd = -1, 0
            for m in range(i, ie):
                hu = S.H[m] >= up; hd = S.L[m] <= dn
                if hu and hd: j, sd = m, 0; break
                if hu: j, sd = m, 1; break
                if hd: j, sd = m, -1; break
            if sd == 0: continue
            if (55 <= S.hm[j] < 115) or not (j < S.EOD[j]) or not (np.isfinite(S.A[j]) and S.A[j] > 0): continue
            px = max(up, S.O[j]) if sd > 0 else min(dn, S.O[j])
            if best is None or j < best[0]: best = (j, sd, px)            # earliest; ties keep the lower member number
        if best: out.append(best)
    if not out: return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0)
    a = np.array(out, dtype=object); return a[:, 0].astype(np.int64), a[:, 1].astype(np.int64), a[:, 2].astype(float)


def corr20(S, prior=None):
    """trailing 20-day (min 15) correlation of 5-bar log returns gold vs silver, days before today (research reg2). -> per span day."""
    i5 = np.where(S.mi % 5 == 0)[0]; i5 = i5[i5 >= 5]
    gr = np.log(S.gC_exact[i5]) - np.log(S.gC_exact[i5 - 5]); sr = np.log(S.C[i5]) - np.log(S.C[i5 - 5])
    ok = np.isfinite(gr) & np.isfinite(sr) & (S.dc[i5] == S.dc[i5 - 5])
    Dd = pd.DataFrame(dict(k=S.dc[i5][ok], g=gr[ok], s=sr[ok])); Dd['gs'] = Dd.g * Dd.s; Dd['gg'] = Dd.g ** 2; Dd['ss'] = Dd.s ** 2
    day = Dd.groupby('k')[['gs', 'gg', 'ss']].sum().rolling(20, min_periods=15).sum().shift(1)
    return (day.gs / np.sqrt(day.gg * day.ss)).reindex(range(len(S.starts))).values


def agree(evs):
    """evs: list of (j, src, d) sorted by (day, j, src) for ONE day -> (j, d, src_that_completed) of the first 2-of-3 agreement, or None."""
    last = [0, 0, 0]
    for j, s, d in evs:
        last[s] = d
        for dd in (1, -1):
            if sum(1 for x in last if x == dd) >= 2: return j, dd, s
    return None


def signals(S, gsig_t, gsig_d, news_t, honest=True):
    """All v1.8 entries in the span. honest=False reproduces the research list exactly (entry = open of the list minute; U4 dropped if a
    later U1 comes that day). Returns DataFrame: t, j, dir, src (1=U1, 4=U4), via (voter that completed the agreement), px, A, w."""
    Gj, Gd = voters_G(S, gsig_t, gsig_d)
    Fj, Fd = catchup(S, F1_L, F1_THR); Fj, Fd = first_per_day(S, Fj, Fd, key_minus1=True)
    Cj, Cd, Cpx = voters_CP(S)
    cpx = dict(zip(Cj.tolist(), Cpx.tolist()))
    ev = [(S.dc[j], j, 0, d) for j, d in zip(Gj, Gd)] + [(S.dc[j - 1], j, 1, d) for j, d in zip(Fj, Fd)] + [(S.dc[j], j, 2, d) for j, d in zip(Cj, Cd)]
    ev.sort(key=lambda x: (x[0], x[1], x[2]))
    U1 = {}
    i = 0
    while i < len(ev):
        k0 = ev[i][0]; day = []
        while i < len(ev) and ev[i][0] == k0: day.append((ev[i][1], ev[i][2], ev[i][3])); i += 1
        r = agree(day)
        if r and r[0] < S.EOD[r[0]] and not (55 <= S.hm[r[0]] < 115): U1[S.dc[r[0]]] = r
    # U4 post-news catch-up
    post = np.zeros(len(S.T), bool)
    for r0 in np.unique(np.searchsorted(S.T, np.asarray(news_t, dtype='datetime64[m]'))):
        if r0 < len(S.T): post[r0:min(len(S.T), r0 + U4_WIN)] = True
    Pj, Pd = catchup(S, U4_L, U4_THR, post); Pj, Pd = first_per_day(S, Pj, Pd)
    U4 = {S.dc[j]: (j, d) for j, d in zip(Pj, Pd)}
    cr = corr20(S); rows = []
    for k in sorted(set(U1) | set(U4)):
        if k in U1 and (not honest or k not in U4 or U1[k][0] <= U4[k][0]):
            j, d, via = U1[k]; src = 1
        elif k in U4 and (honest or k not in U1):
            (j, d), via, src = U4[k], 1, 4
        else: continue
        if src == 1 and via == 2 and honest: px = cpx[j]                    # completed by a compression break: the break price
        else: px = float(S.O[j])
        w = 2 if (np.isfinite(cr[k]) and cr[k] < CUT) else 1
        rows.append(dict(t=S.T[j], j=int(j), dir=int(d), src=src, via=['gold signal', 'fast catch-up', 'compression break'][via] if src == 1 else 'news catch-up',
                         px=px, A=float(S.A[j]), w=w, corr=float(cr[k]) if np.isfinite(cr[k]) else None))
    return pd.DataFrame(rows)


def manage(S, j, d, px, A, upto=None):
    """U3 exit on silver minutes from the bar after entry. upto = last closed index to look at (live). Returns dict with status/exit/half."""
    risk = STOP * A; stop = px - d * risk; tgt = px + d * HALF_R * risk; e = S.EOD[j]; part = False; best = px; half_t = None
    stop0 = stop; end = e if upto is None else min(e, upto)
    for m in range(j + 1, end + 1):
        if m == e and S.isct[e]:
            return dict(status='day end', exit=float(S.O[m]), exit_j=m, half=part, half_j=half_t, stop=stop, stop0=stop0, tgt=tgt)
        if d > 0:
            if S.O[m] <= stop: return dict(status='stop' if not part else 'trail', exit=float(S.O[m]), exit_j=m, half=part, half_j=half_t, stop=stop, stop0=stop0, tgt=tgt)
            if S.L[m] <= stop: return dict(status='stop' if not part else 'trail', exit=float(stop), exit_j=m, half=part, half_j=half_t, stop=stop, stop0=stop0, tgt=tgt)
            if not part and S.H[m] >= tgt: part = True; half_t = m; stop = max(stop, px)
            if part: best = max(best, S.H[m]); stop = max(stop, best - TRAIL * A)
        else:
            if S.O[m] >= stop: return dict(status='stop' if not part else 'trail', exit=float(S.O[m]), exit_j=m, half=part, half_j=half_t, stop=stop, stop0=stop0, tgt=tgt)
            if S.H[m] >= stop: return dict(status='stop' if not part else 'trail', exit=float(stop), exit_j=m, half=part, half_j=half_t, stop=stop, stop0=stop0, tgt=tgt)
            if not part and S.L[m] <= tgt: part = True; half_t = m; stop = min(stop, px)
            if part: best = min(best, S.L[m]); stop = min(stop, best + TRAIL * A)
    if upto is None or upto >= e:
        return dict(status='day end', exit=float(S.C[e]), exit_j=e, half=part, half_j=half_t, stop=stop, stop0=stop0, tgt=tgt)
    return dict(status='open', exit=None, exit_j=None, half=part, half_j=half_t, stop=stop, stop0=stop0, tgt=tgt)


def result_R(px, d, A, m, w):
    """size-weighted R of a managed trade (before costs): half at target when hit."""
    risk = STOP * A
    if m['exit'] is None: return None
    x = m['exit']; g = (0.5 * (m['tgt'] - px) * d + 0.5 * (x - px) * d) if m['half'] else (x - px) * d
    return w * g / risk
