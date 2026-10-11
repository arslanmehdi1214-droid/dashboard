from fam4 import *
IDEAS5={}
def add5(n,f): IDEAS5[n]=f
TIMES=(0,3,6,9,12,15)
# ---------- J1 level-break / level-fade machinery
def lvl_touch(up_,dn_,Tb,fade,need_inside=True):
    def g():
        E=[]
        for k in range(1,ND):
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0 or not (np.isfinite(up_[k]) and np.isfinite(dn_[k])): continue
            if ie<0: ie=ends[k]
            if need_inside and not (dn_[k]<O[i]<up_[k]): continue
            j,sd=first_touch(i,ie,up_[k],dn_[k],H,L)
            if sd==0: continue
            px=max(up_[k],O[j]) if sd>0 else min(dn_[k],O[j])
            if fade: px=up_[k] if sd>0 else dn_[k]
            E.append((k,j,px,-sd if fade else sd))
        return E
    return g
rg=pH-pL
LV={'R1/S1':(R1,S1),'R3/S3':(Pp+2*(pH-pL)*0+ (R1-S1)+ (Pp-pL)*0 + (pH-pL),Pp-(R1-S1)-(pH-pL)) }
LV['R3/S3']=(pH+2*(Pp-pL),pL-2*(pH-Pp))
LV['Camarilla H3/L3']=(pC+rg*1.1/4,pC-rg*1.1/4); LV['Camarilla H4/L4']=(pC+rg*1.1/2,pC-rg*1.1/2)
LV['Fib pivot 0.382']=(Pp+0.382*rg,Pp-0.382*rg); LV['Fib pivot 0.618']=(Pp+0.618*rg,Pp-0.618*rg); LV['Fib pivot 1.0']=(Pp+rg,Pp-rg)
# weekly / monthly pivots
def per_piv(key):
    s=pd.DataFrame({'k':key,'h':dhi,'l':dlo,'c':dcl}); g_=s.groupby('k',sort=False).agg(h=('h','max'),l=('l','min'),c=('c','last'))
    g_=g_.shift(1); P=(g_.h+g_.l+g_.c)/3; r=g_.h-g_.l
    m=lambda x:pd.Series(x.values,index=g_.index).reindex(key).values
    return m(P),m(r),m(g_.h),m(g_.l)
wP,wr,_,_=per_piv(wk); mP,mr,_,_=per_piv(mkey)
LV['weekly R1/S1']=(2*wP-(wP-wr/2)*0-wP+wP- (wP-wr) + wP - wP + (wP + (wP - (wP-wr))) - wP ,None)
wPH=wP+wr*0; 
LV['weekly R1/S1']=(wP+wr*0.5,wP-wr*0.5); LV['weekly R2/S2']=(wP+wr,wP-wr); LV['monthly R1/S1']=(mP+mr*0.5,mP-mr*0.5); LV['monthly R2/S2']=(mP+mr,mP-mr)
for nm,(u,d_) in LV.items():
    for Tb in TIMES:
        for fade in (0,1): add5(f"J1 {nm} first touch from {D(Tb)} {'fade' if fade else 'break'}",lvl_touch(u,d_,Tb,fade))
# ---------- J4 ATR bands around day open / yesterday hi-lo
for kk in (0.25,0.5,0.75,1.0):
    for Tb in (3,6,9,12):
        for fade in (0,1): add5(f"J4 day open ±{kk}ATR first touch from {D(Tb)} {'fade' if fade else 'break'}",lvl_touch(dop+kk*dA,dop-kk*dA,Tb,fade))
for kk in (0.1,0.25):
    for Tb in (3,6,9,12):
        for fade in (0,1): add5(f"J5 yesterday hi/lo ±{kk}ATR first touch from {D(Tb)} {'fade' if fade else 'break'}",lvl_touch(pH+kk*dA,pL-kk*dA,Tb,fade,False))
# ---------- J3 opening ranges
def orng(h0,mins,W,fade):
    def g():
        E=[]
        for k in range(ND):
            i0=BI[k,h0]
            if i0<0: continue
            i=i0+mins; ie=min(i+W*60,ends[k])
            if i>=ends[k]: continue
            up=H[i0:i].max(); dn=L[i0:i].min(); j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            E.append((k,j,max(up,O[j]) if sd>0 else min(dn,O[j]),-sd if fade else sd))
        return E
    return g
