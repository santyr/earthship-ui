# Forecast Divergence Scoring — Design (v2 increment)

**Date:** 2026-07-19 · **Status:** Approved by Sat (conversation) and deployed.

**North-star goal (Sat):** continuously identify where Open-Meteo forecasts
diverge from the Earthship's measured data, learn from the divergence, and
adjust forecasts and downstream actions so accuracy improves over time.

## What this increment adds (in `~/openhab/scripts/forecast_intel.py`)

Extends the daily 06:40 Phase-1 scorer (which already scores PV kWh and
overnight trough, calibrating `k_res`/`d_direct`):

1. **Precipitation**: yesterday's forecast daily inches (`precip_in`, stored
   at prediction time) vs the rain gauge (`max(AmbientWeatherWS2902A_RainFallDay)`
   over the day — the accumulator resets at midnight). Publishes
   `Forecast_Precip_Error_7d` (rolling mean |err|, inches).
2. **Temperature**: forecast high/low vs measured outdoor extremes from
   persistence. Publishes `Forecast_TempHigh_Error_7d`,
   `Forecast_TempLow_Error_7d` (mean |err| °F) and
   `Forecast_TempHigh_Bias_7d` (mean SIGNED error — the future bias-correction
   input).
3. **Day-3 horizon skill**: each morning stores day+3's forecast (hi,
   precip); when that day's actuals exist, scores them. Publishes
   `Forecast_Day3_High_Error_7d`, `Forecast_Day3_Precip_Error_7d`. Answers
   "how much can we trust 3-day-ahead planning at this site."

All scoring is nil-guarded (missing persistence or pre-v2 predictions skip
silently) and state lives in `~/.local/state/forecast-intel/state.json`
(`precip_errors`, `temp_hi_errors` (signed), `temp_lo_errors`,
`day3_hi_errors`, `day3_precip_errors`, `horizon`). Horizon entries older
than 7 days are pruned.

## Explicitly deferred (future tiers)

Hourly radiation bias curve (pyranometer vs hourly forecast), curtailment
scoring, thermal-advisory outcome verification against the zone
instrumentation, APPLYING bias corrections to displayed/used forecasts, and
UI display of the new error items.

## Versioning note

`~/openhab/scripts/forecast_intel.py` is not under git on the host; a
canonical snapshot is tracked at `openhab/scripts/forecast_intel.py` in this
repo (copy-deployed manually; backups in `~/openhab/backups/`).

## v3a addendum (same day): Kalman bias correction — DEPLOYED

Backfill analysis (364 days) locked the design:
- **Radiation: NO filter.** Bias is proportional (measured/forecast ≈ 0.66,
  stable across quarters; proportional fit residual 0.74 < additive 0.83).
  `k_res` already learns this ratio; an additive filter would double-correct.
- **Temp high**: seasonal drift (−3.9 summer → −1.1 winter) → random-walk
  Kalman, Q=0.05, R=6. Seeded −2.56°F from the last 60 backfill days.
- **Temp low**: +9.5°F warm bias (valley cold pool invisible to the grid
  model), Q=0.10, R=32 — the single largest correction available.

Mechanics: scalar filters in state.json (`kalman.hi/.lo`), innovation = raw
forecast − measured each 06:40 scoring pass (predictions store stays RAW so
learning tracks truth). Corrections applied to `Forecast_Tomorrow_High/Low`
and the thermal-advisory inputs; magnitudes published as
`Forecast_HighCorrection_F` / `Forecast_LowCorrection_F`. Display strips
(hourly/ten-day JSON) intentionally stay raw — hourly-shape correction is
future work. First observable effect on deploy day: corrected tomorrow-high
96.7° (raw 94.1°) flipped the advisory vent_tonight → close_up_tomorrow.

Remaining for v3b (~Aug 2): conformal intervals on trough/PV once enough
post-cutover live days accumulate.
