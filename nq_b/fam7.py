from fam import *
IDEAS7={}
def add7(n,f): IDEAS7[n]=f
def ema(x,n): return pd.Series(x).ewm(span=n,adjust=False).mean().values
# L1 daily EMA pullback in trend: yesterday close above EMA_f > EMA_s (uptrend) -> buy first touch of EMA_f level today
def l1(nf,ns,Tb,fade):
    ef=sh(ema(dcl,nf)); es=sh(ema(dcl,ns)); c1=pC
    def g():
        E=[]
        for k in range(ns+2,ND):
            if not np.isfinite(ef[k]): continue
            up=c1[k]>ef[k]>es[k]; dn=c1[k]<ef[k]<es[k]
            if not (up or dn): continue
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0: continue
            if ie<0: ie=ends[k]
            lv=ef[k]
            if up and O[i]<=lv or dn and O[i]>=lv: continue
            j,sd=first_touch(i,ie,lv if dn else 1e18,lv if up else -1e18,H,L)
            if sd==0: continue
            d=1 if up else -1; E.append((k,j,lv,-d if fade else d))
        return E
    return g
for nf,ns in ((10,30),(20,50),(10,50),(5,20)):
    for Tb in (0,6,9):
        for fade in (0,1): add7(f"L1 daily trend EMA{nf}>{ns}: first touch of EMA{nf} from {D(Tb)} -> {'break' if fade else 'bounce with trend'}",l1(nf,ns,Tb,fade))
# L3 week-so-far range break on Wed/Thu/Fri
wkkey=pd.DatetimeIndex(dday).to_period('W').astype(str).values
def l3(days_,Tb,fade):
    def g():
        E=[]
        for k in range(1,ND):
            if wd[k] not in days_: continue
            m=[q for q in range(max(0,k-5),k) if wkkey[q]==wkkey[k]]
            if len(m)<2: continue
            up=dhi[m].max(); dn=dlo[m].min(); i=BI[k,Tb]; ie=BI[k,END]
            if i<0: continue
            if ie<0: ie=ends[k]
            j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            E.append((k,j,max(up,O[j]) if sd>0 else min(dn,O[j]),-sd if fade else sd))
        return E
    return g
for nm,dd_ in (('Wed',(2,)),('Thu',(3,)),('Fri',(4,)),('Wed-Fri',(2,3,4))):
    for Tb in (0,6,9):
        for fade in (0,1): add7(f"L3 {nm}: break of week-so-far range from {D(Tb)} {'fade' if fade else 'follow'}",l3(dd_,Tb,fade))
# L4 Monday break of Friday hi/lo
def l4(Tb,fade):
    def g():
        E=[]
        for k in range(1,ND):
            if wd[k]!=0: continue
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0: continue
            if ie<0: ie=ends[k]
            j,sd=first_touch(i,ie,pH[k],pL[k],H,L)
            if sd==0: continue
            E.append((k,j,max(pH[k],O[j]) if sd>0 else min(pL[k],O[j]),-sd if fade else sd))
        return E
    return g
for Tb in (0,6,9):
    for fade in (0,1): add7(f"L4 Monday break of Friday hi/lo from {D(Tb)} {'fade' if fade else 'follow'}",l4(Tb,fade))
# L5 volatility contraction: ATR5/ATR20 (daily ranges) < x -> break of 3-day range
r5=sh(pd.Series(dhi-dlo).rolling(5).mean().values); r20=sh(pd.Series(dhi-dlo).rolling(20).mean().values)
def l5(x,nd,Tb,fade):
    def g():
        E=[]
        for k in range(25,ND):
            if not (r5[k]/r20[k]<x): continue
            up=dhi[k-nd:k].max(); dn=dlo[k-nd:k].min(); i=BI[k,Tb]; ie=BI[k,END]
            if i<0: continue
            if ie<0: ie=ends[k]
            j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            E.append((k,j,max(up,O[j]) if sd>0 else min(dn,O[j]),-sd if fade else sd))
        return E
    return g
for x in (0.6,0.7,0.8):
    for nd in (2,3,5):
        for Tb in (0,9):
            for fade in (0,1): add7(f"L5 calm (5d/20d range <{x}): break of {nd}-day range from {D(Tb)} {'fade' if fade else 'follow'}",l5(x,nd,Tb,fade))
