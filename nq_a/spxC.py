"""C. S&P 500-specific ideas (broker clock = New York + 7 h all year -> US cash open 9:30 am NY = 16:30 broker, cash close 4:00 pm NY = 23:00
broker = the day end; 8:30 am NY data = 15:30; lunch 12:00-1:30 pm NY = 19:00-20:30; Xetra open 10:00 broker, Xetra close 17:30 CET = 18:30 broker;
Tokyo open broker 02:00/03:00). Every feature uses only data before the entry minute (closed bars, levels fixed before the scan starts)."""
import sys, os, io, contextlib, pickle, numpy as np, pandas as pd
pass  # desk: no chdir
with contextlib.redirect_stdout(io.StringIO()):
    from fam import *
IDEASC = {}
def addc(n, f): IDEASC[n] = f
hm = hr * 60 + T.minute.values
def at_hm(k, h, m_):
    s, e = starts[k], ends[k]; p = s + np.searchsorted(hm[s:e], h * 60 + m_)
    return p if p < e and hm[p] <= h * 60 + m_ + 5 else -1          # the bar must start within 5 min of the clock time
CASH = (16, 30)
# cash close of each day = close of the last bar before 23:00 broker (known from 23:00 on; used only on the NEXT day)
cc = np.full(ND, np.nan)
for k in range(ND):
    s, e = starts[k], ends[k]; p = s + np.searchsorted(hm[s:e], 23 * 60) - 1
    if p >= s and hm[p] >= 22 * 60 + 30: cc[k] = C[p]
pCC = sh(cc)
# C1 cash-open opening range (first N min) -> first break within W hours, follow / fade
def c1(mins, W, fade):
    def g():
        E = []
        for k in range(ND):
            a = at_hm(k, *CASH); b = at_hm(k, CASH[0], CASH[1] + mins)
            if a < 0 or b < 0 or b - a < mins // 2: continue
            c_ = at_hm(k, CASH[0] + W, CASH[1] + mins)
            if c_ < 0: c_ = min(ends[k], EOD[starts[k]] if EOD[starts[k]] > b else ends[k])
            up = H[a:b].max(); dn = L[a:b].min(); j, sd = first_touch(b, c_, up, dn, H, L)
            if sd == 0: continue
            E.append((k, j, max(up, O[j]) if sd > 0 else min(dn, O[j]), -sd if fade else sd))
        return E
    return g
for mins in (5, 15, 30, 60):
    for W in (2, 4, 6):
        for fade in (0, 1): addc(f"C1 cash open first {mins}min range break within {W}h {'fade' if fade else 'follow'}", c1(mins, W, fade))
# C2 overnight session (day start -> 16:30) high / low -> first break after the cash open within W hours
def c2(W, fade, buf):
    def g():
        E = []
        for k in range(ND):
            s = starts[k]; a = at_hm(k, *CASH)
            if a < 0 or a - s < 120: continue
            up = H[s:a].max() + buf * dA[k]; dn = L[s:a].min() - buf * dA[k]
            c_ = at_hm(k, CASH[0] + W, CASH[1]);  c_ = ends[k] if c_ < 0 else c_
            j, sd = first_touch(a, c_, up, dn, H, L)
            if sd == 0: continue
            E.append((k, j, max(up, O[j]) if sd > 0 else min(dn, O[j]), -sd if fade else sd))
        return E
    return g
for W in (2, 4, 6):
    for buf in (0.0, 0.05):
        for fade in (0, 1): addc(f"C2 overnight high/low (+{buf}ATR) first break after cash open within {W}h {'fade' if fade else 'follow'}", c2(W, fade, buf))
# C3 gap at the cash open vs yesterday's cash close -> fade (gap fill) / follow, entry at the cash open
def c3(thr, fade, mx=9.0):
    def g():
        E = []
        for k in range(1, ND):
            i = at_hm(k, *CASH)
            if i < 0 or not np.isfinite(pCC[k]): continue
            gp = O[i] - pCC[k]
            if abs(gp) < thr * dA[k] or abs(gp) > mx * dA[k] or gp == 0: continue
            d = 1 if gp > 0 else -1; E.append((k, i, O[i], -d if fade else d))
        return E
    return g
