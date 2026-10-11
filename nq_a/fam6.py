from fam import *
IDEAS6={}
def add6(n,f): IDEAS6[n]=f
def at(Tb,dirs,fade=False):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]; d=dirs[k]
            if i<0 or not np.isfinite(d) or d==0: continue
            E.append((k,i,O[i],int(-d if fade else d)))
        return E
    return g
# K1 daily RSI(2) / RSI(3) extremes (Connors), with/without 200-day trend
def rsin(x,n):
    d=np.diff(x,prepend=x[0]); u=pd.Series(np.clip(d,0,None)).ewm(alpha=1/n,adjust=False).mean(); w=pd.Series(np.clip(-d,0,None)).ewm(alpha=1/n,adjust=False).mean()
    return (100*u/(u+w)).values
sma200=pd.Series(dcl).rolling(200).mean().values
for n in (2,3):
    r=sh(rsin(dcl,n))   # yesterday's close RSI, known today
    for lo,hi in ((10,90),(5,95),(20,80)):
        sig=np.where(r<lo,1.0,np.where(r>hi,-1.0,np.nan))
        tr=np.sign(sh(dcl)-sh(sma200))
        for Tb in (0,6):
            add6(f"K1 daily RSI{n} <{lo}/>{hi} reversal at {D(Tb)}",at(Tb,sig))
            add6(f"K1 daily RSI{n} <{lo}/>{hi} reversal WITH 200d trend at {D(Tb)}",at(Tb,np.where(sig==tr,sig,np.nan)))
# K2 NR4 / NR7 / inside day yesterday -> break of yesterday range today
rng=dhi-dlo
nr4=np.array([k>=4 and rng[k]==rng[k-3:k+1].min() for k in range(ND)]); nr7=np.array([k>=7 and rng[k]==rng[k-6:k+1].min() for k in range(ND)])
inside=np.r_[False,(dhi[1:]<=dhi[:-1])&(dlo[1:]>=dlo[:-1])]; outside=np.r_[False,(dhi[1:]>dhi[:-1])&(dlo[1:]<dlo[:-1])]
def ybreak(cond,Tb,fade):
    def g():
        E=[]
        for k in range(1,ND):
            if not cond[k-1]: continue
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0: continue
            if ie<0: ie=ends[k]
            j,sd=first_touch(i,ie,pH[k],pL[k],H,L)
            if sd==0: continue
            E.append((k,j,max(pH[k],O[j]) if sd>0 else min(pL[k],O[j]),-sd if fade else sd))
        return E
    return g
for nm,c in (('NR4',nr4),('NR7',nr7),('inside day',inside),('outside day',outside)):
    for Tb in (0,6,9):
        for fade in (0,1): add6(f"K2 yesterday {nm}: break of yesterday hi/lo from {D(Tb)} {'fade' if fade else 'follow'}",ybreak(c,Tb,fade))
# K3 acceptance: 2 consecutive H1 closes beyond the morning range (open..Tb) -> follow
def accept(Tb,nh,buf):
    def g():
        E=[]
        for k in range(ND):
            s0=starts[k]; i=BI[k,Tb]
            if i<0 or i<=s0: continue
            up=H[s0:i].max()+buf*dA[k]; dn=L[s0:i].min()-buf*dA[k]; cnt=0; side=0
            for hh in range(Tb,END):
                a_=BI[k,hh]; b_=BI[k,hh+1] if hh+1<=24 else -1
                if a_<0 or b_<0 or b_<=a_: continue
                c=C[b_-1]; sd_=1 if c>up else (-1 if c<dn else 0)
                if sd_!=0 and sd_==side: cnt+=1
                else: cnt=1 if sd_!=0 else 0; side=sd_
                if cnt>=nh: E.append((k,b_,O[b_],side)); break
        return E
    return g