for h0,lab in ((0,'day open 1am'),(7,'NY-midnight 8am'),(10,'London 11am'),(9,'Frankfurt 10am')):
    for mins in (15,30,60,120):
        for W in (3,6):
            for fade in (0,1): add5(f"J3 opening range {lab} first {mins}min, break within {W}h {'fade' if fade else 'follow'}",orng(h0,mins,W,fade))
# ---------- hourly bars
hid=np.r_[0,np.where((np.diff(dc)!=0)|(np.diff(hr)!=0))[0]+1]; hend=np.r_[hid[1:],len(dc)]
hO=O[hid]; hC=C[hend-1]; hH=np.maximum.reduceat(H,hid); hL=np.minimum.reduceat(L,hid)
min2h=np.searchsorted(hid,np.arange(len(dc)),side='right')-1   # hour bar of each minute
def ema(x,n): return pd.Series(x).ewm(span=n,adjust=False).mean().values
hC_s=pd.Series(hC)
E20,E50,E200=ema(hC,20),ema(hC,50),ema(hC,200)
bbm=hC_s.rolling(20).mean().values; bbs=hC_s.rolling(20).std().values
dch20=pd.Series(hH).rolling(20).max().values; dcl20=pd.Series(hL).rolling(20).min().values
dch55=pd.Series(hH).rolling(55).max().values; dcl55=pd.Series(hL).rolling(55).min().values
tr=np.maximum(hH-hL,np.maximum(abs(hH-np.r_[hC[0],hC[:-1]]),abs(hL-np.r_[hC[0],hC[:-1]]))); hatr=pd.Series(tr).rolling(14).mean().values
def supertrend(m):
    up=(hH+hL)/2+m*hatr; dn=(hH+hL)/2-m*hatr; d=np.ones(len(hC)); fu=up.copy(); fd=dn.copy()
    for t in range(1,len(hC)):
        fu[t]=up[t] if (up[t]<fu[t-1] or hC[t-1]>fu[t-1]) else fu[t-1]
        fd[t]=dn[t] if (dn[t]>fd[t-1] or hC[t-1]<fd[t-1]) else fd[t-1]
        d[t]=1 if hC[t]>fu[t-1] else (-1 if hC[t]<fd[t-1] else d[t-1])
    return d
ST3=supertrend(3.0); ST2=supertrend(2.0)
haC=(hO+hH+hL+hC)/4; haO=np.zeros(len(hC)); haO[0]=hO[0]
for t in range(1,len(hC)): haO[t]=(haO[t-1]+haC[t-1])/2
HA=np.sign(haC-haO)
def hstate(fn,Tb,fade):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]
            if i<0: continue
            m=min2h[i]-1   # last completed hour
            if m<210: continue
            d=fn(m)
            if not np.isfinite(d) or d==0: continue
            d=int(d); E.append((k,i,O[i],-d if fade else d))
        return E
    return g
HS={'H1 EMA20>EMA50':lambda m:np.sign(E20[m]-E50[m]),'H1 close>EMA200':lambda m:np.sign(hC[m]-E200[m]),'H1 EMA20/50 fresh cross (last 3h)':lambda m:np.sign(E20[m]-E50[m]) if np.sign(E20[m]-E50[m])!=np.sign(E20[m-3]-E50[m-3]) else 0,
 'H1 outside BB(20,2)':lambda m:np.sign(hC[m]-bbm[m]) if abs(hC[m]-bbm[m])>2*bbs[m] else 0,'H1 outside BB(20,2.5)':lambda m:np.sign(hC[m]-bbm[m]) if abs(hC[m]-bbm[m])>2.5*bbs[m] else 0,
 'H1 Donchian20 new extreme':lambda m:1 if hH[m]>=dch20[m-1] else (-1 if hL[m]<=dcl20[m-1] else 0),'H1 Donchian55 new extreme':lambda m:1 if hH[m]>=dch55[m-1] else (-1 if hL[m]<=dcl55[m-1] else 0),
 'H1 Supertrend(10,3)':lambda m:ST3[m],'H1 Supertrend(10,2)':lambda m:ST2[m],'H1 Heikin-Ashi colour':lambda m:HA[m],'H1 3 HA candles same colour':lambda m:HA[m] if HA[m]==HA[m-1]==HA[m-2] else 0,
 'H4-ish: last 4 H1 closes up/down':lambda m:np.sign(hC[m]-hC[m-4])}
