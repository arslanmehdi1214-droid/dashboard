from fam2 import *
from itertools import combinations
def states(Tb):
    S={}
    i=BI[:,Tb]; ok=i>=0; px=np.where(ok,O[np.clip(i,0,None)],np.nan)
    for N in (3,5,10,20,50):
        r=np.full(ND,np.nan); r[N+1:]=np.sign(dcl[N:-1]-dcl[:-N-1]); S[f'{N}d trend']=r
    S['gap dir']=np.sign(dop-pC); S['yesterday colour']=np.sign(pC-pO)
    for nm,ref in (('week open',wopen),('month open',mopen),('yday mid',(pH+pL)/2),('day open',dop)): S[f'px vs {nm}']=np.sign(px-ref)
    for N in (4,24):
        S[f'px vs {N}h avg']=np.array([np.sign(O[ii]-C[ii-N*60:ii].mean()) if ii>=N*60 else np.nan for ii in i])
    hs=[h for h in (1,3,6,8,10,12) if h<=Tb+1]; h1=max(hs)
    S['gold since 1am (lag)']=np.sign(XM['gold'][h1]/XM['gold'][1]-1); S['usdjpy since 1am (lag)']=np.sign(XM['usdjpy'][h1]/XM['usdjpy'][1]-1)
    S['H1 RSI>50']=np.array([np.sign(rsi(C[ii-15*60:ii:60])-50) if ii>=15*60 else np.nan for ii in i])
    return S,i
IDEAS3={}
for Tb in (6,9):
    S,i=states(Tb); names=list(S)
    for a,b in combinations(names,2):
        def mk(a=a,b=b,S=S,i=i):
            E=[]
            for k in range(ND):
                x,y=S[a][k],S[b][k]
                if i[k]<0 or not np.isfinite(x) or x==0 or x!=y: continue
                E.append((k,i[k],O[i[k]],int(x)))
            return E
        IDEAS3[f"G7 {a} AND {b} agree at {D(Tb)}"]=mk
print('ideas3',len(IDEAS3))
def g8(Tb,lo,hi,buf,fade,gapc=0):
    def g():
        E=[]
        for k in range(1,ND):
            i=BI[k,Tb]; s0=starts[k]; ie=BI[k,END]
            if i<0 or i<=s0: continue
            if ie<0: ie=ends[k]
            a=dA[k]; rh=H[s0:i].max(); rl=L[s0:i].min(); rr=(rh-rl)/a
            if not (lo<=rr<hi): continue
            j,sd=first_touch(i,ie,rh+buf*a,rl-buf*a,H,L)
            if sd==0: continue
            if gapc:
                gd=np.sign(dop[k]-pC[k])
                if gd==0 or (gapc==1 and gd!=sd) or (gapc==-1 and gd==sd): continue
            px=max(rh+buf*a,O[j]) if sd>0 else min(rl-buf*a,O[j]); E.append((k,j,px,-sd if fade else sd))
        return E
    return g
for Tb in (8,9,10):
    for lo,hi in ((0,0.3),(0.3,0.6),(0.6,9)):
        for buf in (0,0.05):
            for fade in (0,1): IDEAS3[f"G8 range open-{D(Tb)} size {lo}-{hi}ATR buf{buf} {'fade' if fade else 'follow'}"]=g8(Tb,lo,hi,buf,fade)
    for gc in (1,-1):
        for fade in (0,1): IDEAS3[f"G8 range open-{D(Tb)} break {'WITH' if gc==1 else 'AGAINST'} gap {'fade' if fade else 'follow'}"]=g8(Tb,0,9,0,fade,gc)
ALL2={**IDEAS2,**IDEAS3}; print('batch B ideas',len(ALL2))
