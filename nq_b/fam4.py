from fam3 import *
from comp import rangerule
import os as _os; lad=pd.read_pickle(_os.path.join(_os.environ['NQ_BASE'],'lad.pkl')); edd=pd.Series(lad.edir.values,index=lad.index).reindex(dday).values
etd=pd.Series(pd.DatetimeIndex(lad.et).values,index=lad.index).reindex(dday).values.astype('datetime64[ns]'); Tn=T.values
IDEAS4={}
def add4(n,f): IDEAS4[n]=f
# ---------- H1 conditioned versions of the 5 upgrades
W={'U1':lambda:rangerule(),'U2':IDEAS2['G6 round $200 break + 1 min close beyond, from 10am'],'U3':IDEAS['F7 gap vs yesterday close >0.05ATR at 1am fade'],
   'U5':IDEAS2['G2 prev-week hi/lo break from 7am follow'],'U6':lambda:[e for e in IDEAS2['G3 range 1pm-3pm break within 4h buf0.1 fade']() if np.isnat(etd[e[0]]) or etd[e[0]]>Tn[e[1]]]}
WE={k:f() for k,f in W.items()}
vr=pd.Series(dA).rolling(100,min_periods=50).mean().values; vrel=dA/vr
er10=np.full(ND,np.nan)
for k in range(11,ND): er10[k]=abs(dcl[k-1]-dcl[k-11])/np.sum(np.abs(np.diff(dcl[k-11:k])))
t5=np.full(ND,np.nan); t5[6:]=np.sign(dcl[5:-1]-dcl[:-6]); gd=np.sign(dop-pC); yr_=(pH-pL)/dA; ycol=np.sign(pC-pO)
CONDS={'vol low (<0.9)':lambda k,d:vrel[k]<0.9,'vol high (>1.1)':lambda k,d:vrel[k]>1.1,'choppy (ER<0.25)':lambda k,d:er10[k]<0.25,'trending (ER>0.4)':lambda k,d:er10[k]>0.4,
 '5d trend agrees':lambda k,d:t5[k]==d,'5d trend against':lambda k,d:t5[k]==-d,'gap agrees':lambda k,d:gd[k]==d,'gap against':lambda k,d:gd[k]==-d,
 'yday big (>1.2ATR)':lambda k,d:yr_[k]>1.2,'yday small (<0.8ATR)':lambda k,d:yr_[k]<0.8,'yday colour agrees':lambda k,d:ycol[k]==d,'yday colour against':lambda k,d:ycol[k]==-d,
 'Mon/Tue':lambda k,d:wd[k]<=1,'Wed-Fri':lambda k,d:wd[k]>=2}
for u,E in WE.items():
    for cn,cf in CONDS.items():
        add4(f"H1 {u} only when {cn}",lambda E=E,cf=cf:[e for e in E if cf(e[0],e[3])])
# ---------- H2 round-number variants
def h2(step,Tb,mode,conf=1):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0: continue
            if ie<0: ie=ends[k]
            p=O[i]; up=np.ceil(p/step)*step; dn=np.floor(p/step)*step
            if up==p: up+=step
            if dn==p: dn-=step
            j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            lvl=up if sd>0 else dn
            if mode=='reject':   # touched, then a 1-min close back on the near side -> reverse
                for jj in range(j,min(j+30,ie)):
                    if (sd>0 and C[jj]<lvl-0.05*dA[k]) or (sd<0 and C[jj]>lvl+0.05*dA[k]): E.append((k,jj,C[jj],-sd)); break
            elif mode=='retest': # close beyond, then pullback to level (limit, needs ASK through: +spread)
                ok=False
                for jj in range(j,ie):
                    if not ok:
                        if (sd>0 and C[jj]>lvl) or (sd<0 and C[jj]<lvl): ok=True
                        continue
                    if (sd>0 and L[jj]<=lvl-0.5) or (sd<0 and H[jj]>=lvl+0.5): E.append((k,jj,lvl,sd)); break
            elif mode=='conf':
                n=0
                for jj in range(j,min(j+60,ie)):
                    if (sd>0 and C[jj]>lvl) or (sd<0 and C[jj]<lvl):
                        n+=1
                        if n>=conf: E.append((k,jj,C[jj],sd)); break
                    else: break
        return E
    return g
