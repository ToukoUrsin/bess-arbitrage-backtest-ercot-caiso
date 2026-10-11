#!/usr/bin/env python3
"""Independent original-input checker for the matched six-location panel."""
from __future__ import annotations
import argparse,csv,hashlib,json
from pathlib import Path
import numpy as np
from scipy.optimize import linprog

DT=.25; P=50.; E=100.; ETA=np.sqrt(.90); S0=50.; CAP=200.
LOC=('HB_HOUSTON','HB_NORTH','HB_WEST','NP15','SP15','ZP26')
CAISO={'NP15':'TH_NP15_GEN-APND','SP15':'TH_SP15_GEN-APND','ZP26':'TH_ZP26_GEN-APND'}

def solve(price,soc0=S0,terminal=S0,cap=CAP,mask=None):
 p=np.asarray(price,float); n=len(p); c=np.r_[DT*p,-DT*p,np.zeros(n)]
 eq=[];rhs=[]
 for t in range(n):
  r=np.zeros(3*n);r[t]=-ETA*DT;r[n+t]=DT/ETA;r[2*n+t]=1
  if t:r[2*n+t-1]=-1;rhs.append(0.)
  else:rhs.append(soc0)
  eq.append(r)
 r=np.zeros(3*n);r[2*n+n-1]=1;eq.append(r);rhs.append(terminal)
 ub=[];ur=[];r=np.zeros(3*n);r[:2*n]=DT;ub.append(r);ur.append(max(0.,cap))
 if mask is not None:
  for t,(allow_c,allow_d) in enumerate(mask):
   if not allow_c:r=np.zeros(3*n);r[t]=1;ub.append(r);ur.append(0.)
   if not allow_d:r=np.zeros(3*n);r[n+t]=1;ub.append(r);ur.append(0.)
 z=linprog(c,A_ub=np.asarray(ub),b_ub=np.asarray(ur),A_eq=np.asarray(eq),b_eq=np.asarray(rhs),bounds=[(0,P)]*(2*n)+[(0,E)]*n,method='highs')
 if not z.success:raise RuntimeError(z.message)
 return z.x[:n],z.x[n:2*n],z.x[2*n:]

def rolling(forecast):
 forecast=np.asarray(forecast,float); ch=[];dis=[];soc=[];s=S0;used=0.
 for t in range(len(forecast)):
  c,d,z=solve(forecast[t:],s,S0,CAP-used);ch.append(c[0]);dis.append(d[0]);soc.append(z[0]);s=z[0];used+=DT*(c[0]+d[0])
 return np.asarray(ch),np.asarray(dis),np.asarray(soc)

