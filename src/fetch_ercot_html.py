#!/usr/bin/env python3
"""Download a dated ERCOT public SPP display and normalize its HTML table."""
from __future__ import annotations
import argparse, csv, html, re, urllib.request
from pathlib import Path

def fetch(day, market):
    suffix = "real_time_spp" if market == "RTM" else "dam_spp"
    url = f"https://www.ercot.com/content/cdr/html/{day}_{suffix}.html"
    req = urllib.request.Request(url, headers={"User-Agent": "bess-bidding-backtest/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r: return url, r.read().decode("utf-8", "replace")

def parse(src):
    tables = re.findall(r"<table[^>]*>(.*?)</table>", src, flags=re.I | re.S)
    if not tables: raise RuntimeError("no table in ERCOT display")
    table = tables[-1]
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, flags=re.I | re.S)
    clean = lambda x: html.unescape(re.sub(r"<[^>]+>", "", x)).strip()
    parsed = [[clean(x) for x in re.findall(r"<(?:td|th)[^>]*>(.*?)</(?:td|th)>", row, flags=re.I|re.S)] for row in rows]
    parsed = [r for r in parsed if r]
    header = parsed[0]
    if not {"Oper Day", "HB_HOUSTON"}.issubset(header): raise RuntimeError(f"unexpected columns: {header[:5]}")
    return header, [dict(zip(header, r)) for r in parsed[1:] if len(r) == len(header)]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--day", required=True, help="YYYYMMDD"); ap.add_argument("--market", choices=["DAM","RTM"], default="RTM"); ap.add_argument("--out",required=True); a=ap.parse_args()
    url, src=fetch(a.day,a.market); h,rows=parse(src)
    with open(a.out,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=h); w.writeheader(); w.writerows(rows)
    print(f"url={url} rows={len(rows)} out={a.out}")
if __name__ == "__main__": main()