for nm,fn in HS.items():
    for Tb in (6,9,12):
        for fade in (0,1): add5(f"J13 {nm} at {D(Tb)} {'fade' if fade else 'follow'}",hstate(fn,Tb,fade))
# ---------- J18 yesterday candle patterns
body=np.abs(pC-pO); uw=pH-np.maximum(pC,pO); lw=np.minimum(pC,pO)-pL
ppO,ppC=sh(dop,2),sh(dcl,2)
PAT={'bull/bear engulfing':np.where((pC>pO)&(ppC<ppO)&(pC>=ppO)&(pO<=ppC),1,np.where((pC<pO)&(ppC>ppO)&(pC<=ppO)&(pO>=ppC),-1,0)),
 'pin bar (wick>2x body)':np.where((lw>2*body)&(lw>uw*2),1,np.where((uw>2*body)&(uw>lw*2),-1,0)),'doji -> fade day-before':np.where(body<0.1*rg,-np.sign(ppC-ppO),0)}
for nm,pv in PAT.items():
    for Tb in (0,6,9):
        for fade in (0,1): add5(f"J18 yesterday {nm} at {D(Tb)} {'fade' if fade else 'follow'}",lambda pv=pv,Tb=Tb,fade=fade:[(k,BI[k,Tb],O[BI[k,Tb]],int(-pv[k] if fade else pv[k])) for k in range(2,ND) if BI[k,Tb]>=0 and np.isfinite(pv[k]) and pv[k]!=0])
# ---------- J19 last week
wkc=pd.Series(dcl).groupby(wk,sort=False).last(); wko=pd.Series(dop).groupby(wk,sort=False).first(); wkh=pd.Series(dhi).groupby(wk,sort=False).max(); wkl=pd.Series(dlo).groupby(wk,sort=False).min()
lwcol=pd.Series(np.sign(wkc-wko).shift(1).values,index=wkc.index).reindex(wk).values
lwloc=pd.Series(((wkc-wkl)/(wkh-wkl)).shift(1).values,index=wkc.index).reindex(wk).values
lwl=np.where(lwloc>0.8,1,np.where(lwloc<0.2,-1,0))
for nm,pv in (('last week colour',lwcol),('last week closed top/bottom 20%',lwl)):
    for Tb in (0,6,9):
        for fade in (0,1): add5(f"J19 {nm} at {D(Tb)} {'fade' if fade else 'follow'}",lambda pv=pv,Tb=Tb,fade=fade:[(k,BI[k,Tb],O[BI[k,Tb]],int(-pv[k] if fade else pv[k])) for k in range(ND) if BI[k,Tb]>=0 and np.isfinite(pv[k]) and pv[k]!=0])
# ---------- J20 impulse hour ; J21 squeeze break
def j20(Tb,thr,fade):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0: continue
            if ie<0: ie=ends[k]
            for m in range(min2h[i],min2h[ie-1]):
                if abs(hC[m]-hO[m])>=thr*dA[k]:
                    d=int(np.sign(hC[m]-hO[m])); jj=hend[m]
                    if jj<ends[k]: E.append((k,jj,O[jj],-d if fade else d))
                    break
        return E
    return g
for Tb in (3,6,9,12):
    for thr in (0.25,0.4,0.6):
        for fade in (0,1): add5(f"J20 first 1h candle >{thr}ATR after {D(Tb)} {'fade' if fade else 'follow'} next hour",j20(Tb,thr,fade))
def j21(Tb,thr,fade):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]
            if i<120: continue
            up=H[i-120:i].max(); dn=L[i-120:i].min()
            if up-dn>thr*dA[k]: continue
            j,sd=first_touch(i,min(i+240,ends[k]),up,dn,H,L)
            if sd==0: continue
            E.append((k,j,max(up,O[j]) if sd>0 else min(dn,O[j]),-sd if fade else sd))
        return E
    return g
for Tb in (3,6,9,12,15):
    for thr in (0.1,0.15,0.2):
        for fade in (0,1): add5(f"J21 2h squeeze (<{thr}ATR) before {D(Tb)} break {'fade' if fade else 'follow'}",j21(Tb,thr,fade))