def dam_mask(dam):
 order=sorted(range(24),key=lambda i:(float(dam[i]),i)); lo=set(order[:4]);hi=set(order[-4:])
 return [(t//4 in lo,t//4 in hi) for t in range(96)]

def caiso(data):
 out={n:{} for n in CAISO}
 for n,node in CAISO.items():
  dam={};rt={}
  for p in sorted(data.glob(f'*_{n}_dam.csv')):
   for r in csv.DictReader(p.open()):
    if r.get('NODE')==node and r.get('XML_DATA_ITEM')=='LMP_PRC':dam[(r['OPR_DT'],int(r['OPR_HR']))]=float(r['MW'])
  for p in sorted(data.glob(f'*_{n}_rt.csv')):
   for r in csv.DictReader(p.open()):
    if r.get('NODE')==node and r.get('XML_DATA_ITEM')=='LMP_PRC':rt[(r['OPR_DT'],int(r['OPR_HR']),int(r['OPR_INTERVAL']))]=float(r['PRC'])
  dates=sorted(set(d for d,h in dam)&set(d for d,h,q in rt))
  for d in dates:
   if len([1 for x in dam if x[0]==d])==24 and len([1 for x in rt if x[0]==d])==96:
    out[n][d]={'dam':np.array([dam[(d,h)] for h in range(1,25)]),'rt':np.array([rt[(d,h,q)] for h in range(1,25) for q in range(1,5)])}
 return out

def ercot(data):
 out={n:{} for n in LOC[:3]}
 for p in sorted(data.glob('*_dam.csv')):
  q=data/(p.name[:8]+'_rtm.csv')
  if not q.exists():continue
  dr=list(csv.DictReader(p.open()));rr=list(csv.DictReader(q.open()))
  if len(dr)!=24 or len(rr)!=96:continue
  d=dr[0]['Oper Day']; parts=d.split('/'); day=f'{parts[2]}-{parts[0]}-{parts[1]}'
  for n in out:
   out[n][day]={'dam':np.array([float(r[n]) for r in dr]),'rt':np.array([float(r[n]) for r in rr])}
 return out

def check_phys(ch,dis,soc,actual):
 s=S0;used=0.;
 for c,d,z in zip(ch,dis,soc):
  assert -1e-5<=c<=P+1e-5 and -1e-5<=d<=P+1e-5 and -1e-5<=z<=E+1e-5
  assert not(c>1e-5 and d>1e-5)
  assert abs(z-(s+ETA*c*DT-d*DT/ETA))<4e-5
  s=z;used+=DT*(c+d)
 assert abs(s-S0)<4e-5 and used<=CAP+4e-5
 return DT*np.dot(actual,dis-ch)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);ap.add_argument('--ercot',type=Path,required=True);ap.add_argument('--caiso',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 d=json.loads(a.result.read_text()); panel=ercot(a.ercot)|caiso(a.caiso); scope=d['scope']; dates=scope['warmup_dates']+scope['scored_dates']; assert dates==sorted(dates)
 # input hashes bind the retained source rows to the result.
 hashes=d['input_sha256'];
 for p,h in hashes.items(): assert Path(p).exists() and hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,(p,'hash')
 checked=0;regen=0; mut_ok=True; shuffle={}; rng=np.random.default_rng(1729)
 for n in LOC:
  s=panel[n]; assert all(x in s for x in dates),n
  for i,day in enumerate(scope['scored_dates'],7):
   prev=dates[i-1]; actual=s[day]['rt']; dam=s[day]['dam']; pd=s[prev]['dam']; pr=s[prev]['rt']; tr=d['traces'][n][i-7]['policies']
   forecasts={'pf':actual,'da_tb':np.repeat(pd,4),'rh_persist':pr,'median7':np.median(np.array([s[x]['rt'] for x in dates[i-7:i]]),axis=0),'dam_rt':np.repeat(dam,4)}
   masks={'da_tb':dam_mask(pd)}
   for name,x in tr.items():
    ch=np.asarray(x['ch']);di=np.asarray(x['dis']);z=np.asarray(x['soc']); rev=check_phys(ch,di,z,actual);assert abs(rev-x['revenue'])<1e-7*max(1,abs(rev));checked+=1
   # independently regenerate every stored policy from history-only forecasts.
   pc,pd_,pz=solve(actual); dc,dd,dz=solve(np.repeat(pd,4),mask=dam_mask(pd)); rc,rd,rz=rolling(pr); mc,md,mz=rolling(forecasts['median7']); tc,td,tz=rolling(np.repeat(dam,4))
   fresh={'pf':(pc,pd_,pz),'da_tb':(dc,dd,dz),'rh_persist':(rc,rd,rz),'median7':(mc,md,mz),'dam_rt':(tc,td,tz)}
   for name,(ch,di,z) in fresh.items():
    assert abs(check_phys(ch,di,z,actual)-tr[name]['revenue'])<1e-6*max(1,abs(tr[name]['revenue'])),(n,day,name)
    regen+=1
   # mutate target RT prices: all causal forecasts/schedules stay fixed.
   mut=actual.copy();mut[0]+=1777
   fresh2={'da_tb':solve(np.repeat(pd,4),mask=dam_mask(pd)),'rh_persist':rolling(pr),'median7':rolling(forecasts['median7']),'dam_rt':rolling(np.repeat(dam,4))}
   for name,(ch,di,z) in fresh2.items():
    old=fresh[name]; mut_ok &= np.allclose(ch,old[0]) and np.allclose(di,old[1]) and np.allclose(z,old[2])
   # fixed-seed shuffle negative control: PF LP should dominate retained causal actions.
   arr=actual.copy();rng.shuffle(arr);pf=solve(arr);pfr=check_phys(*pf,arr);cr={k:check_phys(np.asarray(v['ch']),np.asarray(v['dis']),np.asarray(v['soc']),arr) for k,v in tr.items() if k!='pf'}
   assert pfr+1e-6>=max(cr.values()),(n,day,pfr,cr)
   shuffle.setdefault(n,0.);shuffle[n]+=1
 out={'status':'PASS','locations':list(LOC),'schedule_traces_checked':checked,'independent_policy_regenerations':regen,'source_hashes_checked':len(hashes),'no_lookahead_mutation':mut_ok,'negative_control_shuffled_days':shuffle,'scored_days':len(scope['scored_dates'])}
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
