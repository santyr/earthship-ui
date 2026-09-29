# Prediction learning review — September 29, 2026

This is an origin-aware design review, not a new control or model release.
Keep `forecast-intel`'s 06:40 as-issued record, the separate display-only
pre-dusk issue, and the qualified Energy/Thermal evidence boundaries intact.
No Hexmem task is used as an authority for this review.

## What the available data says about charge timing

The 06:40 `Forecast_10Day_JSON` JDBC archive retains hourly Open-Meteo
radiation *as issued*. The restricted `BMS_SOC_Evidence_JSON` Item 613 stores
source-bound SoC receipts. The September 20–28 local-day diagnostic found
seven first readings at 100% and two days without one before 19:00. The first
100% readings ranged from 10:17 to 13:58 MDT. This is only nine complete
late-September days, not a seasonally representative training set.

| Local date | 06:40 SoC | 06:40 forecast radiation, kWh/m² | First 100% | SoC near 19:00 |
| --- | ---: | ---: | --- | ---: |
| Sep 20 | 86% | 6.27 | 10:17 | 98% |
| Sep 21 | 85% | 5.76 | 10:25 | 97% |
| Sep 22 | 85% | 5.58 | 10:30 | 97% |
| Sep 23 | 85% | 2.68 | 12:42 | 98% |
| Sep 24 | 85% | 2.17 | not observed | 93% |
| Sep 25 | 79% | 4.12 | 13:58 | 97% |
| Sep 26 | 85% | 5.61 | 10:23 | 98% |
| Sep 27 | 86% | 4.94 | 10:37 | 94% |
| Sep 28 | 81% | 1.48 | not observed | 85% |

The low-radiation no-full days suggest a useful relationship, but neither a
threshold nor a causal effect has been established. Sep 23 reached full with
only 2.68 kWh/m² forecast; Sep 25 started at lower SoC and reached full much
later. An observed first 100% is not a dusk SoC: after reaching full, these
days ended 2–6 points lower near 19:00. September 29 was still in progress at
the review: its 06:40 SoC was 72%, forecast radiation 4.12 kWh/m², and first
100% receipt appeared at 12:34 MDT. It is not a completed-day outcome.

An eight-night restricted read-only replay of the existing qualified
20:00-to-trough assessor found actual start-to-minimum declines of 12–15
percentage points with 99.85–99.99% source-bound coverage. The morning
forecast currently uses `99 - minimum` as a proxy; that is 15–29 points on
these same nights and systematically includes the difference between an
assumed 99% start and the *actual* 20:00 start (83–97%). This helps explain
low morning predictions. Do not simply substitute the smaller true overnight
drop into the pre-dusk model: additional discharge between its sunset-minus-75
origin and 20:00 must then be predicted separately. On the four-night
pre-dusk counterfactual, the frozen proxy achieved 2.5-point MAE and an
unadjusted true-night-drop substitution achieved about 3.0 points; neither
is yet a seasonal release result.

`SkyCondition` is a derived ratio of observed to theoretical solar radiation,
not a separate independent sensor named `is_sunny`. Treat it as a quality-
gated sky-regime feature, not independent corroboration of irradiance. Raw
solar-radiation history is available; source freshness and gaps must be
qualified before training or using it in a control-adjacent decision.
As a diagnostic only, a 120-second-gap-bounded integration of the persisted
07:00–19:00 radiation series covered 94.0–99.5% of each September 20–28 day.
The two no-full days accumulated about 1.34 and 0.63 kWh/m²; the seven
full-charge days ranged about 1.98–4.42 kWh/m². These are measured irradiance
integrals, **not** qualified MPPT energy or independent `is_sunny` labels.
Persisted dated Astro events also give actual sunrise-to-sunset length, from
732.4 minutes on September 20 to 712.6 on September 28. That 19.8-minute
range is too narrow to estimate a seasonal day-length effect from this sample.

## Prioritized model improvements

