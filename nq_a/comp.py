from fam import *
import os as _os; lad=pd.read_pickle(_os.path.join(_os.environ['NQ_BASE'],'lad.pkl')); ed=pd.Series(lad.edir.values,index=lad.index).reindex(dday).values; et=pd.Series(lad.et.values,index=lad.index).reindex(dday).values
def rangerule(Tb=9,mode='mix'):
    E=[]
    for k in range(ND):
        i=BI[k,Tb]; s0=starts[k]; ie=BI[k,END]
        if i<0 or i<=s0: continue
        if ie<0: ie=ends[k]
        up=H[s0:i].max(); dn=L[s0:i].min(); j,sd=first_touch(i,ie,up,dn,H,L)
        if sd==0: continue
        px=max(up,O[j]) if sd>0 else min(dn,O[j])
        known=np.isfinite(ed[k]) and pd.Timestamp(et[k])<=T[j]
        d=sd if (known or mode=='follow') else -sd
        E.append((k,j,px,d))
    return E
C_={'R100 break':IDEAS['F5 round $400 first touch from 7am break'](),'R50 break':IDEAS['F5 round $200 first touch from 7am break'](),
    'HL5 break':IDEAS['F12 5-day high/low break from 7am follow'](),'HL10 break':IDEAS['F12 10-day high/low break from 7am follow'](),
    'GAP fade 1am':IDEAS['F7 gap vs yesterday close >0.05ATR at 1am fade'](),'RANGE rule':rangerule()}
def show(nm,E):
    r=evaluate(E); print(f"{nm:55s} days {r['cov']:5.1f}% buy {r['buy']:3.0f}% | all {r['all']:5.1f} IS {r['IS']:5.1f} OOS {r['OOS']:5.1f} min {r['mn']:5.1f} {r['p']}")
for n,E in C_.items(): show(n,E)
def combo(names,how='time'):
    best={}
    for pri,n in enumerate(names):
        for e in C_[n]:
            k=e[0]; key=(e[1] if how=='time' else pri)
            if k not in best or key<best[k][0]: best[k]=(key,e)
    return [v[1] for v in best.values()]
print('--- combos')
for names in (['R100 break','R50 break','RANGE rule'],['R50 break','RANGE rule'],['R50 break','HL5 break','RANGE rule'],['R100 break','R50 break','HL10 break','HL5 break','RANGE rule']):
    for how in ('time','priority'): show(f"{how}: "+' > '.join(names),combo(names,how))
