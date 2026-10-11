from core import *
def D(h): h=(h+1)%24; return f"{(h-1)%12+1}{'am' if h<12 else 'pm'}"
IDEAS={}
def add(name,fn): IDEAS[name]=fn
END=19  # broker hour: stop looking for entries
# F1 range break
def f1(st,Tb,buf,fade):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]; s0=BI[k,max(st if st>=0 else Tb+st,0)]; ie=BI[k,END]
            if i<0 or s0<0 or i<=s0: continue
            if ie<0: ie=ends[k]
            a=dA[k]; up=H[s0:i].max()+buf*a; dn=L[s0:i].min()-buf*a
            j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            px=max(up,O[j]) if sd>0 else min(dn,O[j]); d=-sd if fade else sd
            E.append((k,j,px,d))
        return E
    return g
for Tb in (6,7,8,9,10,11):
    for st in (0,-3,-2):
        for buf in (0,0.05,0.1):
            for fade in (0,1): add(f"F1 range {'open' if st==0 else str(-st)+'h'}->{D(Tb)} buf{buf} {'fade' if fade else 'follow'}",f1(st,Tb,buf,fade))
# F2 prev day high/low
def f2a(Tb,fade):
    def g():
        E=[]
        for k in range(1,ND):
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0: continue
            if ie<0: ie=ends[k]
            j,sd=first_touch(i,ie,pH[k],pL[k],H,L)
            if sd==0: continue
            px=max(pH[k],O[j]) if sd>0 else min(pL[k],O[j]); E.append((k,j,px,-sd if fade else sd))
        return E
    return g
for Tb in (0,6,9,13):
    for fade in (0,1): add(f"F2 prev-day hi/lo break from {D(Tb)} {'fade' if fade else 'follow'}",f2a(Tb,fade))
def f2b(Tb,x,W,rev):
    def g():
        E=[]
        for k in range(1,ND):
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0: continue
            if ie<0: ie=ends[k]
            a=dA[k]; j,sd=first_touch(i,ie,pH[k]+x*a,pL[k]-x*a,H,L)
            if sd==0: continue
            lvl=pH[k] if sd>0 else pL[k]
            for jj in range(j+1,min(j+W,ie)):
                if (sd>0 and C[jj]<lvl) or (sd<0 and C[jj]>lvl):
                    d=-sd if rev else sd; E.append((k,jj,C[jj],d)); break
        return E
    return g
for Tb in (0,6,9,13):
    for x in (0,0.05,0.1):
        for W in (30,90):
            add(f"F2 sweep prev-day hi/lo by {x}ATR from {D(Tb)} back inside <{W}min -> reverse",f2b(Tb,x,W,1))
# F3 window momentum
def f3(a_,b_,thr,fade):
    def g():
        E=[]
        for k in range(ND):
            i0=BI[k,a_]; i1=BI[k,b_]
            if i0<0 or i1<0 or i1<=i0: continue
            mv=O[i1]-O[i0]
            if mv==0 or abs(mv)<thr*dA[k]: continue
            d=1 if mv>0 else -1; E.append((k,i1,O[i1],-d if fade else d))
        return E
    return g
for a_ in (0,3,6,9,12):
    for L_ in (1,2,3,4):
        for fade in (0,1):
            add(f"F3 move {D(a_)}->{D(a_+L_)} {'fade' if fade else 'follow'}",f3(a_,a_+L_,0,fade))
            if L_ in (2,4): add(f"F3 move {D(a_)}->{D(a_+L_)} >0.2ATR {'fade' if fade else 'follow'}",f3(a_,a_+L_,0.2,fade))
# F4 cross markets, 60-min lag for safety
def lastc(path,ts,lagmin=60):
    return np.full(len(ts),np.nan)   # NOEXT
    m=pd.read_pickle(path); tt=m.time.values; cc=m.c.values.astype(float)
    ts=ts-np.timedelta64(lagmin,'m'); j=np.searchsorted(tt,ts,side='right')-1; out=cc[np.clip(j,0,None)]
    age=(ts-tt[np.clip(j,0,None)]).astype('timedelta64[m]').astype(float); out[(j<0)|(age>180)]=np.nan; return out
XM={}
for nm,p in (('gold','/home/claude/m1/m1_fixed.pkl'),('usdjpy','/home/claude/jpym1/m1.pkl'),('silver','/home/claude/xagm1/m1_xag.pkl')):
    XM[nm]={hh:lastc(p,np.array([T[BI[k,hh]] if BI[k,hh]>=0 else T[starts[k]] for k in range(ND)],dtype='datetime64[ns]')) for hh in (1,3,6,8,10,12)}