1. **SoC and full-charge timing.** At each issue origin, retain current atomic
   SoC, battery epoch, hourly forecast radiation curve, daylight length and
   sun angle, recent qualified PV input power, qualified AC/inverter load and
   relevant auxiliary/charging states. First predict the probability of
   reaching full *today*, then a time interval conditional on reaching it.
   Days that never reach full are censored outcomes, not missing rows or a
   fabricated 19:00 charge time. Fit a simple regularized energy-balance or
   survival baseline before a larger ML model, and score chronologically
   against constant-clock and radiation-only baselines.
2. **Afternoon and overnight SoC.** Learn the trajectory *after* first full
   separately from the charge-to-full trajectory, using remaining forecast
   radiation, observed PV, qualified household load, controller/curtailment
   state and time until sunset. Keep the near-dusk fresh-SoC issue as the final
   display estimate even if an earlier full-charge milestone produces a
   provisional one. Replace the current `99 - night minimum` overnight-drop
   proxy only after measured start-to-trough drops have enough qualified
   nights across weather and seasons. Score morning, post-full, pre-dusk and
   actual trough origins separately; publish calibrated intervals only when
   their held-out coverage is demonstrated.
3. **PV and curtailment.** Calibrate the *hourly* irradiance-to-available-PV
   relationship against source-bound MPPT input power, with sun geometry,
   temperature, cloud/sky regime and seasonal effects. Actual harvested PV
   after a full battery may be demand-limited, so daily PV kWh alone is not
   solar potential. Keep the current qualified-PV calibration release gate
   closed until complete days and recovery cases pass. Distinguish available,
   harvested and curtailed energy before training a curtailment predictor.
   Forecast harvest and the SoC path jointly in an hourly energy balance:
   available PV is weather/season dependent, but accepted PV is bounded by
   simultaneous load and battery charge headroom. Feed an updated observed
   SoC/PV-so-far into a *remaining-day* revision, not a circular independent
   "predicted SoC" feature that was itself calculated from predicted PV.
4. **Weather and indoor thermal forecasts.** Preserve immutable Open-Meteo
   issue/target pairs and the existing qualified hourly/daily temperature
   scoring. Evaluate lead-time, hour-of-day, season and sky-specific residuals
   before increasing model complexity. The thermal model already has air,
   mass, glazing, outdoor temperature, radiation and action/shade histories;
   add actual zone temperatures and shade positions as hardware arrives.
   Intervention labels must be observed or confirmed, not inferred from a
   model's own predictions. Keep thermal advice in shadow until chronological
   outcomes and action-confirmation gates pass.
5. **Rain, wind and other targets.** The forecast archive contains hourly
   precipitation, wind and weather codes, but a learned correction needs a
   source-qualified observed target, an explicit consumer, and enough
   scored events. Do not fit rain or wind merely because a forecast field is
   present. Air quality and Bitcoin price are display data here, not current
   Earthship control-prediction targets.

## Runtime and learning policy

Keep data capture and prediction issuance separate from training. A light
check can react to a fresh full-charge milestone or material weather update,
but heavy inference should run only when new information can change the
answer; always retain an Astro-relative pre-dusk fallback. The current
half-hourly check performs only a sunset read outside its 60–90-minute gate.
Do not move the live issue time based on nine late-September days. Prefer
user-level systemd services/timers for new observational workers; reserve
system-level units and elevated writes for capabilities that actually need
them.

Use the existing immutable forecast-snapshot and qualified feature-grid
infrastructure where possible. Join only features available by each issue
time to later outcomes, preserve source expiry and coverage gaps, and split
validation chronologically by day/season. Publish a new model only after it
beats the current morning and pre-dusk baselines on the same qualified days
and is calibrated for both full/no-full and low-trough cases. Prefer
incremental sufficient statistics and bounded recent-window refits to daily
full-history retraining; measure runtime and memory as part of each release.

