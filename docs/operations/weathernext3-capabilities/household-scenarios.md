# Household weather scenarios — implementation in progress

Task 8 remains in progress. Its deterministic construction, one bounded joint
method and initial weather-scoring kernels are implemented locally. Original-bound
report publication/replay, joint-extreme and household outcome assessment, complete
wall-model integration and actual eligible-data assessment remain required. Nothing
is installed, selected or physically/statistically qualified by these tests.

The [frozen protocol](scenario-protocol.json) was committed before any real Task 8
outcome assessment. It fixes three conditional cases: the original central means,
half the mean solar energy, and a 3 °C warmer/1.2-times-solar case. All cases use the
same explicitly versioned PV, nominal-storage and supplied thermal response
arithmetic. They are sensitivity inputs, never percentile battery trajectories.
The native component path is a separately named unselected model, not the currently
selected serving package or a reason to reuse its electrical gains.

`weather_learning.scenarios.ScenarioForcing` retains the literal original verified
native or historical forecast, frozen protocol and construction recipe. Validation
rebuilds every row and refuses resealed edits. Operational native forecast
validators reject these constructed objects. Only the pure component-model input
boundary admits their exact type, under
`constructed_unqualified_weather_sensitivity`. Original forecasts and source
capsules remain unchanged. Temperature values stay point values and solar stays
ending-hour mean energy. Common solar scaling preserves the original direct/total
relation. Existing native reconstruction and terrain masking keep modeled night
solar at zero and preserve diffuse light behind the skyline.

The single joint method adds complete multivariate residual blocks for temperature,
scalar wind and physical GHI. It retains original forecasts and observation rows,
actual acquisition clocks, grid/cohort identities and the full residual vector.
A reported local solar proxy cannot enter as physical GHI. Templates must cover
the same horizon and exact local hour/fold sequence, share the forecast grid and
observation cohort, and be completely available before the new decision. The
training window is 28 days with eight distinct target dates required. One
representative original block per date is chosen by sorted original hash before
fixed-seed sampling, so repeated forecast issues do not increase a day's sampling
mass. Seed 0 selects at most six complete blocks; time steps and variables are
never shuffled independently. Original inputs are bounded to 16 MiB/10,000 rows.

Constructed wind/solar are nonnegative. Solar perturbations retain the original
native mean direct fraction, a fixed assumption rather than inferred direct-beam
uncertainty. Unsupported fractions or out-of-domain constructed trajectories are
refused. Sampling and reconciliation remain visible in the original recipe. Missing
future-label availability, phase/cohort mismatches and sparse support produce an
explicit `insufficient_evidence` disposition. No upstream members or ECC are
claimed.

`propagate` uses the existing component PV model and nominal constant-load storage
simulation. It records the exact PV version and source/geometry/configuration
identities. A supplied, issue-available component-response model can project indoor
air using its separate physical-component feature contract; legacy local radiation
proxy weights and electrical corrections are never substituted. This model has no
north-wall output, which remains explicitly unavailable. Supporting and assessing a
suitable original wall trajectory is still Task 8 work.

Weather is the varied scope. Household load, initial state, capacity, acceptance,
action state and fitted parameters are held fixed and listed as assumptions.
Weather-only sensitivity is not total household uncertainty. Reserve-breach and
overheating probabilities are withheld, and all action and probability flags stay
false.

`weather_learning.scenario_scores.assess_joint` scores unique original joint
members against complete matching physical observations actually available by the
assessment. It excludes the origin/past rows. Whole future trajectories use equal
local-member mass and declared scales of 5 °C, 3 m/s and 300 W/m², with Euclidean
length normalized by the square root of target count. The variogram uses p=0.5,
all scaled time/variable pairs and inverse one-plus-hour-lag weights. Reports also
retain point-mean and ramp errors, lag-one/cross-variable correlations and finite
trajectory-range coverage. Constant-series correlations are undefined, not zero
skill. Stress cases cannot be passed off as an empirical joint distribution.
The score is a retrospective diagnostic, not proof of an as-issued probability
product. Joint-extreme and household utility fields currently explain their missing
assessment inputs; those software paths remain unfinished.

Verification so far: the affected pre-scorer tree passed 705 backend tests and
165 subtests, with four named unchanged isolated SDK-profile skips. The current
scenario and scoring suites pass 23 cases, including original replay, source/cohort
and availability refusal, shared physics, modeled night zero, original-block
selection, resealed corruption and closed-form empirical energy scoring. These
counts overlap and are not added as unique coverage. Real Task 8 stress/household
experiments and the task completion gate are still pending.
