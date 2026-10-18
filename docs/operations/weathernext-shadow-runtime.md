# WeatherNext prospective shadow runtime

Implementation date: 2026-10-18. The [private backend](2026-10-18-weathernext-shadow-activation.md) uses tested commit f5775f8; the separate [comparison activation](2026-10-18-weathernext-comparison-activation.md) adds the narrow live UI patch and Item publication: hourly collection, hourly retained shadow inference/publication and separate weekly candidate training. Three unlinked file-owned Items and the live Weather comparison UI are active. The first fresh Google/local candidate has one qualified pair, SHADOW_ONLY status and no validation; prospective skill/reliability remain unqualified. Household production forecasts, notifications and actuators are unchanged. The 19:40:31Z natural published trigger is verified against its retained issue and all three live Item states.

## Data and state flow

1. The separate bounded collector writes original WeatherNext snapshots to the private archive.
2. Hourly `local_forecast_shadow.py` selects a fresh, complete snapshot for the authoritative site. It loads a previously fitted candidate, never fits during inference, retains the original decision and outputs, then optionally publishes three shadow Item states.
3. Weekly `local_forecast_train.py` reads those retained original decisions and the existing qualified native outdoor-temperature reader. It fits a fresh Google/local bias or residual candidate and atomically advances a private model-receipt pointer only after successful fitting. Missing labels leave the previous candidate intact.

Private model receipts bind model bytes and actual fit-completion time. Each original issue retains its decision/completion times, source snapshot, sensor epoch, serving revision and any separately captured incumbent control. Source, model and epoch mismatches refuse local-model use; fresh raw Google forecasts can remain visible with the local candidate explicitly unavailable. Missing/stale source produces an unavailable view without inventing zero values.

The training policy is fixed before outcomes: select the earliest retained issue per local calendar date, then native future-hour positions 1–24, 36, 48, 60, 72, and every 24 hours from 96 through 360 where retained. At most 40 targets/date across at most 366 dates remains below the existing 20,000-pair artifact bound. Default fitting looks back 90 elapsed days. Daily issues are ranked before applying the rolling lower bound: a partial oldest date is omitted if its original first issue falls outside the window; a later issue never replaces it. If the maximum 366-day interval touches 367 local dates, retain the latest 366 original daily decisions. Labels are selected in bounded UTC-day batches through the existing native reader; missing labels cannot cause selection of a different/easier original issue. This policy is candidate research, not a declaration that full release evidence exists.

Model and issue objects are immutable, private and content-addressed; candidate pointer updates use write/fsync/rename. The separate training/inference locks prevent duplicate owners without making inference wait on fitting. State accounting refuses at 10,000 objects / 2 GiB or inadequate free disk; it does not silently delete source evidence. The collector archive has its separately documented limits.

## Publication and UI

Only `Forecast_Local_Shadow_JSON`, `Forecast_Comparison_JSON` and `Forecast_Provider_Status_JSON` may be published. They contain the same closed, bounded, sealed generation; source status is written last. The UI requires all three states to match, so interrupted publication is unavailable rather than mixed data. No Item commands, rule execution or actuator API exists in this publisher.

The Weather page exposes the comparison only after at least one shadow Item exists. The read-only dialog keeps corrected Open-Meteo, raw WeatherNext and local candidate temperatures distinct, shows source-run age, decision time, training support and forecast horizon, and explicitly states that validation is unavailable and candidates are not qualified. Stale/disconnected/incomplete data hides forecast values. No generic confidence percentage is generated. Existing weather-grid dimensions are unchanged.

The optional incumbent capture reads the existing corrected `Forecast_10Day_JSON` Item, retaining the actual observation time and original state. It is a separate pre-cutover control, never a new-model fitting input. Remove `weather_learning/incumbent.py`, the CLI/service `--include-incumbent` path and incumbent UI column at provider retirement; preserve only detached historical control records.

## Entry points and deployment inputs

`local_forecast_shadow.py` defaults to local shadow recording; `--publish` is explicit. `local_forecast_train.py` defaults to dry-run fitting; `--apply` explicitly installs a validated private candidate. `--algorithm residual` selects the regularized candidate; bias is the initial default. Both use the existing shared RAM admission/CPU/memory/swap/task/deadline launcher when scheduled.

The service templates read private `~/.config/earthship-weather/runtime.env`, now installed for the backend-only activation. Deployment supplies:

- `EARTHSHIP_WEATHER_CODE_ROOT`: isolated immutable deployment source directory.
- `EARTHSHIP_WEATHER_PYTHON`: tested isolated Python executable.
- `EARTHSHIP_WEATHER_CODE_REVISION`: pinned source commit used by that deployment; this is a recorded deployment assertion, not a substitute for verifying the deployed files.
- `EARTHSHIP_WEATHER_ARCHIVE`: private collector archive.
- `EARTHSHIP_WEATHER_SHADOW_STATE`: private model/issue state outside Git and browser-served directories.
- `EARTHSHIP_WEATHER_TEMPERATURE_POLICY`: existing native outdoor policy with the current hardware epoch.
- `EARTHSHIP_WEATHER_TEMPERATURE_DB_CONFIG`: existing dedicated read-only `weather_temperature_reader` JSON config.

Reuse the installed qualified reader/policy; do not create a new authority or request broader database grants. Credentials remain in private configuration and are never included in Item payloads or CLI error output.

The proposed order is collector at :35, shadow at :40 and weekly candidate training Sunday 06:50. The backend-only deployment now passes native point/full-horizon capture, immutable-source and installed-run checks; its three timers are active. The three unlinked Items are installed, ownership is verified, and the local-recording override was removed. Explicit publication and live browser checks pass; the first natural matching published trigger also passed at 19:40:31Z, with identical retained/live generations. Natural timer execution is tracked separately from manual service qualification. Recovery rehearsals remain deferred.

## Remaining work

The first real WeatherNext/local candidate exists with one pair; no qualified predictive skill, completed prospective reliability interval, untouched holdout report or production cutover is established. Source/epoch inventory, required-variable/downstream qualification, production-provider replacement and complete Open-Meteo removal remain separate unfinished plan requirements. This implementation has no promotion or equipment-control authority.
