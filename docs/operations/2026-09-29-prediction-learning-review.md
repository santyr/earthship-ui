# Prediction learning review — September 29, 2026

This is an origin-aware design review, not a new control or model release.
Keep `forecast-intel`'s 06:40 as-issued record, the separate display-only
pre-dusk issue, and the qualified Energy/Thermal evidence boundaries intact.
No Hexmem task is used as an authority for this review.

## October 4 first paired reported-full day

The existing SELECT-only `--charge-only` assessment, run after October 3
sunset at `2026-10-04T12:54:19.972849Z`, qualifies one `reported_full` day.
Its original morning issue is `2026-10-03T12:40:58.396244Z`; the atomic SoC
assessment is the distinct `12:40:58.411000Z` clock, with **87%** SoC.
The first native reported **100%** occurs at `16:00:58.575454Z` (10:00 MDT),
12,000.164454 seconds later. True sunset is `2026-10-04T00:42:07.214Z`,
with sunset SoC 99% and charge-day coverage 99.982747%.

Source digest: `c8755608e6c60a9cda92f215bb813d14b55e278c199cf2102536ad6c7119b19b`.
Charge-profile digest: `e07c08f5e5619a7df2abc78dd2d4aeb50ba8eecc5181a1f92c635a7946c94b46`.
Forecast-state SHA-256: `44aba2710926998a2d710c8220f252fa5f6e3493af4a483ad0d27a1f67d842aa`.
This is a reported-full observation, not the exact physical charge-completion
instant. Together with the two earlier censored days, it remains insufficient
to fit full-charge scheduling. No production model changed. October 3's
separately frozen overnight comparisons still wait for October 4 11:00 MDT.

## October 3 original low-temperature correction watch

At **2026-10-04T00:03:11.344244Z** (October 3 18:03 MDT), a restricted
read-only comparison paired six immutable advisory **tomorrow-low** origins
with six completed outdoor calendar-day outcomes. Each native outcome was
re-read at its original recorded assessment clock and passed the current
strict complete-coverage contract, matching every archived value and history
digest. Older archived summaries lack `gap_count`; they were not rewritten
or given a fabricated field. The fresh native replay supplies that verification.
Every origin has exactly one matching target, precedes target start, validates
under the closed decision schema and preserves its original applied bias.

| Target day | Original issue date, 06:40 MDT | Raw low | Applied bias | Corrected low | Actual low | Corrected error |
| --- | --- | --- | --- | --- | --- | --- |
| September 21 | September 20 | 52.600 F | 7.297 F | 45.303 F | 45.860 F | -0.557 F |
| September 22 | September 21 | 54.000 F | 7.297 F | 46.703 F | 48.020 F | -1.317 F |
| September 25 | September 24 | 51.100 F | 7.187 F | 43.913 F | 45.500 F | -1.587 F |
| September 26 | September 25 | 49.700 F | 7.187 F | 42.513 F | 40.640 F | +1.873 F |
| September 27 | September 26 | 53.300 F | 7.247 F | 46.053 F | 42.980 F | +3.073 F |
| October 1 | September 30 | 48.900 F | 7.422 F | 41.478 F | 39.380 F | +2.098 F |

Raw MAE is **7.870 F**; original corrected MAE is **1.750833 F**, with
corrected signed bias **+0.597167 F**. Correction wins **six of six** pairs.
Three corrected misses are cold and three warm; the three later available
dates still have warm residuals of 1.873–3.073 F. This narrows the old generic
under-correction watch to a chronological/regime-specific residual watch.
It does **not** justify increasing the global low bias from the raw-MAE Item,
which measures a different predictor and horizon. Missing fully covered days
stay excluded; do not mistake this selected complete-day cohort for seasonal
coverage or reconstruct unobserved lows from change-only numeric history.

This verifies frozen **advisory predictor inputs**, not delivery or rendering
of every weather UI revision. No current Kalman bias is substituted into an
old issue; the thermal path's separate raw-weather forcing is unchanged.
Neither interval calibration, seasonal skill nor thermal graduation is proved.
No state, forecast, filter, notification, Item, journal or control changed.
Forecast-state SHA-256 remains
`e60f26adb4ff14d2cb3a5994c13576cbbf5acb60705009ef881151f4c9c73fc7`.

Original decision IDs, in table order:

- `19f39fb4-e0e6-4f10-8edd-59abd2c56602`
- `01657602-ef24-4aa8-990c-5d15085070bb`
- `2aae0b06-f84e-4dde-94ac-f6af0ea4f45e`
- `b180fe8d-f568-4955-b73a-8e324242e82f`
- `307b6cce-8f99-4a6e-9e3a-d375dda1c877`
- `a494c9f3-c87a-457c-8c14-edb3107a00c4`

Replayed native outcome digests, in the same order:

- `bdeaa3d2c793cf1e813b80c4b898cb95483bdee64e071014e628f95dbf14da39`
- `bafafff30eb0985fbf3d22fc11febfc70b871bd53976c92f2bea615e8a256b37`
- `d1e6843c85997f0913aa98962ab68195c967f9c4168e1e5c98c44e943b3dc889`
- `b80b658436cdb9ccb8543bcd9f6dee86cfb2c2c3f077ce4c9772d0ca67bd3892`
- `1bfe61f2fc734fb1377fd34164ec124a868cfdfe144192a953336cb5cb6b51aa`
- `da5c4f302c751fa08545a5529b820b617a1ba5602a6cb9dbb22ed492332fba79`

## October 3 comparison frozen before tonight's outcome

At **2026-10-03T23:46:16.838503Z** (17:46 MDT), a bounded, restricted
SELECT-only calculation qualified the original morning/late/numeric/native
SoC chain and calculated the two existing counterfactuals. It read **no
October 3 target outcome**. Creation precedes both today's true sunset and
the canonical 20:00–11:00 overnight window; this is an unscored comparison,
not an original 17:30 production issue or evidence of forecast skill.

The original late issue is `2026-10-03T23:30:00.934426Z`, linked to morning
`2026-10-03T12:40:58.396244Z`, with source SoC **100%** and true sunset
`2026-10-04T00:42:07.214Z`. Its native receipt persisted at
`2026-10-03T23:30:00.847423Z`, epoch
`61b2c967-b217-429e-840f-eebf68a36da0`, digest
`1c6aa1d514e5fbfdfb901fb252ed797a0fa61c9491f037252024de147888d4bf`.
The numeric and issue receipts persisted at `23:30:00.936Z` and
`23:30:00.938Z`, respectively. The live estimate remains **74%**.

| Calculation | Drop, percentage points | Frozen trough |
| --- | --- | --- |
| Original live proxy | 26.333 | 74% |
| Measured sunset-to-trough | 16.667 | 83% |
| Measured matching pre-dusk-phase-to-trough | 17.667 | 82% |

