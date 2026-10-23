# Household weather scenarios — locally verified advisory

Task 8 is complete locally. The [final verification](scenario-final-verification.json)
binds its scenario software, complete frozen-population experiments, matching
outcome assessment and five original-producer contract checks. The optional
producer is off by default. Scientific support remains insufficient for physical
calibration, local probability qualification or selecting these models for serving.
The capability branch is not deployed. Tasks 9–11 continue separately.

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
refused, including wind outside the shared component model's 0–250 mph domain.
A refused residual construction is counted explicitly before propagation. Sampling and reconciliation remain visible in the original recipe. Missing
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


The next original-producer assessment succeeds under the retained deployment's
actual interpreter and source imports, with the new construction adapter loaded
under a separate package name. Its original runtime guard passes without replacing
any module or source identity. All three 24-hour native air/wall stress cases ran;
the central trajectory matches the literal original within 1e-9 °F. Exact adapter
and original source packages, scripts and energy/plan input receipts are retained.
The three conditioning mathematical source files are byte-identical across those
packages. The standalone default-off current-runtime worker still refuses the old
model; a maintained retained-producer handoff remains required. See
[original producer verification](scenario-original-producer-verification.json).

Actual source inventory found eight verified retained stages and 383 energy
forecast receipts over three local dates, with all adjacent plans present. Of those
receipts, 339 report conditional nominal-storage inputs and 44 name AC-load/skew
limitations. The additional [experiment protocol](scenario-experiment-protocol.json)
freezes one earliest original per UTC issue-hour, independently of its numerical
output or later outcomes. It retains missingness, never replaces a refused origin,
and binds all 37 selected receipts before assessment. Experiments use at most eight
origins/90 seconds per batch and all five existing horizons. This is an explicit
hourly representative experiment over the complete inventoried population.

Native issue seconds remain exact. Household targets now accept fractional origins
and integrate the native qualified power intervals over their precise overlap.
Complete-bin censoring rules remain unchanged; no five-minute total is prorated.
Missing boundary-hour power withholds energy while independent battery/temperature
targets can still be scored. The new regressions failed before repair; 61 combined
current native/household/report/energy/battery tests pass (overlapping earlier runs).
No actual matching household-outcome experiment is claimed complete by this
source/geometry/projection progress.


Before opening matching outcome values, registered scoring history revealed seven
additional historical stages outside that first native-state directory. The
[current population](scenario-population.json) includes those registrations and
retains the original origin cutoff. It contains 648 distinct receipts across
four local dates and 17 verified stage directories (some have no forecast before
the cutoff). The experiment-protocol v2 records this pre-outcome population
amendment and binds the new complete selection; the earlier 37-origin protocol,
selection and preliminary projection batch remain retained. Construction policy,
model choices, all five horizons and earliest-per-hour sampling stay unchanged.
A seven-origin first attempt hit its 90-second bound; two-origin partitions passed
without increasing the limit or replacing any origin. All 819 current affected
backend tests and 165 subtests passed, with four named isolated SDK-profile skips.


The retained-source run identified two older native radiation contracts: one uses
the original ending-hour right endpoint for each step, and one linearly
interpolates the original scalar radiation field. Those versions are recognized
by the exact retained source-file hashes; unknown legacy versions are refused.
Their original fitted input bases are preserved, separately from the new conserved
component PV model. The newer native model keeps its overlap-mean contract.
Original air/wall central parity remains mandatory for every accepted origin.
The constructed state adapter also directly implements the existing qualified
BMS/bank/AC-load contract, so older producers do not need the later calibrated
sidecar package. No original producer file or model weight was changed.

Three portability regressions failed before repair; 48 focused worker/native/
target/report cases pass afterward. An actual older-source batch now passes:
two origins, six full native trajectories, 30 component projections across all
five horizons, and central parity within 1e-9 °F. Complete experiment execution
and matching outcome assessment remain in progress.


One retained earlier conditioned producer also uses the corrected ending-hour
right value. That exact conditioner source is now recognized separately; its
original calibration/feature functions are imported from the original producer,
and the wrapper preserves its corrected right-hour value across fractional
boundaries. The native overlap-mean conditioner remains separate. The new
regression failed before repair, then 49 focused cases passed. Its real original
source batch passed two origins/six 24-hour trajectories/30 component projections
with central parity within 1e-9 °F. Existing source guards, weights, admissions
and expiry clocks are preserved.


The complete frozen projection experiment is now verified: all 32 bounded
batches account for all 62 original forecasts, with 57 projected origins and five
withheld for original BMS/load source skew. It retains 855 component projections
(three cases × five horizons) and 171 full 24-hour original native air/wall
trajectories. All central native trajectories match their literal original with
maximum absolute difference 0 °F. Verification checks every retained input/package
digest, every origin exactly once, modeled energy/storage balances, bounded SoC,
and 57,804 zero-valued modeled nighttime segments. The three original forcing
families remain separate (34 overlap-mean, 20 right-selector and three linear
origins). Counts of repeated segments/hour uses are not independent evidence.

The [projection experiment](scenario-projection-experiment.json) gives descriptive
ranges of hypothetical changes from each central case. Those are neither
prediction intervals nor measured forecast errors. Source inputs are qualified at
the original issue clock using the existing fixed-state contract; the inventory's
original energy-receipt status was assessed later. The fixed-state issue-time
contract admits four additional origins; their original publication statuses
remain preserved as separate facts. No old output is
used as an invented load, capacity or measured state. This distinction changes
none of the raw receipts. Matching actual outcome assessment is still pending.
The current affected backend suite passed 823 tests and 165 subtests with four
named isolated SDK-profile skips after the legacy-conditioner change.


