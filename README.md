# Battery energy-arbitrage backtest on public ERCOT and CAISO prices (9 months, 6 locations)

An out-of-sample backtest of a simple causal bidding policy for a 100 MWh / 50 MW battery
(90% round-trip, 1 cycle/day, energy only, price-taker) on official public prices at three ERCOT
hubs (HB_HOUSTON, HB_NORTH, HB_WEST; 15-minute RT SPP) and three CAISO trading hubs (NP15, SP15,
ZP26; 15-minute RTPD LMP). The frozen comparator and battery model are in `COMPARATOR.md`.

Policies, all re-solved with the same LP and the same daily terminal state of charge:
- **PF** – perfect foresight on realized prices (the denominator for capture %).
- **DA-TB** – charge in the 4 cheapest / discharge in the 4 dearest hours of the previous day's DAM.
- **RH-PERSIST** – rolling-horizon LP every 15 min with yesterday's RT profile as the forecast.
- **candidate (median7)** – the same rolling-horizon LP with the median RT profile of the previous
  7 complete days as the forecast. No same-day prices are used.
- **same-day DAM** – rolling LP using today's DAM as the forecast (a sensitivity: it uses
  information published the day before, which the candidate does not).

## Result: 259 scored days per location (May–Aug 2025 and Mar–Jul 2026)

Net energy revenue in $ (sum over scored days):

| location | days | PF | DA-TB | RH-PERSIST | candidate | same-day DAM | cand. vs DA-TB | cand. vs PERSIST |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| HB_HOUSTON | 259 | 1,485,770 | 492,087 | 646,864 | 805,479 | 875,395 | +63.7% | +24.5% |
| HB_NORTH | 259 | 1,481,993 | 560,863 | 687,707 | 861,348 | 951,292 | +53.6% | +25.2% |
| HB_WEST | 259 | 1,581,804 | 546,289 | 680,257 | 803,631 | 1,034,229 | +47.1% | +18.1% |
| NP15 | 259 | 950,127 | 399,798 | 565,299 | 578,992 | 582,598 | +44.8% | +2.4% |
| SP15 | 259 | 1,104,406 | 539,901 | 771,812 | 808,833 | 774,054 | +49.8% | +4.8% |
| ZP26 | 259 | 1,050,336 | 514,968 | 752,773 | 777,182 | 730,814 | +50.9% | +3.2% |
| **median of 6** | 259 | 1,293,200 | 527,435 | 683,982 | 804,555 | 824,724 | **+52.5%** | **+17.6%** |

The median-of-six candidate revenue is 1.525x DA-TB and 1.176x RH-PERSIST, so it clears the
comparator's 1.10x gate against both weak baselines, at 59.5% of perfect foresight. It is 2.4% below
the same-day-DAM sensitivity. The gain is concentrated in ERCOT (+18% to +25% vs persistence);
the three CAISO hubs are only +2% to +5%, and July 2026 alone fails the persistence gate (-4.7%).

- May–Aug 2025 (`results/2025-05_2025-08/`): fresh fetch of 260 ERCOT and 780 CAISO daily files,
  123 scored days; candidate +55.9% vs DA-TB, +10.5% vs persistence, -1.5% vs same-day DAM.
  Independent checker: 3,690 schedule replays and 3,690 independent policy regenerations, 1,040
  source hashes, a no-lookahead mutation test and shuffled-day negative controls all pass.
- Mar–Jul 2026 (`results/2026-03_2026-07/`): five monthly panels, 136 scored days, each with its
  own 7-day warm-up and its own independent checker run.
- `results/pooled-9-months.json` pools them per location (`src/pool_matched.py`).

## Scope

Nine of the nineteen months in 2025-01..2026-07 are covered; Jan–Apr and Sep 2025–Feb 2026 are not
yet scored (CAISO OASIS rate limits stopped those fetches). Energy only: no ancillary services, no
degradation cost, perfect execution at the settlement price, and no publication-time check beyond
using only prior complete operating days. This is a backtest of public prices, not a trading
record.

Reproduce one segment: `bash run_segment.sh 2025-04-24 2025-08-31 s2` (Python 3.12, `requests`,
`numpy`, `scipy`); it fetches the official ERCOT SPP pages and CAISO OASIS data, runs
`src/matched_month.py` and `src/verify_matched.py`.