# L6 double test of the day's high/low (second touch within 0.05 ATR, >=60 min after first extreme) after Tb -> fade / follow break
def l6(Tb,fade):
    def g():
        E=[]
        for k in range(ND):
            s0=starts[k]; i=BI[k,Tb]; ie=BI[k,END]
            if i<0 or i-s0<60: continue
            if ie<0: ie=ends[k]
            hi_=H[s0:i].max(); lo_=L[s0:i].min(); ih=s0+np.argmax(H[s0:i]); il=s0+np.argmin(L[s0:i]); tol=0.05*dA[k]
            for j in range(i,ie):
                if H[j]>hi_ or L[j]<lo_: break
                if j-ih>=60 and H[j]>=hi_-tol: E.append((k,j,C[j],1 if fade else -1)); break
                if j-il>=60 and L[j]<=lo_+tol: E.append((k,j,C[j],-1 if fade else 1)); break
        return E
    return g
for Tb in (8,10,12,14):
    for fade in (0,1): add7(f"L6 second test of day high/low after {D(Tb)} -> {'expect break' if fade else 'reject (fade)'}",l6(Tb,fade))
# L7 retrace of today's morning move (open -> Tb) by fr, then continue
def l7(Tb,fr,mn):
    def g():
        E=[]
        for k in range(ND):
            s0=starts[k]; i=BI[k,Tb]; ie=BI[k,END]
            if i<0 or i<=s0: continue
            if ie<0: ie=ends[k]
            mv=O[i]-dop[k]
            if abs(mv)<mn*dA[k]: continue
            d=1 if mv>0 else -1; ext=H[s0:i].max() if d>0 else L[s0:i].min(); lv=ext-d*fr*abs(ext-dop[k])
            j,sd=first_touch(i,ie,lv if d<0 else 1e18,lv if d>0 else -1e18,H,L)
            if sd==0: continue
            E.append((k,j,lv,d))
        return E
    return g
for Tb in (8,10,12):
    for fr in (0.382,0.5,0.618):
        for mn in (0.3,0.5): add7(f"L7 morning move >{mn}ATR by {D(Tb)}, pullback {fr} -> continue",l7(Tb,fr,mn))
# L8 silver daily breakout without gold (yesterday): silver closed at 5-day high/low, gold did not -> gold follows
import pandas as _pd
xs=_pd.DataFrame({'time':_pd.to_datetime([]),'c':[]}).astype({'c':float})  # NOEXT
sdly=_pd.Series(xs.c.values,index=_pd.DatetimeIndex(xs.time)).resample('1D').last().dropna()
sh5=sdly.rolling(5).max(); sl5=sdly.rolling(5).min()
sflag=np.where(sdly>=sh5,1,np.where(sdly<=sl5,-1,0)); sfl=_pd.Series(sflag,index=sdly.index)
gd_=_pd.DatetimeIndex(dday); idx=np.searchsorted(sfl.index.values,gd_.values,side='left')-2   # 2-day lag: safe for timezone
sy=np.full(len(idx),np.nan)  # NOEXT
gh5=np.array([np.nan]+[dcl[k-1]>=dcl[max(0,k-5):k].max() for k in range(1,ND)],float); gl5=np.array([np.nan]+[dcl[k-1]<=dcl[max(0,k-5):k].min() for k in range(1,ND)],float)
gflag=np.where(gh5==1,1,np.where(gl5==1,-1,0))
for Tb in (0,6,9):
    add7(f"L8 gold made 5-day extreme, silver did not (2-day lag) -> silver follows at {D(Tb)}",(lambda Tb=Tb:[(k,BI[k,Tb],O[BI[k,Tb]],int(sy[k])) for k in range(ND) if BI[k,Tb]>=0 and np.isfinite(sy[k]) and sy[k]!=0 and gflag[k-1 if k>0 else 0]!=sy[k]]))
# L9 N1 neighbours: gap fill then keep going, other times/sizes
def l9(Tb,thr):
    def g():
        E=[]
        for k in range(1,ND):
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0 or not np.isfinite(pC[k]): continue
            if ie<0: ie=ends[k]
            gp=dop[k]-pC[k]
            if abs(gp)<thr*dA[k]: continue
            if (gp>0 and O[i]<=pC[k]) or (gp<0 and O[i]>=pC[k]): continue
            j,sd=first_touch(i,ie,pC[k] if gp<0 else 1e18,pC[k] if gp>0 else -1e18,H,L)
            if sd==0: continue
            E.append((k,j,pC[k],sd))
        return E
    return g
for Tb in (3,6,8,9,10,12):
    for thr in (0.05,0.1,0.2): add7(f"L9 gap >{thr}ATR filled from {D(Tb)} -> keep going",l9(Tb,thr))
print('batch F ideas',len(IDEAS7))