Matching outcome acquisition is complete for the collection cutoff recorded in
[the source audit](scenario-outcome-acquisition.json). All 138 BMS endpoints and
86 native air/north-wall targets per role replay as qualified under the original
hardware/sensor phases. There are 67 original energy hours: 31 reused immutable
archive receipts and 36 new captures through the existing restricted read-only
role. Every raw packet, acquisition envelope and source identity is retained
privately. Original forecasts and the selected origin population are unchanged.
These are source-admission counts; complete energy-window/censoring checks and
matched model errors are assessed separately. Full-population outcome scoring and independent original-source verification
are complete for that fixed collection cutoff.

A measured 24-hour target uses 25 hourly originals totaling 38,101,333 bytes.
Household target records now admit 48 MiB, with at most 25 original energy hours
and a 16 MiB limit per hour. Full assessments admit 64 MiB for the target collection
and weather observations. The increased aggregate limits preserve complete raw
receipts and replay. The frozen forecast/template construction limits retain their
original scope. Focused verification passes 53 tests, including full-day target
replay, refusal of oversized originals/collections and assessment replay above
16 MiB. The final task gate and maintained retained-producer handoff are verified below.


The [complete outcome experiment](scenario-household-outcomes.json) accounts for
all 62 selected originals: 57 projected and five withheld for source skew. There
are 264 mature origin–horizon assessments; 21 further horizons were immature at
the fixed acquisition cutoff. All 264 air and north-wall endpoints are observed.
There are 254 matching nominal-SoC grid minima; ten windows are withheld because
the original model's initial SoC differs from the independently acquired origin
endpoint. Each available target is compared separately with all three cases.
Four independent verification partitions rederive observed energy coverage,
nominal-SoC minima, temperature values, full original target identities and every
reported error without refitting. They verify 2,346 application error pairs and
replay 3.73 GB of overlapping original target content through retained source
references. Repeated cases/horizons retain explicit support counts; they do not
create additional independent dates.

At 24 elapsed hours the central case has 41 air/wall comparisons over three target
local dates: descriptive MAE is 3.94 °F for air and 1.19 °F for north wall. The
39 matching battery comparisons have MAE 5.38 nominal-SoC percentage points.
These are conditional comparisons against actual behavior with the original
fixed load, state, actions and coefficients. They do not establish as-issued
forecast skill, causal benefit, total household uncertainty or a qualified risk
product. The report retains all three cases and all five horizons without
selecting a winner from their errors.

The 67 energy-hour originals contain qualified power over nearly their entire
span, with no ambiguous sequence failures, but every hour has a subsecond
publication gap. Controller output has 3599.635–3599.746 qualified seconds per
hour. Exact full-window captured-energy totals remain unavailable; the gaps are
not silently filled. The potential-energy proxy additionally has only 32 eligible
low-SoC/charging bins out of 804 five-minute bins. These explicit coverage and
censoring limits prevent daily-energy MAE from being asserted on these originals.
Covered-time energy remains distinguishable from an exact daily total.

The [joint-source audit](scenario-joint-evidence.json) checks all 104,264 pairs in
the complete frozen native marginal corpus: 81,731 temperature, 18,597 wind and
3,936 reported solar-proxy pairs. Their actual acquisition followed their own
original forecast issue. The 43 unique source-qualified solar-proxy hours span
three dates and do not supply physical GHI. The 388 unique wind observation
targets have no sensor-health receipts. Consequently there are zero complete
qualified physical temperature/wind/GHI blocks and zero eligible template dates,
below the frozen minimum of eight. Actual multivariate energy/variogram scores,
dependence/ramp/extreme diagnostics and trajectory coverage are explicitly
unavailable. Synthetic software tests exercise their formulas; no substitute
physical measurements, upstream members, ranks or risk probabilities are created.


The maintained retained-producer path uses the same optional worker with profile
schema `earthship-optional-household-scenario-producer/v2`. It adds a closed
`retained_producer` object containing schema
`earthship-retained-native-scenario-producer/v1`, an explicit absolute `stage`,
and its original `deployment_sha256`. All v1 fields remain required, including
`enabled`, `state`, `energy_path`, `template_paths`,
`observation_cohort_sha256` and `runtime_sha256`. Obtain the current parent pin
with `python -m weather_learning.scenario_worker --print-runtime` under the
intended interpreter and source package. An operator must explicitly enable the
private profile. Preview uses `--profile /private/scenario-profile.json`;
`--apply` permits only the separate private report archive and advisory cache.

The bounded child runs `/usr/bin/python3` with the verified original stage's
global imports and loads the new adapter in a separate namespace. It preserves
the original capture, fitted model, source/environment checks and native physics.
The current component PV/storage calculation remains source-bound in the parent.
Retained reports include both complete literal production source packages and
both numerical environments, original energy/plan bindings, prepared household
inputs and native trajectory identities. Restoring a context rederives its
preparation. A changed stage, adapter, binary, model identity or response binding
is refused. Per-opportunity memoization keeps repeated report replay bounded and
rechecks original source and binary bytes before reuse.

All five retained forcing/conditioning contract groups reproduced all original
thermal fields and full trajectories exactly for central, reduced-solar and
warm/high-gain cases. Two additional forcing/conditioning labels are recorded
where an earlier experiment lacked them. The five real private archive operations
took 42–66 seconds, within the existing 90-second opportunity. Expired historical
reports did not refresh the advisory cache. Fresh-cache publication, disabled
profiles, original-model substitution, corrupt replies, changed sources/binaries
and partial-publication behavior are covered by the maintained tests. The final
suite passed 832 cases and 165 subtests; its four normal-profile SDK skips were
executed separately under the pinned SDK with outbound sockets blocked, all four
passing without skips. No service, controller, selector, fitted parameters or
operational cache was changed by this task.
