# Local marginal calibration — implementation in progress

Task 7 is not complete or deployed. Complete frozen native coverage now includes
104,264 pairs across 29 bounded cohorts, with all comparisons and original
prediction math replayed. The closed optional producer/public status and
prospective cohort/subgroup reports remain required. The earlier 25-cohort legacy sample is preserved
separately. The frozen protocol is
[marginal-calibration-protocol.json](marginal-calibration-protocol.json).
No challenger is selected and no local coverage or probability qualification is claimed.

The temperature challenger learns bounded location and positive scale from the
raw mean and native p90–p10 width. Width is a predictor, not an assertion about
full ensemble variance. Missing or crossing statistics refuse that family;
zero width remains a literal input with a positive model scale floor. A separate
past-error temperature challenger has an explicitly selected half-life, bounded
correction, lead decay and cold/expired fallback. The empirical residual-quantile
benchmark remains available independently of native statistics. Its point
estimate is its locally generated median; it does not claim a distribution mean.

Solar and scalar-wind marginals use a zero atom and a positive truncated
log1p-normal component. An unsupported positive component is refused. The solar
target is one complete hour of the existing qualified **reported solar proxy**,
expressed as mean W/m². It is not calibrated irradiance, plane-of-array energy or
PV electricity. Scalar wind is a complete one-hour mean in m/s. Native boundary
means can construct its predictor; instantaneous native quantiles cannot be
averaged into hourly quantiles.

Each source/grid/measurement-quality/lead cohort has separate training and
chronological evaluation. Inner-date tuning is frozen before the earliest outer
origin. Scheduled rolling refits use only earlier, already available labels.
Historical assumed readiness and actual acquisition/completion clocks remain
separate. Retrospective observed measurement strata do not establish that a
future sensor phase was known at operational issuance. Retrospective models
cannot serve live predictions.

Predictions retain original fitted values and source/model identities before
scoring. Scoring never consults a current selector or refits. Matched candidate
support and full fallback behavior are reported separately, with explicit absent
regimes, local hours and seasons. Native p50 absence remains absence; a modeled
median is separately labeled. Raw p10/p90 can support interval score, coverage
and width, but do not establish a full distribution, CRPS or WIS.

The [population inventory](marginal-population.json) records all 25,745 replayed
pairs across 25 cohorts: 20,071 temperature, 1,738 scalar wind, and 3,936
forecast-to-proxy matches. The 43 unique proxy hours span three local target
dates (the last is a single midnight endpoint); repeated forecasts do not
increase that target count. Fewer than 48 training targets is an explicit solar
support blocker. All 25 legacy-parent cohort comparisons are complete; fitted originals and score replay are
verified in [the experiment summary](marginal-experiment.json).

Software currently covers the kernels, original-source adapters, chronological
comparison, immutable prediction scoring and bounded offline experiment entry
point. Actual-time candidate fitting, original model/source retention and prospective
issue preparation now exist. Complete native population expansion and comparisons
are verified. Durable original emission/confirmation and bounded monitor scoring
now exist; the closed producer/public status and prospective cohort summaries
are still required. The default raw temperature range and current point forecasts
remain independently usable.


## Legacy-parent comparison results

All 25 experiments finished separately within the 120-second bound (maximum
25.80 seconds; 133.64 seconds summed sequentially). They retained 379 models and
7,980 original outer prediction records. Independent replay checked source
packages, training membership and availability, empirical quantiles and adaptive
weights, fitted prediction math, and all matched/fallback score reports. These
are retrospective diagnostics, not forecasts issued before their outcomes.

Three cases pass the frozen score/subgroup review gate:

| Candidate and comparator | Lead | Matched targets / local dates | Result |
| --- | --- | --- | --- |
| Adaptive temperature vs raw native mean | 24–72 h | 90 / 4 | MAE 2.35548 → 2.27889 °C; 3.25% improvement |
| Temperature location/scale vs empirical residual intervals | 1–24 h | 94 / 4 | IS80 7.01087 → 6.72161 °C; 4.13% improvement |
| Nonnegative scalar wind vs empirical residual intervals | 1–24 h | 167 / 10 | IS80 3.15230 → 2.17975 m/s; 30.85% improvement |

