from fam8 import *
IDEAS9={}
def add9(n,f): IDEAS9[n]=f
# TTM squeeze daily: BB(20,2) inside Keltner(20, 1.5 x ATR20 of daily ranges) yesterday
ma20=pd.Series(dcl).rolling(20).mean().values; sd20=pd.Series(dcl).rolling(20).std().values
tr=np.maximum(dhi-dlo,np.maximum(abs(dhi-np.r_[np.nan,dcl[:-1]]),abs(dlo-np.r_[np.nan,dcl[:-1]]))); atr20=pd.Series(tr).rolling(20).mean().values
for m in (1.5,2.0):
    sq=sh((ma20+2*sd20<ma20+m*atr20)&(ma20-2*sd20>ma20-m*atr20)); c=np.nan_to_num(sq).astype(bool)
    for n in (2,3,5):
        for Tb in (0,9,10):
            add9(f"P1 TTM squeeze (KC {m}): break of {n}-day range from {D(Tb)} follow",brk(c,hi_n(n),Tb,0,25))
# daily ADX low
def adx(n=14):
    up=dhi-np.r_[np.nan,dhi[:-1]]; dn=np.r_[np.nan,dlo[:-1]]-dlo
    pdm=np.where((up>dn)&(up>0),up,0.0); ndm=np.where((dn>up)&(dn>0),dn,0.0)
    a=pd.Series(tr).ewm(alpha=1/n,adjust=False).mean(); pdi=100*pd.Series(pdm).ewm(alpha=1/n,adjust=False).mean()/a; ndi=100*pd.Series(ndm).ewm(alpha=1/n,adjust=False).mean()/a
    dx=100*abs(pdi-ndi)/(pdi+ndi); return dx.ewm(alpha=1/n,adjust=False).mean().values
ADX=sh(adx())
for th in (15,18,20):
    c=np.nan_to_num(ADX<th).astype(bool)
    for n in (2,3,5):
        for Tb in (0,9):
            add9(f"P2 daily ADX<{th}: break of {n}-day range from {D(Tb)} follow",brk(c,hi_n(n),Tb,0,30))
# weekly compression: last 2 weeks range vs 10-week average weekly range
Wk=pd.DataFrame({'w':wkk,'h':dhi,'l':dlo}).groupby('w',sort=False).agg(h=('h','max'),l=('l','min'))
w2h=Wk.h.rolling(2).max().shift(1); w2l=Wk.l.rolling(2).min().shift(1); wr10=(Wk.h-Wk.l).rolling(10).mean().shift(1)
ratio=((w2h-w2l)/(2*wr10)); mp=lambda s:pd.Series(s.values,index=Wk.index).reindex(wkk).values
W2H,W2L,WRAT=mp(w2h),mp(w2l),mp(ratio)
for x in (0.6,0.7,0.8):
    c=np.nan_to_num(WRAT<x).astype(bool)
    for Tb in (0,6,9):
        add9(f"P3 last 2 weeks quiet (<{x} of usual): break of 2-week range from {D(Tb)} follow",brk(c,lambda k:(W2H[k],W2L[k]),Tb,0))
# intraday compression: last N hours range < x ATR, then break of that box
def p4(Tb,nh,x):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]
            if i<nh*60: continue
            up=H[i-nh*60:i].max(); dn=L[i-nh*60:i].min()
            if up-dn>x*dA[k]: continue
            j,sd=first_touch(i,min(i+360,ends[k]),up,dn,H,L)
            if sd==0: continue
            E.append((k,j,max(up,O[j]) if sd>0 else min(dn,O[j]),sd))
        return E
    return g
for Tb in (6,8,9,10,12):
    for nh in (3,4,6):
        for x in (0.2,0.25,0.3): add9(f"P4 last {nh}h box < {x}ATR before {D(Tb)}: break follow",p4(Tb,nh,x))
# second break of 2-day range: first break fails back inside, then the other side breaks -> follow
def p5(n,Tb):
    def g():
        E=[]
        for k in range(n,ND):
            up,dn=hi_n(n)(k); i=BI[k,Tb]; ie=BI[k,END]
            if i<0: continue
            if ie<0: ie=ends[k]
            j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            j2,sd2=first_touch(j+1,ie,up if sd<0 else 1e18,dn if sd>0 else -1e18,H,L)
            if sd2!=0: E.append((k,j2,max(up,O[j2]) if sd2>0 else min(dn,O[j2]),sd2))
        return E
    return g
for n in (1,2,3):
    for Tb in (0,6,9): add9(f"P5 {n}-day range: first break fails, other side breaks from {D(Tb)} -> follow",p5(n,Tb))
print('batch H ideas',len(IDEAS9))