Both alternatives retain the exact original three sample **ending dates**,
October 2, October 1 and September 30, the original source SoC, zero cloud
penalty and existing rounding/clamps. All historical profiles are assessed
only at the original morning clock. The phase comparison uses tonight's exact
**4326.279574-second** sunset-relative lead, not a fixed clock or season proxy.

| Prior prediction night | Phase start, UTC | Phase SoC | Sunset SoC | Canonical trough | Phase drop | Phase / canonical coverage |
| --- | --- | --- | --- | --- | --- | --- |
| October 1 | 23:33:08.184426 | 87% | 87% | 72% | 15 pp | 99.879810% / 99.861448% |
| September 30 | 23:34:42.374426 | 85% | 83% | 65% | 20 pp | 99.949861% / 99.943067% |
| September 29 | 23:36:16.895426 | 99% | 98% | 81% | 18 pp | 99.992628% / 99.992570% |

Frozen phase input digests, in that order:

- `4f0992ce8fccf8639d1fffd3de34a0f0251fcdf54d758ae753654d7f625f06f5`
- `4160e091112cb4940c3337a5f67c3d042fbda84bf420b5b895b78bd1b5c0dc97`
- `caa6c312017f843f3342eebfcfd6661254e3f3bf974edf9d1a4bc377a8aed16e`

Frozen sunset-only input digests, in the same order:

- `4e1ce21a4999e38ce7d785321d2ca126a48d118515e8560f635ef851c3ccc4fd`
- `cb71d50e76a4ce964ea5749ef5792d1ba4249e65b85c7e2dab4c0a8b205b2dfd`
- `6096972afbe52a70520f0a69a6d9192020a62c3d77ab2125ea23430b11d32989`

Forecast-state SHA-256 at creation:
`e60f26adb4ff14d2cb3a5994c13576cbbf5acb60705009ef881151f4c9c73fc7`.
Existing benchmark source SHA-256:
`cc3c92322f23a34d4b84fc1db84dd6f5ee1ddc91f173e73c9e577206e3c9a563`.
No model, learned state, schedule, display value, notification or control
changed; no temporary file, service, container or diagnostic process remains.

After **October 4 11:00 MDT plus receipt settling**, use the unchanged
completed-target benchmark to score this frozen comparison:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/experiment-sunset-soc-drop.py \
  --start-day 2026-10-03 --end-day 2026-10-04 --include-pre-dusk
```

Require the same original issue, lead and input digests; do not silently
replace this comparison using revised samples or input clocks. Compare 74%,
82% and 83% against the same qualified canonical minimum. An unavailable
outcome stays unscored. A single night's result cannot establish seasonal
skill or justify promoting the fixed three-night average, which still lacks
an explicit remaining-daylight charge/load and overnight-load model.

## October 3 shared charge qualification across benchmark modes

The combined overnight benchmark still used the weather clock for its optional
charge profile even after `--charge-only` gained atomic-input qualification.
Both modes now share exact public/private/native SoC verification, use the
actual assessment clock, and bind only the charge window (including its
120-second input lookback). Later overnight rows cannot change that target's
digest. Missing original charge input withholds only that optional profile;
independently qualified trough/pre-dusk comparisons are retained.

The restricted read-only comparison at `2026-10-03T10:44:43.735470Z` proves
identical charge targets across both modes: September 30 digest
`a8f3cde709c5d61d1c7991fd9c2dd27a18679c987ef776fc30212adef4a350b6`
and October 1 digest
`0e4fa03a3444b70d22888aba8cf97870fb74b56acb614c35a6c6a2dad7dc1afe`.
Both remain no-full outcomes; five earlier optional charge profiles are
withheld, not relabeled as paired training examples. Historical digests below
retain their original, differently bounded evidence scope. All 152 affected
tests pass, including both CLI modes, missing-source refusal, preserved trough
scores and extra overnight observations. The learned-state SHA remains
`26987242320a094645ea8c06e223e3d7405aea5a9558aada842777e28d94c23f`.
No live worker, prediction, model, timer, label or household control changed.

## October 3 independent completed-charge assessment

The benchmark now supports `--charge-only`, independent of the next day's
unfinished 20:00–11:00 trough. The existing overnight modes and live forecasts
are unchanged. This mode requires sunset to have passed, its original archived
context to have been available at the morning issue, and the original atomic
SoC receipt to match both private state and the public prediction receipt.
It verifies the latest persisted source at the **SoC assessment clock**, not
the slightly earlier weather issue; native expiry, epoch, digest and SoC must
match. A later fault cannot be bypassed by selecting an older valid receipt.
Prior-night drop samples are not a prerequisite for this separate target.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/experiment-sunset-soc-drop.py \
  --start-day 2026-09-25 --end-day 2026-10-03 --charge-only
```

The actual restricted read-only run at `2026-10-03T08:05:56.198603Z`
qualifies two original-input/outcome pairs:

| Date | Atomic SoC assessment, UTC | Morning → sunset SoC | Coverage | Charge outcome |
| --- | --- | --- | --- | --- |
| Sep 30 | 12:40:30.518 | 85 → 83% | 99.991549% | No full report; censored at sunset |
| Oct 1 | 12:40:30.519 | 69 → 87% | 99.991455% | No full report; censored at sunset |

Their weather clocks remain respectively `12:40:30.514550` and
`12:40:30.513835`; none is backdated to the other. New outcome digests are
`172efc70f5f40d066afacda28d0d7c70808d2f7f7035e406dc9ea23b42a04ff1`
and `175ad0e8dea837bb94659d03fe8c59826ca51082ac3d10c25502e7d4fa3efa53`.
These differ from earlier weather-clock profiles because the assessed horizon
and evidence binding now use the exact atomic clock; older evidence is retained,
not relabeled. Five earlier dates lack this stronger original-input pairing.
Their previously qualified observational charge outcomes are not discarded,
but are not promoted into paired forecast-training inputs by this command.

October 2 has no original morning prediction in state. Sanitized user-unit
journal evidence traces its 06:40 job failure to `getaddrinfo` during the
Open-Meteo fetch. The documented 08:14 recovery started only weather JSON and
thermal shadow jobs; it did not create a replacement morning energy issue.
Do not backfill October 2 from that later weather revision or run a historical
production issue now. The October 3 morning timer remains active at 06:40 MDT.
State SHA-256 remains
`26987242320a094645ea8c06e223e3d7405aea5a9558aada842777e28d94c23f`.

The focused source/profile/history/release regression slice passes **145
tests**, including real native-evidence CLI assessment after sunset while the
overnight window is incomplete, strict-source refusal cases, and incompatible
mode rejection. This closes assessment latency and exact-input pairing, not
charge-timing model skill. There are no paired reported-full examples in this
run: a survival/full-charge timing fit must wait for adequate chronological
paired events rather than fitting two censored outcomes. No training, timer,
prediction, notification, label or household control changed.

