import io,contextlib
with contextlib.redirect_stdout(io.StringIO()):
    from fam10 import *
    from fam6 import nr7,inside
IDEAS11={}
def add11(n,f): IDEAS11[n]=f
sq15=np.nan_to_num(sh((ma20+2*sd20<ma20+1.5*atr20)&(ma20-2*sd20>ma20-1.5*atr20))).astype(bool)
Qm={'ADX<18':np.nan_to_num(ADX<18).astype(bool),'calm<0.8':np.nan_to_num(r5/r20<0.8).astype(bool),'BB<=20%':np.nan_to_num(bbp<=0.2).astype(bool),
    'TTM':sq15,'yday NR7':np.r_[False,nr7[:-1]],'yday inside':np.r_[False,inside[:-1]]}
score=sum(v.astype(int) for v in Qm.values())
# R3 quiet score (count of 6 compression measures)
for s in (1,2,3):
    c=score>=s
    for n in (2,3):
        for Tb in (9,12):
            add11(f"R3 quiet score>={s}: break of {n}-day range from {D(Tb)} follow",brk(c,hi_n(n),Tb,0,30))
# generic break with entry variants
def brkx(cond,n,Tb,mode,par):
    def g():
        E=[]
        for k in range(30,ND):
            if not cond[k]: continue
            up,dn=hi_n(n)(k); i=BI[k,Tb]; ie=BI[k,END]
            if i<0: continue
            if ie<0: ie=ends[k]
            a=A[i]
            if mode=='buf':      # need price beyond level + par*ATR
                j,sd=first_touch(i,ie,up+par*a,dn-par*a,H,L)
                if sd==0: continue
                E.append((k,j,max(up+par*a,O[j]) if sd>0 else min(dn-par*a,O[j]),sd)); continue
            j,sd=first_touch(i,ie,up,dn,H,L)
            if sd==0: continue
            lv=up if sd>0 else dn
            if mode=='close':    # first par-minute close beyond the level within 2h, before price returns 0.3ATR inside
                for m in range(j,min(j+120,ie)):
                    if (m-j)%par==par-1:
                        if (C[m]-lv)*sd>0: E.append((k,m,C[m],sd)); break
                    if (lv-(L[m] if sd>0 else H[m]))*sd>0.3*a: break
            elif mode=='retest': # after break wait for pullback to level within 4h, enter there
                ok=False
                for m in range(j+5,min(j+240,ie)):
                    if (H[m]-lv>=par*a if sd>0 else lv-L[m]>=par*a): ok=True
                    if ok and ((L[m]<=lv) if sd>0 else (H[m]>=lv)): E.append((k,m,min(lv,O[m]) if sd>0 else max(lv,O[m]),sd)); break
            elif mode=='fail':   # break fails: back inside by par*ATR within 60 min -> reverse
                for m in range(j+1,min(j+60,ie)):
                    if (lv-L[m] if sd>0 else H[m]-lv)>=par*a: E.append((k,m,lv-par*a if sd>0 else lv+par*a,-sd)); break
        return E
    return g
for qn in ('ADX<18','calm<0.8','BB<=20%','TTM'):
    c=Qm[qn]
    for n in (2,3):
        for Tb in (9,12):
            for b in (0.1,0.2): add11(f"R11 {qn}: break of {n}-day range by +{b}ATR from {D(Tb)} follow",brkx(c,n,Tb,'buf',b))
            for p in (5,15): add11(f"R10 {qn}: {n}-day break then {p}-min close beyond from {D(Tb)} follow",brkx(c,n,Tb,'close',p))
            add11(f"R1 {qn}: {n}-day break, run 0.2ATR, retest level from {D(Tb)} -> continue",brkx(c,n,Tb,'retest',0.2))
            add11(f"R13 {qn}: {n}-day break fails (0.15ATR back inside <60min) from {D(Tb)} -> reverse",brkx(c,n,Tb,'fail',0.15))
# R6 intraday quiet: quiet regime + today's range so far small -> break of today's range so far
def r6(cond,Tb,x):
    def g():
        E=[]
        for k in range(30,ND):
            if not cond[k]: continue
            s=starts[k]; i=BI[k,Tb]; ie=BI[k,END]
            if i<=s+30: continue
            if ie<0: ie=ends[k]
            up=H[s:i].max(); dn=L[s:i].min()
            if up-dn>x*A[i]: continue
            j,sd=first_touch(i,ie,up,dn,H,L)
            if sd: E.append((k,j,max(up,O[j]) if sd>0 else min(dn,O[j]),sd))
        return E
    return g
for qn in ('any quiet','ADX<18','calm<0.8'):
    c=score>=1 if qn=='any quiet' else Qm[qn]
    for Tb in (8,10,12):
        for x in (0.3,0.5): add11(f"R6 {qn} + day range by {D(Tb)} <{x}ATR: break of it follow",r6(c,Tb,x))
print('batch J ideas',len(IDEAS11))
