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