## October 2 matched pre-dusk phase benchmark

The source-only `pre_dusk_phase_profile` now measures **true Astro sunset
minus the original late prediction's lead**, through the unchanged canonical
20:00–11:00 trough. `phase_start_at` and `sunset_at` remain distinct;
no earlier issue time is relabeled as sunset. It requires original sunset
context available before the phase, source-bound SoC at both phase and sunset,
completed canonical outcomes, at least 99.5% coverage in both windows, bounded
original observations, and one physical bank. A lower minimum before the
canonical window, missing endpoint, future row or ambiguous sequence refuses.
Its separately versioned digest binds the lead, true sunset/context, bank and
canonical raw-evidence digest. DST uses actual elapsed time.

The optional benchmark keeps the exact morning-selected prior dates and
unchanged cloud penalty. Each prior profile is assessed only with receipts
available by that original morning; the known original late lead selects the
historical phase. Current late SoC remains the independently qualified
original input. The later target profile is explicitly scoring evidence,
not a candidate input. Run from the repository:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/experiment-sunset-soc-drop.py \
  --start-day 2026-09-29 --end-day 2026-10-02 --include-pre-dusk
```

The restricted SELECT-only run at `2026-10-02T21:24:27.932462Z` qualifies
all three comparisons with no unavailable phase cases. Rolling prediction
state SHA remains `26987242320a094645ea8c06e223e3d7405aea5a9558aada842777e28d94c23f`.

| Prediction day | Original lead, seconds | Prior matched-phase drops, pp | Candidate drop including unchanged cloud penalty, pp | Original trough | Phase candidate | Actual trough |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| Sep 29 | 4703.095055 | 19, 16, 14 | 18.333 | 81% | 81% | 81% |
| Sep 30 | 4608.578552 | 16, 19, 16 | 17.000 | 64% | 68% | 65% |
| Oct 1 | 4514.390785 | 18, 16, 19 | 17.667 | 65% | 69% | 72% |

The matched-phase candidate MAE is **2.000 pp** versus the original
**2.667 pp** and sunset-only **2.333 pp**. Its errors are 0, +3 and -3 pp:
one improved night, one worse and one unchanged. Zero mean error on these
three observations is not proof of unbiased or seasonal performance. No
live coefficient, publication, learner or control is changed.

Actual target phase-to-trough drops are 18, 20 and 15 pp, with pre-sunset
declines 1, 2 and 0 pp. Their coverage is respectively 99.992612%,
99.950041% and 99.880140%; canonical coverage independently exceeds 99.5%.
The target-profile digests are, in that order:

- `f6dd03fc3b476de05c75f8d2880aaef3af6c7c56243ffdc856c1653e55a95bd5`
- `f1d14608cd30a0c3156cf6b5045367a56beaed7ec963a248486c46627aa4958f`
- `de7150b75a45ce6166e680b1b2afec5fa621a90a696daa3c08c544c10707f90a`

The historical pre-sunset declines used in the three candidates are
5/1/1, 1/5/1 and 1/1/5 pp respectively. Thus a fixed recent mean also
misrepresents that phase on some days. The next joint-model comparison
should predict remaining daylight charge/load separately from overnight
load, using as-issued weather/radiation, SoC/headroom and actual sunset/day
length; neither a 99% assumed start nor a universally smaller drop is justified.

Regression-first verification passes **131** affected profile, benchmark,
original-source, issue-history and completed-outcome tests without skips,
including 19 new phase-profile and seven phase-binding cases. Task-owned
temporary fixtures are removed. This is repository-only measurement and
diagnostic support, not a production installation or forecasting release.

## October 2 completed PV, charge and selected pre-dusk comparison

The read-only October 1 join retains the original morning weather issue
`2026-10-01T12:40:30.513835Z`, its exact archived raw-weather digest
`ea7bac6fb4a7435bb80f4e72fd967da9191aa3a7a6c0549005693509ab6c72e7`,
and the original public prediction receipt. Its SoC assessment is separately
`12:40:30.519Z`, slightly later than the weather issue; do not backdate it.
The source-qualified native MPPT daily outcome is **6.697 kWh**, with
99.939745% coverage and 2,020 receipts. The original **6.58 kWh** forecast
misses by -0.117 kWh (-1.75%). Original forecast radiation is 18.21 MJ/m²
(5.058333 kWh/m²); resource gain 1.3 gives 6.576 kWh, the limiting branch.
The retained diagnostics give direct demand 5.403 kWh, charge deficit
6.683 kWh and combined demand 12.086 kWh.

The earlier exploratory resource-gain/direct-demand pair 2.45/4.1, which
looked useful on September 29, instead predicts **10.78 kWh** from the
same October 1 inputs: +4.083 kWh, approximately +61%. This rejects a
blanket coefficient increase, not a causal conclusion about PV production.
The qualified PV calibration release remains false.

Independent inverter-only qualified AC integration measures 5.857844 kWh
for the full day (99.930279% coverage), including 1.197069 kWh before
the morning SoC assessment, **3.154324 kWh from that assessment to the
original Astro sunset** (99.996247% coverage), and 1.506450 kWh afterward.
The 16,664 source-qualified intervals have tuple digest
`15992f44a99a08a9561dfc5c6bf2bdbe5412e3e5ae73a5b5007c8f53a7b3637b`.
AC load is a useful timing covariate, **not** interchangeable with DC
direct demand. No conversion efficiency or battery energy balance is inferred.

The larger October 1 forecast miss is dusk SoC: **74.458% estimated versus
87% measured at the original sunset**, from 69% at the morning origin.
There was no reported 100% before sunset. The completed charge profile
has 99.991455% coverage and digest
`75123d3a977e57e9b57062005b259e6592578db60f8bc51bd7541bfdd35a9765`.
September 30 likewise had no full-charge report: morning 85%, sunset 83%,
99.991549% coverage, digest
`749c29ae2e6fe5efec9c3324e5d510858aeb3d0d5a77ce1cae792a90d2e08c6f`.
The bounded September 25–October 1 replay now has **seven** qualified
charge profiles: four reported-full outcomes and three right-censored
no-full outcomes. An intelligent scheduler cannot always wait for 100%.

The source-only `scripts/experiment-sunset-soc-drop.py --include-pre-dusk`
now reuses the existing strict original morning/late/numeric/native-source
qualification chain. It substitutes measured prior sunset-to-trough drops
only, keeps the original three selected prior dates and cloud penalty,
and preserves the actual late SoC and positive-half-up rounding. Prior
profiles must be unique, newest-first, within the original four-day selection
window, available by the original morning, and at least 99.5% covered.
Later actual troughs are used only for scoring, never candidate inputs.

| Prediction day | Original late SoC | Original drop | Candidate drop | Original trough | Candidate trough | Actual trough |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Sep 29 | 99% | 18.333 pp | 16.000 pp | 81% | 83% | 81% |
| Sep 30 | 85% | 21.000 pp | 14.667 pp | 64% | 70% | 65% |
| Oct 1 | 87% | 22.000 pp | 15.333 pp | 65% | 72% | 72% |

The original selected pre-dusk MAE is **2.667 pp**, versus **2.333 pp**
for this counterfactual. The small average improvement hides worse results
on two of three nights and shifts the mean error from -2.667 to +2.333 pp.
It is **not released**. These original issues preceded true sunset:
late-to-sunset SoC changes were -1, -2 and 0 pp respectively. Matching
the actual pre-dusk phase to the trough, plus separate remaining-day and
overnight load/weather, is the next diagnostic; do not disguise an earlier
phase time as Astro sunset or promote a three-night fit.

The bounded replay completed at `2026-10-02T21:07:00.138028Z`, with four
older days explicitly lacking a qualified pre-dusk issue. The private rolling
state digest stayed
`26987242320a094645ea8c06e223e3d7405aea5a9558aada842777e28d94c23f`.
All **105** affected benchmark, sunset/charge, original-source, issue-history
and tuning/outcome tests pass without skips. Testing fixtures are cleaned.
This is read-only diagnosis and a source-only optional benchmark: no model,
coefficient, production worker, timer, message or household control changed.

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
September 30 run is now qualified by the exact original issue/value/provenance
comparison [below](#september-30-natural-morning-snapshot-capture). This does
not establish complete capture for every earlier morning origin.

A source-only `pre_dusk_tuning.score_pair` now provides an exact same-target
comparison for immutable morning and pre-dusk receipts against the existing
source-bound 20:00–11:00 completed-night assessment. It refuses mismatched
issue dates, stale SoC at issue, an incomplete or low-coverage night, and an
outcome with the wrong bank-evidence source or window. It reports signed and
absolute-error differences but no causal reward. At the source-only checkpoint,
the September 29 issue and its following-day 11:00 target were still pending;
the issue has since arrived naturally, as recorded below.

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
job was needed for these read-only checks. The first completed following-night
outcome and longer chronological/seasonal comparisons remain open.

At 17:30 MDT September 29, the scheduled `forecast-pre-dusk.service` exited
successfully with `pre-dusk trough: issued`; it was not run manually. The
restricted read-only verifier found one 06:40 morning issue, one 17:30
pre-dusk issue, and the matching persisted numeric Item value of **81%**.
The late receipt is bound to a source-qualified BMS SoC evidence row persisted
at 17:29:33 MDT, in the same source epoch and with the same digest. A
read-only Lenovo-sized browser check of the live Energy page, after its
initial OpenHAB snapshot loaded, displayed `pre-dusk estimate: 81%` with no
failed REST response. This closes the first natural issue/JDBC/UI-selection
gate. The verifier's `display_selection_verified` field remains `false` by
design because its server-side reader never inspects the browser; browser
evidence is recorded separately here. The following 20:00–11:00 night has
not finished, so no accuracy or learning claim is made. Score the immutable
pair only after September 30 11:05 MDT and the strict outcome gate.

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

### September 30 operator-selected operational display

The operator chose the pre-dusk estimate as the displayed overnight forecast
and retained the morning calculation/history for comparison. Energy and the
shared UI forecast-alert projector now accept only the validated pre-dusk
receipt, without falling back to the low morning estimate. The morning Item,
receipt publication and JDBC series are untouched; keeping them is necessary
to score divergence and test future algorithm changes against original issues.
This is a presentation/source-selection decision, not an accuracy graduation.

The evening issue stays valid until the following-day 11:00 Mountain target;
it is no longer wrongly discarded at midnight. Calendar/timezone checks cover
the overnight DST transition, and the dashed projection terminates at that
fixed target rather than extending eighteen hours from every refresh. Both
chart segments share one `Pre-dusk trough` legend entry. Without valid evidence
the headline shows `pre-dusk estimate: —` and no projected trough or trough UI
alert is manufactured. Morning PV/curtailment and thermal-advice provenance
remain separate and keep their original current-day rules.

All 1,927 UI unit tests and 15 isolated Energy browser cases pass; the production
build passes with existing chunk-size warnings. One initial browser run exposed
host-clock-based fixture rows outside the frozen browser history window; those
rows now follow the browser clock, so a missing forecast cannot mask an empty
history fixture. A read-only live 1340×800 Lenovo-size check displayed the
original `81%` pre-dusk issue with exactly one trough legend entry, zero morning
trough legends, zero browser errors and zero write requests. No screenshot or
test artifact was retained. The morning job's separate deep-cycle DM policy
was still unchanged at this display checkpoint; its subsequent retirement is
recorded below. Pre-dusk notification delivery remains outstanding.

### Retired morning-trough DM path

`MORNING_TROUGH_DM_ENABLED=False` disables only the morning estimate's deep-
cycle notification eligibility. Its numerical calculation, Item publication,
immutable issue receipt, persisted history and scoring continue unchanged.
The observational advisory capture truthfully records notification eligibility
false and `not_eligible`; it does not invent a suppressed/sent message.
Current-SoC safety monitoring, thermal advice and protected controls are not
modified. The pre-dusk worker still sends no DM pending its delivery and
deduplication qualification.

All 189 forecast/advisory capture/record tests pass. The new main-path
regression uses a below-threshold forecast and proves zero notification calls,
unchanged prediction records/Item writes and no false sent marker. Legacy
notification-capture tests explicitly enable the old policy for replay tests;
that is not the production default. The first command omitted Solar_PV's
analytics import path and had 11 missing-module failures; with the required
cross-repository `PYTHONPATH`, the full selected suite passes.

The installed forecast preimage was
`84ce22d5b0e3c43203de6aa71768d2b2bd41660a9a712e495b2721bd8a903a73`;
installed/source now both equal
`19568956faea6c7ab66bd610539ebabb6cc5e27dac032ddd9149c1e4c75d53df`.
All five importing forecast/thermal services were inactive before and after
briefly stopping their user timers. The one-file transaction's private receipt
is `/home/sat/.local/state/thermal-intel/deploy-receipts/morning-dm-retire-20260930/files`.
Independent receipt and rollback-preimage verification passed; installed import
confirms the default false flag. All five timers returned active/enabled,
accepted artifact bytes stayed unchanged and no message or control was sent.
The full thermal publication runtime is now `0864f4d6...`, distinct from its
accepted training identity; private before/after bundles preserve that fact.

### September 30 first completed natural morning/pre-dusk pair

The read-only `qualify-pre-dusk-natural-issue.py --day 2026-09-29
--score-completed-night` passed at 11:05 MDT with status
`scored_completed_night`. Morning issued at `2026-09-29T12:40:17.987351Z`
predicted 53%; pre-dusk issued at `2026-09-29T23:30:00.079945Z`
predicted 81%. The measured trough was 81% across the common target
`2026-09-30T02:00:00Z` through `2026-09-30T17:00:00Z` (20:00–11:00
Mountain), with 99.9925695% qualified source coverage. Signed forecast errors
were -28 and 0 percentage points: a 28-point absolute-error improvement.

The pre-dusk numeric/receipt rows persisted at `23:30:00.099Z` and
`23:30:00.101Z`; its original `BMS_SOC_Evidence_JSON` input persisted at
`2026-09-29T23:29:33.195421Z`, stream epoch
`6b58b416-0c8b-459e-8eca-55f1f83a1831`, input digest
`d92ab4bbf931c4129ed7177a150021e667d59c27398de941416b1ba1c768ba7f`.
Completed-night evidence digest:
`bbca61af3255aa399b68e7491705caa228086772bfba9ba77f8a5f77431f4e77`.

This is one qualified night, not seasonal graduation or causal advisory
reward. The reader reports `night_outcome_scored=true`,
`causal_reward_proven=false` and `display_selection_verified=false` (it does
not inspect the browser). No database, Item, model, message or control writes
were made; original morning calculation/history and calibration are unchanged.

### October 1 second completed natural morning/pre-dusk pair

After the following-day 11:00 Mountain target completed, the read-only
`qualify-pre-dusk-natural-issue.py --day 2026-09-30 --score-completed-night`
passed with `scored_completed_night`. It compared the original same-target
morning issue at `2026-09-30T12:40:30.514550Z` with the original pre-dusk issue
at `2026-09-30T23:30:00.075448Z`; neither prediction was reconstructed using
later evidence.

| Same overnight target | Original forecast | Actual minimum | Signed error |
| --- | --- | --- | --- |
| Morning | 47% | 65% | -18 percentage points |
| Pre-dusk | 64% | 65% | -1 percentage point |

The common qualified target is `2026-10-01T02:00:00Z` through
`2026-10-01T17:00:00Z` (20:00–11:00 Mountain), with **99.9430670%** source
coverage. Pre-dusk improves absolute error by **17 percentage points** for
this completed night. Completed-night evidence digest is
`48f0271b3e5b8a1b859342ce7a1b810ae8e251fb2b93d51a02fd0712ac3974fb`.

The pre-dusk numeric and receipt persisted at `23:30:00.076Z` and
`23:30:00.078Z`. Its original `BMS_SOC_Evidence_JSON` input persisted at
`2026-09-30T23:29:12.404875Z`, stream epoch
`6b58b416-0c8b-459e-8eca-55f1f83a1831`, with source digest
`835724d3cdaf749c4f1d00679473a98a4045d27f4b569f49e67464843e044dae`.
The scorer verified that exact original source/numeric/JDBC chain and the
physical bank epoch, not held SoC getter freshness or a change-only sample age.

This is the second qualified morning/pre-dusk comparison and supports retaining
the operator-selected pre-dusk display. It is not seasonal holdout, causal
advisory reward or evidence that a new coefficient/model should be promoted.
`night_outcome_scored=true`, `causal_reward_proven=false`, and
`display_selection_verified=false` are retained literally: this reader does
not inspect the browser. No database, Item, model, DM or equipment write was
made. Continue collecting original forcing and complete outcomes for the
chronological joint SoC/PV/day-length/afternoon-discharge analysis.

All 41 existing release, original-source, pair-scoring and completed-outcome
regressions passed in 0.07 seconds with
`PYTHONPATH=/home/sat/Solar_PV/analytics/src`, matching the scorer's explicit
dependency bootstrap. The first focused invocation omitted that external
package path and produced six import-dependent failures; a direct import probe
confirmed the missing path and the unchanged tests passed after correcting only
the invocation. No product-code workaround or relaxed evidence gate was added.

### October 2 third completed natural morning/pre-dusk pair

The read-only existing scorer, run with `--day 2026-10-01
--score-completed-night`, returned `scored_completed_night`. It verified the
original morning issue at `2026-10-01T12:40:30.513835Z` and pre-dusk issue at
`2026-10-01T23:30:00.073215Z`, without reconstructing either prediction.

| Same overnight target | Original forecast | Actual minimum | Signed error |
| --- | --- | --- | --- |
| Morning | 52% | 72% | -20 percentage points |
| Pre-dusk | 65% | 72% | -7 percentage points |

The target is `2026-10-02T02:00:00Z`–`2026-10-02T17:00:00Z`, with
**99.8614485%** qualified source coverage, not 100%. It includes the day of
the actual production JVM restart; the scorer's strict outcome gate passed,
but this result does not establish complete-day continuity for other sources.
Pre-dusk improves absolute error by **13 percentage points**. Outcome digest:
`71dfd2acd73cc709d7a11bb3c52a927890d3b5f5aae36b0b74f0a5555f9d78de`.

The pre-dusk numeric/receipt persisted at `23:30:00.075Z`/`23:30:00.076Z`.
Its exact original `BMS_SOC_Evidence_JSON` input persisted at
`2026-10-01T23:29:14.270052Z`, epoch
`6b58b416-0c8b-459e-8eca-55f1f83a1831`, source digest
`edd4b66470ffccb29ee40c6fe627210784a8a67f6450f0b6fe4972f73c224df7`.

Across these three completed targets, pre-dusk errors are 0, -1 and -7 points
(MAE **2.67 points**) versus morning -28, -18 and -20 (MAE **22 points**).
This supports retaining the selected pre-dusk estimate, not declaring it
unbiased or promoting a new fit. Three nights are not seasonal holdout or
causal reward. Browser selection remains unverified by this reader. No model,
database, Item, message or equipment write was made by the score check.

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
be treated as a newly qualified training label. The exact prior installed
worker hash `c1b7a391...5f9bfb45e` was checked while the service was idle;
the diagnostic-only source was atomically installed at hash
`849a1253...b208d03` with a private mode-0600 rollback copy at
`/home/sat/.local/state/forecast-intel/pv-diagnostics-SanI7azs`.
The 06:40 timer remains active for September 30; no forecast job was run
manually. The first natural receipt, JDBC persistence and later qualified
PV-day pairing must be verified before using these fields for calibration.
Verification before install: 112 focused Python forecast/history tests, 1,910
UI unit tests and the production UI build passed. No coefficient, predicted
number, DM threshold, OpenHAB control or existing receipt was changed.

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

### Fixed-artifact closed-airflow diagnostic

The replay command formerly assumed an artifact's training code revision was
also its publication runtime revision. A later runtime optimization can change
the latter while the accepted artifact stays the same. The command now accepts
an explicit full `--expected-runtime-revision` SHA-256 pin. It verifies that
pin before simulation, still requires exact equality with the original saved
publication before any scenario run, and rechecks the runtime afterward. Its
default artifact-revision binding remains available. Ten focused tests pass.

Under the installed runtime pin
`1927d7e9c58338de103598be332a090991a926c2a8ac0acffb1c37ebbcb2747b`,
four mature six-hour publications from today's exact artifact
`e707ce61cac24571cc9d4280e54a400422f949f707cdc949481445de696ccff7`
replayed exactly. Their original indoor target receipts passed the qualified
reader. Signed errors below are forecast minus observed temperature, in °F;
issue/target times are September 29 MDT.

| Issue | Target | As issued | Assumed closed vents | Persistence | Outdoor forecast |
| --- | --- | ---: | ---: | ---: | ---: |
| 08:26 | 14:00 | +2.360 | +2.360 | −6.300 | +0.380 |
| 10:26 | 16:00 | +1.771 | +1.771 | −5.040 | +2.620 |
| 12:26 | 18:00 | −4.891 | −4.891 | +0.540 | +2.640 |
| 14:27 | 20:00 | −3.764 | −3.558 | +2.340 | +0.260 |

The four overlapping pairs have MAE 3.196°F as issued, 3.145°F under the
closed-vent scenario, and 3.555°F for persistence. The chronological
non-overlapping subset has only two windows: 3.062/2.959/4.320°F respectively.
All publications remain low confidence; the scenario supplies no observed
window/skylight state or training label. This small single-day result supports
further regime analysis, not graduation. The large 18:00 cold error persists
with zero modeled vent forcing even though the outdoor forecast is warm;
isolate solar/shade forcing and stored-heat dynamics next rather than assuming
vent timing alone accounts for the divergence.

### September 30 solar sensitivity and learned-shade origin correction

The bounded replay tool now accepts `--solar-scale 0` through `2`. It first
requires exact original replay under the pinned runtime, then changes only a
copied forecast-radiation input. It refuses nonfinite/out-of-range irradiance,
preserves captured/current facts and reports whether modeled schedule selection
changes. This is a weather-input hypothesis, never measured irradiance, action
evidence or a new calibration label. All 18 tool tests pass.

Eight sensitivity runs used the same September 29 accepted artifact
`e707ce61cac24571cc9d4280e54a400422f949f707cdc949481445de696ccff7`
and installed runtime
`fe044985ffb79b2ee911b67ceb67061c8f0b46fb8c849a08ca93bc8df5e51e27`.
Every original replay passed. At the 08:26/10:26 origins, zero forecast solar
changed the six-hour air prediction by −10.433/−9.192°F. At the 12:26/14:27
origins, both zero and 1.25× solar changed it by 0.000°F. The modeled
schedule did not change in these tests. This identified a schedule boundary,
not proof that the real house stopped receiving solar heat.

The learned nonwinter shade scheduler always initialized a new horizon as
**open**, even when that day's modeled closing event preceded the issue and
the opening event was still ahead. Those missing past transitions do not mean
that the modeled daily schedule reset. The source correction derives the
initial state from the learned cyclic close/open clock times; future transition
timestamps and their modeled provenance are preserved. Eleven new regressions
cover before/at/after both transitions, midnight-spanning intervals and tied
times. One initial test expectation incorrectly ignored a closing transition
at the first five-minute forcing; it was corrected before implementation.
All 377 affected behavior/pipeline/evaluation/artifact/dynamics/replay tests pass.

The installed behavior file remains unchanged at SHA-256
`f2bcbe5021a68cde2a824f50311acc99a499f828b490a9ba6dad57bf13489a8e`;
the source candidate is
`dedce8c8b4488aaa899b08e105adbc9486a23c1c4a77582e9e8d3ae54f8e0372`.
Their only semantic difference is that initialization. A fresh process loaded
only the candidate function into the otherwise pinned installed runtime for
offline comparison, after each original capture replayed exactly. The exact
fourteen target instants were read through the restricted indoor reader with
WH32B ID 235, original receipt/persistence/expiry checks and no numeric fallback.
All 17 matured pairs qualified, with no journal, Item, model or installed-file
write. They share one artifact and one day, not seventeen independent days.

| Horizon | Overlapping pairs | As-issued / corrected MAE °F | Non-overlapping pairs | As-issued / corrected MAE °F |
| --- | ---: | ---: | ---: | ---: |
| 1 hour | 8 | 0.917 / 0.719 | 8 | 0.917 / 0.719 |
| 6 hours | 6 | 3.197 / 2.618 | 2 | 3.062 / 2.148 |
| 12 hours | 3 | 2.792 / 1.830 | 1 | 0.905 / 0.905 |

The 12:26 six-hour estimate moved from 67.609 to 75.743°F versus a qualified
72.500°F actual: the cold error became a smaller warm error, not a complete
fix. The 14:27 estimate moved from 67.836 to 69.664°F versus 71.600°F actual.
Two later six-hour cold errors were unchanged. No 24-hour target for this
artifact had matured during the study, and no shadow graduation is claimed.

Another physical-model limitation is now explicit: `solar_indoor_closed` is
applied independently of the outdoor shade, while `solar_outdoor` applies only
with indoor shades open. The accepted outdoor-shade gain is essentially zero,
so closing the modeled indoor shade can increase heat gain when outdoor shade
is present. Existing constraints bound each shade gain below unshaded gain but
do not constrain their combined interaction. Do not fix that by imposing an
unsupported ordering between indoor-only and outdoor-only attenuation. A
versioned joint-shade model, qualified state/outcome evidence and chronological
refit must resolve it. The scheduling correction remains source-only pending
broader candidate qualification; accepted runtime, artifacts, collector and
controls remain unchanged.

### September 30 versioned joint-shade solar candidate

The split-airflow candidate now uses four independent solar regimes:
unshaded, indoor-only, outdoor-only and both shades. The old three-regime
basis is deliberately unchanged for the legacy model; its accepted
coefficients cannot be relabelled as four independently identified gains.
The candidate's seed, air/mass/glazing fitting, batched analytic-gradient
refinement and origin-aware forecast/replay all use the same four-state basis.

At fixed forcing, nonnegative joint gain is constrained no greater than either
single-shade gain; each single remains no greater than unshaded. No ordering
between indoor-only and outdoor-only is imposed. Fractional states use bilinear
area-fraction interpolation, which preserves total normalized incident forcing
and this gain order. These are **explicit model assumptions**, not proof of
causal household temperature effects or calibrated shade-position accuracy.
Other thermal terms may still increase room temperature after shades close.
Actual percent-position/source qualification remains required when hardware
arrives; the UI simulation is not a measurement.

The artifact, forecast, capture and retrospective-fold schemas are now v2,
with dynamics version 2. The closed artifact records the exact solar contract
and refuses an old v1 schema/model, missing joint coefficient or altered
fraction-model interpretation. Its complete 29-file runtime closure includes
`thermal_model/joint_solar.py`; this checkpoint's runtime SHA-256 is
`c22ffae33550507172a37eb4e2b303f04706e611ce0071de6f1187570a023fd2`.
Fresh candidates must be refitted and bound to that runtime and their actual
training rows, not assigned an earlier artifact's coefficients or identity.

No combined-state observation means an explicitly inactive zero coefficient,
not an inferred effect: a later daylight forecast activating that state is
refused. Combined-only labels without independent single-shade identification
also refuse fitting. Tests recover independently generated synthetic
air/mass/glazing coefficients, check both possible single-shade orderings,
fractional monotonicity, the original near-zero outdoor-gain paradox,
full multihorizon gradients and exact 1–72-hour replay. All 506 affected
candidate and legacy regressions pass in 74.37 seconds. This is synthetic
identification/contract evidence, not new household skill or whole-trainer
performance evidence.

This closes the versioned **source-model** correction, not its household
refit, chronological as-issued validation, accepted-artifact/runtime recovery
qualification or shadow graduation. Nothing was installed or activated;
installed dynamics remain SHA-256
`2850ce20b4df5d39866dcead43f809c81b7501153af2f6d7377b9931e65a393c`.
The accepted artifact, journal, collector, Items and physical controls remain
unchanged. Qualified independent window/skylight/shade observations and
outcomes remain prerequisites for using this model operationally.

### First qualified harvested-PV divergence — September 30

The completed September 29 native PV day qualifies at 10.396 kWh with
99.943443% original-source coverage and 2,008 valid receipts in one epoch.
Its natural 23:58:37 zero reset preserved the earlier peak and terminal
midnight coverage. The sole immutable morning issue is
`2026-09-29T12:40:17.987351+00:00` (06:40 MDT), 5.36 kWh. Its exact timestamp
and value match the frozen rolling prediction record: error is −5.036 kWh,
or −48.442% of the qualified actual.

At that origin, forecast radiation was 4.125 kWh/m², `k_res=1.3`, direct
demand 5.4 kWh, charge deficit 6.04 kWh and total modeled demand 11.44 kWh.
Morning atomic SoC reference was 72%. Resource was only 5.362 kWh, so this
issue was resource-limited, not constrained by battery headroom. The previously
documented exploratory `k_res=2.45`, `d_direct=4.1` candidate gives 10.106 kWh
on these frozen inputs (−0.290 kWh). This is its first comparison against a
qualified outcome, not a blind prospective or seasonal validation: its earlier
training labels were diagnostic and only one qualified day exists. It predicts
harvest, not unconstrained solar potential; actual irradiance/load/curtailment
still need decomposition before releasing coefficients.

No prediction or coefficient changed. The installed morning scorer already
separates qualified error scoring from coefficient release, so its next natural
06:40 run should record the error while retaining the false calibration flag.
That natural receipt/state/Item continuity remains to verify. September 29
rain remains withheld after 2,880 bounded original rows report a source-fault
or packet-replay transition; no numeric zero or historical rain fallback was
used. The BMS day passes dynamic temperature parity but remains partial from
actual pre-cadence expiry gaps, as recorded in the
[auxiliary assessment](2026-09-29-bms-aux-source-cadence.md#september-30-complete-day-reader-and-scaler-assessment).

### September 30 expanded overnight shade-origin comparison

At `2026-09-30T10:43:10Z`, the bounded fixed-artifact experiment was extended
to all matured 1/6/12/24-hour pairs issued since September 29 08:00 MDT.
Ten captured origins replayed exactly under installed runtime
`fe044985ffb79b2ee911b67ceb67061c8f0b46fb8c849a08ca93bc8df5e51e27`
before substituting only the pure `_nonwinter_shade_schedule` function from
source hash `dedce8c8b4488aaa899b08e105adbc9486a23c1c4a77582e9e8d3ae54f8e0372`
in memory. The artifact stayed fixed at `e707ce61...696ccff7`; all other
runtime functions, coefficients, weather inputs and current observations were
unchanged. Seventeen distinct target instants passed the restricted original
WH32B ID 235 receipt reader, producing 23 qualified overlapping pairs.

| Horizon | Pairs | As-issued MAE °F | Corrected MAE °F | Persistence MAE °F |
| --- | ---: | ---: | ---: | ---: |
| 1 hour | 10 | 0.8648 | 0.7066 | 0.4680 |
| 6 hours | 8 | 3.0809 | 2.6464 | 2.7225 |
| 12 hours | 5 | 3.3716 | 2.6416 | 3.4560 |
| 24 hours | 0 | — | — | — |

Chronological non-overlapping six-hour windows are only three, with
as-issued/corrected/persistence MAE 3.0033/2.3940/3.4200°F. Twelve hours still
has only one independent window (0.905/0.905/3.960°F); the ten one-hour pairs
do not overlap. All corrected intervals covered these outcomes, but these
are low-confidence forecasts from one artifact and one day, not independent
seasonal skill or interval recalibration. The candidate remains worse than
persistence at one hour. No 24-hour target for this artifact has yet matured;
the first 08:00 MDT target requires its five-minute qualification delay.

The two newly mature twelve-hour targets (02:00 and 04:00 MDT) retained cold
errors of −3.732 and −3.987°F after correction. Their outdoor forecasts were
warm by +1.22 and +2.30°F, respectively. Thus the scheduling bug explains
some, not all, cold bias; this does not isolate a physical cause. Source-only
joint-shade refit, qualified independent airflow/shade observations and
chronological day/seasonal outcome comparisons remain necessary. No file,
artifact, journal, Item, label or control changed during this experiment.

### September 30 first matured near-24-hour outcome

At 08:06 MDT the first target in the 24-hour audit bucket qualified after
its five-minute settling delay. The September 29 08:26:26.838838 MDT issue
targets September 30 08:00 MDT, within the audit's documented ±30-minute
hourly-point tolerance, not exactly 24 elapsed hours. It embeds the prior
accepted artifact `e707ce61...696ccff7`, not the newly trained September 30
artifact. Original WH32B ID 235 evidence at that target yields 68.900°F;
the published 65.516°F forecast is 3.384°F too cold. Persistence is 1.260°F
too cold on the identical target. The qualified outdoor forecast error is
−0.300°F, so outdoor-input error alone is not an identified explanation.

The original capture `20260929T142626Z-04736667d38d4183.json.gz` replays
exactly under the pinned `a4a68a17...` installed runtime, output SHA-256
`04736667d38d41836ed142dc4dc2a5233e079bf8072bbd32e82facd80541e081`.
Substituting only the pure `_nonwinter_shade_schedule` function from the
already reviewed `dedce8c8...e0372` source leaves its entire trajectory and
this target's prediction/interval unchanged. The shade-origin fix therefore
does not explain this particular miss. No coefficient, artifact, runtime,
journal, label, Item, schedule or control changed.

The broad low-confidence interval covers the outcome with 10.413°F width;
one covered outcome is not evidence of calibrated intervals or seasonal
skill. The audit scores one pair and withholds eleven future targets. It
continues to refuse operational graduation because this artifact loses to
persistence here, confidence is low, confirmed-action outcomes are absent,
and approved operational graduation thresholds are unset. Later origin-
paired day/seasonal targets and versioned physics/action-evidence work remain
necessary. This closes only the previously future-only first near-24-hour
outcome check; it does not validate the newly trained artifact's live skill.

### September 30 exact SoC origin for future energy-learning comparisons

The morning worker previously validated one fresh `BMS_SOC_Evidence_JSON`
receipt but retained only its numeric percentage in the PV issue diagnostics.
It now returns the original single receipt's provenance together with that
same value and completed-night observations. The optional `energySocOrigin`
object in the existing version-1 prediction receipt contains version 1,
`assessedAtMs`, `recordedAtMs`, `validUntilMs`, `streamEpoch`,
`evidenceSha256` (SHA-256 of the exact UTF-8 Item state), and `socPct`.
All times are UTC milliseconds. The rolling private prediction record retains
the same object as `soc_origin`.

The assessment clock belongs to the SoC input acquisition/validation, not the
earlier weather snapshot's `issuedAt`. No source timestamp or native expiry is
renewed or backdated. Invalid, duplicate-key, unavailable, future or expired
receipts return no current number or provenance; no held numeric fallback or
second live SoC read exists. Empty/full/partial SoC all preserve their actual
values. A normal enriched receipt fits the existing 1,024-byte history/UI bound;
if future optional diagnostics exceed it, the origin is omitted with a static
diagnostic rather than breaking the existing forecast display contract.

This is forward-only input provenance, **not** a qualified training label or
control authority. A learning consumer must still find the exact original
persisted source receipt by digest/epoch/times, enforce original identity,
as-of availability and expiry, and pair it with a complete qualified outcome.
Missing proof must remain unqualified. Historical percentage-only records are
not reconstructed or silently promoted. No learner/coefficient calibration
is activated, and predicted values, DM thresholds and the weather issue clock
are unchanged. Existing UI readers ignore the diagnostic object.

Before deployment, 229 forecast/advisory/source-evidence/deployment regressions
and nine focused UI receipt/comparison tests passed. A read-only probe of the
actual current atomic receipt confirmed exact value/hash/time binding. The
planned release changes only `forecast_intel.py`, with an exact installed
preimage, private rollback receipt, idle services and briefly stopped/restored
user-level forecast/thermal timers. The next natural 06:40 receipt, original
source/JDBC matching and later outcome qualification remain release checks;
no ad-hoc forecast or DM is planned.

The single-file release subsequently passed with the exact installed preimage
`849a12531c4c483c82f145b7865f292c4de7011b2606dfba3f93935b6b208d03`
and new source/installed SHA-256
`84ce22d5b0e3c43203de6aa71768d2b2bd41660a9a712e495b2721bd8a903a73`.
The private transaction/rollback receipt is under
`/home/sat/.local/state/thermal-intel/deploy-receipts/soc-origin-20260930-feygr4p3`.
All three forecast/thermal services were idle; their user timers were briefly
stopped and restored enabled/active. Accepted/candidate/previous model files
and the backtest report remained byte-identical; the PV calibration flag is
still false and the trough DM threshold remains 30%.

Independent post-release replay of the prior 04:30 natural thermal publication
under the new installed 21-file runtime pin
`a4a68a173f7a3a9c206901b1c56bbc89f1ccaf8fc7ca7c04dbd1f627295f8b8a`
was exact, with unchanged output digest `e12f318b...64a8420`. That thermal
source pin changed because the shared forecast helper is in the manifest;
no thermal dynamics, artifact, journal or collector changed. The old pinned
publication-runtime recovery archive and the exact old worker rollback are
retained. Next natural jobs remain 06:30 shadow, 06:40 morning forecast and
06:50 training. This installs provenance capture, not a qualified new learning
sample: the first natural enriched receipt and matching original JDBC source
still must be verified. Only this turn's owned synthetic fixtures were removed.

The first natural September 30 06:40 worker subsequently completed at
06:40:30 MDT. Its 691-byte receipt retains both diagnostic objects and has
exactly one matching JDBC row. The private issue record matches the same
85% source value and complete origin object. A bounded read-only query found
exactly one original SoC receipt by its exact UTF-8 SHA256; the shared strict
parser verified its value, epoch, native recording/expiry and validity at the
actual `12:40:30.518000Z` assessment. Its original JDBC row was already
available then. The earlier weather issue clock remains separately
`12:40:30.514550Z`; no source clock was renewed or backdated.

The same natural run recorded September 29's first qualified PV measurement:
10.396 kWh, 99.943443% coverage and 2,008 source receipts. Its calibration
status is explicitly `release_gate_closed`; coefficients were not promoted
from this single qualified day. Today's receipt reports the resource-limited
branch and 1.78 kWh. These checks close natural enriched-publication/private-
record/source/JDBC continuity only. Future energy-learning admission still
requires complete, qualified outcomes and proper chronological source use;
this retained input is not itself an outcome or permission to activate controls.

## September 30 natural morning snapshot capture

A restricted read-only check at `2026-09-30T23:36:54Z` selected exactly one
original `Forecast_10Day_JSON` JDBC row for generation time
`2026-09-30T06:40:29-06:00`, persisted at `12:40:30.632Z`. Its exact UTF-8
payload SHA-256 is
`a56426bbb34b52136da273ef29b68580eb30f4e751902ddeccf1346a7d915f37`.
All **1,458** expected `open_meteo_openhab` normalized facts match the immutable
analytics rows exactly by issue, target, metric, value, unit and provenance.
There are no missing/extra facts or duplicate keys. Every fact was captured
at `12:45:29.129981Z`, before the following weather revision. The existing
restricted reader was used; no grant, backfill or production write occurred.

This closes the new 06:45 calendar event's first-natural-capture gate. The
capture was not available at 06:40 and must not be backdated when reconstructing
analytics knowledge at an earlier origin. The September 27 gap remains a gap.
The producer's original issue and its source/assessment clocks remain separate.

The new source-only [charge-day extension](2026-09-27-trough-calibration-checkpoint.md#september-30-qualified-charge-time-and-afternoon-decline-targets)
now qualifies first reported full charge, no-full censoring and post-full
decline on five completed days. It keeps the accepted pre-dusk path and
historical morning prediction/scoring intact; it does not fit or promote a
new forecast from that small sample.
