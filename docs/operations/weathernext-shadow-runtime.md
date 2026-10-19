# WeatherNext prospective shadow runtime

Implementation date: 2026-10-18; v2 activated 2026-10-19 at **03:18:48 MDT**.
Shadow inference and weekly training now select immutable source
`59c0b81d20bcd3f33d1d26f4c19768e441b5752f`. Its 1,995 source files were verified
against committed Git blobs and made read-only. The collector retains its
separate 8be69ea source pin. The three shadow Items and matching live UI now use
the Google-only v2 contract. Its first fresh candidate now has **one qualified
Google/local pair**, SHADOW_ONLY status and no validation claim. Household
production forecast ownership, notifications and actuators remain unchanged.

## Installed v2 cohort

The producer publishes `earthship-weather-provider-shadow/v2`, retains
`earthship-weather-shadow-issue/v2`, and shows raw WeatherNext versus a local
candidate in the read-only model/status dialog. Both inference and fitting use
the fresh `google-local-v2` child of the configured shadow-state root. They open
the collector archive read-only. A missing source stays explicitly unavailable
without creating collector history; only the collector initializes/writes it.
No incumbent issue, fitted candidate, error history or bias is imported.

The initial private, nonpublishing qualification retained a real **337-hour**
issue at **09:12:19 UTC**. Published Item states, the collector index and the old
candidate pointer were unchanged. The installed manual service qualification at
**09:18:47 UTC** then published identical READY states to all three Items, using
source snapshot
`98604b6dd95026d0c30b3ccca3c68fff324f4a4785d5bbabc765d696ee104d0a`.
At activation the fresh cohort reported **UNTRAINED, zero pairs**, with no local
predictions or validation claim. The previous v1 one-pair model and original issues remain
separate and unchanged. This intentionally replaces the earlier v1 comparison
column; it does not promote a model or change the main production forecast.

The rollout changed only two source-selection keys in private runtime.env,
removed the obsolete `--include-incumbent` argument from the existing shadow
unit, and installed the matching parser/dialog plus their tests/fixture. All
other live UI source/test files were hash-checked unchanged. The running UI
process, collector definition/pin, training unit/weekly cadence, resource
properties and six shared launcher/guard source files were unchanged. The two
existing shadow/training timers were briefly stopped for the transaction and
resumed with their prior active/enabled states. No new timer, credential, grant,
resource policy or production provider was installed.

Verification: **2,554 migration frontend tests passed** across 168 files in
47.29 seconds. The staged live UI passed its **10 parser/component/integration
tests** and production build (1.03 seconds, existing large-chunk warning).
Real unmocked browser checks at **1440×900** and **1024×768** showed a contained,
working dialog with 24 forecast rows, explicit untrained status, no console
errors and no mutating REST requests. The UI service did not restart.
[Typed public qualification evidence](2026-10-19-weathernext-v2-shadow-qualification.json)
records source/invocation/generation identity and test results. Raw weather
responses, screenshots and operational preimages remain private.

The first **natural v2 trigger is verified**: timer **09:40:25.398458 UTC**,
service start **09:40:25.417148**, successful exit **09:40:26.508830**, invocation
`17464742b2be4110b33a807a9e4037d6`. All three Items exactly match the retained v2
issue and source snapshot
`aa8c44c6e21711aba43be3b501efe685206861b8cfefe3517e3492c1f7665e81`,
which completed during the preceding natural collector invocation at
**09:36:04 UTC** with all **4,320 values** present. The new issue contains 337
hours and remains UNTRAINED with zero pairs. Raw systemd timestamps prove the
18,690-microsecond start-after-trigger ordering; no manual restart established
this natural run. This is one scheduled cycle, not a completed prospective day.
The approved reliability, training/holdout, variable/regime and model-promotion
intervals remain incomplete. The broader source retirement status is in
[the removal contract](openmeteo-retirement.md).

## First fresh v2 candidate — October 19

The first retained v2 issue was actually made at **09:12:19 UTC**, before its
**10:00 UTC** target. After that target elapsed, one manual qualification of the
existing training service ran at **10:04:50–10:04:51 UTC**, invocation
`3c47280d20264cab8bd3d77b20f1628a`. It fitted a new bounded-bias artifact from
**one qualified Google/local pair on one observed date**:
`a61b19c36d833f09f329c033a450c404b1cdf4a29c60b1e20cb0c1f21113b292`.
The original Google target, qualified local outcome and pair digest were
independently reconstructed at the original cutoff; rerunning the pure fit
reproduced the saved model exactly. This is provenance/reproducibility evidence,
not a validation score. No v1 candidate or learning state was imported; the old
v1 model identity and fit time remain unchanged.