# ---------- J23 round-number magnet
def j23(step,Tb,near,toward):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]
            if i<0: continue
            p=O[i]; up=np.ceil(p/step)*step; dn=np.floor(p/step)*step
            du,dd=up-p,p-dn
            if min(du,dd)>near*dA[k] or du==dd: continue
            d=1 if du<dd else -1; E.append((k,i,p,d if toward else -d))
        return E
    return g
for step in (200,400):
    for Tb in (6,9,12):
        for toward in (1,0): add5(f"J23 near round ${step} (<0.15ATR) at {D(Tb)} {'go toward it' if toward else 'go away'}",j23(step,Tb,0.15,toward))
# ---------- J26 retrace of yesterday's move
def j26(fr,Tb):
    def g():
        E=[]
        for k in range(2,ND):
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0 or not np.isfinite(pC[k]): continue
            if ie<0: ie=ends[k]
            c=np.sign(pC[k]-pO[k])
            if c==0: continue
            lv=pH[k]-fr*rg[k] if c>0 else pL[k]+fr*rg[k]
            if (c>0 and O[i]<=lv) or (c<0 and O[i]>=lv): continue
            j,sd=first_touch(i,ie,lv if c<0 else 1e18,lv if c>0 else -1e18,H,L)
            if sd==0: continue
            E.append((k,j,lv,int(c)))
        return E
    return g
for fr in (0.382,0.5,0.618):
    for Tb in (0,6,9):
        add5(f"J26 pullback to {fr} of yesterday's range from {D(Tb)} -> continue yesterday",j26(fr,Tb))
        add5(f"J26 pullback to {fr} of yesterday's range from {D(Tb)} -> reverse",lambda f=j26(fr,Tb):[(e[0],e[1],e[2],-e[3]) for e in f()])
# ---------- J28 gap fill
def j28(Tb,fade):
    def g():
        E=[]
        for k in range(1,ND):
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0 or not np.isfinite(pC[k]): continue
            if ie<0: ie=ends[k]
            gp=dop[k]-pC[k]
            if abs(gp)<0.05*dA[k]: continue
            if (gp>0 and O[i]<=pC[k]) or (gp<0 and O[i]>=pC[k]): continue
            j,sd=first_touch(i,ie,pC[k] if gp<0 else 1e18,pC[k] if gp>0 else -1e18,H,L)
            if sd==0: continue
            E.append((k,j,pC[k],-sd if fade else sd))
        return E
    return g
for Tb in (0,6,9):
    for fade in (0,1): add5(f"J28 gap filled (touch yesterday close) from {D(Tb)} -> {'bounce back' if fade else 'keep going'}",j28(Tb,fade))
# ---------- J27 yesterday's most-traded price (mode of M1 closes) and value area
poc=np.full(ND,np.nan); vah=np.full(ND,np.nan); val=np.full(ND,np.nan)
for k in range(1,ND):
    s,e=starts[k-1],ends[k-1]; x=C[s:e]
    if len(x)<100: continue
    hist,edges=np.histogram(x,bins=30); b=np.argmax(hist); poc[k]=(edges[b]+edges[b+1])/2
    order=np.argsort(-hist); cum=np.cumsum(hist[order])/hist.sum(); sel=order[:np.searchsorted(cum,0.7)+1]
    vah[k]=edges[sel.max()+1]; val[k]=edges[sel.min()]
for Tb in (3,6,9):
    for fade in (0,1):
        add5(f"J27 yesterday value-area hi/lo touch from {D(Tb)} {'fade' if fade else 'break'}",lvl_touch(vah,val,Tb,fade))
        add5(f"J27 yesterday POC ±0.1ATR touch from {D(Tb)} {'fade' if fade else 'break'}",lvl_touch(poc+0.1*dA,poc-0.1*dA,Tb,fade,False))
# ---------- conditioned U1(11am) and U8
WE2={'U1b':IDEAS4['H15 range rule, range open-11am, entries until 10pm'](),'U8':IDEAS4['H6 pivots R2/S2 first touch from 1pm break']()}
for u,E in WE2.items():
    for cn,cf in CONDS.items(): add5(f"J30 {u} only when {cn}",lambda E=E,cf=cf:[e for e in E if cf(e[0],e[3])])
    for c1,c2 in pairs: add5(f"J30 {u} only when {c1} & {c2}",lambda E=E,f1=CONDS[c1],f2=CONDS[c2]:[e for e in E if f1(e[0],e[3]) and f2(e[0],e[3])])
print('batch D ideas',len(IDEAS5))
