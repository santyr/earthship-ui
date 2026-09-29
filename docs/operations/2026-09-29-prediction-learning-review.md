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

The September 27 06:40 OpenHAB forecast issue exists in JDBC but was absent
from `energy_analytics.forecast_snapshots`: its two-hour user timer captured
the preceding and following weather revisions instead. Solar_PV `4dd13ad`
adds a 06:45 user-timer event alongside the existing two-hour cadence. The
installed timer loaded both expressions and remains active. This repairs the
prospective capture schedule, not the historical gap. Its first natural
September 30 run must be checked for exact 06:40 issue identity and values
before analytics snapshots are treated as complete morning-origin history.

A source-only `pre_dusk_tuning.score_pair` now provides an exact same-target
comparison for immutable morning and pre-dusk receipts against the existing
source-bound 20:00–11:00 completed-night assessment. It refuses mismatched
issue dates, stale SoC at issue, an incomplete or low-coverage night, and an
outcome with the wrong bank-evidence source or window. It reports signed and
absolute-error differences but no causal reward. This does not fabricate a
September 29 outcome: the first natural pre-dusk issue and its following-day
11:00 completed target are still pending.

The complementary source-only history adapters now read only the two exact
forecast-receipt Items through OpenHAB's bounded local JDBC persistence API
and assess a completed night from `BMS_SOC_Evidence_JSON` under a dedicated
read-only PostgreSQL snapshot. The issue reader preserves multiple morning
origins and selects only the one explicitly linked by a single pre-dusk
receipt; it never substitutes the current Item state. A live read returned
one September 29 06:40:17 morning issue and zero pre-dusk issues before the
eligible window. The restricted outcome reader independently re-assessed the
completed September 28 night as measured at 70% SoC, 0.99991 coverage from
886 original in-window receipts. No extra database grant or scheduled scoring
job was needed for these read-only checks. The first natural same-day pair,
its completed following-night outcome, and longer chronological/seasonal
comparisons remain open.

### Origin-paired morning trough divergence

A read-only September 20–28 audit paired archived morning prediction receipts
with the same source-bound completed-night assessor. No receipt was persisted
for September 20–23, so those four measured nights are **not** treated
as archived morning issues. September 24–28 each had one immutable morning
receipt and a measured night with 99.990–99.992% coverage. Their issued versus
actual troughs were 58/77, 63/84, 73/84, 71/80 and 46/70 percent: five
negative errors and 16.8 percentage points mean absolute error. This is an
as-issued warm-season baseline, not a model-release holdout.

For September 25–28, the frozen morning state also retained the forecast dusk
SoC and overnight-drop proxy; each record's issue timestamp and trough matched
its sole persisted receipt exactly. Exact 20:00 SoC was read from valid
source-bound intervals, not a held numeric Item. Decomposing against the
assessor's 20:00–11:00 minima gives:

| Day | Forecast dusk / actual 20:00 SoC | Forecast / actual 20:00-to-minimum drop | Morning trough error |
| --- | ---: | ---: | ---: |
| Sep 25 | 78.4 / 96% | 15.7 / 12 pp | −21 pp |
| Sep 26 | 93.4 / 97% | 20.0 / 13 pp | −11 pp |
| Sep 27 | 90.7 / 92% | 19.7 / 12 pp | −9 pp |
| Sep 28 | 64.8 / 83% | 19.3 / 13 pp | −24 pp |

The drop proxy overestimated every qualified night's actual 20:00 decline
by 3.7–7.7 points. The forecast dusk value was also below the actual 20:00
reference, particularly on September 25 and 28 (about 18 points). Since
20:00 is later than sunset, that comparison includes late-afternoon and early-
evening trajectory error; it does **not** isolate a causal PV coefficient
error. Tune the daytime/early-evening SoC path and the overnight-drop model
as separate stages, then test their combined trough forecast on later
qualified origins. Do not simply subtract the 20:00 drop at a 17:30 pre-dusk
origin without forecasting the intervening period.

