# Historical model learning and PV calibration

Required scope: retrain and evaluate Earthship thermal models with historical OpenHAB and Google WeatherNext data; identify and implement all other supported beneficial historical retraining cases. Restore daily PV potential and calibrate it against qualified measurements. Preserve original forecasts, separate retrospective experiments from prospective scores, and leave actual actuation disabled.

## Model inventory

| Model or forecast | Historical inputs and targets | Required improvement | Evidence/status |
|---|---|---|---|
| Indoor thermal air and mass | Qualified indoor, wall and outdoor temperature receipts; measured irradiance; operator shade/vent history; historical Google forcing | Refit physical response from measurements; train/evaluate forecast-error correction with historical Google forcing; compare held-out errors and daily/six-hour fitting | Historical pairing and first fresh fits implemented; earlier-cutoff native physics refit completed; later physical-baseline comparison and serving integration pending |
| Outdoor-temperature correction | Historical Google station temperature, original lead times, qualified local outdoor receipts | Chronological bias/residual training and evaluation; daily refresh | Daily live fitting deployed; historical experiments implemented; later qualification and selection pending |
| Solar irradiance correction | Historical Google GHI/direct flux and local station radiation | Fit site-specific correction and analyze hour/season/terrain effects | Required; local station radiation is explicitly a lux-derived proxy, not a calibrated pyranometer |
| PV array potential | Irradiance, native Astro geometry, terrain profile, array declaration, uncensored controller production | Calibrate irradiance and array losses separately; compare with uncalibrated physics on later periods | Ten-day provisional potential deployed; calibration pending |
| Captured PV | Qualified production meters, battery SoC/charging state, AC demand and potential PV | Fit/evaluate acceptance/capture adjustments only for compatible meter scope | Required assessment; curtailment must not be used as an array-efficiency label |
| Household AC demand | Qualified inverter AC history, hourly/daily pattern, recent demand | Retain daily 14-day profile; add hourly residual update and chronological comparison | Required; existing daily profile remains in use |
| Battery/storage SoC trajectory | Qualified SoC, capture and AC demand, nominal bank configuration | Evaluate identifiable capacity/loss/acceptance corrections against hold-SoC/current-power baselines | Required assessment; separate DC overhead, efficiency and usable capacity are not all identifiable from SoC alone |
| Rainfall correction | Historical Google hourly rain and qualified local rain accumulation | Evaluate bias correction against raw Google if supported by completed wet/dry periods | Required assessment; preserve hourly accumulation and missing coverage |
| Wind/site exposure | Historical Google wind and qualified local wind | Assess whether available observations support a useful site correction | Inventory assessment; no invented gust output |
| Shade and ventilation action effects | Actual recorded state transitions and temperature/solar response | Retain known regimes in thermal learning; assess observational support separately from causal effects | Automatic actuation remains disabled; unknown historical states remain unknown |
| Household plan/ranking and outcome comparisons | Retained plans, original source identities, action/constraint/outcome evidence | Recompute applicable comparisons with the retrained forecasts; preserve original scores | No reward/owner/actuation authority inferred from forecast accuracy |

## Current authoritative evidence

- Daily PV physics: 53 Python checks, including DST and retained native geometry; 22 frontend checks cover the GET transport, expiry and actual Home/Weather rendering. Live browser verified ten PV values on both pages. Hourly sidecar is independently frozen and has completed successfully.
- Daily outdoor correction: 34 tests and 17 subtests; installed timer is 06:35 Denver; an actual run fitted 14 completed pairs. Unchanged paired evidence is a no-op.
- Local historical temperature evidence: 28 UTC days, September 20 through October 17. Of 8,092 five-minute targets, indoor air has 8,082 qualified, wall mass 8,052, outdoor 8,083 and bedroom 4,901. Day boundary targets overlap intentionally. Raw originals remain private.
- Older receipts identify the sensor model and hardware ID but lack sensorEpoch. Retrospective capture records that absence; it does not backdate today's hardware epoch.
- Active thermal daily checkpoint is healthy and already trained through October 19 06:00 UTC. An older failed checkpoint belongs to an inactive state directory.

## Historical evidence rules

Google originals are kept in a separate historical archive. Actual retrieval/first-seen clocks remain unchanged. Original metadata, native-cell identity and normalized units are rederived before use. Historical forecasts can train current models and support retrospective chronological tests; they cannot be relabeled as operational forecasts previously served by this host.

Retrospective experiments must record their forecast-availability assumption, train on earlier outcomes, and test on later disjoint issues and targets. Report independent dates and lead-time groups rather than treating overlapping hourly predictions as independent days. Final production artifacts must retain the paired-data and runtime identities, and prospective scores must start from their actual deployment.

## October 19 historical acquisition and first experiments