for thr in (0.0, 0.1, 0.2, 0.3, 0.5):
    for fade in (0, 1): addc(f"C3 gap cash open vs prior cash close >{thr}ATR {'fade (fill)' if fade else 'follow'}", c3(thr, fade))
for thr, mx in ((0.1, 0.3), (0.3, 0.6)):
    for fade in (0, 1): addc(f"C3b gap {thr}-{mx}ATR {'fade (fill)' if fade else 'follow'}", c3(thr, fade, mx))
# C4 break of yesterday's cash close level after the cash open (first touch from the open side), follow / fade
def c4(W, fade):
    def g():
        E = []
        for k in range(1, ND):
            a = at_hm(k, *CASH)
            if a < 0 or not np.isfinite(pCC[k]): continue
            lv = pCC[k]; side = 1 if O[a] > lv else -1
            if abs(O[a] - lv) < 0.05 * dA[k]: continue
            c_ = at_hm(k, CASH[0] + W, CASH[1]); c_ = ends[k] if c_ < 0 else c_
            for j in range(a, c_):
                if (side > 0 and L[j] <= lv) or (side < 0 and H[j] >= lv):
                    d = -side; E.append((k, j, min(lv, O[j]) if d < 0 else max(lv, O[j]), -d if fade else d)); break
        return E
    return g
for W in (2, 4, 6):
    for fade in (0, 1): addc(f"C4 yesterday cash close level break after the open within {W}h {'fade' if fade else 'follow'}", c4(W, fade))
# C5 move over a window -> follow / fade at the window end
def c5(a_, b_, thr, fade):
    def g():
        E = []
        for k in range(ND):
            i0 = at_hm(k, *a_); i1 = at_hm(k, *b_)
            if i0 < 0 or i1 < 0 or i1 <= i0: continue
            mv = O[i1] - O[i0]
            if abs(mv) < thr * dA[k] or mv == 0: continue
            d = 1 if mv > 0 else -1; E.append((k, i1, O[i1], -d if fade else d))
        return E
    return g
WIN = (((1, 0), (16, 30), 'overnight (day start->cash open)'), ((10, 0), (16, 30), 'Europe->cash open'), ((15, 30), (16, 30), '8:30 data->cash open'),
       ((15, 30), (15, 40), '8:30 data first 10min'), ((16, 30), (17, 0), 'cash first 30min'), ((16, 30), (17, 30), 'cash first hour'),
       ((16, 30), (19, 0), 'cash open->noon'), ((19, 0), (20, 30), 'lunch'), ((16, 30), (21, 0), 'cash open->2pm'), ((16, 30), (22, 0), 'cash open->3pm'))
for a_, b_, lab in WIN:
    for thr in (0, 0.2, 0.4):
        for fade in (0, 1): addc(f"C5 move {lab} >{thr}ATR {'fade' if fade else 'follow'}", c5(a_, b_, thr, fade))
# C6 DAX (Xetra hours) and Nikkei (Tokyo) moves as leads (60-min lag on the other market's last price)
def m1load(p):
    return np.array([], dtype='datetime64[m]'), np.array([])   # NOEXT
    x = pd.read_pickle(p); return x.time.values.astype('datetime64[m]'), x.c.values.astype(float)
def from_hd(P):
    return np.array([], dtype='datetime64[m]'), np.array([])   # NOEXT
    import zipfile, glob
    fr = []
    for z in sorted(glob.glob(f'/home/claude/wti_dt/eq/{P}/DAT_MT_{P}_M1_*.zip')):
        with zipfile.ZipFile(z) as Z:
            n = [x for x in Z.namelist() if x.endswith('.csv')][0]; fr.append(pd.read_csv(Z.open(n), header=None, names=['d', 't', 'o', 'h', 'l', 'c', 'v']))
    d = pd.concat(fr); d['time'] = pd.to_datetime(d.d + ' ' + d.t, format='%Y.%m.%d %H:%M') + pd.Timedelta(hours=7)
    d = d.sort_values('time').drop_duplicates('time', keep='last'); return d.time.values.astype('datetime64[m]'), d.c.values.astype(float)
