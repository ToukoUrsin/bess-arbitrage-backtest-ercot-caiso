from __future__ import annotations
import argparse, csv, hashlib, io, json, time, zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
import requests

NODES = {
    'NP15':'TH_NP15_GEN-APND',
    'SP15':'TH_SP15_GEN-APND',
    'ZP26':'TH_ZP26_GEN-APND',
}
BASE='https://oasis.caiso.com/oasisapi/SingleZip'

def daterange(a,b):
    d=a
    while d<=b:
        yield d; d+=timedelta(days=1)

def fetch_one(day: date, node_name: str, node: str, market: str, out: Path, retries=10):
    # The energy comparator uses DAM hourly LMP and FMM/RTPD 15-minute LMP.
    # RTPD is the public 15-minute forecast/settlement product; RTM 5-minute
    # data is retained only as a separate sensitivity in the charter.
    q = 'PRC_LMP' if market=='dam' else 'PRC_RTPD_LMP'
    run = 'DAM' if market=='dam' else 'RTPD'
    version = '12' if market=='dam' else '2'
    # CAISO OASIS uses GMT; the operating day begins at 07:00 GMT in winter.
    start=f'{day:%Y%m%d}T07:00-0000'; end=f'{(day+timedelta(days=1)):%Y%m%d}T07:00-0000'
    params={'queryname':q,'startdatetime':start,'enddatetime':end,'version':version,'market_run_id':run,'resultformat':'6','node':node}
    path=out/f'{day}_{node_name}_{market}.csv'; side=path.with_suffix('.json')
    if path.exists() and side.exists(): return {'status':'cached','path':str(path)}
    last=''
    for attempt in range(retries):
        try:
            r=requests.get(BASE,params=params,timeout=60)
            if r.status_code==429:
                time.sleep(10.0*(attempt+1)); continue
            r.raise_for_status()
            z=zipfile.ZipFile(io.BytesIO(r.content)); names=z.namelist()
            csvnames=[n for n in names if n.lower().endswith('.csv')]
            if not csvnames:
                raise RuntimeError('no CSV in zip: '+','.join(names))
            raw=z.read(csvnames[0])
            text=raw.decode('utf-8-sig')
            path.write_text(text)
            side.write_text(json.dumps({'url':r.url,'sha256':hashlib.sha256(raw).hexdigest(),'rows':text.count('\n')-1,'zip_member':csvnames[0]},indent=2))
            # Keep a request trace in the sidecar; this makes source scope and
            # product version auditable without retaining duplicate ZIP files.
            return {'status':'ok','path':str(path),'rows':text.count('\n')-1,'url':r.url,'query':q,'version':version}
        except Exception as e:
            last=repr(e); time.sleep(1.0*(attempt+1))
    return {'status':'error','path':str(path),'error':last}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--start',required=True); ap.add_argument('--end',required=True); ap.add_argument('--out',type=Path,required=True); ap.add_argument('--workers',type=int,default=3)
    a=ap.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
    jobs=[(d,nm,node,m) for d in daterange(date.fromisoformat(a.start),date.fromisoformat(a.end)) for nm,node in NODES.items() for m in ('dam','rt')]
    results=[]
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        fs=[ex.submit(fetch_one,d,nm,node,m,a.out) for d,nm,node,m in jobs]
        for i,f in enumerate(as_completed(fs),1):
            r=f.result(); results.append(r); print(i,'/',len(fs),r,flush=True)
    manifest={'start':a.start,'end':a.end,
              'jobs':[[d.isoformat(),nm,node,m] for d,nm,node,m in jobs],
              'results':results}
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True))
    bad=[r for r in results if r.get('status')=='error']
    if bad: raise SystemExit(f'{len(bad)} fetches failed')
if __name__=='__main__': main()