- Receipt-qualified temperatures: 29 UTC days, September 20–October 18, with exact original receipt versions and hardware identity availability retained.
- Numeric OpenHAB air, wall, outdoor and radiation history: all 291 UTC days January 1–October 18 captured. Older temperature units are inferred against actual recent receipt overlap, not seasonal plausibility. Older numeric values retain unknown hardware health; they never fill gaps in receipt coverage.
- Google recent history: all 116 full-cycle runs (four cycles/day, September 20–October 18) retained independently from operational forecasts. Weekly four-cycle seasonal sampling from January 1 through September 19 is in progress under the same external request/byte/deadline policy.
- First preliminary experiment used only 31 retained runs: air MAE improved from 4.52 C persistence to 2.10 C; outdoor and wall candidates were worse than their respective raw-Google/persistence baselines. None selected live. Larger-history experiments and comparison to the existing physical thermal forecast remain required.
- Native physical model refitted with a strict October 14 cutoff, from October 9 13:10 UTC native evidence, retaining 19 eligible endpoints. No production model selection changed. This supports a later holdout comparison without using weights fitted on the holdout.
- Exact source retention and environment identities now accompany new historical training experiments. Retrospective assumptions never replace actual Google retrieval or model-availability clocks.
- Historical PV-input, captured-PV-output, battery-DC, AC-output and BMS-SoC acquisition is implemented and running in bounded hourly chunks through the restricted read-only account. Invalid receipts remain barriers. A low-SoC charging and sub-clipping selection is explicitly a provisional censoring proxy, not certified unrestricted production.
- Focused acquisition/learning/PV checks: 43 passed, plus two energy-target cases. Existing dependency-light Google environment: 237 unittest cases passed.

PV calibration remains a required active task. The initial directional correction below is ready for provisional short-horizon deployment. Separate irradiance/terrain identification, seasonal validation, downstream same-issue PV/storage integration and prospective full-day monitoring remain incomplete.

## Actual chronological energy comparisons

All 696 UTC energy hours September 20–October 18 have been retained and rederived from original power, AC and BMS receipts. The common split trains before October 14 and assesses later origins through October 19 UTC. No prospective score or original model was overwritten.

| Candidate | Later comparison | Decision |
|---|---|---|
| One effective PV gain | 124 uncensored-proxy intervals on five days: raw physics MAE 560.91 W, candidate 458.29 W | Improvement is uneven by sun direction; do not apply one global multiplier to every day |
| Fixed 45-degree PV sectors, 24-pair shrinkage toward physics | Same retained split: MAE 438.91 W (about 22% lower); raw/adjusted bias +180.29 / -188.27 W | Provisional development candidate; correction limited to next 24 hours; unsupported directions and longer horizons retain physics |
| Hourly AC residual over daily profile | 440 forecasts over five origin dates: daily profile 50.26 W MAE, hourly adjustment 54.73 W, completed-current-hour persistence 104.66 W | Retain existing daily profile; higher fitting frequency has no demonstrated benefit here |
| Apparent battery capacity from signed DC energy/SoC changes | 120 later hours: nominal-capacity SoC-change MAE 0.528 percentage points, learned 0.719 | Retain nominal capacity; no separate capacity/loss/SoC-scale claim |
| Controller input-to-output conversion | 52 later hours: unity conversion MAE 0.02984 kWh, learned conversion 0.00983 kWh | Useful conditional conversion evidence; does not establish battery-acceptance or captured-PV forecast accuracy |

The directional variant was designed after inspecting the initial global comparison. Its later split is a retrospective development assessment, not a fresh independent qualification set. Production monitoring is required. The remaining afternoon subset has slightly worse MAE; the report retains that finding. Model fitting never used those later labels for its earlier coefficients.

The effective PV factors combine forecast irradiance, geometry, array and meter response. These data do not separately identify certified irradiance or array efficiency. The local station radiation remains a lux-derived proxy. Low-SoC charging and sub-clipping thresholds are explicit censoring assumptions, not charge-mode/fault receipts.

The v2 daily potential view retains uncalibrated kWh alongside adjusted values, marks each date's calibration scope, and preserves a read-only, disabled-actuation contract. Receipts retain exact five-minute raw/adjusted prediction steps for prospective scoring. Changing source/model bytes or geometry declarations refuses the correction and falls back to raw physics. An explicitly selected model becomes unavailable after 14 days without refresh; the underlying PV forecast continues.

Seasonal Google acquisition has reached 51 of 152 sampled full cycles. One older cycle lacks one direct-solar and one IMERG precipitation target while temperature/GHI are complete. Explicit training-core mode preserves optional gaps; the strict default remains unchanged. Two-run batches respect the original 75-second external deadline. Acquisition stopped cleanly during a transient shared-pressure event and must resume from retained progress.