No compatible original incumbent point predictions were retained for this
population, so the adaptive comparator is explicitly the raw mean. It does not
measure a gain over today's selected local correction. Other temperature
comparisons fail supported subgroup/gain gates or have insufficient support.
Both temperature review cases cover autumn and only four local target dates.
The temperature normal case passes against the empirical benchmark and fails
its separate comparison gate against raw native bounds.

Wind's weighted coverage is 0.8014 versus empirical 0.7436, with width 1.3498
versus 1.7439 m/s and point MAE 0.44065 versus 0.70297 m/s. This meets the limited
coverage/date support check for further review. Its observations are explicitly
unqualified numeric history, and its outer cases contain neither observed zero
wind nor any season except autumn. Neither its zero atom nor all-season
calibration is established. Recorded-ingestion outer cohorts have no eligible
past-available fitted candidate; their explicit raw fallback remains visible.
Solar's 43 distinct qualified target hours cannot supply 48 training targets;
all solar model comparisons remain insufficient rather than silently omitted.

Every candidate remains unselected and locally unqualified. The three score
cases merit prospective shadow evaluation under their own source/measurement
identity; they do not authorize a probability display, deployment or actuation.


## Full-source coverage correction and prospective preparation

The [source-scope audit](marginal-source-scope-audit.json) replays all 347 frozen
forecast originals against the original measurement grids. It identifies 81,731
temperature and 18,597 scalar-wind matches. Together with 3,936 solar-proxy matches,
the complete native scope is 104,264 pairs. The legacy parents omit 61,660
usable temperature pairs and 16,859 wind pairs, mainly at hourly longer leads
and additional recorded origins. The old comparative scores remain evidence for
their declared sample; they cannot close the all-eligible-data requirement.
Those additional matches are now included in separately identified coherent datasets
and fresh comparisons under unchanged numerical settings. All original values,
targets and availability clocks survived repartition/readback. No old model or
score receipt is relabeled.

The explicit actual-time fitter retains candidate models, literal training inputs
and preprocessing source bytes. Its compatibility guard covers the interpreter
and numerical binary hashes as well as preprocessing code and package versions.
Preview creates no state namespace; explicit retention installs no current model
selector. Historical assumed-readiness records are refused for these prospective
artifacts. Original future labels remain ineligible until actual acquisition.

A fresh private probe on the legacy recorded-ingestion population found 51
distinct near-term temperature targets across three local dates, sufficient to
fit its three predeclared candidate families at the actual current clock.
The other five recorded cohorts retained explicit cold bundles. A qualified
current native temperature receipt was acquired before the new decision; the
compiler then prepared and fully replayed 88 raw/local rows from two exact
retained weather originals: 24 local temperature rows and 64 raw fallbacks.
The issue is **prepared, unissued and unqualified**. No production configuration,
model selector, Item or cache was changed. [Preparation evidence](marginal-prospective-preparation.json)
records the current prototype and its remaining integration work.


## Complete frozen native comparison and current preparation

The [complete inventory](marginal-native-population.json),
[comparison report](marginal-native-experiment.json) and
[verification](marginal-native-verification.json) supersede the legacy sample for
full-source coverage. They retain 81,731 temperature, 18,597 wind and 3,936
solar-proxy matches from all 347 frozen source originals. Oversized coherent
groups are partitioned into adjacent whole-native-lead blocks chosen from counts
only, within the original source, measurement quality, grid, timezone and broad
lead class. The largest of 29 cohorts has 9,954 rows, below the 10,000-row bound.
An earlier exact-hour partition sensitivity pass (288 cohorts, 475 models,
40,908 outer records) remains preserved separately; it is not pooled with the
canonical results.

