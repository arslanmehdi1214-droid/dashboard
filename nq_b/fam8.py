from fam import *
IDEAS8={}
def add8(n,f): IDEAS8[n]=f
rngd=dhi-dlo
def brk(cond,lvfun,Tb,fade,start=1):
    def g():
        E=[]
        for k in range(start,ND):
            if not cond[k]: continue
            up,dn=lvfun(k); i=BI[k,Tb]; ie=BI[k,END]
            if i<0 or not (np.isfinite(up) and np.isfinite(dn)): continue
            if ie<0: ie=ends[k]
            j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            E.append((k,j,max(up,O[j]) if sd>0 else min(dn,O[j]),-sd if fade else sd))
        return E
    return g
hi_n=lambda n:(lambda k:(dhi[max(0,k-n):k].max(),dlo[max(0,k-n):k].min()))
# M1 compression measures -> N-day range break
bbw=pd.Series(dcl).rolling(20).std().values/pd.Series(dcl).rolling(20).mean().values
bbp=sh(pd.Series(bbw).rolling(120,min_periods=60).apply(lambda x:(x[-1]>=x).mean(),raw=True).values)
rp=sh(pd.Series(rngd).rolling(5).mean().rolling(120,min_periods=60).apply(lambda x:(x[-1]>=x).mean(),raw=True).values)
r3=sh(pd.Series(rngd).rolling(3).mean().values); r20=sh(pd.Series(rngd).rolling(20).mean().values)
CMP={'BB width in lowest 20% (120d)':bbp<=0.2,'BB width in lowest 30%':bbp<=0.3,'5d range in lowest 20% (120d)':rp<=0.2,'5d range in lowest 30%':rp<=0.3,'3d/20d range <0.7':r3/r20<0.7,'3d/20d range <0.6':r3/r20<0.6}
for cn,c in CMP.items():
    c=np.nan_to_num(c).astype(bool)
    for n in (2,3,5):
        for Tb in (0,6,10):
            add8(f"M1 {cn}: break of {n}-day range from {D(Tb)} follow",brk(c,hi_n(n),Tb,0,5))
# M3 expansion regime -> fade N-day range break
r5=sh(pd.Series(rngd).rolling(5).mean().values)
for x in (1.3,1.5):
    c=np.nan_to_num(r5/r20>x).astype(bool)
    for n in (2,3):
        for Tb in (0,10):
            for fade in (0,1): add8(f"M3 wild (5d/20d range >{x}): break of {n}-day range from {D(Tb)} {'fade' if fade else 'follow'}",brk(c,hi_n(n),Tb,fade,5))
# M7 two inside days / NR4+inside
ins=np.r_[False,(dhi[1:]<=dhi[:-1])&(dlo[1:]>=dlo[:-1])]
nr4=np.array([k>=4 and rngd[k]==rngd[k-3:k+1].min() for k in range(ND)])
ii=np.r_[False,ins[1:]&ins[:-1]]; nr4id=nr4&ins
for nm,c in (('two inside days',ii),('NR4 + inside day',nr4id)):
    cc=np.r_[False,c[:-1]]   # yesterday pattern
    for Tb in (0,6,10):
        for fade in (0,1): add8(f"M7 yesterday {nm}: break of yesterday hi/lo from {D(Tb)} {'fade' if fade else 'follow'}",brk(cc,lambda k:(pH[k],pL[k]),Tb,fade,2))
# M8 last week inside / narrow week -> break of last week hi/lo
wkk=pd.DatetimeIndex(dday).to_period('W').astype(str).values
W=pd.DataFrame({'w':wkk,'h':dhi,'l':dlo}).groupby('w',sort=False).agg(h=('h','max'),l=('l','min'))
W['rg']=W.h-W.l; W['ins']=(W.h<=W.h.shift(1))&(W.l>=W.l.shift(1)); W['nr4']=W.rg<=W.rg.rolling(4).min()
pw=W.shift(1); mapw=lambda s:pd.Series(s.values,index=W.index).reindex(wkk).values
pwh,pwl,pwins,pwnr=mapw(pw.h),mapw(pw.l),mapw(pw.ins.astype(float)),mapw(pw.nr4.astype(float))
for nm,c in (('last week inside week',pwins==1),('last week narrowest of 4',pwnr==1)):
    for Tb in (0,6,10):
        for fade in (0,1): add8(f"M8 {nm}: break of last week hi/lo from {D(Tb)} {'fade' if fade else 'follow'}",brk(np.nan_to_num(c).astype(bool),lambda k:(pwh[k],pwl[k]),Tb,fade))