for step in (100,200,400):
    for Tb in (0,3,6,9,12,15):
        add4(f"H2 round ${step} touch then close back -> reverse, from {D(Tb)}",h2(step,Tb,'reject'))
        add4(f"H2 round ${step} break, close beyond, then retest -> follow, from {D(Tb)}",h2(step,Tb,'retest'))
        add4(f"H2 round ${step} break + 1min close, from {D(Tb)}",h2(step,Tb,'conf',1))
        add4(f"H2 round ${step} break + 2min close, from {D(Tb)}",h2(step,Tb,'conf',2))
# ---------- H3 failed break of morning range -> reverse ; second break
def h3(Tb,mode,buf=0):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]; s0=starts[k]; ie=BI[k,END]
            if i<0 or i<=s0: continue
            if ie<0: ie=ends[k]
            a=dA[k]; up=H[s0:i].max(); dn=L[s0:i].min()
            j,sd=first_touch(i,ie,up+buf*a,dn-buf*a,H,L)
            if sd==0: continue
            if mode=='fail':
                for jj in range(j+1,min(j+120,ie)):
                    if (sd>0 and C[jj]<up) or (sd<0 and C[jj]>dn): E.append((k,jj,C[jj],-sd)); break
            elif mode=='other side':   # after first break, the opposite side breaks -> follow that
                j2,sd2=first_touch(j+1,ie,up if sd<0 else 1e18,dn if sd>0 else -1e18,H,L)
                if sd2!=0: E.append((k,j2,max(up,O[j2]) if sd2>0 else min(dn,O[j2]),sd2))
            elif mode=='extend':       # break extends 0.3ATR beyond -> fade the extension
                lv=up+0.3*a if sd>0 else dn-0.3*a
                j2,sd2=first_touch(j,ie,lv if sd>0 else 1e18,lv if sd<0 else -1e18,H,L)
                if sd2!=0: E.append((k,j2,lv,-sd))
        return E
    return g
for Tb in (6,7,8,9,10,11):
    for mode in ('fail','other side','extend'):
        for buf in (0,0.05): add4(f"H3 range open-{D(Tb)} {mode} buf{buf}",h3(Tb,mode,buf))
# ---------- H4 US session ranges (NY open ~4:30pm Dubai summer = broker 15:30)
def h4(a_,amin,b_,bmin,W,fade):
    def g():
        E=[]
        for k in range(ND):
            i0=BI[k,a_]; i=BI[k,b_]
            if i0<0 or i<0: continue
            i0+=amin; i+=bmin
            if i>=ends[k] or i<=i0: continue
            ie=min(i+W*60,ends[k]); up=H[i0:i].max(); dn=L[i0:i].min()
            j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            E.append((k,j,max(up,O[j]) if sd>0 else min(dn,O[j]),-sd if fade else sd))
        return E
    return g
for (a_,am,b_,bm,lab) in ((15,30,15,45,'4:30-4:45pm'),(15,30,16,0,'4:30-5pm'),(15,30,16,30,'4:30-5:30pm'),(15,0,16,0,'4-5pm'),(14,0,15,30,'3-4:30pm'),(16,0,17,0,'5-6pm')):
    for W in (1,2,3):
        for fade in (0,1): add4(f"H4 US range {lab} break within {W}h {'fade' if fade else 'follow'}",h4(a_,am,b_,bm,W,fade))
# ---------- H5 new high/low of the day after T
def h5(Tb,fade,minr):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]; s0=starts[k]; ie=BI[k,END]
            if i<0 or i<=s0: continue
            if ie<0: ie=ends[k]
            up=H[s0:i].max(); dn=L[s0:i].min()
            if (up-dn)<minr*dA[k]: continue
            j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            E.append((k,j,max(up,O[j]) if sd>0 else min(dn,O[j]),-sd if fade else sd))
        return E
    return g
for Tb in (12,13,14,15,16,17):
    for fade in (0,1):
        for minr in (0,0.5,0.8): add4(f"H5 new day high/low after {D(Tb)} (range>={minr}ATR) {'fade' if fade else 'follow'}",h5(Tb,fade,minr))
# ---------- H6 classic floor pivots
Pp=(pH+pL+pC)/3; R1=2*Pp-pL; S1=2*Pp-pH; R2=Pp+(pH-pL); S2=Pp-(pH-pL)
def h6(up_,dn_,Tb,fade):
    def g():
        E=[]
        for k in range(1,ND):
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0 or not np.isfinite(up_[k]): continue
            if ie<0: ie=ends[k]
            if not (dn_[k]<O[i]<up_[k]): continue
            j,sd=first_touch(i,ie,up_[k],dn_[k],H,L)
            if sd==0: continue
            px=(max(up_[k],O[j]) if sd>0 else min(dn_[k],O[j])); E.append((k,j,px,-sd if fade else sd))
        return E
    return g