All 29 canonical experiments completed within 120 seconds each (maximum 38.70
seconds; 360.85 seconds summed sequentially). They retained 877 fitted models
and 40,681 outer prediction records. Independent replay verified source-package
bytes, original datasets, model/training membership and past availability,
empirical weighted quantiles, adaptive decay, normal and nonnegative prediction
math, and every matched/fallback score and gate. These remain retrospective
experiments, not outcomes from operationally issued candidates.

Twelve comparison gates pass: eight temperature comparisons in limited
source/quality/lead cohorts, and nonnegative wind versus empirical intervals in
all four broad lead ranges. These are overlapping comparisons, not twelve
independent discoveries. Temperature review cases have only three to seven
local target dates, below the eight-date probability-review minimum. One
long-lead temperature normal case has 97.1% coverage; another has 67.7% coverage,
so better interval score alone does not establish 80% calibration. Wind's
score gains range from 17.4% to 34.6%, with 78.7–85.4% weighted coverage on
157–180 targets over ten or eleven local dates. Its measurement source remains
unqualified numeric history; no physical or all-season probability claim follows.
All failures, absent regimes, subgroup supports and fallback-inclusive results
remain in the complete report. Solar still has only 43 distinct qualified
proxy hours, below the 48-target training minimum. No contender is promoted.

The [new actual-time preparation](marginal-native-preparation.json) uses all six
recorded-ingestion cohorts of the expanded collection. Near-term temperature
has 53 past-available targets across three local dates and fits the three frozen
families. Other cohorts remain cold: mid-term temperature has 29 targets across
two dates; wind has 29 targets across three dates or 19 across two; solar has 43
or 34 targets across three dates. Repeated forecast matches do not inflate those
target counts. A fresh native origin receipt acquired before the decision yields
88 fully replayed rows: 24 local temperature candidates and 64 raw fallbacks.
Six private original artifacts are retained with literal training/source bytes;
there is no selected pointer. This preparation is unissued and unqualified, and
protected configuration/selector bytes are unchanged. Durable emission,
confirmation/recovery and bounded monitor scoring are implemented below. The
closed producer/public status and prospective cohort/subgroup reports remain
required.


## Durable shadow issuance and scoring progress

The [durable progress evidence](marginal-durable-progress.json) records a new
private shadow issue prepared from fresh native origin evidence and confirmed
at 2026-10-22T03:47:40.637475Z. Its 88 literal raw/local rows are frozen with the
original six fitted artifacts, training inputs and source bytes. The 24 local
temperature rows reuse the original fitted values; no refit or selector change
occurred. Restart readback reconstructs the same original issue and emission.
The separate index registers 31 fixed future targets. No future label was
queried or scored, and the installed household cache remains unchanged.

Preparation alone is not issuance. The queue retains original inputs before
cache publication, confirms actual cache write/readback completion, and preserves
its emission receipt. Recovery without that receipt uses the actual recovery
clock and withholds already-past targets from as-issued scoring. Later scoring
reads saved predictions and literal first-acquired observations, never current
weights or a regenerated view. Native temperature, qualified reported solar
proxy and explicitly unqualified numeric wind retain their source meanings.
The seven-day observation-arrival allowance applies to actual first acquisition;
later discovery can reuse a timely original capture, including after 336-hour
maturity. Completed scores survive restart and are not reread. Preview changes
no retained issue, emission, observation or index bytes.

The optional monitor reserves at most eight labels inside the existing global
64-label budget. Unknown partial failures consume that reservation; resource
failures remain global stops. It uses existing restricted local readers and is
disabled when its separate index is absent. The 64 MiB index and existing shared
immutable-object cap remain explicit, with no automatic pruning. Current tests
pass 658 backend cases and 165 subtests; four isolated SDK-profile skips remain
named. Task 7 still requires the closed optional producer profile, public GET
status, complete prospective cohort/subgroup report, and remaining capacity and
fault verification before its completion gate. No household service is enabled
or changed by this private probe.
