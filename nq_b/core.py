import os,numpy as np,pandas as pd
_B=os.environ['NQ_BASE']
from numba import njit
z=np.load(os.path.join(_B,'base.npz')); O,H,L,C,A=z['O'],z['H'],z['L'],z['C'],z['A']; dc,hr,EOD,yr,dow=z['dcode'],z['hr'],z['EOD'],z['yr'],z['dow']
T=pd.DatetimeIndex(pd.read_pickle(os.path.join(_B,'base_t.pkl'))['t'])
starts=np.r_[0,np.where(np.diff(dc)!=0)[0]+1]; ends=np.r_[starts[1:],len(dc)]; ND=len(starts)
dday=T[starts].normalize(); NB=len(pd.bdate_range(dday[0],dday[-1]))
dyr=yr[starts]
BI=np.full((ND,25),-1,np.int64)
for k,(s,e) in enumerate(zip(starts,ends)):
    h=hr[s:e]
    for hh in range(25):
        p=np.searchsorted(h,hh)
        BI[k,hh]=s+p if p<len(h) else -1
BI0=BI.copy()
for hh in range(25): BI[:,hh]=BI0[:,min(hh+10,24)]   # NQ4: every start hour shifted +10 h into the US session

dhi=np.array([H[s:e].max() for s,e in zip(starts,ends)]); dlo=np.array([L[s:e].min() for s,e in zip(starts,ends)])
dop=O[starts]; dcl=C[ends-1]; dA=A[starts]
def sh(x,n=1): r=np.full(len(x),np.nan); r[n:]=x[:-n]; return r
pH,pL,pC,pO=sh(dhi),sh(dlo),sh(dcl),sh(dop)
KT=0.3; SPR=0.0
@njit(cache=True)
def f05(i,px,d,H,L,A,EOD,k):
    a=A[i]*k; e=EOD[i]
    for j in range(i+1,e+1):
        up=H[j]-px if d>0 else px-L[j]; dn=px-L[j] if d>0 else H[j]-px
        if dn>=a and up>=a: return np.nan
        if up>=a: return 1.0
        if dn>=a: return 0.0
    return np.nan
@njit(cache=True)
def first_touch(i0,i1,up,dn,H,L):
    for j in range(i0,i1):
        hu=H[j]>=up; hd=L[j]<=dn
        if hu and hd: return j,0
        if hu: return j,1
        if hd: return j,-1
    return -1,0
per=((2004,2007),(2008,2011),(2012,2015),(2016,2019),(2020,2022),(2023,2026))
def evaluate(E):
    """E: list of (k,j,px,d). returns dict"""
    if len(E)<50: return None
    E=np.array(E,float); k=E[:,0].astype(int); j=E[:,1].astype(int); px=E[:,2]; d=E[:,3]
    acc=np.array([f05(jj,p+SPR*dd,int(dd),H,L,A,EOD,KT) for jj,p,dd in zip(j,px,d)])
    y=dyr[k]; ok=np.isfinite(acc)
    pp=[np.nanmean(acc[ok&(y>=lo)&(y<=hi)])*100 if (ok&(y>=lo)&(y<=hi)).sum()>20 else np.nan for lo,hi in per]
    IS=np.nanmean(acc[ok&(y<=2018)])*100; OOS=np.nanmean(acc[ok&(y>=2019)])*100
    return dict(n=len(k),cov=len(np.unique(k))/NB*100,buy=(d>0).mean()*100,IS=IS,OOS=OOS,all=np.nanmean(acc)*100,mn=np.nanmin(pp),p=np.round(pp,1),days=k,acc=acc,dir=d)
