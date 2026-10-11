# Public backtest comparator (v1.1; aligned 2026-10-07)

This is the frozen comparator for the first implementation. It defines what counts as a valid out-of-sample result; it does not claim a revenue result yet.

## Acceptance score

For each ISO and each selected location, report total net market revenue and revenue capture

\[
  100 \times R_{policy}/R_{PF}
\]

where `PF` is the perfect-foresight linear program run on the realized prices in the test interval. The primary acceptance number is the median across the six location series (three ERCOT, three CAISO); also report every series separately and the ISO medians. A policy passes only if all of the following are true on the same input rows and battery parameters:

* median net revenue is at least 1.10 times both the day-ahead top-bottom policy and the rolling-horizon LP with persistence forecasts (the capture percentage is reported separately);
* no location has an infeasible schedule or a failed original-input replay;
* the no-lookahead test and a negative-control shuffled-price test pass.

The test range is `2025-01-01` through the latest complete operating day available at the run date. Missing or repeated-hour rows are excluded only from the affected location/day and are reported. ERCOT is split at `2025-12-05`, the official RTC+B go-live date, and the all-period score is accompanied by pre-RTC+B and post-RTC+B scores. The post-RTC+B subset is the decision-relevant subset for the charter.

## Common battery and settlement model

All policies use one normalized 100 MWh / 50 MW battery, initial and terminal state of charge 50 MWh, state of charge bounds 0--100 MWh, charge and discharge bounds 0--50 MW, and charge/discharge efficiencies `sqrt(0.90)`. The interval length is one hour for DAM and 15 minutes for RTM/FMM. A 1 equivalent-cycle-per-day throughput cap is applied (`sum(charge + discharge) * dt <= 200 MWh` per operating day). Degradation cost is zero for the primary score and a fixed 1 $/MWh throughput sensitivity is reported separately; it is identical for every policy and does not alter feasibility.

For energy, charging is a negative injection and discharging a positive injection. For every interval `t`:

```text
soc[t+1] = soc[t] + eta_c * charge[t] * dt - discharge[t] / eta_d * dt
energy_revenue[t] = (discharge[t] - charge[t]) * energy_price[t] * dt
```

Ancillary capacity is co-optimized where the public source provides a clearing price. Up-reserve consumes `duration * reserve / eta_d` of available SoC and down-reserve consumes `duration * reserve * eta_c` of headroom. Energy plus reserve capacity is bounded by 50 MW. ERCOT uses the five public products `REGUP`, `REGDN`, `RRS`, `NSPIN`, and `ECRS`; CAISO uses `RU`, `RD`, `SR`, and `NR` and the published region price. Reserve duration is the source-market duration field when published; otherwise the conservative one-hour duration is used and recorded in the run manifest. AS revenue is `reserve_MW * MCPC * dt`.

The first implementation must also emit an energy-only score. This isolates an AS parser or settlement discrepancy from the forecasting result. CAISO's public AS reports are regional clearing prices and aggregate procurement/cost rows with no resource, unit, pnode, or award identifier; a price-only AS capacity schedule is therefore a labelled proxy and cannot by itself establish settlement-correct CAISO battery revenue. The acceptance run is not admitted as AS-inclusive until a public award/settlement source is identified or this limitation is explicitly accepted as a charter change.

## Policies compared

* **Perfect foresight LP (`PF`)**: a daily-reset LP on each complete realized operating day, with the same 50 MWh initial/terminal SoC and 200 MWh/day throughput contract as every policy. A full-path PF with only the first/last terminal reset is a separately labelled sensitivity; it is never mixed into the primary denominator.
* **Day-ahead top-bottom (`DA-TB`)**: at the day-ahead gate, use the previous available day’s same-hour price as the forecast, rank the next operating day’s 24 hourly slots using the previous complete day’s DAM profile; permit charging only in the four lowest and discharging only in the four highest hours (stable clock-order ties), expand those masks to the RT/FMM grid, and solve the direction-masked physical optimization on that forecast. It is a deterministic threshold heuristic, not an oracle.
* **Persistence rolling LP (`RH-PERSIST`)**: every 15-minute decision point, forecast each remaining horizon price by the most recently observed price at the same market/hour position, solve the remaining operating-day horizon to the common daily terminal SoC, execute only the first interval, and repeat. The forecast profile is the prior complete day’s RT/FMM profile; target-day settlement prices are not observations for this baseline. The first day is scored only after the required history is available.
* **Candidate policy**: the transparent forecast plus rolling-horizon optimizer from this track. Forecast inputs are timestamped and must be available at the decision timestamp; no realized test price may enter a forecast or optimization objective.

For DAM schedules, the decision timestamp is the prior-day DAM gate and only the prior-day history is allowed. For RTM/FMM schedules, each 15-minute action may use data whose publication timestamp is no later than that interval’s start. Prices from the same interval are settlement inputs only.

## Public input sources and locations

### ERCOT

The official market-price index documents that DAM is daily, RTM is interval-based, and historical SPP/AS products are public: <https://www.ercot.com/mktinfo/prices/>. The historical 2025 files probed on 2026-10-07 were:

