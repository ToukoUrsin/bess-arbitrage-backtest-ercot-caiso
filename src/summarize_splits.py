#!/usr/bin/env python3
"""Derive all-period and ERCOT RTC+B split scores from a frozen panel."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np


POLICIES = ("pf", "da_tb", "rh_persist", "median7", "dam_rt")
CUT = date.fromisoformat("2025-12-05")


def score(result: dict, keep):
    rows = {}
    for location, traces in result["traces"].items():
        selected = [row for row in traces if keep(date.fromisoformat(row["date"]))]
        rows[location] = {
            "days": len(selected),
            "revenue": {
                policy: float(sum(row["policies"][policy]["revenue"] for row in selected))
                for policy in POLICIES
            },
        }
        pf = rows[location]["revenue"]["pf"]
        rows[location]["capture_pct"] = {
            policy: 100.0 * value / pf if pf else None
            for policy, value in rows[location]["revenue"].items()
        }
        rows[location]["median7_vs_da_pct"] = (
            100.0 * (rows[location]["revenue"]["median7"] / rows[location]["revenue"]["da_tb"] - 1.0)
            if rows[location]["revenue"]["da_tb"] else None
        )
        rows[location]["median7_vs_persist_pct"] = (
            100.0 * (rows[location]["revenue"]["median7"] / rows[location]["revenue"]["rh_persist"] - 1.0)
            if rows[location]["revenue"]["rh_persist"] else None
        )
    eligible = [row for row in rows.values() if row["days"]]
    median_revenue = {
        policy: (float(np.median([row["revenue"][policy] for row in eligible])) if eligible else None)
        for policy in POLICIES
    }
    median_capture_pct = {
        policy: (float(np.median([row["capture_pct"][policy] for row in eligible])) if eligible else None)
        for policy in POLICIES
    }
    return {
        "locations": rows,
        "median_revenue": median_revenue,
        "median_capture_pct": median_capture_pct,
        "median7_gate": bool(eligible) and all(
            median_revenue["median7"] >= 1.10 * median_revenue[baseline]
            for baseline in ("da_tb", "rh_persist")
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.result.read_text())
    payload = {
        "source_result": str(args.result),
        "rtc_b_cut": "2025-12-05",
        "all_scored": score(result, lambda _: True),
        "pre_rtc_b": score(result, lambda d: d < CUT),
        "post_rtc_b": score(result, lambda d: d >= CUT),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({key: value["median_revenue"] for key, value in payload.items() if key in ("all_scored", "pre_rtc_b", "post_rtc_b")}, indent=2))


if __name__ == "__main__":
    main()