LEAD = {'DAX': from_hd('GRXEUR'), 'Nikkei': from_hd('JPXJPY'), 'gold': m1load('/home/claude/m1/m1_fixed.pkl'), 'USDJPY': m1load('/home/claude/jpym1/m1.pkl')}
def lastc_at(tt, cc_, ts, maxage=120):
    p = np.searchsorted(tt, ts, side='right') - 1
    return cc_[p] if p >= 0 and (ts - tt[p]) <= np.timedelta64(maxage, 'm') else np.nan
Tm = T.values.astype('datetime64[m]')
def c6(nm, h0, h1, at, fade):
    tt, cx = LEAD[nm]
    def g():
        E = []
        for k in range(1, ND):
            i = at_hm(k, *at)
            if i < 0: continue
            day0 = Tm[starts[k]].astype('datetime64[D]').astype('datetime64[m]')
            ta = day0 + np.timedelta64(h0 * 60, 'm'); tb = min(day0 + np.timedelta64(h1 * 60, 'm'), Tm[i] - np.timedelta64(1, 'm'))
            a = lastc_at(tt, cx, ta); b = lastc_at(tt, cx, tb)
            if not (np.isfinite(a) and np.isfinite(b)) or a == b: continue
            d = 1 if b > a else -1; E.append((k, i, O[i], -d if fade else d))
        return E
    return g
for nm, h0, h1, at, lab in (('DAX', 10, 16, CASH, 'Xetra 10:00->16:00 at cash open'), ('DAX', 10, 18, (18, 30), 'Xetra day at Xetra close'),
                            ('Nikkei', 3, 9, (10, 0), 'Tokyo session at Europe open'), ('Nikkei', 3, 9, CASH, 'Tokyo session at cash open'),
                            ('gold', 1, 16, CASH, 'gold overnight at cash open'), ('USDJPY', 1, 16, CASH, 'USDJPY overnight at cash open')):
    for fade in (0, 1): addc(f"C6 {nm} lead: {lab} {'fade' if fade else 'follow'}", c6(nm, h0, h1, at, fade))
# C7 calendar days (FOMC 2pm, 3rd-Friday expiry, month turn, Monday, Friday): the cash-open 30-min range break, follow / fade
pass  # desk: no FOMC list (no FOMC idea in the live set)
try:
    with contextlib.redirect_stdout(io.StringIO()):
        import dates as CAL
    FOMC = set(pd.DatetimeIndex(getattr(CAL, 'FOMC', [])).normalize())
except Exception:
    FOMC = set()
dd = pd.DatetimeIndex(dday)
third_fri = set(d for d in dd if d.dayofweek == 4 and 15 <= d.day <= 21)
mturn = set(); mm = pd.Series(dd.to_period('M'))
for i in range(len(dd)):
    if i == 0 or mm[i] != mm[i - 1]: mturn.add(dd[i])
    if i + 1 < len(dd) and mm[i] != mm[i + 1]: mturn.add(dd[i])
def c7(dayset, mins, fade):
    base = c1(mins, 6, fade)
    return lambda: [e for e in base() if dd[e[0]] in dayset]
CALS = (('FOMC day', FOMC), ('3rd-Friday expiry', third_fri), ('month turn', mturn), ('Monday', set(d for d in dd if d.dayofweek == 0)), ('Friday', set(d for d in dd if d.dayofweek == 4)))
for lab, ds in CALS:
    if len(ds) < 40: continue
    for fade in (0, 1): addc(f"C7 {lab}: cash open first 30min range break {'fade' if fade else 'follow'}", c7(ds, 30, fade))
# C8 FOMC 2pm: the 20:30-21:00 range -> first break after 21:00 within 2h (FOMC days only)
def c8(fade):
    def g():
        E = []
        for k in range(ND):
            if dd[k] not in FOMC: continue
            a = at_hm(k, 20, 30); b = at_hm(k, 21, 0)
            if a < 0 or b < 0: continue
            up = H[a:b].max(); dn = L[a:b].min(); j, sd = first_touch(b, ends[k], up, dn, H, L)
            if sd == 0: continue
            E.append((k, j, max(up, O[j]) if sd > 0 else min(dn, O[j]), -sd if fade else sd))
        return E
    return g
if len(FOMC) >= 40:
    for fade in (0, 1): addc(f"C8 FOMC 2pm range break {'fade' if fade else 'follow'}", c8(fade))
print('S&P C ideas', len(IDEASC), '| FOMC days', len(FOMC))