| Use | EMIL product | Public product page | 2025 archive content | Location key |
|---|---|---|---|---|
| DAM energy | NP4-180-ER | <https://www.ercot.com/mp/data-products/data-product-details?id=NP4-180-ER> | `DAMLZHBSPP_2025.xlsx`, hourly SPP | `HB_NORTH`, `HB_HOUSTON`, `HB_WEST` |
| RT energy | NP6-785-ER | <https://www.ercot.com/mp/data-products/data-product-details?id=NP6-785-ER> | `RTMLZHBSPP_2025.xlsx`, 15-minute SPP | `HB_NORTH`, `HB_HOUSTON`, `HB_WEST` |
| DAM AS | NP4-181-ER | <https://www.ercot.com/mp/data-products/data-product-details?id=NP4-181-ER> | `DAMASMCPC_2025.csv`, hourly MCPC | `REGUP`, `REGDN`, `RRS`, `NSPIN`, `ECRS` |
| RT AS | NP6-796-ER | <https://www.ercot.com/mp/data-products/data-product-details?id=NP6-796-ER> | `HIST_15Min_RTM_MCPC_2025.xlsx`, 15-minute MCPC | same five AS types |

The all-period ERCOT locations are the three public hubs above. The live 15-minute node/hub/zone product is NP6-905-CD (report type 12301), documented at <https://www.ercot.com/mp/data-products/data-product-details?id=NP6-905-CD>; its public retention is seven days, so the reproducible historical comparator uses NP6-785-ER and the current tail is optionally cross-checked with NP6-905-CD. The ERCOT public API release notes list the historical and RTC+B products: <https://developer.ercot.com/applications/pubapi/relnotes/>.

RTC+B changes are not silently mixed with the old settlement model. ERCOT’s implementation notice dates the first RTC+B operating day to 2025-12-05: <https://www.ercot.com/services/comm/mkt_notices/M-C110525-01>. The settlement formulas and AS imbalance treatment are in the public protocol section 9 and section 6 documents, for example <https://www.ercot.com/files/docs/2025/07/31/August-1-2025-Nodal-Protocols.pdf>.

The 2025 RT-AS archive probe begins on 2025-12-05, matching RTC+B go-live. Therefore the pre-RTC+B comparator is energy-only unless an older ERCOT AS product is found and independently validated; the post-RTC+B score includes RT AS. This is a declared coverage boundary, not an imputed price.

### CAISO

CAISO’s official OASIS FAQ gives the exact API forms and says the API uses GMT. It documents DAM `PRC_LMP`, FMM `PRC_RTPD_LMP`, and 5-minute RTD `PRC_INTVL_LMP`: <https://www.caiso.com/documents/oasis-frequently-asked-questions.pdf>. The three fixed pricing nodes are `TH_NP15_GEN-APND`, `TH_SP15_GEN-APND`, and `TH_ZP26_GEN-APND`.

| Use | OASIS query | Granularity |
|---|---|---|
| DAM energy | `queryname=PRC_LMP&market_run_id=DAM&version=12` | hourly |
| FMM energy | `queryname=PRC_RTPD_LMP&market_run_id=RTPD&version=2` | 15-minute |
| DAM AS | `queryname=PRC_AS&market_run_id=DAM&anc_type=ALL&anc_region=ALL&version=1` | hourly regional clearing price |
| RT AS | `queryname=PRC_INTVL_AS&market_run_id=RTM&anc_type=ALL&anc_region=ALL&version=1` | 15-minute regional clearing price |

The CAISO OASIS specification identifies the AS clearing-price reports and their region/type fields: <https://www.caiso.com/documents/oasisapispecification.pdf>. The historical bulk downloader confirms public price coverage back to 2016, although it requires an AWS account for bulk retrieval; daily OASIS requests are anonymous and are the default source here: <https://oasis-bulk.caiso.com/>.

To keep ancillary revenue comparable across locations, the first score uses the CAISO ISO-wide `AS_CAISO` clearing-price row for all three selected nodes. The region-specific rows are retained in the raw download for sensitivity analysis; if the ISO-wide row is absent for an interval, the AS component is omitted and the energy-only score remains valid.

## Required checks before admitting a result

1. Re-download the exact source URLs from a clean directory and hash the normalized input rows.
2. Verify monotone timestamps, expected 24 hourly DAM rows / 96 RT rows per location-day (with DST flags handled explicitly), finite prices, and no duplicate `(timestamp, location, product)` keys.
3. Run every policy on the original inputs and independently recompute revenue from the emitted schedule; the two totals must agree to 1e-8 relative.
4. Run a no-lookahead audit that truncates each forecast at its decision timestamp and fails if any later source row is read.
5. Run a negative control by shuffling each test-day price series with a fixed seed; PF must remain above the causal policies and the candidate must not retain its claimed uplift.
6. Verify all SoC, power, reserve, terminal-SoC, and daily-throughput constraints from the emitted schedule, including DST days.
7. Report coverage, source revision dates, pre/post-RTC+B splits, per-location revenues, capture percentages, and medians. “Reported” and “reproduced” remain separate from “independently checked” until a second checker passes.

## Alignment of inherited packets

`results/comparator-003/` remains a descriptive January–March ERCOT pool, not the frozen six-location score: its DA-TB implementation uses target-day DAM and eight low/high slots. `worker/worker5-009/` uses hourly averages of five-minute CAISO RT prices and UTC-day cuts, so it is also a separate sensitivity. The new matched run must use the four-slot, prior-DAM and 15-minute native-clock convention above. Existing numbers are not comparable by simply pooling these packets.

At negative prices, a charge/discharge LP relaxation can choose simultaneous charging and discharging. A physical schedule must pass the converter-direction check; where the relaxation does not, a binary-direction solve supplies the executable policy. The LP objective may be reported only as a labelled upper bound, never as a feasible dispatch.
