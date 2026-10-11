"""CAISO native 15-minute public energy-only comparator.

The official OASIS node reports are requested per operating day. DAM is hourly
PRC_LMP (v12); realized energy is 15-minute RTPD PRC_RTPD_LMP (v2). The
replay uses the frozen comparator's 100 MWh / 50 MW battery and scores only
complete common days after one causal warm-up day.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from pathlib import Path
from collections import defaultdict
import numpy as np
from scipy.optimize import linprog

POINTS = ("NP15", "SP15", "ZP26")
ETA = np.sqrt(0.90); P = 50.0; E = 100.0; SOC0 = 50.0; DT = 0.25; CAP = 200.0

def _read(path: Path, kind: str):
    """Extract only LMP price rows and key by CAISO operating-day clock."""
    out = {}
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            if r.get("LMP_TYPE") != "LMP" or r.get("XML_DATA_ITEM") != "LMP_PRC":
                continue
            day = r["OPR_DT"]
            if kind == "dam": key = (day, int(r["OPR_HR"]))
            else: key = (day, int(r["OPR_HR"]), int(r["OPR_INTERVAL"]))
            if key in out: raise ValueError(f"duplicate price key {path.name} {key}")
            out[key] = float(r["MW"] if kind == "dam" else r["PRC"])
    return out

def load_panel(data: Path):
    per = {p: {} for p in POINTS}
    for p in POINTS:
        for dp in sorted(data.glob(f"*_{p}_dam.csv")):
            for (d,h), v in _read(dp,"dam").items(): per[p].setdefault(d,{})[('dam',h)] = v
        for rp in sorted(data.glob(f"*_{p}_rt.csv")):
            for (d,h,q), v in _read(rp,"rt").items(): per[p].setdefault(d,{})[('rt',h,q)] = v
    common = sorted(set.intersection(*[set(per[p]) for p in POINTS]))
    complete=[]
    for d in common:
        if all(len([k for k in per[p][d] if k[0]=='dam']) == 24 and
               len([k for k in per[p][d] if k[0]=='rt']) == 96 for p in POINTS):
            complete.append(d)
    if len(complete) < 2: raise ValueError("fewer than two complete common days")
    out={}
    for p in POINTS:
        dam=[]; rt=[]
        for d in complete:
            x=per[p][d]
            dam.append([x[('dam',h)] for h in range(1,25)])
            rt.append([x[('rt',h,q)] for h in range(1,25) for q in range(1,5)])
        out[p]={'dates':complete,'dam':np.asarray(dam,float),'rt':np.asarray(rt,float)}
    return out

def solve(prices, initial=SOC0, final=SOC0, cap=CAP, cm=None, dm=None):
    p=np.asarray(prices,float); n=len(p)
    cm=np.ones(n,bool) if cm is None else np.asarray(cm,bool)
    dm=np.ones(n,bool) if dm is None else np.asarray(dm,bool)
    # The binary converter-direction variable is unnecessary for this linear
    # energy-only objective: simultaneous charge/discharge at one price can be
    # removed without lowering revenue and only increases losses. Dropping it
    # makes the repeated rolling-horizon LP tractable for a month.
    c=np.r_[DT*p,-DT*p,np.zeros(n)]
    eq=[]; er=[]; rows=[]; rhs=[]
    for t in range(n):
        r=np.zeros(3*n); r[2*n+t]=1; b=initial if t==0 else 0
        if t: r[2*n+t-1]=-1
        r[t]=-ETA*DT; r[n+t]=DT/ETA; eq.append(r); er.append(b)
        if not cm[t]: r=np.zeros(3*n); r[t]=1; rows.append(r); rhs.append(0)
        if not dm[t]: r=np.zeros(3*n); r[n+t]=1; rows.append(r); rhs.append(0)
    r=np.zeros(3*n); r[2*n+n-1]=1; eq.append(r); er.append(final)
    r=np.zeros(3*n); r[:2*n]=DT; rows.append(r); rhs.append(max(0.0,cap))
    res=linprog(c,A_ub=np.asarray(rows) if rows else None,b_ub=np.asarray(rhs) if rhs else None,A_eq=np.asarray(eq),b_eq=np.asarray(er),bounds=[(0,P)]*n+[(0,P)]*n+[(0,E)]*n,method='highs')
    if not res.success: raise RuntimeError(res.message)
    return res.x[:n],res.x[n:2*n],res.x[2*n:3*n]

def revenue(price,ch,dis): return float(DT*np.dot(price,np.asarray(dis)-np.asarray(ch)))

def da_tb(prev_dam):
    order=np.argsort(prev_dam,kind='mergesort'); low=set(order[:4]); high=set(order[-4:])
    return np.array([h//4 in low for h in range(96)]), np.array([h//4 in high for h in range(96)])

def rh_persist(prev_rt, cur_rt):
    ch=np.zeros(96); dis=np.zeros(96); soc=np.zeros(96); s=SOC0; used=0.0
    for t in range(96):
        c,d,_=solve(prev_rt[t:],s,SOC0,CAP-used)
        ch[t]=c[0]; dis[t]=d[0]; s=s+ETA*ch[t]*DT-dis[t]*DT/ETA; soc[t]=s; used += DT*(ch[t]+dis[t])
    return ch,dis,soc

def feasible(ch,dis,soc):
    if len(ch)!=96 or np.any(ch < -1e-6) or np.any(dis < -1e-6) or np.any(ch>P+1e-6) or np.any(dis>P+1e-6): return False
    if np.any((np.asarray(ch)>1e-6) & (np.asarray(dis)>1e-6)): return False
    if np.any(soc < -1e-5) or np.any(soc > E+1e-5) or DT*np.sum(ch+dis)>CAP+1e-5: return False
    s=SOC0
    for c,d,z in zip(ch,dis,soc):
        if c>1e-6 and d>1e-6 or abs(z-(s+ETA*c*DT-d*DT/ETA))>1e-5: return False
        s=z
    return abs(soc[-1]-SOC0)<1e-5

def run(data: Path, out: Path):
    panel=load_panel(data); traces={}; metrics={}
    for p,s in panel.items():
        tr=[]
        for i in range(1,len(s['dates'])):
            rt=s['rt'][i]; pfc,pfd,pfs=solve(rt); cm,dm=da_tb(s['dam'][i-1]); dac,dad,das=solve(np.repeat(s['dam'][i-1],4),cm=cm,dm=dm); rhc,rhd,rhs=rh_persist(s['rt'][i-1],rt)
            for name,c,d,z in [('pf',pfc,pfd,pfs),('da_tb',dac,dad,das),('rh_persist',rhc,rhd,rhs)]:
                if not feasible(c,d,z): raise RuntimeError(f'{p}/{s["dates"][i]}/{name} infeasible')
            tr.append({'date':s['dates'][i],'pf':revenue(rt,pfc,pfd),'da_tb':revenue(rt,dac,dad),'rh_persist':revenue(rt,rhc,rhd),'pf_ch':pfc.tolist(),'pf_dis':pfd.tolist(),'pf_soc':pfs.tolist(),'da_ch':dac.tolist(),'da_dis':dad.tolist(),'da_soc':das.tolist(),'rh_ch':rhc.tolist(),'rh_dis':rhd.tolist(),'rh_soc':rhs.tolist()})
        pf=sum(x['pf'] for x in tr); da=sum(x['da_tb'] for x in tr); rh=sum(x['rh_persist'] for x in tr)
        metrics[p]={'n_days':len(tr),'dates':[x['date'] for x in tr],'pf_revenue':pf,'da_tb_revenue':da,'rh_persist_revenue':rh,'da_tb_capture_pct':100*da/pf,'rh_persist_capture_pct':100*rh/pf}
        traces[p]=tr
    d=[metrics[p]['da_tb_capture_pct'] for p in POINTS]; r=[metrics[p]['rh_persist_capture_pct'] for p in POINTS]
    metrics['_summary']={'points':list(POINTS),'complete_common_days':len(next(iter(panel.values()))['dates']),'score_days':len(next(iter(traces.values()))),'median_da_tb_capture_pct':float(np.median(d)),'median_rh_persist_capture_pct':float(np.median(r)),'rh_vs_da_relative_pct':100*(sum(metrics[p]['rh_persist_revenue'] for p in POINTS)/sum(metrics[p]['da_tb_revenue'] for p in POINTS)-1),'source':'CAISO OASIS PRC_LMP v12 and PRC_RTPD_LMP v2; prices keyed by OPR_DT/OPR_HR/OPR_INTERVAL; complete common source days; first day warm-up'}
    obj={'parameters':{'power_mw':P,'energy_mwh':E,'eta_charge':ETA,'eta_discharge':ETA,'initial_soc_mwh':SOC0,'terminal_soc_mwh':SOC0,'interval_hours':DT,'throughput_mwh_day':CAP},'metrics':metrics,'traces':traces}
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(obj,indent=2,sort_keys=True)); return obj

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--data',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args(); print(json.dumps(run(a.data,a.out)['metrics'],indent=2,sort_keys=True))