# M9 previous month small range -> break of prev month hi/lo
mkk=pd.DatetimeIndex(dday).to_period('M').astype(str).values
Mo=pd.DataFrame({'m':mkk,'h':dhi,'l':dlo}).groupby('m',sort=False).agg(h=('h','max'),l=('l','min')); Mo['rg']=Mo.h-Mo.l; Mo['sm']=Mo.rg<Mo.rg.rolling(6).median()
pm=Mo.shift(1); mapm=lambda s:pd.Series(s.values,index=Mo.index).reindex(mkk).values
pmh,pml,pmsm=mapm(pm.h),mapm(pm.l),mapm(pm.sm.astype(float))
for nm,c in (('prev month smaller than usual',pmsm==1),('any month',np.ones(ND,bool))):
    for Tb in (0,6,10):
        for fade in (0,1): add8(f"M9 {nm}: break of prev month hi/lo from {D(Tb)} {'fade' if fade else 'follow'}",brk(np.nan_to_num(c).astype(bool),lambda k:(pmh[k],pml[k]),Tb,fade))
# M12 breakout retest: yesterday closed above prior 10-day high (breakout); today price returns to that level -> buy
def m12(n,Tb):
    def g():
        E=[]
        for k in range(n+2,ND):
            prevhi=dhi[k-1-n:k-1].max(); prevlo=dlo[k-1-n:k-1].min()
            if dcl[k-1]>prevhi: d,lv=1,prevhi
            elif dcl[k-1]<prevlo: d,lv=-1,prevlo
            else: continue
            i=BI[k,Tb]; ie=BI[k,END]
            if i<0: continue
            if ie<0: ie=ends[k]
            if (d>0 and O[i]<=lv) or (d<0 and O[i]>=lv): continue
            j,sd=first_touch(i,ie,lv if d<0 else 1e18,lv if d>0 else -1e18,H,L)
            if sd==0: continue
            E.append((k,j,lv,d))
        return E
    return g
for n in (5,10,20):
    for Tb in (0,6,10): add8(f"M12 yesterday closed beyond {n}-day range; retest of that level from {D(Tb)} -> continue",m12(n,Tb))
# M13 momentum close: yesterday closed beyond prior n-day high/low -> follow at time
for n in (5,10,20):
    s=np.full(ND,np.nan)
    for k in range(n+2,ND):
        if dcl[k-1]>dhi[k-1-n:k-1].max(): s[k]=1
        elif dcl[k-1]<dlo[k-1-n:k-1].min(): s[k]=-1
    for Tb in (0,6,10):
        for fade in (0,1): add8(f"M13 yesterday closed beyond {n}-day range -> {'fade' if fade else 'follow'} at {D(Tb)}",(lambda s=s,Tb=Tb,fade=fade:[(k,BI[k,Tb],O[BI[k,Tb]],int(-s[k] if fade else s[k])) for k in range(ND) if BI[k,Tb]>=0 and np.isfinite(s[k])]))
# M14 two strong closes in a row (close in top/bottom 25% of range both days)
loc=(dcl-dlo)/np.maximum(rngd,1e-9); s2=np.full(ND,np.nan)
for k in range(2,ND):
    if loc[k-1]>=0.75 and loc[k-2]>=0.75: s2[k]=1
    elif loc[k-1]<=0.25 and loc[k-2]<=0.25: s2[k]=-1
for Tb in (0,6,10):
    for fade in (0,1): add8(f"M14 two strong closes in a row -> {'fade' if fade else 'follow'} at {D(Tb)}",(lambda Tb=Tb,fade=fade:[(k,BI[k,Tb],O[BI[k,Tb]],int(-s2[k] if fade else s2[k])) for k in range(ND) if BI[k,Tb]>=0 and np.isfinite(s2[k])]))
print('batch G ideas',len(IDEAS8))