Manual shadow publication at **10:09:43 UTC**, invocation
`8e2a08d7f1594a92a965f199ca5c5943`, published one matching READY generation across
all three Items with that exact model, **337 hours**, finite local predictions,
SHADOW_ONLY status, one pair and `validation=null`. Actual laptop/tablet browser
checks passed again: 24 local-prediction rows, explicit one-pair support and
“Validation unavailable; candidate not qualified,” no console errors and no
mutating REST requests. Private screenshots remain separate from activation
screenshots. Main production forecasts, native building/PV models, notifications
and equipment authority are unchanged.

The weekly timer's unit bytes/calendar and enabled state are unchanged. Its next
execution remains Sunday October 25 around 06:50 MDT, within the existing
two-minute randomized delay. A post-check initially compared its volatile next
fire timestamp too strictly; configuration/readback corrected that verifier.
Training was executed **once**, with no retry due to that verification error.
These are manual candidate/publication qualifications, not normal trained-shadow
days, a complete qualified training day, held-out outcomes or promotion evidence.

## Collector source maintenance

The collector uses immutable revision 8be69ea through the source-release drop-in
and private collector-release.env. Shadow inference and
training retain their existing shared runtime root and UI/cohort contract. The
[October 19 timeout correction](2026-10-19-weathernext-collector-timeout.md) records
two natural ReadTimeout failures, the unchanged overall/resource bounds and the
successful diagnostic, manual and natural full native captures. The 02:40 shadow
run consumed the new live snapshot and published a matching READY generation. Collector maintenance does not activate
the prepared v2 shadow cohort or change household production forecast ownership.

## Data and state flow

1. The separate bounded collector writes original WeatherNext snapshots to the private archive.
2. Hourly `local_forecast_shadow.py` selects a fresh, complete snapshot for the authoritative site. It loads a previously fitted candidate, never fits during inference, retains the original decision and outputs, then optionally publishes three shadow Item states.
3. Weekly `local_forecast_train.py` reads those retained original decisions and the existing qualified native outdoor-temperature reader. It fits a fresh Google/local bias or residual candidate and atomically advances a private model-receipt pointer only after successful fitting. Missing labels leave the previous candidate intact.

Private model receipts bind model bytes and actual fit-completion time. Each original issue retains its decision/completion times, source snapshot, sensor epoch and serving revision. The prepared v2 issue has no incumbent source or values. Source, model and epoch mismatches refuse local-model use; fresh raw Google forecasts can remain visible with the local candidate explicitly unavailable. Missing/stale source produces an unavailable view without inventing zero values.

The training policy is fixed before outcomes: select the earliest retained issue per local calendar date, then native future-hour positions 1–24, 36, 48, 60, 72, and every 24 hours from 96 through 360 where retained. At most 40 targets/date across at most 366 dates remains below the existing 20,000-pair artifact bound. Default fitting looks back 90 elapsed days. Daily issues are ranked before applying the rolling lower bound: a partial oldest date is omitted if its original first issue falls outside the window; a later issue never replaces it. If the maximum 366-day interval touches 367 local dates, retain the latest 366 original daily decisions. Labels are selected in bounded UTC-day batches through the existing native reader; missing labels cannot cause selection of a different/easier original issue. This policy is candidate research, not a declaration that full release evidence exists.

Model and issue objects are immutable, private and content-addressed; candidate pointer updates use write/fsync/rename. The separate training/inference locks prevent duplicate owners without making inference wait on fitting. State accounting refuses at 10,000 objects / 2 GiB or inadequate free disk; it does not silently delete source evidence. The collector archive has its separately documented limits.

## Publication and UI

Only `Forecast_Local_Shadow_JSON`, `Forecast_Comparison_JSON` and `Forecast_Provider_Status_JSON` may be published. They contain the same closed, bounded, sealed generation; source status is written last. The UI requires all three states to match, so interrupted publication is unavailable rather than mixed data. No Item commands, rule execution or actuator API exists in this publisher.