def f4(nm,h0,h1,sg,fade,div=False):
    def g():
        E=[]
        for k in range(ND):
            i1=BI[k,h1]; i0=BI[k,h0]
            if i1<0 or i0<0: continue
            r=XM[nm][h1][k]/XM[nm][h0][k]-1
            if not np.isfinite(r) or r==0: continue
            if div:
                gr=O[BI[k,max(h1-1,0)]]/O[BI[k,max(h0-1,0)]]-1   # gold lagged the same 60 min
                r=r-gr
            d=int(np.sign(r))*sg; E.append((k,i1,O[i1],-d if fade else d))
        return E
    return g
for nm,sg in (('gold',1),('usdjpy',1),('silver',1)):
    for h0,h1 in ((1,6),(1,10),(3,8),(6,10),(8,12)):
        for fade in (0,1):
            add(f"F4 {nm} move {D(h0-1)}->{D(h1-1)} (60min lag) {'fade' if fade else 'follow'}",f4(nm,h0,h1,sg,fade))
            if nm=='gold': add(f"F4 gold minus silver {D(h0-1)}->{D(h1-1)} {'fade' if fade else 'follow'}",f4(nm,h0,h1,sg,fade,True))
# F5 round numbers
def f5(step,Tb,bounce):
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
            px=(max(up,O[j]) if sd>0 else min(dn,O[j])) if not bounce else (max(up,O[j]) if sd>0 else min(dn,O[j])); d=-sd if bounce else sd; E.append((k,j,px,d))
        return E
    return g
for step in (40,80,100,160,200,300,400,600,800):
    for Tb in (6,9,12):
        for b in (1,0): add(f"F5 round ${step} first touch from {D(Tb)} {'bounce' if b else 'break'}",f5(step,Tb,b))
# F6 yesterday structure
def f6(cond,Tb,mode):
    def g():
        E=[]
        for k in range(2,ND):
            i=BI[k,Tb]
            if i<0 or not np.isfinite(pC[k]): continue
            a=dA[k]; rng=(pH[k]-pL[k])/a; col=np.sign(pC[k]-pO[k]); loc=(pC[k]-pL[k])/max(pH[k]-pL[k],1e-9)
            ok,d=cond(k,rng,col,loc)
            if not ok or d==0: continue
            E.append((k,i,O[i],d if mode==0 else -d))
        return E
    return g
for thr in (1.2,1.5,2.0):
    for Tb in (0,6,9):
        for m_ in (0,1): add(f"F6 yesterday range>={thr}ATR, trade {'with' if m_==0 else 'against'} yesterday colour at {D(Tb)}",f6(lambda k,r,c,l,thr=thr:(r>=thr,c),Tb,m_))
for thr in (0.5,0.7):
    for Tb in (0,6,9):
        for m_ in (0,1): add(f"F6 yesterday range<={thr}ATR (quiet), {'with' if m_==0 else 'against'} colour at {D(Tb)}",f6(lambda k,r,c,l,thr=thr:(r<=thr,c),Tb,m_))
for q in (0.2,0.3):
    for Tb in (0,6,9):
        for m_ in (0,1): add(f"F6 yesterday closed in top/bottom {int(q*100)}%, {'with' if m_==0 else 'against'} at {D(Tb)}",f6(lambda k,r,c,l,q=q:(l>=1-q or l<=q,1 if l>=1-q else -1),Tb,m_))
# F7 gap
def f7(thr,Tb,fade):
    def g():
        E=[]
        for k in range(1,ND):
            i=BI[k,Tb]
            if i<0 or not np.isfinite(pC[k]): continue
            gp=dop[k]-pC[k]
            if gp==0 or abs(gp)<thr*dA[k]: continue
            d=1 if gp>0 else -1; E.append((k,i,O[i],-d if fade else d))
        return E
    return g
for thr in (0,0.05,0.1):
    for Tb in (0,3,6):
        for fade in (0,1): add(f"F7 gap vs yesterday close >{thr}ATR at {D(Tb)} {'fade' if fade else 'follow'}",f7(thr,Tb,fade))
# F8 calendar
def f8(cond,Tb,d0):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]
            if i<0 or not cond(k): continue
            E.append((k,i,O[i],d0))
        return E
    return g
