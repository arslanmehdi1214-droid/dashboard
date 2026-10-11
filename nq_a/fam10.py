from fam9 import *
from fam5 import hC, min2h
IDEAS10={}
def add10(n,f): IDEAS10[n]=f
# Q1 neighbours of N13 (ADX) and N11 (calm) at other times / thresholds
for th in (12,15,18):
    c=np.nan_to_num(ADX<th).astype(bool)
    for n in (2,3):
        for Tb in (0,6,9,10,12):
            add10(f"Q1 ADX<{th}: break of {n}-day range from {D(Tb)} follow",brk(c,hi_n(n),Tb,0,30))
# Q2 quiet regime + 50d trend direction filter on breakout
t50=np.full(ND,np.nan); t50[51:]=np.sign(dcl[50:-1]-dcl[:-51])
def brk_tr(cond,lv,Tb,tr):
    base=brk(cond,lv,Tb,0,30)
    return lambda:[e for e in base() if tr[e[0]]==e[3]]
for nm,c in (('ADX<15',np.nan_to_num(ADX<15).astype(bool)),('ADX<20',np.nan_to_num(ADX<20).astype(bool)),('calm<0.8',np.nan_to_num(r5/r20<0.8).astype(bool))):
    for Tb in (9,10):
        add10(f"Q2 {nm} break of 2-day range from {D(Tb)} only WITH 50d trend",brk_tr(c,hi_n(2),Tb,t50))
# Q3 squeeze release: yesterday closed outside its 2/3-day range after a quiet regime -> follow today at open/7am
for nm,cq in (('ADX<20',ADX<20),('calm<0.8',r5/r20<0.8),('BB lowest 20%',bbp<=0.2)):
    cq=np.nan_to_num(cq).astype(bool)
    for n in (2,3,5):
        s=np.full(ND,np.nan)
        for k in range(n+3,ND):
            if not cq[k-1]: continue
            hh=dhi[k-1-n:k-1].max(); ll=dlo[k-1-n:k-1].min()
            if dcl[k-1]>hh: s[k]=1
            elif dcl[k-1]<ll: s[k]=-1
        for Tb in (0,6):
            add10(f"Q3 quiet ({nm}) then yesterday closed beyond {n}-day range -> follow at {D(Tb)}",(lambda s=s,Tb=Tb:[(k,BI[k,Tb],O[BI[k,Tb]],int(s[k])) for k in range(ND) if BI[k,Tb]>=0 and np.isfinite(s[k])]))
# Q4 H4 narrow bar: last completed 4h block is the narrowest of last 7 -> break of it
def q4(Tb,nn):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]
            if i<0 or i<nn*240+10: continue
            rngs=[H[i-240*(m+1):i-240*m].max()-L[i-240*(m+1):i-240*m].min() for m in range(nn)]
            if rngs[0]>min(rngs): continue
            up=H[i-240:i].max(); dn=L[i-240:i].min(); j,sd=first_touch(i,min(i+360,ends[k]),up,dn,H,L)
            if sd==0: continue
            E.append((k,j,max(up,O[j]) if sd>0 else min(dn,O[j]),sd))
        return E
    return g
for Tb in (4,6,8,10,12,14):
    for nn in (4,7): add10(f"Q4 last 4h block narrowest of {nn} before {D(Tb)}: break follow",q4(Tb,nn))
# Q5 hourly squeeze: H1 BB(20) width lowest 10%/20% of last 200 hours -> break of last 6h range
hbw=pd.Series(hC).rolling(20).std().values/pd.Series(hC).rolling(20).mean().values
hbp=pd.Series(hbw).rolling(200,min_periods=100).apply(lambda x:(x[-1]>=x).mean(),raw=True).values
def q5(Tb,pc,nh):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]
            if i<nh*60: continue
            m=min2h[i]-1
            if m<220 or not (hbp[m]<=pc): continue
            up=H[i-nh*60:i].max(); dn=L[i-nh*60:i].min(); j,sd=first_touch(i,min(i+360,ends[k]),up,dn,H,L)
            if sd==0: continue
            E.append((k,j,max(up,O[j]) if sd>0 else min(dn,O[j]),sd))
        return E
    return g
for Tb in (6,8,10,12,14):
    for pc in (0.1,0.2):
        for nh in (4,6): add10(f"Q5 H1 squeeze (BB width lowest {int(pc*100)}%) at {D(Tb)}: break of last {nh}h range follow",q5(Tb,pc,nh))
print('batch I ideas',len(IDEAS10))
