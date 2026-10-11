#!/usr/bin/env python3
"""Matched six-location March energy screen, policies fixed before scoring."""
import argparse,csv,hashlib,json,sys
from pathlib import Path
import numpy as np
import caiso_native as c

NODES=('HB_HOUSTON','HB_NORTH','HB_WEST')
def ercot(root):
 out={n:{} for n in NODES}
 for dp in sorted(root.glob('*_dam.csv')):
  rp=root/(dp.name[:8]+'_rtm.csv')
  if not rp.exists(): continue
  dr=list(csv.DictReader(dp.open())); rr=list(csv.DictReader(rp.open()))
  if len(dr)!=24 or len(rr)!=96: continue
  if [int(r['Hour Ending']) for r in dr] != list(range(1,25)): continue
  def minute(x):
   x=int(x);return x//100*60+x%100
  if [minute(r['Interval Ending']) for r in rr] != list(range(15,1441,15)):continue
  ds=dp.name[:8]; date=ds[:4]+'-'+ds[4:6]+'-'+ds[6:]
  for n in NODES:out[n][date]={'dam':np.array([float(r[n]) for r in dr]),'rt':np.array([float(r[n]) for r in rr])}
 return out

def main():
 a=argparse.ArgumentParser();a.add_argument('--ercot',type=Path,required=True);a.add_argument('--caiso',type=Path,required=True);a.add_argument('--out',type=Path,required=True);a=a.parse_args()
 panel=ercot(a.ercot)
 cp=c.load_panel(a.caiso)
 for n,s in cp.items():panel[n]={date:{'dam':s['dam'][i],'rt':s['rt'][i]} for i,date in enumerate(s['dates'])}
 dates=sorted(set.intersection(*(set(s) for s in panel.values())))
 # Seven prior common complete days are required by the candidate at every location.
 scored=dates[7:]; traces={};metrics={}
 for n,s in panel.items():
  tr=[]
  for i,date in enumerate(dates[7:],7):
   rt=s[date]['rt'];prior=s[dates[i-1]]
   forecast=np.median(np.array([s[d]['rt'] for d in dates[i-7:i]]),axis=0)
   cm,dm=c.da_tb(prior['dam'])
   plans={'pf':c.solve(rt),'da_tb':c.solve(np.repeat(prior['dam'],4),cm=cm,dm=dm),'rh_persist':c.rh_persist(prior['rt'],rt),'median7':c.rh_persist(forecast,rt),'dam_rt':c.rh_persist(np.repeat(s[date]['dam'],4),rt)}
   row={'date':date,'history_dates':dates[i-7:i],'policies':{}}
   for name,(ch,dis,soc) in plans.items():
    if not c.feasible(ch,dis,soc):raise RuntimeError(f'{n}/{date}/{name} infeasible')
    row['policies'][name]={'revenue':c.revenue(rt,ch,dis),'ch':ch.tolist(),'dis':dis.tolist(),'soc':soc.tolist()}
   tr.append(row)
  totals={name:sum(x['policies'][name]['revenue'] for x in tr) for name in plans}
  metrics[n]={'days':len(tr),'revenue':totals,'capture_pct':{k:100*v/totals['pf'] for k,v in totals.items()},'median7_vs_da_pct':100*(totals['median7']/totals['da_tb']-1),'median7_vs_persist_pct':100*(totals['median7']/totals['rh_persist']-1)};traces[n]=tr
  print(n,metrics[n],flush=True)
 summary={name:float(np.median([v['capture_pct'][name] for v in metrics.values()])) for name in plans}
 medrev={name:float(np.median([v['revenue'][name] for v in metrics.values()])) for name in plans}
 files=list(a.ercot.glob('*.csv'))+list(a.caiso.glob('*.csv'))
 result={'scope':{'settlement':'15-minute RT SPP / CAISO RTPD LMP; energy-only price taker','scored_dates':scored,'warmup_dates':dates[:7],'excluded_common_date':'2026-03-08','baseline':'four-slot prior-complete-DAM and rolling prior-complete-RT','candidate':'seven-prior-common-day median RT profile, rolling daily-terminal optimizer; no target RT inputs','dam_rt':'target-day DAM as RT forecast sensitivity, known by day start assumed; not DA settlement','publication_availability':'Date-based causal history; original publication timestamps not supplied by historical extracts. Full timestamp audit remains open.'},'metrics':metrics,'median_capture_pct':summary,'median_revenue':medrev,'median7_gate':all(medrev['median7']>=1.1*medrev[k] for k in ('da_tb','rh_persist')),'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'traces':traces}
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,separators=(',',':'))+'\n');print(json.dumps({'median_capture_pct':summary,'median_revenue':medrev,'median7_gate':result['median7_gate']},indent=2))
if __name__=='__main__':main()
