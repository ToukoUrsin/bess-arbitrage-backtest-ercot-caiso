#!/usr/bin/env python3
"""Run the frozen matched six-location April 2026 energy panel."""
import argparse,json,hashlib,csv
from pathlib import Path
import numpy as np
import caiso_native as c
from matched_panel import ercot,NODES

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--ercot',type=Path,required=True); ap.add_argument('--caiso',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args()
 panel=ercot(a.ercot); cp=c.load_panel(a.caiso)
 for n,s in cp.items(): panel[n]={d:{'dam':s['dam'][i],'rt':s['rt'][i]} for i,d in enumerate(s['dates'])}
 dates=sorted(set.intersection(*(set(s) for s in panel.values())))
 if len(dates)<8: raise RuntimeError(f'only {len(dates)} common days')
 scored=dates[7:]; traces={}; metrics={}
 for n,s in panel.items():
  tr=[]
  for i,d in enumerate(scored,7):
   rt=s[d]['rt']; prev=s[dates[i-1]]; forecast=np.median(np.array([s[x]['rt'] for x in dates[i-7:i]]),axis=0); cm,dm=c.da_tb(prev['dam'])
   plans={'pf':c.solve(rt),'da_tb':c.solve(np.repeat(prev['dam'],4),cm=cm,dm=dm),'rh_persist':c.rh_persist(prev['rt'],rt),'median7':c.rh_persist(forecast,rt),'dam_rt':c.rh_persist(np.repeat(s[d]['dam'],4),rt)}
   row={'date':d,'history_dates':dates[i-7:i],'policies':{}}
   for name,(ch,dis,soc) in plans.items():
    if not c.feasible(ch,dis,soc): raise RuntimeError(f'{n}/{d}/{name} infeasible')
    row['policies'][name]={'revenue':c.revenue(rt,ch,dis),'ch':ch.tolist(),'dis':dis.tolist(),'soc':soc.tolist()}
   tr.append(row)
  totals={k:sum(x['policies'][k]['revenue'] for x in tr) for k in plans}; metrics[n]={'days':len(tr),'revenue':totals,'capture_pct':{k:100*v/totals['pf'] for k,v in totals.items()},'median7_vs_da_pct':100*(totals['median7']/totals['da_tb']-1),'median7_vs_persist_pct':100*(totals['median7']/totals['rh_persist']-1)}; traces[n]=tr; print(n,metrics[n],flush=True)
 summary={k:float(np.median([v['capture_pct'][k] for v in metrics.values()])) for k in plans}; medrev={k:float(np.median([v['revenue'][k] for v in metrics.values()])) for k in plans}
 files=list(a.ercot.glob('*.csv'))+list(a.caiso.glob('*.csv'))
 out={'scope':{'settlement':'15-minute RT SPP / CAISO RTPD LMP; energy-only price taker','scored_dates':scored,'warmup_dates':dates[:7],'candidate':'seven-prior-common-day median RT/FMM profile, rolling daily-terminal optimizer; no target RT inputs','baseline':'four-slot prior-complete-DAM and rolling prior-complete-RT','publication_availability':'Date-based causal history; historical extracts do not supply publication timestamps.'},'metrics':metrics,'median_capture_pct':summary,'median_revenue':medrev,'median7_gate':all(medrev['median7']>=1.1*medrev[k] for k in ('da_tb','rh_persist')),'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'traces':traces}
 a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(out,separators=(',',':'))+'\n'); print(json.dumps({'median_capture_pct':summary,'median_revenue':medrev,'median7_gate':out['median7_gate']},indent=2))
if __name__=='__main__': main()
