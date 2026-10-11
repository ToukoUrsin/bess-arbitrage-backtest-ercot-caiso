#!/usr/bin/env python3
"""Pool matched monthly panels without crossing each month's warm-up boundary."""
from __future__ import annotations
import argparse, json, statistics
from pathlib import Path

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument('--panels',nargs='+',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args()
    objs=[json.loads(p.read_text()) for p in a.panels]
    locs=sorted(objs[0]['metrics'])
    assert all(sorted(o['metrics'])==locs for o in objs)
    policies=('pf','da_tb','rh_persist','median7','dam_rt')
    metrics={}
    for loc in locs:
        rev={k:sum(o['metrics'][loc]['revenue'][k] for o in objs) for k in policies}
        metrics[loc]={'days':sum(o['metrics'][loc]['days'] for o in objs),'revenue':rev,'capture_pct':{k:100*rev[k]/rev['pf'] for k in policies}}
    medrev={k:statistics.median(metrics[x]['revenue'][k] for x in locs) for k in policies}
    medcap={k:statistics.median(metrics[x]['capture_pct'][k] for x in locs) for k in policies}
    out={'scope':f"matched monthly panels: {len(a.panels)} inputs; each month retains its own causal warm-up",'source_panels':[str(p) for p in a.panels],'metrics':metrics,'median_revenue':medrev,'median_capture_pct':medcap,'candidate_vs_da_tb_pct':100*(medrev['median7']/medrev['da_tb']-1),'candidate_vs_persist_pct':100*(medrev['median7']/medrev['rh_persist']-1),'candidate_vs_same_day_dam_forecast_pct':100*(medrev['median7']/medrev['dam_rt']-1),'gate':all(medrev['median7']>=1.10*medrev[k] for k in ('da_tb','rh_persist'))}
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps(out,indent=2))
if __name__=='__main__': main()