for Tb in (8,9,10,11):
    for nh in (1,2,3):
        for buf in (0,0.1): add6(f"K3 {nh} H1 close(s) beyond range open-{D(Tb)} buf{buf} -> follow",accept(Tb,nh,buf))
# K4 time-of-day continuation: at Tb, day move from open > x ATR -> follow / fade
for Tb in (12,13,14,15,16,17):
    for x in (0.4,0.6,0.8,1.0):
        for fade in (0,1):
            add6(f"K4 day move since open >{x}ATR at {D(Tb)} {'fade' if fade else 'follow'}",
                 (lambda Tb=Tb,x=x,fade=fade:[(k,BI[k,Tb],O[BI[k,Tb]],int((-1 if fade else 1)*np.sign(O[BI[k,Tb]]-dop[k]))) for k in range(ND) if BI[k,Tb]>=0 and abs(O[BI[k,Tb]]-dop[k])>=x*dA[k]]))
# K5 day range already large at Tb (range so far >= x ATR) -> fade position in range (near high -> sell)
def k5(Tb,x,fade):
    def g():
        E=[]
        for k in range(ND):
            s0=starts[k]; i=BI[k,Tb]
            if i<0 or i<=s0: continue
            hi_,lo_=H[s0:i].max(),L[s0:i].min()
            if hi_-lo_<x*dA[k]: continue
            pos=(O[i]-lo_)/(hi_-lo_)
            if 0.2<pos<0.8: continue
            d=1 if pos>=0.8 else -1; E.append((k,i,O[i],-d if fade else d))
        return E
    return g
for Tb in (10,12,14,16):
    for x in (0.8,1.0,1.3):
        for fade in (0,1): add6(f"K5 range so far >={x}ATR at {D(Tb)}, price at an extreme -> {'fade' if fade else 'follow'}",k5(Tb,x,fade))
# K6 big gap not filled by Tb -> follow gap
def k6(thr,Tb):
    def g():
        E=[]
        for k in range(1,ND):
            i=BI[k,Tb]; s0=starts[k]
            if i<0 or i<=s0 or not np.isfinite(pC[k]): continue
            gp=dop[k]-pC[k]
            if abs(gp)<thr*dA[k]: continue
            filled=(L[s0:i].min()<=pC[k]) if gp>0 else (H[s0:i].max()>=pC[k])
            if filled: continue
            E.append((k,i,O[i],int(np.sign(gp))))
        return E
    return g
for thr in (0.1,0.2,0.3):
    for Tb in (3,6,9): add6(f"K6 gap >{thr}ATR not filled by {D(Tb)} -> follow gap",k6(thr,Tb))
# K7 Connors 3 down days in uptrend (above 200d) buy / 3 up days in downtrend sell
for n in (2,3,4):
    col=np.sign(dcl-np.r_[np.nan,dcl[:-1]])
    s=np.full(ND,np.nan)
    for k in range(n+1,ND):
        c=col[k-n:k]; tr=np.sign(dcl[k-1]-sma200[k-1]) if np.isfinite(sma200[k-1]) else 0
        if np.all(c<0) and tr>0: s[k]=1
        if np.all(c>0) and tr<0: s[k]=-1
    for Tb in (0,6): add6(f"K7 {n} closes against the 200d trend -> buy/sell the dip at {D(Tb)}",at(Tb,s))
# K8 Bollinger %b daily extremes (20,2) of yesterday
bm=pd.Series(dcl).rolling(20).mean().values; bs=pd.Series(dcl).rolling(20).std().values; pb=sh((dcl-bm)/(2*bs))
for th in (1.0,0.8):
    for Tb in (0,6):
        s=np.where(pb>th,1.0,np.where(pb<-th,-1.0,np.nan))
        add6(f"K8 yesterday close outside daily BB {th} -> follow at {D(Tb)}",at(Tb,s)); add6(f"K8 yesterday close outside daily BB {th} -> fade at {D(Tb)}",at(Tb,s,True))
print('batch E ideas',len(IDEAS6))
