# Local marginal calibration — implementation in progress

Task 7 is not complete or deployed. The frozen protocol is
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
support blocker. Actual cohort comparisons are in progress.

Software currently covers the kernels, original-source adapters, chronological
comparison, immutable prediction scoring and bounded offline experiment entry
point. Actual complete-cohort results and prospective monitor/status wiring are
still required. The default raw temperature range and current point forecasts
remain independently usable.