dd_=pd.DatetimeIndex(dday); mo=dd_.month.values; dom=dd_.day.values
lastd=np.r_[mo[1:]!=mo[:-1],True]; last2=lastd|np.r_[lastd[1:],False]; first=np.r_[True,mo[1:]!=mo[:-1]]; first2=first|np.r_[False,first[:-1]]
wd=dd_.dayofweek.values
for Tb in (6,9):
    for d0 in (1,-1):
        for w in range(5): add(f"F8 weekday {['Mon','Tue','Wed','Thu','Fri'][w]} always {'buy' if d0>0 else 'sell'} at {D(Tb)}",f8(lambda k,w=w:wd[k]==w,Tb,d0))
        add(f"F8 last 2 days of month {'buy' if d0>0 else 'sell'} at {D(Tb)}",f8(lambda k:last2[k],Tb,d0))
        add(f"F8 first 2 days of month {'buy' if d0>0 else 'sell'} at {D(Tb)}",f8(lambda k:first2[k],Tb,d0))
        add(f"F8 mid-month 14-16 {'buy' if d0>0 else 'sell'} at {D(Tb)}",f8(lambda k:14<=dom[k]<=16,Tb,d0))
# F9 distance from day open
def f9(Tb,thr,fade):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]
            if i<0: continue
            mv=O[i]-dop[k]
            if abs(mv)<thr*dA[k] or mv==0: continue
            d=1 if mv>0 else -1; E.append((k,i,O[i],-d if fade else d))
        return E
    return g
for Tb in range(6,15):
    for thr in (0.2,0.4,0.6):
        for fade in (0,1): add(f"F9 price vs day open at {D(Tb)} >{thr}ATR {'fade' if fade else 'follow'}",f9(Tb,thr,fade))
# F10 first-hour candle of sessions
def f10(h,fade):
    def g():
        E=[]
        for k in range(ND):
            i0=BI[k,h]; i1=BI[k,h+1]
            if i0<0 or i1<0 or i1<=i0: continue
            mv=O[i1]-O[i0]
            if mv==0: continue
            d=1 if mv>0 else -1; E.append((k,i1,O[i1],-d if fade else d))
        return E
    return g
for h in (0,1,2,6,7,8,9,14,15,16):
    for fade in (0,1): add(f"F10 hour candle {D(h)} {'fade' if fade else 'follow'} (enter {D(h+1)})",f10(h,fade))
# F11 price vs moving average of last N hours (M1 closes), RSI of hourly closes
Cs=pd.Series(C)
def f11(Tb,N,fade):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]
            if i<N*60: continue
            ma=C[i-N*60:i].mean(); mv=O[i]-ma
            if mv==0: continue
            d=1 if mv>0 else -1; E.append((k,i,O[i],-d if fade else d))
        return E
    return g
for Tb in (6,9,12):
    for N in (4,8,24,48):
        for fade in (0,1): add(f"F11 price vs {N}h average at {D(Tb)} {'fade' if fade else 'follow'}",f11(Tb,N,fade))
def rsi(x):
    dd=np.diff(x); u=dd[dd>0].sum(); dn=-dd[dd<0].sum(); return 100*u/(u+dn) if u+dn>0 else 50
def f11r(Tb,N,lo,hi,fade):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]
            if i<(N+1)*60: continue
            r=rsi(C[i-(N+1)*60:i:60])
            if r>=hi: d=-1
            elif r<=lo: d=1
            else: continue
            E.append((k,i,O[i],-d if fade else d))
        return E
    return g
for Tb in (6,9,12):
    for N in (14,):
        for lo,hi in ((30,70),(40,60)):
            for fade in (0,1): add(f"F11 H1 RSI{N} {lo}/{hi} at {D(Tb)} {'reversal' if not fade else 'momentum'}",f11r(Tb,N,lo,hi,fade))
# F12 multi-day highs/lows
def f12(nd,Tb,fade):
    def g():
        E=[]
        for k in range(nd,ND):
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0: continue
            if ie<0: ie=ends[k]
            up=dhi[k-nd:k].max(); dn=dlo[k-nd:k].min()
            j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            px=max(up,O[j]) if sd>0 else min(dn,O[j]); E.append((k,j,px,-sd if fade else sd))
        return E
    return g
for nd in (2,3,5,10):
    for Tb in (0,6,9):
        for fade in (0,1): add(f"F12 {nd}-day high/low break from {D(Tb)} {'fade' if fade else 'follow'}",f12(nd,Tb,fade))
# F13 N-day trend at time
def f13(N,Tb,fade):
    def g():
        E=[]
        for k in range(N+1,ND):
            i=BI[k,Tb]
            if i<0: continue
            d=np.sign(dcl[k-1]-dcl[k-1-N])
            if d==0: continue
            E.append((k,i,O[i],-d if fade else d))
        return E
    return g
for N in (1,2,3,5,10,20,50,100,200):
    for Tb in (6,9):
        for fade in (0,1): add(f"F13 {N}-day trend at {D(Tb)} {'against' if fade else 'with'}",f13(N,Tb,fade))
print('ideas',len(IDEAS))