for nm,(u,dd_) in {'R1/S1':(R1,S1),'R2/S2':(R2,S2),'pivot-band P±0.25ATR':(Pp+0.25*dA,Pp-0.25*dA)}.items():
    for Tb in (0,3,6,9,12):
        for fade in (0,1): add4(f"H6 pivots {nm} first touch from {D(Tb)} {'fade' if fade else 'break'}",h6(u,dd_,Tb,fade))
print('batch C ideas',len(IDEAS4))
# ---------- H7 two conditions on each upgrade
from itertools import combinations
pairs=[('vol low (<0.9)','5d trend agrees'),('vol high (>1.1)','5d trend agrees'),('vol low (<0.9)','gap agrees'),('vol high (>1.1)','gap against'),('choppy (ER<0.25)','gap against'),
 ('trending (ER>0.4)','5d trend agrees'),('5d trend agrees','gap agrees'),('5d trend agrees','yday colour agrees'),('5d trend against','yday colour against'),('yday big (>1.2ATR)','5d trend agrees'),
 ('yday small (<0.8ATR)','gap agrees'),('yday small (<0.8ATR)','5d trend agrees'),('choppy (ER<0.25)','yday colour against'),('trending (ER>0.4)','gap agrees'),('vol low (<0.9)','yday small (<0.8ATR)'),
 ('vol high (>1.1)','yday big (>1.2ATR)'),('Mon/Tue','5d trend agrees'),('Wed-Fri','5d trend agrees'),('gap against','yday colour against'),('choppy (ER<0.25)','5d trend against')]
for u,E in WE.items():
    for c1,c2 in pairs:
        add4(f"H7 {u} only when {c1} & {c2}",lambda E=E,f1=CONDS[c1],f2=CONDS[c2]:[e for e in E if f1(e[0],e[3]) and f2(e[0],e[3])])
# ---------- H8 range-edge retest entries (limit, spread-safe)
def h8(Tb,fade):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]; s0=starts[k]; ie=BI[k,END]
            if i<0 or i<=s0: continue
            if ie<0: ie=ends[k]
            up=H[s0:i].max(); dn=L[s0:i].min(); j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            lvl=up if sd>0 else dn; far=False
            for jj in range(j+1,ie):
                if not far:
                    if (sd>0 and H[jj]>=lvl+0.1*dA[k]) or (sd<0 and L[jj]<=lvl-0.1*dA[k]): far=True
                    continue
                if (sd>0 and L[jj]<=lvl-0.5) or (sd<0 and H[jj]>=lvl+0.5): E.append((k,jj,lvl,-sd if fade else sd)); break
        return E
    return g
for Tb in (7,8,9,10):
    for fade in (0,1): add4(f"H8 range open-{D(Tb)} break, run 0.1ATR, back to edge -> {'fade' if fade else 'follow'}",h8(Tb,fade))
# ---------- H9 longer highs/lows
mkey=pd.DatetimeIndex(dday).to_period('M').astype(str).values
mh=pd.Series(dhi).groupby(mkey).max(); ml=pd.Series(dlo).groupby(mkey).min(); um=pd.unique(mkey)
pmh=pd.Series(mh.shift(1).reindex(um).values,index=um).reindex(mkey).values; pml=pd.Series(ml.shift(1).reindex(um).values,index=um).reindex(mkey).values
h20=pd.Series(dhi).rolling(20).max().shift(1).values; l20=pd.Series(dlo).rolling(20).min().shift(1).values
for nm,lv in (('prev-month hi/lo',(pmh,pml)),('20-day hi/lo',(h20,l20))):
    for Tb in (0,6,9):
        for fade in (0,1): add4(f"H9 {nm} break from {D(Tb)} {'fade' if fade else 'follow'}",g2(lv,Tb,fade))
# ---------- H10 price vs average price since day open (VWAP-like)
def h10(Tb,fade,thr):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]; s0=starts[k]
            if i<0 or i-s0<60: continue
            mv=O[i]-C[s0:i].mean()
            if abs(mv)<thr*dA[k] or mv==0: continue
            d=1 if mv>0 else -1; E.append((k,i,O[i],-d if fade else d))
        return E
    return g
for Tb in (6,8,10,12,14,16):
    for thr in (0,0.15):
        for fade in (0,1): add4(f"H10 price vs day average at {D(Tb)} >{thr}ATR {'fade' if fade else 'follow'}",h10(Tb,fade,thr))