An origin-safe shadow substitution used each morning record's original
`overnight_drop_sample_days` entries as **ending dates**: each maps to the
preceding prediction-day 20:00–11:00 target, already complete by the morning
issue. Every substituted start-to-trough drop passed the same source-bound
assessment, including its no-post-origin-row guard. Holding that morning's
forecast dusk and cloud penalty fixed, replacing only `99 − minimum` with
the mean of those earlier measured drops changed September 25–28 estimates
from 63/73/71/46% to 65/77/75/50%, against actual 84/84/80/70%.
Four-origin MAE fell from 16.25 to 12.75 points, but the September 25 and 28
misses remained 19 and 20 points. This small, late-September shadow result is
not a production calibration. The separate four-night *pre-dusk* counterfactual
above actually worsened when the true 20:00 drop was substituted without
modeling the intervening 17:30-to-20:00 trajectory. Morning and pre-dusk
origin-specific models need independent chronological validation.

### First as-issued outdoor-temperature comparison

Six fully covered September 20–28 local days had matched 06:40 daily issues.
The corrected daily high/low MAE was 0.875/1.689°F versus reconstructed
same-origin raw 3.643/8.050°F. Three other days were withheld because source
receipt gaps prevented complete-day qualification; no sparse numeric extrema
were substituted. These results support retaining the learned daily
correction, but are not a seasonal calibration result.

For next-day hourly issues on September 26–28, 72/72 target hours had strict
source-bound outcome receipts and retained raw capture records. Corrected
MAE was 3.273°F versus raw 4.918°F. The Sep 27 corrected next-day issue was
warm-biased by 3.831°F. On identical 07:00–23:00 target hours, a newer 06:40
same-day issue was not reliably better: prior-day versus same-day MAE was
3.371/2.928°F on Sep 26, 2.654/2.685°F on Sep 27, and 2.133/5.779°F on
Sep 28. The Sep 28 same-day issue was warm-biased by 5.671°F. Do not infer
that simply moving or rerunning the job later improves hourly weather skill;
investigate forecast revisions and sky/front regimes on a larger chronological
sample before changing the correction policy.

The Energy PV card now reads the immutable current-day prediction receipt,
not the 10-day payload whose weather refresh can carry the frozen morning PV
estimate. Before the receipt it says the morning forecast is unavailable;
after actual PV exceeds that issue, it says so rather than presenting an
impossible `actual of predicted` comparison. The 10-day PV outlook remains
visible. This presentation change does not recalibrate or revise PV kWh.

### Durable as-issued PV branch diagnostics

The morning worker previously kept radiation resource, SoC headroom and direct
demand only in its rolling 30-day state file. Future
`Forecast_Prediction_Receipt_JSON` records can now carry a bounded, versioned
`pvDiagnostics` object with those same as-issued components and the
resource/demand limiting branch. This adds no forecast, coefficient, UI or DM
change; older receipts remain valid and the UI ignores the optional diagnostic
object. A source-only consistency check refuses nonfinite or contradictory
components rather than persisting a false decomposition. The SoC percentage
is diagnostic and still lacks an embedded original-source digest; it must not
be treated as a newly qualified training label. The first natural issue,
persistence and later qualified PV-day pairing must be verified before using
these fields for calibration.

### Current thermal shadow comparison

The September 29 read-only published-shadow scorer was run with
`--require-capture` and the **installed v4** runtime. The source checkout has
v5 artifact validation; using it to verify older captured v4 artifacts fails
schema validation, so the scorer must pin the runtime that produced them.
Across 56 matured, exact-forcing, overlapping 24-hour publications since
September 24, model MAE was 2.940°F versus 2.205°F same-origin persistence,
with 82.14% coverage of its approximately 10.414°F-wide intervals. Five
non-overlapping selected windows were 4.079°F versus 2.052°F, with 60%
interval coverage. The selected outdoor forecast's paired MAE/bias was
4.279/+3.161°F. These publications mix revisions and are not 56 independent
days or an attribution of indoor error to weather alone.

Today's accepted artifact `00611a5e...ef2cd5a` has four mature, captured
one-hour publications: model MAE 1.130°F versus 0.810°F persistence; all
remain low confidence, and no 24-hour target for this artifact has matured.
Neither this small early sample nor the mixed-revision aggregate qualifies
thermal advice for shadow exit. The next fit experiment should hold an
artifact/revision fixed, evaluate exact forcing and confirmed action labels,
and compare weather forcing versus physical-model residuals by regime.
