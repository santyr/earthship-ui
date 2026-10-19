# Historical model learning and PV calibration

Required scope: retrain and evaluate Earthship thermal models with historical OpenHAB and Google WeatherNext data; identify and implement all other supported beneficial historical retraining cases. Restore daily PV potential and calibrate it against qualified measurements. Preserve original forecasts, separate retrospective experiments from prospective scores, and leave actual actuation disabled.

## Model inventory

| Model or forecast | Historical inputs and targets | Required improvement | Evidence/status |
|---|---|---|---|
| Indoor thermal air and mass | Qualified indoor, wall and outdoor temperature receipts; measured irradiance; operator shade/vent history; historical Google forcing | Refit physical response from measurements; train/evaluate forecast-error correction with historical Google forcing; compare held-out errors and daily/six-hour fitting | Required; historical temperature capture complete, pairing/training pending |
| Outdoor-temperature correction | Historical Google station temperature, original lead times, qualified local outdoor receipts | Chronological bias/residual training and evaluation; daily refresh | Daily live fitting deployed; historical fitting pending |
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