The Weather page exposes the model dialog only after at least one shadow Item exists. The prepared read-only dialog keeps raw WeatherNext and local candidate temperatures distinct, shows source-run age, decision time, training support and forecast horizon, and explicitly states that validation is unavailable and candidates are not qualified. Stale/disconnected/incomplete data hides forecast values. No generic confidence percentage is generated. Existing weather-grid dimensions are unchanged.

The prepared source no longer reads the corrected incumbent forecast Item. `weather_learning/incumbent.py`, its CLI/service option and its UI column have been removed. Previously retained controls remain detached historical evidence and cannot enter the new cohort.

## Entry points and deployment inputs

`local_forecast_shadow.py` defaults to local shadow recording; `--publish` is explicit. `local_forecast_train.py` defaults to dry-run fitting; `--apply` explicitly installs a validated private candidate. `--algorithm residual` selects the regularized candidate; bias is the initial default. Both use the existing shared RAM admission/CPU/memory/swap/task/deadline launcher when scheduled.

The service templates read private `~/.config/earthship-weather/runtime.env`, now installed for the backend-only activation. Deployment supplies:

- `EARTHSHIP_WEATHER_CODE_ROOT`: isolated immutable deployment source directory.
- `EARTHSHIP_WEATHER_PYTHON`: tested isolated Python executable.
- `EARTHSHIP_WEATHER_CODE_REVISION`: pinned source commit used by that deployment; this is a recorded deployment assertion, not a substitute for verifying the deployed files.
- `EARTHSHIP_WEATHER_ARCHIVE`: private collector archive.
- `EARTHSHIP_WEATHER_SHADOW_STATE`: private state base outside Git and browser-served directories; prepared v2 uses its fresh `google-local-v2` child for models/issues.
- `EARTHSHIP_WEATHER_TEMPERATURE_POLICY`: existing native outdoor policy with the current hardware epoch.
- `EARTHSHIP_WEATHER_TEMPERATURE_DB_CONFIG`: existing dedicated read-only `weather_temperature_reader` JSON config.

Reuse the installed qualified reader/policy; do not create a new authority or request broader database grants. Credentials remain in private configuration and are never included in Item payloads or CLI error output.

The proposed order is collector at :35, shadow at :40 and weekly candidate training Sunday 06:50. The backend-only deployment now passes native point/full-horizon capture, immutable-source and installed-run checks; its three timers are active. The three unlinked Items are installed, ownership is verified, and the local-recording override was removed. Explicit publication and live browser checks pass; the first natural matching published trigger also passed at 19:40:31Z, with identical retained/live generations. Natural timer execution is tracked separately from manual service qualification. Recovery rehearsals remain deferred.

## Remaining work

The installed v2 cohort has its own one-pair SHADOW_ONLY candidate; its older v1 one-pair candidate is retained separately and unused. No qualified predictive skill, completed prospective reliability interval, untouched holdout report or production cutover is established. Source/epoch inventory, required-variable/downstream qualification, production-provider replacement and complete Open-Meteo removal remain separate unfinished plan requirements. This implementation has no promotion or equipment-control authority.

## First scheduled trained-candidate publication

At **2026-10-19 10:40:25 UTC (04:40:25 MDT)** the normal timer started
invocation `2d2aa7e897f9456ab1751feeebfa8d88`, 18,082 microseconds after its
trigger. It exited successfully at 10:40:26 UTC. All three live shadow Items
exactly match retained issue
`55194dd13ddd2dcfe99ad5ed2361af058d7a5b5b989f0b6c86c79c7a5b0c0838`.
The scheduled run used the original fresh v2 candidate `a61b19c36d833f09f329c033a450c404b1cdf4a29c60b1e20cb0c1f21113b292`,
with 337 local predictions present, one training pair, SHADOW_ONLY status and
`validation=null`. Its source was the preceding natural collector's complete
4,320-point capture, completed at 10:37:38 UTC. This is the first verified normal
trained-v2 cycle, not a completed shadow day or an accuracy/promotion result.

Verification was read-only: no training or publication was manually started.
Source pins, weekly fitting cadence, production provider ownership and actuator
authority are unchanged. The [qualification record](2026-10-19-weathernext-v2-shadow-qualification.json)
contains the exact timer, service, model, issue and source identities.
