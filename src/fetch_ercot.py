#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,time
from datetime import date,timedelta
from pathlib import Path
from fetch_ercot_html import fetch,parse

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--out',type=Path,required=True); ap.add_argument('--start',default='2026-04-01'); ap.add_argument('--end',default='2026-04-30'); ap.add_argument('--sleep',type=float,default=.2); a=ap.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
 d=date.fromisoformat(a.start); end=date.fromisoformat(a.end); man=[]
 while d<=end:
  day=d.strftime('%Y%m%d')
  for market,suffix in [('DAM','dam'),('RTM','rtm')]:
   path=a.out/f'{day}_{suffix}.csv'; ent={'day':day,'market':market,'path':str(path),'url':None,'rows':0,'status':'error','error':None}
   try:
    url,src=fetch(day,market); header,rows=parse(src)
    with path.open('w',newline='') as f:
     w=csv.DictWriter(f,fieldnames=header); w.writeheader(); w.writerows(rows)
    ent.update(url=url,rows=len(rows),status='ok')
   except Exception as e:
    ent['error']=f'{type(e).__name__}: {e}'
    if path.exists(): path.unlink()
   man.append(ent); print(ent,flush=True); time.sleep(a.sleep)
  d+=timedelta(days=1)
 (a.out/'fetch_manifest.json').write_text(json.dumps(man,indent=2)+'\n')
if __name__=='__main__': main()