# ---------- H11 fast vs slow morning-range break
def h11(Tb,maxmin,fade):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]; s0=starts[k]
            if i<0 or i<=s0: continue
            ie=min(i+maxmin,ends[k]); up=H[s0:i].max(); dn=L[s0:i].min(); j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            E.append((k,j,max(up,O[j]) if sd>0 else min(dn,O[j]),-sd if fade else sd))
        return E
    return g
for Tb in (8,9,10):
    for mm in (15,30,60):
        for fade in (0,1): add4(f"H11 range open-{D(Tb)} break within first {mm}min {'fade' if fade else 'follow'}",h11(Tb,mm,fade))
# ---------- H12 H1 inside-bar break
def h12(Tb,fade):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]
            if i<120 or i+60>=ends[k]: continue
            h1,l1=H[i-60:i].max(),L[i-60:i].min(); h0,l0=H[i-120:i-60].max(),L[i-120:i-60].min()
            if not (h1<=h0 and l1>=l0): continue
            j,sd=first_touch(i,min(i+180,ends[k]),h1,l1,H,L)
            if sd==0: continue
            E.append((k,j,max(h1,O[j]) if sd>0 else min(l1,O[j]),-sd if fade else sd))
        return E
    return g
for Tb in (3,6,8,10,12,15):
    for fade in (0,1): add4(f"H12 H1 inside-bar at {D(Tb)} break {'fade' if fade else 'follow'}",h12(Tb,fade))
# ---------- H13 yesterday's other markets (daily, no timing risk)
def dailyret(path):
    return np.full(ND,np.nan)   # NOEXT
    r=np.sign(d.pct_change()); return r.reindex(pd.DatetimeIndex(dday)-pd.Timedelta(days=1)).values
gr=np.sign(dcl-pC)
for nm,p,sg in (('gold','/home/claude/m1/m1_fixed.pkl',1),('usdjpy','/home/claude/jpym1/m1.pkl',1),('silver','/home/claude/xagm1/m1_xag.pkl',1)):
    rr=dailyret(p)*sg
    for Tb in (6,9):
        for fade in (0,1):
            add4(f"H13 yesterday {nm} direction at {D(Tb)} {'fade' if fade else 'follow'}",lambda rr=rr,Tb=Tb,fade=fade:[(k,BI[k,Tb],O[BI[k,Tb]],int(-rr[k] if fade else rr[k])) for k in range(ND) if BI[k,Tb]>=0 and np.isfinite(rr[k]) and rr[k]!=0])
print('batch C ideas',len(IDEAS4))
# ---------- H14 round break in engine direction (engine already out)
def h14(step,Tb):
    base=h2(step,Tb,'conf',1)
    return lambda:[e for e in base() if not np.isnat(etd[e[0]]) and etd[e[0]]<=Tn[e[1]] and edd[e[0]]==e[3]]
for step in (100,200,400):
    for Tb in (6,9): add4(f"H14 round ${step} break +1min close IN engine direction, from {D(Tb)}",h14(step,Tb))
# ---------- H15 U1 range-rule timing variants
def h15(Tb,endh):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]; s0=starts[k]; ie=BI[k,endh]
            if i<0 or i<=s0: continue
            if ie<0: ie=ends[k]
            up=H[s0:i].max(); dn=L[s0:i].min(); j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            known=(not np.isnat(etd[k])) and etd[k]<=Tn[j]
            E.append((k,j,max(up,O[j]) if sd>0 else min(dn,O[j]),sd if known else -sd))
        return E
    return g
for Tb in (7,8,9,10,11):
    for endh in (13,15,17,21): add4(f"H15 range rule, range open-{D(Tb)}, entries until {D(endh)}",h15(Tb,endh))
# ---------- H16 crossing a reference level after T
def h16(ref,Tb,fade):
    def g():
        E=[]
        for k in range(1,ND):
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0 or not np.isfinite(ref[k]): continue
            if ie<0: ie=ends[k]
            if O[i]>ref[k]: j,sd=first_touch(i,ie,1e18,ref[k],H,L)
            else: j,sd=first_touch(i,ie,ref[k],-1e18,H,L)
            if sd==0: continue
            E.append((k,j,ref[k] if (sd>0 and O[j]<=ref[k]) or (sd<0 and O[j]>=ref[k]) else O[j],-sd if fade else sd))
        return E
    return g
for rn,ref in (('week open',wopen),('month open',mopen),('yesterday close',pC)):
    for Tb in (6,9,12):
        for fade in (0,1): add4(f"H16 price crosses {rn} after {D(Tb)} {'fade' if fade else 'follow'}",h16(ref,Tb,fade))
print('batch C ideas',len(IDEAS4))
