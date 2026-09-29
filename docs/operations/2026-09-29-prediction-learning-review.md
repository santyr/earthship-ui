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

`SkyCondition` is a derived ratio of observed to theoretical solar radiation,
not a separate independent sensor named `is_sunny`. Treat it as a quality-
gated sky-regime feature, not independent corroboration of irradiance. Raw
solar-radiation history is available; source freshness and gaps must be
qualified before training or using it in a control-adjacent decision.

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