The current 06:40 PV formula already includes morning SoC in
`demand = d_direct + charge_deficit`, then issues
`min(radiation_resource, demand)`. Its September 25–29 persisted origins all
have `radiation_resource < demand`, so their published PV estimates are
**insensitive to SoC** despite the headroom term. The radiation gain `k_res`
is at its configured 1.3 ceiling. For example, September 25 issued 5.36 kWh
at SoC 79% versus a later diagnostic numeric PV-day maximum 8.282 kWh;
September 26 issued 7.30 at SoC 85% versus 8.298. September 29 had already
exceeded its 5.36-kWh issue by 13:20. These maxima are legacy/change-only or
incomplete-day diagnostics, not calibration labels. The source-bound PV-day
stream began partway through September 28, and the qualified calibration
release flag remains false. The next model evaluation should decompose
resource error, load/headroom error, and foregone generation before changing
either the coefficient limit or production forecast.
An exploratory chronological fit of this same capped formula on September
20–24 diagnostic numeric PV-day maxima, using only 06:40 SoC and radiation,
selected `k_res=2.45` and `d_direct=4.1`. On the four held-out September
25–28 days, absolute error averaged 0.639 kWh/day versus 1.269 for the
actual as-issued forecasts. This is a useful *shadow benchmark*, not
permission to deploy those coefficients: both the training labels and
holdout labels predate a complete source-bound PV day, the five-day fit is
fragile, and cloudy/seasonal/fault regimes are underrepresented.

## Cross-pipeline forecast-versus-actual tuning queue

For each target, compare the forecast *as it existed at issue time* with a
later qualified observation. Record exact local target windows, origin,
source/epoch identity and coverage. Diagnose error by forecast lead, weather
regime and season, then test the smallest candidate correction on a
chronological holdout against current production and persistence baselines.
This comparison is the algorithm-tuning loop, not a separate report-only task.

| Target | Existing issue/outcome evidence | Current divergence or missing gate |
| --- | --- | --- |
| Harvested PV kWh | 06:40 origin plus archived hourly radiation; native PV-day receipts start Sep 28 | Recent morning underprediction is evident diagnostically; no complete qualified PV day or coefficient release yet. Separate solar potential from demand-limited harvest. |
| Full-charge time and overnight SoC trough | Atomic BMS receipts and completed-night assessor; morning and new pre-dusk origins | Seven of nine completed days reached full, with afternoon decline afterward. Morning trough is low; pre-dusk natural outcomes and seasonal holdout are due. |
| Outdoor daily and hourly temperatures | Immutable corrected forecasts plus qualified temperature receipts and hourly scoring | Compare corrections as issued by lead/hour/season; never score today's bias against yesterday's forecast. |
| Indoor temperature / thermal trajectory | Shadow artifacts, weather forcing capture, qualified temperature and action history | Latest accepted 24-hour air MAE 2.179°F versus 1.690°F persistence; zero confirmed-action rows. Diagnose forcing/action regimes before shadow exit. |
| Rain and wind | Hourly forecast fields exist; new rain source receipts collect naturally | Rain complete-day scoring is gated by receiver quality; wind lacks a qualified outcome and an approved consumer. |
| Curtailment and load | Forecast curtailment issue, MPPT/AC/switch evidence and operator-confirmed inverter-only topology | Physical curtailment and complete-day load attribution remain unqualified; do not call predicted hours observed. |
| Shades and zone heating/cooling | Action/shade history schema and future 27-slot UI | Hardware and per-zone position/temperature receipts are not yet installed; retain observational/shadow design only. |

The existing immutable Energy forecast snapshots and OpenHAB prediction
receipts are the preferred origin sources. A correction that improves a sunny
week but fails cloudy, no-full, cold-season or missing-sensor days is not a
qualified production improvement. These rows are open tuning work, not
claims that every comparison or fix has already been completed.

The Energy PV card now reads the immutable current-day prediction receipt,
not the 10-day payload whose weather refresh can carry the frozen morning PV
estimate. Before the receipt it says the morning forecast is unavailable;
after actual PV exceeds that issue, it says so rather than presenting an
impossible `actual of predicted` comparison. The 10-day PV outlook remains
visible. This presentation change does not recalibrate or revise PV kWh.
