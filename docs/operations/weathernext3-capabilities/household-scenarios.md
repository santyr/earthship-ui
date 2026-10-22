# Household weather scenarios — implementation in progress

Task 8 remains in progress. Its deterministic construction, one bounded joint
method and initial weather-scoring kernels are implemented locally. Retained report publication/replay, training-only joint-extreme diagnostics and
source-replayed household outcome scoring are also implemented. The original native air/wall adapter and explicit default-off source-adapted
producer now pass focused verification. Actual eligible-data assessment, experiments
and integrated task gates remain required. Nothing
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
proxy weights and electrical corrections are never substituted. This separate response family has no
north-wall output, which remains explicitly unavailable. The native adapter instead
uses the literal original air/wall model, initial state, fixed actions and native
geometry. Its central case must match every original hourly state within 1e-9 °F.
The original weather-conditioning capsules are reapplied with their existing
mathematical kernels; changed inputs are never relabeled original receipts.
Current producer identity and every fitted dependency remain strict requirements.

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
product. Joint-extreme thresholds use the complete eligible training population,
one representative block per template date and equal actual target-date/unique-
target weighting. The p10/p90 thresholds never use assessment outcomes. Counts of
hot/calm/low-solar targets are descriptive counts, never reserve-risk probabilities.
Late templates remain withheld, and fewer than eight template dates leaves the
thresholds unavailable.

Household targets replay literal original energy-hour, atomic BMS endpoint and
native v2 temperature-source packets through their existing strict readers. They
retain actual collection clocks, policy and hardware epochs, exact target windows
and an independent nominal-bank binding. Potential-PV proxy energy and captured
controller output stay separate. Energy scores require complete matching coverage;
censoring or missingness never becomes a zero observation. The measured SoC
minimum uses the same origin/elapsed-hour endpoint grid as this nominal simulation,
not a continuous trough. Indoor and north-wall observations remain separate; an
unavailable model prediction is withheld even when its measurement exists. A
rolling 24-hour target is not relabeled a local-calendar day.

Original reports retain input forecasts, all template originals, fixed household
assumptions, literal production/companion source bytes and numerical environment,
as well as all constructed projections. Replay rederives those outputs and refuses
source/environment changes; historical originals require their original producer.
Public projections omit private capsules/paths and identify actual native versus
total-only solar support. Explicit retention keeps immutable private reports under
the existing shared 2 GiB/10,000-object cap. Expired reports can be retained for
replay but cannot refresh the advisory cache. Later assessment uses these original
predictions and raw qualified sources without fitting or consulting a model
selector. The source-adapted standalone producer retains the original energy and plan
receipts too, revalidates their raw configuration bindings on replay, and derives
new outputs from those inputs. No existing service publishes these new reports.

Verification so far: the affected household/report tree passed 837 backend tests
and 165 subtests, with four named unchanged isolated SDK-profile skips. That run
preceded the final later-assessment and public-fallback additions; all current
scenario, weather score, household target and report tests pass 49 cases. Cases
include original replay, strict source/cohort/availability refusal, shared physics,
modeled night zero, original-block selection, training-only thresholds, source and
error corruption, archive-cap refusal and closed-form empirical energy scoring.
These counts overlap and are not added as unique coverage. Real Task 8
stress/household experiments and the task completion gate are still pending.


`python -m weather_learning.scenario_worker --print-runtime` inventories the new
producer. Its explicit private 0600 profile uses schema
`earthship-optional-household-scenario-producer/v1` and the exact fields `enabled`,
`state`, `energy_path`, `template_paths`, `observation_cohort_sha256` and
`runtime_sha256`. The state and original paths must be absolute; `energy_path`
identifies an immutable owned energy receipt with its adjacent original plan.
No current selector is consulted. `enabled=false` is the default operating choice.
Run `--profile /absolute/private/profile.json` for a read-only preview, adding
`--apply` only for the separate private advisory namespace. The checked protocol
file must be owned and non-writable by group/others. The worker enforces a 90-second
deadline and the frozen combined residual byte/row budgets. A failure after a
publication attempt reports uncertain retention, rather than promising unchanged
state. No new service/timer, cloud request, database query, Item write or equipment
action is included.

The actual October 22 read-only probe used the installed original energy/plan
and native model. Snapshot restoration succeeded. The new producer refused the
native context because its original runtime differs in nine identity fields
(including five weather-source hashes and numerical dependencies). No source guard,
weight or original capture was retagged. Both disabled and enabled preview paths
created no state. A compatible retained producer and actual complete-source
experiments remain necessary; synthetic fixture runtime injection is explicitly
separate from this unmocked compatibility result. This disposition does not prove
that native thermal physics changed, nor grant the current process permission to
reinterpret the old model. See [adapter verification](scenario-adapter-verification.json).

Current native-adapter/source-worker verification passed 68 focused tests and the
816-case affected backend suite plus 165 subtests. Four named isolated SDK-profile
skips remain explicit; overlapping counts are not added. Complete native conditioning
requires its original time grid; unsupported partial grids are refused. The earlier
837-case run above precedes these additions and is not evidence for them.
