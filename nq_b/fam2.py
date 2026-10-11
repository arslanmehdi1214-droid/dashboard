from fam import *
IDEAS2={}
def add2(n,f): IDEAS2[n]=f
wk=pd.DatetimeIndex(dday).to_period('W').astype(str).values; mk=pd.DatetimeIndex(dday).to_period('M').astype(str).values
wopen=pd.Series(dop).groupby(wk).transform('first').values; mopen=pd.Series(dop).groupby(mk).transform('first').values
wh=pd.Series(dhi).groupby(wk).max(); wl=pd.Series(dlo).groupby(wk).min(); ulist=pd.unique(wk)
pwh=pd.Series(wh.shift(1).reindex(ulist).values,index=ulist).reindex(wk).values; pwl=pd.Series(wl.shift(1).reindex(ulist).values,index=ulist).reindex(wk).values
# G1 price vs reference level at time T (weekly open, monthly open, yesterday mid, yesterday close)
refs={'week open':wopen,'month open':mopen,'yesterday mid':(pH+pL)/2,'yesterday close':pC,'yesterday high':pH,'yesterday low':pL}
def g1(ref,Tb,fade):
    def g():
        E=[]
        for k in range(1,ND):
            i=BI[k,Tb]
            if i<0 or not np.isfinite(ref[k]): continue
            mv=O[i]-ref[k]
            if mv==0: continue
            d=1 if mv>0 else -1; E.append((k,i,O[i],-d if fade else d))
        return E
    return g
for rn,ref in refs.items():
    for Tb in (6,9,12):
        for fade in (0,1): add2(f"G1 price vs {rn} at {D(Tb)} {'fade' if fade else 'follow'}",g1(ref,Tb,fade))
# G2 break of weekly levels / prev week hi-lo
def g2(lv,Tb,fade):
    def g():
        E=[]
        for k in range(ND):
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0 or not np.isfinite(lv[0][k]): continue
            if ie<0: ie=ends[k]
            j,sd=first_touch(i,ie,lv[0][k],lv[1][k],H,L)
            if sd==0: continue
            px=max(lv[0][k],O[j]) if sd>0 else min(lv[1][k],O[j]); E.append((k,j,px,-sd if fade else sd))
        return E
    return g
for Tb in (0,6,9):
    for fade in (0,1): add2(f"G2 prev-week hi/lo break from {D(Tb)} {'fade' if fade else 'follow'}",g2((pwh,pwl),Tb,fade))
# G3 session ranges: range [a,b) then break in [b,b+W)
def g3(a_,b_,W,buf,fade):
    def g():
        E=[]
        for k in range(ND):
            i0=BI[k,a_]; i=BI[k,b_]; ie=BI[k,min(b_+W,24)]
            if i0<0 or i<0 or i<=i0: continue
            if ie<0: ie=ends[k]
            a=dA[k]; up=H[i0:i].max()+buf*a; dn=L[i0:i].min()-buf*a
            j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            px=max(up,O[j]) if sd>0 else min(dn,O[j]); E.append((k,j,px,-sd if fade else sd))
        return E
    return g
for a_,b_ in ((6,8),(7,9),(8,10),(12,14),(13,15),(14,16),(15,17),(9,12),(12,15)):
    for W in (2,4):
        for buf in (0,0.1):
            for fade in (0,1): add2(f"G3 range {D(a_)}-{D(b_)} break within {W}h buf{buf} {'fade' if fade else 'follow'}",g3(a_,b_,W,buf,fade))
# G4 consecutive days
def g4(n,Tb,fade):
    def g():
        E=[]
        for k in range(n+1,ND):
            i=BI[k,Tb]
            if i<0: continue
            cols=np.sign(dcl[k-n:k]-dop[k-n:k])
            if abs(cols.sum())!=n: continue
            d=int(cols[0]); E.append((k,i,O[i],-d if fade else d))
        return E
    return g
for n in (2,3,4):
    for Tb in (0,6,9):
        for fade in (0,1): add2(f"G4 {n} same-colour days in a row, {'against' if fade else 'with'} at {D(Tb)}",g4(n,Tb,fade))
# G5 big first bar after session open (15-min move > x ATR)
def g5(h,mins,x,fade):
    def g():
        E=[]
        for k in range(ND):
            i0=BI[k,h]
            if i0<0 or i0+mins>=ends[k]: continue
            i1=i0+mins; mv=O[i1]-O[i0]
            if abs(mv)<x*dA[k]: continue
            d=1 if mv>0 else -1; E.append((k,i1,O[i1],-d if fade else d))
        return E
    return g
for h in (0,6,7,8,9,14,15,16):
    for mins in (15,30):
        for x in (0.05,0.1):
            for fade in (0,1): add2(f"G5 first {mins}min after {D(h)} moved >{x}ATR {'fade' if fade else 'follow'}",g5(h,mins,x,fade))
# G6 round-number variants: close beyond level (confirmation), and bounce with retest
def g6(step,Tb,conf):
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
            for jj in range(j,min(j+conf*6,ie)):
                seg=C[jj]
                if (sd>0 and seg>lvl) or (sd<0 and seg<lvl):
                    if jj-j+1>=conf: E.append((k,jj,C[jj],sd)); break
                else: break
        return E
    return g
for step in (200,400):
    for Tb in (6,9):
        for conf in (1,3,5,10,15): add2(f"G6 round ${step} break + {conf} min close beyond, from {D(Tb)}",g6(step,Tb,conf))
print('ideas2',len(IDEAS2))
