# Thermal model graduation: active goal

Owner: Hex. Hexmem task99. Operator explicitly added completion of the requisite
work to move the model out of shadow on September20,2026. This is part of the
broad Earthship/OpenHAB goal, not an indefinite optional follow-up. Do not rush
the evidence gates or equate a working shadow publisher with completion.

## Current evidence, September20

The latest [October 2 late-evening independent-window comparison](2026-09-30-forecast-input-capture.md#october-2-late-evening-independent-window-solar-rejection)
rejects the blanket 90% solar hypothesis: both selected six-hour windows and
both mature 12-hour targets worsen in aggregate, despite pooled six-hour MAE
improving on one large miss. Two 12-hour errors have opposite signs; closed-vent
sensitivity helps one and hurts the other. Current-artifact 24-hour outcomes
remain immature. Keep the model in shadow and prioritize independently known
shade/window/skylight state and chronological identification; do not promote
an unqualified scalar correction or turn chat recollections into labels.

The October 2 evening [first natural radiation-enabled current-input
publication](2026-10-02-radiation-history-and-shade-collision.md#first-natural-qualified-current-publication--october-3-0336z)
now passes actual timer/capture/Item/JDBC, exact replay and cold-code recovery
checks. Its private rollout proof is pinned. This closes delivery, not
complete-day radiation learning, confirmed actions, predictive skill or
graduation. Existing numerical and independent-observation gates still apply.

For the latest October 2 evening evidence, see the
[mature current-artifact targets and exact solar tradeoff](2026-09-30-forecast-input-capture.md#october-2-evening-mature-12-hour-outcome-and-batched-scoring).
One qualified current-artifact near-12-hour target is substantially better than
persistence, but it is only one target. A 90% solar hypothesis improves the
largest of four overlapping six-hour misses while worsening the other three
and the selected independent window. No coefficient or forcing multiplier is
promoted. Efficient shared-grid auditing now preserves exact original scores;
it does not close confirmed-action, independent seasonal skill or reviewed
numerical graduation gates. The model remains in shadow.

The scheduled trainer uses the400-day default, bounded physical fitting and
chronological walk-forward evaluation. Today's accepted artifact is in use.
Live Thermal_Model_JSON at23:29:48Z reports low confidence, reconstructed action
labels, no physically valid bounded candidate and no alternate schedule.
Forecast temperatures already appear in the UI. Advisory graduation is distinct
from training-artifact acceptance and from automatic actuation.

## September 29 operational checkpoint

The capture-strict read-only 24-hour scorer has 62 matured published pairs,
but only six independent, non-overlapping targets across several runtime
revisions. On those six, model MAE is 3.5438°F versus 2.6100°F for
same-origin persistence; nominal interval coverage is 4/6. All scored
publications are low-confidence. No 24-hour target from today's accepted
revision has matured, so neither pooled bias nor a six-day result licenses a
coefficient change or shadow exit. The next target from today's captured
14:27 MDT publication is due after September 30 14:00 MDT plus the scorer's
five-minute maturity lag.

The accepted artifact's exact source was recovered and preserved in the
[private replay recovery point](2026-09-28-thermal-replay-recovery.md). An
exact as-issued replay found that assuming closed vents raises one 12-hour
hallway forecast by 0.656°F. This is modeled sensitivity, not confirmation
that vents were closed, and does not explain the entire operational low bias.
The current `vent_open` forcing is a single coarse state and does not
distinguish window from skylight airflow. Its physical mapping must be
resolved before a partly open configuration is turned into a signed action
label through the collector. Chat reports alone remain diagnostic context.
The operator has now chosen separate window and skylight action states; see
the [source-only state decision](2026-09-29-thermal-window-skylight-state.md).
Neither opening is yet mapped to legacy `vent_open`, and the collector remains
off while the journal vocabulary and model revision are qualified.
The approved operator bunker passed a client signing challenge and both
signed inbox routes were verified, but the thermal confirmation collector
remains off pending a reviewed private prompt policy, journal/SQLite recovery,
and an attended genuine reply/acknowledgement trial. Do not count an operator
recollection or an unanswered question as a training label.

## Required work and evidence

The [September20 baseline audit](2026-09-20-thermal-graduation-baseline.md)
records errors, interval coverage and absent confirmed action evidence. It also
identifies evaluation-only persistence blending: resolve forecast-output parity
before tuning or using those metrics to qualify the displayed trajectory.

Source-only parity repair now removes evaluation-only blending and advances the
model/backtest schemas to v5/v3. Daily extrema, horizon errors, candidate scoring
and published states use raw physical simulation. Legacy v4/v2 evidence is
explicitly rejected by the new validators; it must not be relabeled or used to
seed a new accepted registry. Production still runs the previous runtime and
accepted model. Before cutover, run the new trainer with a separate candidate
state directory, verify recalculated residual intervals and unchanged acceptance
gates, and retain the old runtime/model pair for rollback. If the candidate
fails, continue tuning rather than deploying this incompatible runtime alone.
Historical weather/action provenance and live no-candidate replay remain open.

An [isolated qualification run](2026-09-20-thermal-v5-qualification.md) used
the frozen parity revision and original historical window. Its source audit
confirms conditional hindcast inputs, not operational forecast replay; retain
that distinction when interpreting any successful training result.
The run was refused on 24-hour error. An
[exploratory chronological blend audit](2026-09-23-thermal-historical-blend-audit.md)
found a possible 24-hour ensemble improvement in a later warm-only segment;
it is a tuning hypothesis, not graduation evidence or a winter result.
A bounded source-only forecast archive reader now enforces `captured_at` and
`issued_at` cutoffs for complete single-issuance weather forcing. Integrating it
with origin-time indoor state, action knowledge and scored outcomes remains open.

September23 follow-up: `thermal_model/action_history.py` now reads action and
mode journal rows in one bounded, read-only repeatable-read snapshot, requiring
both reported `received_at` and actual receipt-row `created_at` to precede the
origin. Corrections arriving later cannot rewrite historical knowledge. The
operational-origin assembler accepts this as an explicitly unqualified action
snapshot alongside the existing captured weather and three qualified temperature
receipts. A live read-only 14:45Z assembly returned26 weather bracket rows,
all three initial temperature roles, known Kiva/outdoor-shade history and no
vent/indoor-shade history. The Kiva entry is model-inferred; this does not prove
the actions happened or establish future action forcing. Scored operational
replay, outcome evidence and advisory graduation remain open.

A [read-only operational-origin census](2026-09-23-thermal-origin-census.md)
then found63/63 hourly origins with complete 24-hour captured weather,
receipt-qualified initial/outcome temperatures and as-of journal snapshots.
Their naive persistence MAE is2.0314°F, but these are overlapping warm-season
samples and no physical model or action benefit was scored. This establishes
replay input availability, not a graduation pass.

The repeatable [capture-safe persistence audit](2026-09-23-thermal-operational-baseline.md)
now pairs those origin-time inputs with qualified later indoor outcomes. All
63 hourly origins pair, reproducing the 2.0314°F overlapping baseline; only
three disjoint 24-hour windows remain, with MAE 1.32°F. The audit does not
score a model or action benefit. Its restricted read-only path is a prerequisite
for future frozen-candidate replay, not evidence for leaving shadow.

An [exact-forcing air-bias sensitivity check](2026-09-23-thermal-bias-sensitivity.md)
reproduced four published v4 trajectories before trying in-memory coefficient
variants. Reducing the negative air bias improved a handful of matured
short-horizon errors while leaving substantial low bias, and some variants
changed the schedule. This is a physical-fit hypothesis only; no artifact or
production advice was changed. Chronological, capture-safe candidate tuning
and an untouched seasonal holdout remain required.

The [actual published-shadow audit](2026-09-23-thermal-shadow-publication-score.md)
then paired31 matured near24-hour trajectories with qualified indoor outcomes.
The model's MAE was2.4565°F versus2.0265°F for its own same-origin persistence
baseline; nominal90% interval coverage was87.1%. All scored outputs were
low-confidence and three revisions were mixed. This is direct operational
evidence against graduating the current shadow output, not a release gate
derived from a few overlapping warm-season days.
The direct publisher originally stamped `generatedAt` before completing its
weather fetch. A narrow timestamp/capture backport is now live on the compatible
installed v4 runtime, preserving the post-input decision time at full precision
and archiving exact raw and normalized forcing for successful publications.
The first attended archive matched the live OpenHAB output digest. The strict
published-shadow scorer requires that archive and deliberately excludes all
pre-capture legacy pairs. Two natural captured one-hour targets have since
matured: model MAE 2.171°F versus same-origin persistence 1.080°F, both
low-confidence and with wide intervals. Their 24-hour targets remain pending.
This fixes a provenance prerequisite and adds early diagnostic scores, not a
model-accuracy pass or a shadow-exit gate.

A [non-overlapping window audit](2026-09-23-thermal-nonoverlap-score.md)
now separates repeated two-hourly forecasts from disjoint 24-hour windows.
The current read-only result remains unfavorable to the model: three selected
non-overlapping, mixed-revision windows have MAE2.5417°F versus1.5600°F
same-origin persistence. The two strict forcing-captured one-hour pairs also
remain worse than persistence. This is diagnostic evidence, not enough
seasonal or stable-revision support to graduate or retune a control threshold.

September 24 07:00 MDT read-only refresh of the exact-forcing-captured
publications: ten disjoint one-hour pairs under one v4 revision have model
MAE 1.3949°F versus 0.5580°F for same-origin persistence. Eight overlapping
six-hour pairs have model MAE 4.1949°F versus 2.3400°F persistence; the two
disjoint six-hour pairs are 4.9995°F versus 3.1500°F. All scored forecasts
remain low-confidence. The five-minute maturity gate still withheld one
one-hour target and three six-hour targets; no 24-hour captured target has
matured. This is further evidence to retain shadow status, not permission to
change the model, intervals, advice or control thresholds.

### Confirmed-action collection audit, September20

Read-only aggregate journal queries still find ten action events: eight
`model_inferred` Kiva events (December2025–January2026), one reconstructed
outdoor-shade event (October2025), and one `manual_dm` outdoor-shade event
(May22,2026). There are no ventilation or indoor-shade events. Mode history has
three reconstructed entries and one May22 manual entry. No message bodies,
notes or credentials were exported and no journal entries were fabricated.

This explains a substantive collection gap, not merely insufficient elapsed
time. The dataset only marks confirmed-source event timestamps which survive
sample construction. Evaluation additionally classifies joined action confidence;
one confirmed outdoor-shade state does not make reconstructed ventilation or
indoor-shade states confirmed. Do not relabel those fields to raise gate counts.

The existing CLI `thermal_intel.py journal` accepts structured `THERMAL` messages
with an explicit receipt/idempotency key and optional aware effective timestamp.
It is a trusted ingestion primitive, not proof of authenticated live transport.
Inspection found the legacy user `nostr-inbox.service` disabled/inactive, pointing
to missing `/home/sat/clawd/scripts/nostr-inbox-listener.sh`. No active thermal
confirmation route was established by the inspected repository/service paths;
this is not proof that every host messaging path was exhaustively checked.
Do not enable that obsolete unit or commandeer unrelated messaging projects.

Next implementable collection work: establish a scoped authenticated operator
confirmation route to the existing append-only journal, with immutable original
receipt identity/time, duplicate handling, explicit effective time, correction
semantics, and acknowledgement only after verified storage. Keep planned future
actions distinct from confirmation of completed actions. Test transport and
journal failure/retry behavior in isolation; only genuine operator reports may
be recorded as production confirmations. Then verify natural ventilation/shade
transitions and associate later qualified outcomes without assuming compliance.

Source-only confirmation hardening now requires full action/mode readback equality
before the journal CLI emits success, including duplicate retries. Missing,
changed, duplicate, unexpected or unavailable stored records produce no success
receipt. This is a tested ingestion prerequisite, not an authenticated collector
or deployed collection path. The approved design specifically chooses scoped
Nostr replies; the shared household proxy token is not individual operator
authentication and should not be repurposed as confirmation identity.

The source-only CLI also refuses receipt timestamps later than processing time
and effective action/mode timestamps later than their original receipt, before
constructing a journal connection. Future interval endpoints remain parseable
as plans but cannot enter this confirmed-action write path. Report actual
transitions separately with explicit aware timestamps; do not manufacture a
later receipt date to turn a plan into evidence. Tests cover current and past
confirmations, duplicate retries, future receipts, modes and overnight intervals.
Production ingestion/runtime remains unchanged pending coordinated deployment.

September23 follow-up: the acknowledgement and future-plan guards were
narrowly backported to the installed compatible v4 CLI without installing the
refused v5 model/runtime. The [live backport receipt](2026-09-23-thermal-journal-cli-backport.md)
records the exact hashes, 28 staged-v4 tests, private rollback copy and
no-production-journal-write check. Authenticated inbound collection, genuine
operator confirmations and next natural shadow verification remain open.

Broader regression verification at source revision `e7af4f2`: all633 local
thermal tests passed in137.87seconds with single-thread numerical libraries.
This includes every `test_thermal*.py` suite except container-backed
`test_thermal_journal.py`, plus the graduation-audit tests. Deployment/systemd
tests use temporary files or mocked services; this result is not a new live
database, inbound-transport, restart or production-deployment qualification.

Subsequent isolated PostgreSQL16 journal verification passed all32 tests
(4.01seconds final run). Actual CLI/database checks now use a completed same-day
ventilation interval: first write stores three records, replay stores zero new
records with the same IDs, and future overnight plans leave no receipt, action
or mode rows. The prior integration fixture represented a future plan and was
updated for the stricter confirmation contract. Fixture DSNs are excluded from
dataclass representations. All owned `thermal-journal-test-*` containers were
removed and absence verified; no production database writes occurred. This
closes isolated storage/replay testing, not Nostr authentication or deployment.

1. Audit the current accepted backtest: errors by horizon, season/regime and
   temperature state; compare persistence, recent/seasonal trajectories and
   existing advisory baselines. Separate legacy history from receipt-qualified
   evidence. Investigate absent candidates rather than assuming time fixes them.
2. Use historical data for bounded tuning of physical parameters and fitting
   choices. Keep chronological train/validation splits and an untouched final
   test period. Preserve physical stability constraints, provenance, budgeted
   computation and reproducible reports; never optimize against the final test
   set or leak future weather/actions into operational forecast claims.
3. Audit and complete confirmed ventilation/shade-action and outcome collection.
   Score comparable nights and uncertainty. Reconstructed actions can support
   exploratory fitting but must not count as confirmed causal benefit evidence.
4. Derive explicit numerical graduation thresholds from baseline evidence:
   accuracy versus baselines, bias, interval coverage, data support and modeled
   benefit. Review thresholds and representative advice before cutover; do not
   fabricate a minimum day count or announce a release date without evidence.
5. Implement repeatable graduation assessment with explicit failure reasons and
   next evidence checkpoint. Implement validated advisory status/schema/UI and
   consumer integration with honest stale/no-candidate fallback and rollback.
   Preserve existing alert codes and controls until their reviewed transition.
6. Deploy eligible advice in stages and verify natural publication plus operator
   review of examples. Retain seasonal scope: warm-season success does not
   qualify winter recommendations. Automatic actuation requires its separate
   authority, reconciliation/manual-override and fail-safe review.

Revisit this task at subsequent thermal work checkpoints and after relevant
completed outcome windows. When a gate is waiting on observations, record the
specific missing evidence and next review opportunity; continue implementable
work in parallel. Do not mark task99 or the overall goal complete merely because
collection is active or the UI badge was changed.

September 24 source-only audit follow-up: `audit-thermal-graduation.py` now
reports explicit advisory blockers for a compatible v5/v3 artifact: shadow-only
status, unapproved graduation thresholds, missing or inferior historical 24h
air skill, absent confirmed action outcomes, and the fact that prospective
qualified operational scores are **not contained** in a backtest artifact.
Seventeen focused tests pass. This is a fail-closed evidence report, not a release
threshold or advice activation. The live accepted artifact remains v4/v2;
the v5/v3 source audit correctly refuses it rather than relabeling its schema.
The matching installed v4/v2 validator separately accepted the current model
and report at revision `507748cee9ca`: 119 paired 24h folds score model
2.17855°F, persistence 1.68989°F and recent-cycle 1.83416°F MAE, with zero
confirmed disjoint action folds and `shadow_only=true`. This validates the
artifact pair, not advisory readiness.
The separate exact-forcing operational scorer at about 12:35 MDT still found
only two overlapping mature 24h targets (model/persistence MAE
6.9255/0.36°F, zero interval coverage); twelve captured targets were not yet
due. Thus neither the source audit nor the live score supports shadow exit.

The exact-forcing operational scorer now also emits
`operational_readiness_blockers` and an explicit false graduation claim. It
distinguishes absent independent pairs from paired model skill worse than
persistence, flags low-confidence outputs, and always states that this scorer
does not verify confirmed action outcomes or supply approved numerical release
thresholds. All 32 focused audit tests pass, including a better-than-persistence
case that still cannot authorize graduation. A live 24h read-only invocation
reported the current independent-window miss (model 6.286°F versus persistence
0.54°F), low confidence, and both unscored action/threshold gates. The next
natural shadow timer and later matured qualified outcomes remain observational
checkpoints; no model, publisher, control, or advisory mode was changed.

## September 29 residual-bias diagnostic

The accepted September 28 chronological backtest still has 119 paired 24-hour
air folds and is worse than persistence in all three regimes: shoulder
2.272/1.497°F, warm 1.927/1.734°F, and winter 2.375/1.759°F model/persistence
MAE. A read-only exploratory check sorted those 119 records by issue time,
reserved the last 36 origins (June 26–September 10), and, at each reserved
origin, subtracted the mean model residual from the last 30 earlier records
whose targets had already matured. Both a global correction and a same-regime
correction required at least eight matured records. On the same 36 holdout
origins, raw model MAE was 1.884°F, versus 2.055°F after global correction and
2.093°F after regime correction; same-origin persistence and recent-cycle
baselines were 1.546°F and 1.633°F. A simple rolling signed-bias adjustment
therefore worsened this diagnostic rather than closing the 24-hour gap.
These records are part of an artifact already selected using its backtest, so
the split is exploratory, **not an untouched release test**. No learned
coefficient, forecast, interval, schedule, or shadow policy was changed.

The capture-strict operational scorer at about 06:10 MDT found 58 overlapping
mature 24-hour pairs but only five greedy non-overlapping windows across
mixed model revisions. Their model/persistence MAE was 3.344/2.340°F, with
60% nominal interval coverage; 11 captured targets were not yet due. The
latest accepted `53d96e5e9637` revision had no mature 24-hour pair yet; the
five overlapping pairs under another captured artifact yield only one
independent pair. This adds evidence against graduation, not enough
current-artifact support to estimate a deployable correction. Prioritize
action-state evidence and physical/lead-time diagnosis over a global residual
offset.

September 29 afternoon read-only refresh under the installed v4 runtime:
62 capture-verified, qualified 24-hour pairs include six non-overlapping
windows. Their model/persistence MAE is 3.5438/2.6100°F, with 66.7% nominal
interval coverage; all 62 scored publications have low confidence. Across
overlapping pairs the indoor model has a −2.7785°F signed bias while its exact
captured outdoor forcing has a +2.6219°F forecast bias. Opposite signs do not
identify a causal mechanism; action-state, model physics and lead-time effects
remain to be tested on origin-safe, disjoint data. Shadow status stays in force.
The scorer also no longer emits `target_confidence:*` counts when no artifact
was selected: those counts were previously inflated by missing artifact IDs
matching an absent target (`None == None`). This was a diagnostic-only defect;
it did not change the score, blocker logic, or live model.


## October 8 sensor-identity migration boundary

New receipt v2 separates collector session (`streamEpoch`) from the declared
hardware phase (`sensorEpoch`). Source, bounded native history, model v6 and
frozen training input/source v2 paths preserve both identities. Explicit
`train-thermal-snapshot.py --receipt-version 2` selects this offline contract;
default v1 readers refuse it. Training persists original sources and binding v3
before saving any candidate. This is a tested offline boundary, not a live
receiver configuration change or a qualified production candidate.

Production origin/outcome integration, graduation/runtime bindings and
publication consumers still require coordinated migration before live v2
adoption. Do not relabel older receipts or bypass physical/numerical gates.
The operator confirms outdoor shades are still installed. Current native
development data lacks unshaded solar support, so the existing complete model
refuses its rank-deficient fit. Recovery work remains deferred; local ML work
remains permitted within enforced resource limits.


Explicit guarded capture now supports `capture-thermal-inputs.py --receipt-version
2`, paired with a private source-v2 policy. Use `--check-only` for configuration
validation without source reads. Default capture remains v1, and mismatched
policy versions refuse collection. The v2 backend preserves hardware/session
identities under the existing read-only budgets and requires both fitting
opt-ins off. This command has been checked with synthetic transports; keep
live policy v1 until the remaining consumers are qualified together.


Multi-part capture v2 now has explicit assembly-v2 support through
`assemble-thermal-inputs.py --receipt-version 2`. It requires adjacent original
v2 inputs with one declared hardware phase per role, preserves source-session
metadata and null barriers, and obtains one fresh journal view. The training
command with `--receipt-version 2 --assembly-binding PATH --input-part PATH`
(repeat the last option for every parent) verifies and retains the original
lineage. Add `--verify-only` to validate without fitting; the existing explicit
fitting/resource requirements still govern `--fit`. Assembled training writes
input binding v4 before saving a candidate; standalone training keeps binding
v3. Legacy readers refuse these contracts. Live adoption and production
qualification remain open pending the remaining consuming-path migration.


Private native shadow origin capture v3 now binds source-v2 receipts to model
v6 and to its declared hardware phases. It preserves collector sessions and
original issue/forcing/initial-state/publication evidence. Its source scorer
emits pair v2 and uses the original issue clock for persistence/recent-cycle
comparisons; new sessions are accepted only within the same hardware phase.
Legacy readers refuse the newer proofs. These are tested explicit APIs; the
live publisher and production release capture/qualification consumers still
need integration. No receipt history is backfilled and no activation is implied.


Native qualification now has explicit source assessment v2, preregistration v2
and report v4 APIs. Use `qualify-thermal-graduation.py --receipt-version 2` with
original model-v6/source-v2 evidence and native preregistration when those real
inputs exist. Missing evidence produces failed gates and an unavailable report.
The legacy default cannot interpret the newer phase contract. Source-bound
threshold preregistration still must precede untouched/prospective intervals;
all independent-support, baseline-skill, fit and freshness thresholds remain
unchanged. Production publication/report-v4 consumption is integrated below;
live qualification and adoption remain open.


Explicit native release mode now uses
`thermal_intel.py release --receipt-version 2 --evidence-inputs PATH`. It emits
publication v3 / release metadata v2 from fresh report v4 and native current
receipts, with unavailable output when gates fail. The default command remains
legacy. Native frozen observation also requires explicit `--receipt-version 2`
and checks model-v6 hardware bindings before delivery. Original accepted native
release output is retained as private capture v4 and scored as source pair v2.
The UI validates v3 before showing mode/confidence and withholds unqualified
action advice. This staged integration does not establish model readiness or
authorize live source adoption; qualification and installation remain open.


## Native point/window readers and hourly learning

Explicit point/window v2 APIs retain declared hardware phases and collector
sessions, source expiry, invalid barriers, original storage delay and half-open
window bounds. Window provenance hashes the entire bounded original history,
including carry and invalid rows. Neither API relabels legacy receipts.

Hourly learning selects the new contract only with
`HOURLY_TEMP_QUALIFIED_ENABLE=1` and `HOURLY_TEMP_RECEIPT_VERSION=2`, plus its
existing private source-v2 policy, read-only database configuration and evidence
cutover. The parent binds the selected outdoor phase before its bounded worker
read; both parent and scorer validate metadata against that hourly policy's
actual temperature range and receipt lifetime before a Kalman update. Equivalent
valid evidence yields the identical existing numeric update. Diagnostic receipts
retain native version, hardware phase and collector session. Missing, expired,
legacy or mismatched native evidence skips learning without fallback.

Daily learning now also selects native evidence explicitly with
`DAILY_TEMP_RECEIPT_VERSION=2`, the existing qualified opt-in and
`DAILY_TEMP_COVERAGE_POLICY=complete_receipt_coverage_v1`. Its private source-v2
policy must retain the reviewed outdoor identity, range and 120-second lifetime.
The parent and worker bind the declared phase before reading. Version 2 result
and summary metadata must match that phase; complete receipt coverage over the
actual Denver calendar day remains mandatory, including 23/25-hour DST days.
Original bounded-history hashes and phase metadata are retained in daily and
day-three learning diagnostics; their numeric equations remain unchanged.
Explicit native selection without qualified opt-in skips temperature learning.

Hourly and daily consumer code migration is implemented. Keep the live receiver
on its existing contract until deployment, schedules and policy bindings are
reconciled together. These synthetic compatibility checks establish transport
correctness, not learned skill or production qualification. Outdoor shades
remain installed; do not fabricate unshaded development support or weaken the
exact rank gate.


### Native collection rollout with the existing shadow model

`thermal_intel.py shadow --receipt-version 2` now exposes the already implemented
native current-input selector. A legacy shadow caller can instead select native
current inputs explicitly with `THERMAL_TEMP_SHADOW_RECEIPT_VERSION=2` and its
existing qualified-shadow opt-in. Invalid selection or absent opt-in refuses
inputs. Neither path promotes an older artifact or makes it native-qualified.

The current live accepted artifact is model v4. The staged v5/v6 registry refuses
v4 and may quarantine an incompatible accepted file. Therefore native collection
rollout must preserve the installed v4 artifact validator, pipeline, model code
and `thermal_intel.py`, updating only the reviewed input helpers and forecast
learning consumers. The private deployment manifest pins those unchanged files.
A synthetic bridge check exercises the exact installed current-state functions
with a generated private v2 policy and real collector/parser fixtures; this proves
input compatibility, not forecasting skill. Native original/release captures
remain strict model v6 and cannot qualify the legacy v4 model.

Keep the old source-v1 policy intact and use a separate private v2 policy for the
new collection phase. Update hourly/daily version selectors and the legacy
shadow input selector together, with dependencies installed before receiver
restart. Preserve normal forecast timer cadence. The incompatible legacy trainer
must remain quiescent during cutover; native development fitting uses a separate
private v6 registry and the existing resource/opt-in guards. A mixed receipt day
cannot train daily corrections; the first complete native Denver day is required.
Do not rewrite historical v1 receipts or relabel them with a hardware phase.


### October 8 input installation readback

The reviewed backward-compatible input/learning code is now installed. The
receiver still serves source v1, and the original v1 policy and accepted model-v4
artifact/runtime remain unchanged. A bounded read-only lookup through the
installed hourly worker qualified one natural original receipt; no learned state,
forecast publication or model fit was forced. Normal forecast, shadow and training
timer cadence is restored; their services were inactive at readback.

Native selection was not enabled. The cutover reached manager reload, where the
host sudo policy requires local authentication specifically for `systemctl`.
The unused new selector drop-ins were removed before normal schedules resumed;
no sudo authentication restriction was bypassed. The private exact-generation
stage retains the source-v2 policy and reviewed cutover driver. Its default
invocation revalidates hashes/resources without writes, and `--apply` requires
full exact-head CI plus local administrative authentication. After actual native
adoption, verify natural source/JDBC receipts and subsequent scheduled consumer
behavior. Synthetic bridge checks are not production model qualification.


### October 8 installed-shade development diagnosis

Original frozen development inputs contain 3,994 samples and 3,965 eligible
five-minute pairs over 14 elapsed days (15 local dates, including partial dates).
Every fitted pair has outdoor shades installed. The unchanged full model still
fails rank: air 5/6 and mass 4/5, with an exactly zero unshaded solar column.

A private exploratory installed-shade projection has rank 5/5 for air and 4/4
for mass; column-normalized condition numbers are 5.57 and 2.33. Its small
bounded development fit passed physical stability checks, but it produced no
artifact and does not satisfy the existing complete-model contract. Any eventual
replacement needs a separate explicit supported-domain contract; it must refuse
unshaded use rather than fabricate an unobserved response. Existing full-model
rank, conditioning, stability and release gates remain intact.

Chronological development probing trained on the first ten elapsed days and
used the remaining development data. Its weather forcing is observed, not
as-issued, and predictions freeze action values known at the origin. These are
conditional diagnostic hindcasts, not release evidence. In the probe with
complete original forcing and qualified origin/target temperatures, air MAE is
0.34/0.71/0.62/1.50 F at 1/6/12/24 hours over 5/5/4/4 local-date origins.
The 24-hour persistence MAE is 1.17 F over the same four cases. The 1-hour recent
cycle MAE is 0.29 F over the same five cases. The candidate therefore does not
establish useful skill across the required horizons. Comparisons to recent
cycle use the same eligible pairs; three, not four, 24-hour cases have all seven
required previous cycles.

The earlier complete-row diagnostic found zero 24-hour windows because 28
sample gaps remove 38 five-minute rows; its longest run is 23h50m. Original
outdoor/radiation forcing actually has a 95h35m complete run and supports four
24-hour development dates with genuine origin/target temperatures. Missing
interior-temperature rows must not be invented; forcing support and qualified
outcomes should be represented separately in the next model investigation.
Dense origins are not independent days. This diagnosis does not relax existing
readers or qualify source-v1 data as declared hardware-phase evidence.

Next scientific work is a separately identified supported-domain model with
source-bound forecast-horizon fitting and evaluation, retaining physical,
conditioning and coefficient-stability checks. One-step fit quality alone is
insufficient. New native evidence, a real frozen candidate, preregistration and
untouched/as-issued baseline wins remain required before production activation.


### Installed-shade horizon refinement and isolated numerical core

A private development-only refinement fits complete original weather forcing and
qualified origin/target temperatures at 1/6/12/24 hours, without synthesizing
missing interior temperatures. It uses only the first ten elapsed development
days for fitting. Its analytic objective gradient agrees with centered numerical
derivatives (maximum relative discrepancy below 4e-7); final sensitivity rank is
10/10 with normalized condition number 18.82. Origin action values remain frozen.
This is observed-weather conditional hindcasting, not as-issued release evidence.

The joint-temperature refinement reduces development 24-hour air MAE from 1.50 F
to 0.96 F versus paired persistence 1.17 F. It still slightly loses to recent
cycle at 1 hour (0.303 F versus 0.293 F). A separate training-persistence-normalized,
equal-local-day-weighted air objective reaches 0.85 F at 24 hours but worsens the
1- and 12-hour results. Neither experiment establishes a release winner. There
are four 24-hour development dates but only three non-overlapping 24-hour windows;
training spans eleven local dates, including partial dates. Coefficient-block
stability, calibrated intervals and untouched/prospective skill remain unproved.

The original joint probe had an exact shade-order violation from solver roundoff
and was refused by the strict core. Repeating with the existing solver feasibility
margin passes exact coefficient/order/stability and the 72-hour guard. No validator
was loosened and no candidate artifact was created.

`thermal_model/installed_shade_dynamics.py` is now an isolated, pure numerical
core for this ten-parameter domain. It has no unshaded coefficient, refuses unknown
or removed outdoor shades, requires complete explicit five-minute forcing, returns
immutable states/sensitivities, and retains the existing coefficient, solar,
spectral, 72-hour and output-range protections. It neither fits nor qualifies,
publishes, controls or installs a model. Numerical tests verify nonzero solar/vent
sensitivities, physical drift refusal, missing-input refusal and immutability.
Full-model fitting and its rank/conditioning/stability gates remain unchanged.

Next integration must use an explicitly versioned supported-domain artifact and
source-bound forcing/endpoints, fit evidence, preregistration, original published
forecasts and independent outcomes. The core alone cannot be loaded by the
existing full-model registry or confer production confidence. Native collection
still requires the operator's local systemctl authentication step. Keep the live
v4 model and normal schedules unchanged while those dependencies remain open.


### Native installed-shade development inputs and endpoint support

Outdoor shades remain installed until the operator reports a change. The pure
`thermal_model/installed_shade_inputs.py` adapter validates an explicitly pinned
original native-v2 input snapshot, its three declared sensor phases, and capture
availability at assessment. Legacy input snapshots are refused. Stream-session
resets remain distinct from the persistent sensor phase, with original outdoor
receipt snapshot digests retained alongside the complete input snapshot digest.

Weather support and endpoint support are separate. Endpoint temperatures must
have original native receipts; missing interior readings remain missing. Forcing
requires a complete five-minute prefix of original outdoor receipts and observed
radiation or explicitly labeled astronomical-night zeros. Interpolated/held
radiation, missing outdoor receipts, detected outdoor jumps, exceptional heating
and outdoor-shade removal/unknown state cannot supply an eligible prefix.
Original journal timestamps also exclude short removal or heat episodes between
five-minute targets; sampled labels cannot hide these domain violations. Origin
indoor-shade and vent values remain frozen in predictive forcing; later action
labels can exclude a case but cannot become predictive inputs. This adds no vent
scenarios or recommendations and preserves the November no-vent default.

The immutable development records explicitly deny release and as-issued
forecast authority. One eligible origin per Denver date is a sampling convention;
non-overlapping windows must still be counted separately. Observed future weather
makes these conditional development hindcasts, never prospective release proof.
The adapter is not installed or connected to the live model/runtime or registry.

Verification: the initial ten boundary tests failed for the missing module, then
passed after implementation. The strengthened native-input, numerical-core and
original-capture checks pass together: 56 tests under CPU 20 percent, memory
256 MiB, zero swap allowance, 24 tasks and one numerical thread. No fitting, live
DB requests, service changes or activation were performed for this milestone.
Source-bound horizon fitting, coefficient-block stability, versioned domain
artifacts, a frozen candidate, preregistration and untouched/as-issued evidence
remain required. PR3 and backup/recovery work remain deferred.

Scoped independent review identified the off-grid eligibility gap; both synthetic
removal/reinstall and heat-on/off cases failed before the correction. The corrected
56-test run passes, and scoped re-review reports no remaining material findings.


### Source-bound installed-shade horizon fitting

`thermal_model/installed_shade_fit.py` now fits the separately identified
installed-shade numerical core from validated native-v2 development inputs.
The entry point requires the original snapshot digest, declared sensor phases,
assessment time, and an exclusive training interval. It selects the required
1/6/12/24-hour endpoints internally; no origin or target at/after the training
cutoff enters optimization. Missing required horizon support refuses fitting.
The fitted report retains the source digest, phases, training bounds, origin
counts and separately counted non-overlapping windows. Observed-weather fitting
remains conditional development hindcasting, not as-issued release evidence.

The objective jointly fits air and mass endpoints with equal horizon weighting
and analytic vectorized sensitivities. Existing coefficient bounds, shade-gain
ordering, solver feasibility margin, convergence controls, exact rank and
normalized conditioning limit remain enforced. Both the seed and final model
must pass the strict core, including the 72-hour physics guard; final training
rollouts are checked step by step. Finite intermediate optimizer trial states
may exceed output bounds during line search, but never become returned forecasts
or accepted models. Solver failure, worsened loss, invalid final physics or bad
conditioning refuses the fit. No final holdout outcomes choose this objective.

Final coefficient stability uses four deterministic Denver-day omission groups,
retaining the existing conservative 24-day support minimum and 0.25 physical-span
movement limit. Each refit excludes every endpoint window touching an omitted day
and must retain every original training horizon. The same finite workload budget
covers the fit and all refits. Short histories report stability unassessed; dense
or overlapping rows cannot establish release support. This does not replace the
separate untouched/prospective support floor or interval-calibration gates.

Original action/mode events entered after their effective times remain intact
for retrospective diagnostics, but affected forecast origins are excluded until
the original receipt time. This prevents backdated labels from supplying future
knowledge. Predictive action values remain frozen at eligible origins. Outdoor
shades remain installed, and the November no-vent default is unchanged.

Verification: nine initial missing-module failures; then analytic-gradient,
known-coefficient synthetic optimization, exact physics, rank/conditioning,
solver-failure, workload-deadline and block-stability checks. A real native-v2
synthetic capture exercises source/cutoff integration with a stub fitter; it is
not household fit evidence. Missing-horizon and retroactive-action gaps were
reproduced before their guards. Final affected suite: 79 passed under CPU 20
percent, memory 256 MiB, swap allowance zero, 24 tasks, one numerical thread and
a 90-second process deadline. Scoped independent review found no remaining
material issues. No household fitting, artifact creation, live installation,
service change, production qualification or activation occurred.

Next: independently version the supported-domain artifact and fit evidence,
bind the runtime/publication and exact original evaluation to that identity,
then fit a genuinely source-qualified candidate and assess baseline skill,
coefficient stability and calibration. Native collection cutover, candidate
freeze/preregistration and adequate untouched/as-issued evidence remain open.
PR3 and recovery work remain deferred; local bounded execution is permitted.


### Distinct installed-shade candidate and numerical evidence bundle

The separately identified ten-parameter model now has the explicit candidate
schema `earthship-installed-shade-candidate/v1` and numerical evidence schema
`earthship-installed-shade-fit-evidence/v1`. The existing full-model v5/v6
contracts and readers are unchanged; the old full-model reader rejects this
format. No absent unshaded coefficient is inserted or interpreted as learned.
Its declared domain is installed outdoor shades, with original input snapshot,
sensor phases, training interval, code revision and runtime revision retained.
Status is explicitly `development_candidate`; release/as-issued authority is
false. Production qualification remains a separate evidence-based decision.

`installed_shade_artifact.build_candidate_bundle` requires a source-bound fit
report and original native-v2 inputs. The fitter now retains its exact initial
coefficient vector, allowing original endpoint losses to be reconstructed before
and after refinement. Bundle validation replays the original capture, selects
all required horizons strictly inside the training interval, verifies seed/final
physics and every rollout step, recomputes rank/normalized conditioning, origin
counts, non-overlapping windows and deterministic day-block movement. Every
retained block coefficient vector must also pass source-derived conditioning
and exact physics on the original retained windows. Numerical limits and all
reported facts are checked, even when altered records are consistently rehashed.

The candidate payload digest excludes the proof pointer; numerical evidence
binds that payload, and the complete artifact binds the evidence digest. This
avoids a circular hash dependency while preserving exact coefficient/source/
runtime identity. Known mode labels stay intact; absent modes are counted as
`unknown`, without promotion to a qualified seasonal regime. Regime counts count
selected endpoint origins across horizons; they are not independent-day claims.
Numerical/source consistency alone does not authenticate optimizer execution or
prove predictive usefulness, calibrated intervals or as-issued skill. Actual
fitting provenance and untouched/prospective qualification remain necessary.

Private persistence requires an existing owned 0700 directory. It retains the
original input snapshot before writing immutable 0600 evidence and candidate
files at their digest addresses; the candidate is written last. Caller records
are detached before verification/write. Repeated identical writes are safe;
changed existing bytes are refused. Typed reads re-open the original evidence
and source files and repeat validation. Missing/incompatible files cannot create
an available production forecast. No existing accepted registry is modified.

Verification: the initial 14 checks refused the missing retained seed field.
The first candidate suite then passed 14 checks. Review identified mixed unknown/
known regime sorting; the original native-capture case reproduced a TypeError,
and explicit unknown counting fixed it. Final affected candidate/fit/input/core/
capture suite: 94 passed under CPU 20 percent, memory 256 MiB, zero swap allowance,
24 tasks, one numerical thread and a hard 90-second process deadline. Tests use
synthetic native captures and mathematical fit reports; they are not household
optimization or release evidence. Rehashed source/runtime/coefficient/loss/
threshold/support/pass-flag changes, future candidates, missing seed, old-reader
compatibility, immutable file transactions and mixed modes are covered. Scoped
independent review reports no remaining material findings.

Next integration must explicitly accept this domain/artifact identity in the
appropriate runtime, original as-issued captures and qualification verifier.
The existing model-v6 qualification/publication path must not silently accept
these coefficients. Genuine native collection, fitting execution, baseline
skill, block stability, calibrated uncertainty, candidate freeze/preregistration
and adequate untouched/prospective windows remain open. Outdoors remain installed;
November no-vent, PR3 deferral and separate deferred recovery work are unchanged.


### Installed-shade original issuance, replay and outcome scoring

`thermal_model/installed_shade_origin.py` now prepares a source-verified
installed-shade candidate before origin acquisition, then constructs an explicit
`earthship-installed-shade-forecast/v1` observation and
`earthship-installed-shade-origin/v1` capture. The original artifact, complete
runtime binding, weather issuance, qualified native-v2 temperature history and
causal initial mass state, known-at-origin action snapshot and output remain
bound to an immutable capture digest. Runtime identity must match the candidate
and include the new domain code plus forecast archive verifier. Sensor hardware
phases must match the fitted source; rotating collection sessions remain distinct.

Weather retains the existing Open-Meteo source and six-hour issuance-age bound.
New explicit `select_origin_forecast_with_receipts` and
`fetch_origin_forecast_with_receipts` APIs preserve individual original
metric values and capture clocks in `earthship-thermal-archived-forecast/v2`.
The bounded, read-only SQL contract is shared with the unchanged default reader.
Replay reconstructs selected hourly rows and the existing archive hash from
those original metric receipts, checking every selected clock and value before
prediction. It does not treat an unverified archive hash as source proof.

The complete five-minute forcing is interpolated without extrapolation, then
simulated through the strict core. Only exact hourly targets are exposed in the
issued output, keeping it inside the existing 16-KiB publication byte budget.
Future observed weather and future action changes never enter prediction. Known
installed outdoor shades, indoor state and a passive heating state are required;
on/unknown heating or the existing two-hour cooldown refuses this domain.
November 1, 2026 Denver starts the persistent no-vent default. A new confirmed
operator entry at/after that boundary can override it; older or reconstructed
vent labels cannot. This creates one frozen-assumption forecast, with no action
scenario comparison or advice. Confidence remains unqualified, intervals unset,
release authority false and automatic actuation disabled.

Private capture writes use an existing owned 0700 directory and immutable,
digest-addressed 0600 files. Typed reads replay exact origin state and forecast
outputs. `score_issued_capture` requires the actual persisted publication to
match the original issued payload and to occur by the captured publication
clock. Only mature, exact-horizon native-v2 outcomes in the same hardware phase
can supply errors. The seven-cycle comparator uses the original issue clock and
unchanged strictly historical Denver clock policy. At 24 hours, the cycle ending
exactly at issue is excluded, so lags 2–8 supply the seven complete cycles.

Scores retain candidate/runtime/source identities and separate model,
persistence and recent-cycle errors under
`earthship-installed-shade-source-scored-pair/v1`. Unqualified intervals remain
null rather than claiming calibration; unknown seasons remain unknown.
Observational scoring alone cannot grant release or confirmed action outcomes.
The qualification/preregistration layer still needs an explicit adapter to this
distinct candidate/capture format and genuine archived sources.

Verification: initial missing-runtime failures, then 22 source/runtime/scoring
checks passed. Delayed persisted publication and malformed action-map cases were
reproduced before their refusal guards. Scoped review identified the dropped
per-metric archive clocks; changed selected weather with a stale archive hash
reproduced the gap. Seven missing-receipt API tests preceded implementation;
40 receipt/runtime/legacy-weather checks then passed. Final affected verification:
182 passed in 65.30 seconds under CPU 20 percent, memory 256 MiB, zero swap allowance,
24 tasks, one numerical thread and a hard 90-second process deadline. Scoped
re-review found no remaining material findings. All captures/publications/
outcomes are synthetic test fixtures; no live household publication, fitting,
sensor-policy adoption, registry mutation or service change occurred.

Next: explicit supported-domain qualification/preregistration and calibrated
publication/UI adapters, then the live entry point and genuine source-qualified
candidate/outcomes. A useful baseline win, coefficient stability, intervals,
frozen candidate and adequate untouched/as-issued support remain required.
Outdoor shades remain installed; PR3 and recovery work remain deferred.


### Installed-domain preregistration and qualification reports

The installed-shade candidate now has explicit source-backed registration APIs:
`register_installed_shade_policy` and `read_installed_shade_registered_policy`.
Their new receipt namespace is `earthship-installed-shade-policy-registration/v1`.
It binds the distinct candidate schema, exact ten-parameter contract and declared
hardware-phase semantics. The original registration clock, declaration-before-
holdout/prospective checks, immutable private copying and baseline-derived policy
rules are preserved. Existing full-model registration readers remain unchanged
and reject this separate namespace. Development thresholds are reproduced from
the retained original issued captures, persisted publications and native outcome/
recent-cycle receipts; altering a cached baseline cannot seal a policy.

`thermal_model/installed_shade_qualification.py` connects the registered policy,
original candidate bundle with native training/source/numerical replay, retained
runtime archive and original issued/outcome packets. Duplicate windows or mixed
candidate/runtime/hardware phases are refused. Diagnostic support retains raw
pair counts, independent non-overlapping windows, first local-day observations
and paired model/persistence/recent-cycle metrics. Missing components close their
specific gates rather than creating an active override. Current uncalibrated
scores remain visible, but unset original intervals cannot pass release.

The report namespace is `earthship-installed-shade-qualification-report/v1`.
It preserves the existing forecast gates and adds explicit issued-interval
availability. Statistical qualification and report replay use the existing
current-monitoring evaluator: historical/holdout skill plus the latest required
independent prospective block for every horizon and regime. Older good results
cannot hide a recent loss. The predeclared 35 independent days/windows, convincing
wins against both baselines, error/bias/interval caps, coefficient stability,
source identity and prospective freshness rules are unchanged. Forecast advice
and automatic actuation remain withheld. Cached reports grant no authority;
production publication must freshly recompute from the original references.

The reproducible command is `python3 scripts/qualify-installed-shade.py` with
`--registration`, `--candidate`, `--runtime-bundle`, `--original-pairs` and
`--output-dir`. Original packet indexes must be private original evidence;
report output requires an existing owned 0700 directory. JSON and Markdown share
one actual UTC assessment, decision and digest, and are written as immutable
0600 files. No assessment-date or active override is accepted. Missing optional
inputs deliberately generate an unavailable report, not synthetic qualification.
Run it serially under the existing resource envelope, for example:

```bash
systemd-run --user --scope --quiet \
  -p CPUQuota=20% -p MemoryMax=256M -p MemorySwapMax=0 -p TasksMax=24 \
  /usr/bin/nice -n 15 /usr/bin/ionice -c 3 /usr/bin/env \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  EARTHSHIP_QUALIFICATION_FIT=0 EARTHSHIP_REMOTE_QUALIFICATION_FIT=0 \
  /usr/bin/timeout --signal=TERM --kill-after=5s 90s \
  python3 scripts/qualify-installed-shade.py \
  --registration "$THERMAL_REGISTRATION_PATH" \
  --candidate "$THERMAL_CANDIDATE_PATH" \
  --runtime-bundle "$THERMAL_RUNTIME_BUNDLE_PATH" \
  --original-pairs "$THERMAL_ORIGINAL_PAIRS_PATH" \
  --output-dir "$THERMAL_QUAL_REPORT_DIR"
```

Verification: eight initial missing-adapter/module failures, then source/gate
integration. One seal-only test seam needed correct archive-relative path
resolution; no source rule was relaxed. Review found accidental use of the older
pooled evaluator. The existing recent-loss fixture reproduced a false pass;
using the current prospective monitor in both decision and report replay fixed
it. Missing human/CLI support was observed before implementation. Final affected
registration/source/runtime/policy/statistics/decision/actual-CLI suite: 109 passed
under CPU 20 percent, memory 256 MiB, zero swap allowance, 24 tasks, one numerical
thread and a hard 90-second deadline. Scoped re-review found no material issues.
Source adapter tests replay original synthetic captures; seal/loader orchestration
seams are explicitly mocked and do not constitute a genuine preregistration or
release. No actual policy, household fit/publication, registry/service change or
production activation occurred.

Next: calibrated uncertainty bound to the frozen candidate and original issuance,
explicit publication/UI adapters and the live entry point, then genuine native
fitting, preregistration and sufficient untouched/prospective qualification.
Outdoor shades remain installed and the November no-vent default persists until
a confirmed operator change. PR3 and recovery work remain separate and deferred.


## Installed-domain production publication contract

The installed-shade path now has a separate publication namespace,
`earthship-installed-shade-publication/v1`, with outer output `version: 4`.
It distinguishes `shadow`, `forecast_active`, and `unavailable`; action advice
remains withheld and automatic actuation is false. It retains the original
numeric forecast/v1 or forecast/v2 unchanged inside `forecast`. The inner
numerical record's historical shadow semantics are preserved. Only the outer,
source-replayed release decision can describe production eligibility.

The calibrated candidate/v2 binds the source-verified base candidate, a separate
calibration/v1 interval, and the executing runtime. Qualification report/v2 and
policy registration/v2 retain the existing baseline, independent-day/window,
current prospective monitoring, physical, conditioning, stability, freshness,
and source gates. A numeric forecast/v1 cannot become active or acquire bands
retroactively. Forecast/v2 supplies exactly four original calibrated intervals
at 1, 6, 12, and 24 hours; the UI draws four individual interval markers and
never interpolates or clips bands into other hours.

`prepare_installed_qualification(reference_path)` accepts an owned private file
with these exact fields:

```json
{
  "schema": "earthship-installed-shade-release-inputs/v1",
  "registration_path": "registration-relative-to-this-file",
  "candidate_path": "candidate.installed-shade-candidate-v2.json",
  "runtime_bundle_path": "runtime-relative-to-this-file",
  "original_pairs_path": "original-pairs-relative-to-this-file"
}
```

Each path points to original private evidence, not a saved qualification report.
`original_pairs_path` may be null when collecting evidence. Only an explicitly
null `registration_path` permits source-verified shadow bootstrap; a configured
registration that fails validation produces unavailable output. Candidate fit
and, for v2, calibration source gates must pass even for bootstrap. Missing
source qualification does not become permission to use cached flags.

The runtime bundle must contain `installed_shade_publication.RUNTIME_PATHS`,
which pins the publication code and its local Python dependency closure,
including the qualification gates, package initializer, and native temperature
proof helpers. Preparation rebuilds the binding from the
actual executing source files, interpreter, and dependency versions. Publication
checks that binding again and replays current original input expiry. Runtime
drift, a changed candidate, expired inputs, failed release gates, or unsupported
current calibrated regime/width results in explicit unavailable output. There
is no cached-report, active-switch, or assessment-date override input.

Available publications expire no later than ten minutes after their original
issue, and active publications also expire at their qualification deadline.
The UI enforces the deadline and rejects future assessments at microsecond
precision. Existing output versions 1, 2, and 3 remain readable. The card keeps
its approved layout, shows forecast/shadow/unavailable mode and revision, and
withholds action recommendations. Current origin vent assumptions are displayed
without creating vent schedules. Outdoor shades remain installed until an
operator change; the November no-vent rule remains unchanged.

This milestone implements publication construction, validation, and display.
It does not install a new Item, publish a household forecast, or activate a model.
The separate actual persisted numeric and main-publication receipt contract is
implemented below. HTTP acceptance alone is insufficient. The live entry point,
native-input adoption, a genuinely qualified frozen
candidate, and sufficient untouched/prospective independent outcomes remain
required before cutover. Backup/recovery work and PR3 remain deferred.

Verification: 24 backend mathematical-contract/source-factory orchestration tests
passed in 24.60 seconds, plus
direct Node parser/chart checks, and direct Svelte server rendering. Fixtures and
mocked runtime/qualification ports are not household release evidence. Full
Vitest/DOM and repository suites run in hosted CI; the local Vitest startup hit
the 90-second guard without reporting test results, so it supplies no pass claim.
All local workloads remain serial with CPU 20 percent, memory at most 256 MiB,
zero swap allowance, and bounded execution time.


## Score the actual installed-domain main publication

`thermal_model/installed_shade_published_origin.py` defines
`earthship-installed-shade-origin/v3` and
`earthship-installed-shade-source-scored-pair/v3`. The observation retains the
unchanged original numeric capture/v1 or v2 plus two actual persisted receipts.
Each receipt contains exactly `item`, `time` (integer Unix milliseconds), and
`state` (the actual persisted JSON string). The numeric Item is
`Thermal_OriginalForecast_JSON`; the main/UI Item is `Thermal_Model_JSON`.
Swapping those identities, replacing a receipt, changing the bound numeric
forecast, or rehashing a changed interval does not create valid source evidence.

The main receipt must follow the original numeric receipt/capture, precede its
publication deadline, and precede the scoring target. The observation records
its actual local collection clock. Original native-input expiry is replayed at
the actual main receipt time. Scoring then verifies the exact stored main receipt
and a later mature native outcome. Persistence and the seven qualified recent
cycles still use the original issue-time information. Numeric and main receipt
hashes remain separate; historical publication mode is recorded without granting
current release authority or action-response qualification.

Private immutable writes retain the original numeric file at its original
address before the v3 observation. The v3 observation also contains the original
numeric capture, so later scoring does not substitute an unrelated file if a
separate copy is missing. Both old capture readers reject v3. Uncalibrated v1
numeric forecasts remain shadow observations with no invented uncertainty.

Qualification report/v3 adds explicit numeric2-or-publication3 source dispatch.
A single frozen candidate/runtime/hardware phase remains required. Duplicate
issue/target/horizon windows are refused even when one comes from the numeric
Item and one from the main Item. Independent-day/window selection, 35-day support,
regime requirements, untouched/prospective intervals, baseline wins, measured
fit, conditioning, block stability, calibration and current monitoring are
unchanged. Existing qualification report/v1 and v2 APIs keep their semantics.

To recompute the new contract, use the existing bounded qualification command
with `--contract-version 3`, the original registration/candidate/runtime/pair
paths, and an owned private output directory. It uses the actual assessment
clock and emits matching private immutable v3 JSON and Markdown reports. Missing
sources produce unavailable output. Current publication preparation selects this
fresh replay for calibrated candidates; a cached report or past active mode is
never an activation input.

This is capture/scoring infrastructure, not proof that a household model has
qualified. The live collector/publication entry point is implemented and awaiting
live integration qualification. Actual Item installation remains outstanding. Genuine native-input adoption and enough
independent calibration, untouched and prospective outcomes still precede
production cutover. Advice and automatic actuation remain disabled.

Hosted verification of preceding publication commit `b0e1bee`: full UI tests,
UI build and completion checks passed; CI and ML failed only the two helper-drift
tests because the runner's tool-cache interpreter did not satisfy the production
ownership/permissions policy. The tests now use an owned copy of actual executable
bytes that they never execute. Production interpreter/source trust checks are
unchanged; these test fixtures do not establish trust in a hosted interpreter.


Final local verification of this milestone: 21 new capture/scoring/CLI cases,
27 publication/routing cases, and 20 existing qualification compatibility cases
passed in separate serial workloads within the unchanged 90-second deadline and
256-MiB memory cap. Scoped read-only reviews found no material defects. Fixture
clocks, runtime ports and positive qualification math are explicitly synthetic;
none establish household release eligibility. Commit `8d578245b66263f34694439649f8b94e61f9c767`
subsequently passed CI, Forecast ML and Thermal delivery. The live-entrypoint
change below requires its own exact-commit hosted verification before integration.


## Bounded installed-domain live entrypoint

`openhab/scripts/thermal_installed_intel.py --config PRIVATE_CONFIG` checks only
owned private configuration. It does not collect sources, create captures or
publish. Only explicit `--publish --shared-lock EXISTING_PRIVATE_SHARED_LOCK` runs one scheduled cycle. There is no active
switch, assessment-date override, fitting path, provider fallback or household
command endpoint.

The production configuration schema is `earthship-installed-shade-live-config/v2`.
The default command-line contract is version 2. Its release reference file must
use the closed `earthship-installed-shade-release-inputs/v3` contract. Candidate/v3,
raw calibration/v2, qualification-report/v5, raw development registration/v3
and original release score-sources/v3 are verified by the publication preparation
path. A configuration check validates configuration structure and permissions;
it does not establish model qualification. Explicit `--contract-version 1`
permits historical configuration checks, legacy withdrawal and the explicit
native base shadow bootstrap described below. General publication
with that profile is refused before resource checks or transport.
It contains exactly `schema`, `openhab_base`, `evidence_directory`,
`release_inputs_path`, `token_file`, `journal_dsn_file`, `forecast_dsn_file`,
`native_db_config` and `native_policy`. File paths must be absolute and resolved;
source files are owned mode 0600 in owned mode 0700 directories. The evidence
output directory is owned mode 0700. Keep credential values and DSNs exclusively
in private files. Reuse the approved Hex token file. The OpenHAB base must be an
approved loopback REST endpoint. Database DSNs must satisfy the existing local,
read-only, bounded-connection contract.

Preparation replays original qualification sources before current input
acquisition. The upcoming five-minute UTC issue must be within 60 seconds.
Weather is selected only from archived forcing available at the actual
precollection clock. Native v2 input receipts retain declared hardware phases
and original grids. Journal actions are read with creation/receipt/effective
cutoffs at that same precollection clock; the held issue snapshot acquires no
future action knowledge. Source acquisition must finish before the issue. Its
actual completion is retained as input availability, never backdated. Outdoor
shades remain installed until an operator change; the November 1 Denver no-vent
default remains until a new confirmed operator override.

An owned private nonblocking lock serializes cycles. One immutable attempt
marker per issue prevents reposting a partly accepted forecast as fresh evidence.
The cycle sends the unchanged original numeric forecast to the fixed String
Item `Thermal_OriginalForecast_JSON`, verifies the exact JDBC receipt, retains
its immutable numeric capture, constructs the main publication/v2 version-5 envelope, sends
it to `Thermal_Model_JSON`, verifies its exact JDBC receipt, and retains the
immutable published origin/v5 observation around numeric origin/v4. A successful HTTP acknowledgement alone
proves neither persistence nor delivery. Configuration/runtime/native expiry
and publication deadlines are checked after Item lookup and request pacing,
immediately before each send. Actual main-receipt expiry is replayed again.

Failures attempt one unavailable publication. A withdrawal is reported verified
only after JDBC returns its matching actual receipt; otherwise the status is
`unverified_failure`. No successful source capture is fabricated from a failed
main receipt or failed withdrawal. In-flight transport failures can still leave
a prior value visible until its validated publication TTL; client freshness
checks remain required.

The service/timer files under `openhab/systemd/user/thermal-installed-forecast.*`
are installation examples, not enabled services. The timer starts 45 seconds
before each issue. The service uses CPU 20%, memory 256 MiB, zero cgroup swap,
24 tasks, nice 15, idle I/O, I/O weight 10, one numerical thread and a 90-second
service deadline. Its separate small-publication preflight requires at least
1.5 GiB host available memory and memory PSI avg10 at most 0.5. This does not
change the larger training/capture preflight or authorize concurrent work.

Before installation, verify the exact candidate/runtime/interpreter binding,
private source configuration, genuine native-v2 collection, both String Items
and JDBC persistence, and a compatible version-5 UI reader. The UI and scorer
integration must be verified before enabling this example service. The separate numeric Item
example is `openhab/file-config/items/thermal-model-original.items`. Disable the
competing legacy shadow publisher before enabling this timer. Honor the actual
systemctl password requirement; do not bypass it. Run the private configuration
check first, then qualify an actual scheduled shadow delivery with both original
persisted receipts. Service enablement is separate from scientific graduation.

Production remains gated on a genuine frozen candidate, stability and calibrated
uncertainty, predeclared baseline wins, and enough untouched and prospective
independent source-qualified days/windows. Fixtures and test clocks confer no
release authority. Advice and automatic actuation remain disabled; PR #3,
WeatherNext and deferred backup/recovery work remain outside this stage.


Local live-entrypoint validation completed in separate serial capped workloads:
26 live orchestration/input/transport checks, 24 publication compatibility checks,
and 14 existing archived-weather checks passed. The two review findings were
reproduced before their fixes: expiry during metadata/pacing and raw mass state
with changing native observations. Follow-up review found no material remaining
issues. The executable local import closure has 55 source files, all within the
57-file declared runtime manifest (the legacy entrypoint and package identity
are additionally retained). Systemd calendar/service/timer syntax checks passed.
These checks make no claim about actual household qualification or publication.


## Collect mature installed-domain outcome packets

`openhab/scripts/thermal_installed_score.py` fills the read-only collection step
between an actual publication/v3 capture and qualification replay. Its default
invocation, `--config PRIVATE_SCORE_CONFIG`, checks owned private configuration
and performs no household query or evidence write. Explicit `--collect` requires
one resolved original `--origin` path and one `--horizon` from 1/6/12/24 hours.
There is no assessment-clock, phase, baseline, model-selection or active override.

The closed private schema is `earthship-installed-shade-score-config/v1`, with
exact fields `schema`, `openhab_base`, `output_directory`, `token_file`,
`native_db_config` and `native_policy`. Keep all three source files owned mode
0600 in owned mode 0700 directories, and the output directory owned mode 0700.
Reuse the approved Hex token file. No forecast-provider credential or journal
DSN is needed by the score reader. Its native configuration must use the fixed
local read-only temperature reader and declared v2 hardware-phase policy.

Run one collection at a time with the same CPU20%, memory256MiB, zero cgroup
swap, tasks24, nice15, idle-I/O, one-thread and hard90-second bounds as the small
live publisher. The strict resource/headroom preflight is shared. For example,
using an already installed compatible interpreter and private configuration:

```sh
systemd-run --user --scope --quiet \
  -p CPUQuota=20% -p MemoryMax=256M -p MemorySwapMax=0 -p TasksMax=24 \
  -p IOWeight=10 \
  nice -n 15 ionice -c 3 env \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  EARTHSHIP_QUALIFICATION_FIT=0 EARTHSHIP_REMOTE_QUALIFICATION_FIT=0 \
  timeout --signal=TERM --kill-after=5s 90s \
  python3 openhab/scripts/thermal_installed_score.py \
  --config /absolute/private/score-config.json --collect \
  --origin /absolute/private/original.installed-shade-origin-v3.json --horizon 24
```

The collector shares the publisher's owned nonblocking lock in the original
source archive. `busy` defers without querying or competing with issuance.
`pending` means the target has not matured by the existing five-minute margin.
It rereads both exact original numeric/main JDBC receipts in their original
millisecond windows, never substituting today's Item value. It selects seven
qualified historical same-local-clock cycles with the original issue as the
assessment cutoff before acquiring the outcome. Outcome and comparator receipts
must have the original air hardware phase; v1 sources, late receipts, missing
cycles, changed configuration or mismatching publication are withheld.

A successful `scored` receipt identifies three owned immutable files. The main
source-packet list is suitable for explicit qualification/v3. The separate
numeric source-packet list retains the unchanged numeric origin and actual
numeric receipt for the existing explicit calibration API. Keep those paths
separate: the duplicate-window guard refuses counting a numeric/main pair twice.
Uncalibrated observations retain absent intervals and remain diagnostics until
a separately frozen calibrated candidate passes the release gates. The scalar
score file is a reproducible cache; it grants no release or action authority.
Qualification must still replay the original packet sources.

The command handles one original horizon, with at most 24 paced source requests
within an 85-second reader budget inside the 90-second process deadline. Source
failures return `withheld`; accepted source files are never fabricated. Partial
private retention on a disk error does not authorize release. This command is not
an enabled scoring schedule: live scheduling, compatible private paths and actual
natural receipt verification remain part of the deployment handoff after genuine
native-v2 adoption. No real household scoring or production qualification is
claimed by the synthetic collector tests.


Collector validation: 15 mature-source/replay/maturity/immutability/serialization
checks and 8 real-reader/CLI boundary checks passed in separate serial capped
runs. The actual kernel resource preflight also passed without querying any
household source. Follow-up read-only review found no material remaining issues.
The shared-lock regression failed before serialization was added. An uncalibrated
fixture initially carried the later aggregate runtime instead of the original
base runtime; only its synthetic execution port was corrected. No runtime or
source validator was weakened. Full exact-commit hosted CI is required for this
collector change before integration.


## Exact temperature correction origins

The auxiliary temperature-learning ledger records raw-provider error, but its
legacy rows do not identify the correction originally displayed. Current bias
state must never be substituted into those old issues. The optional
`forecast_temperature_origin.py` observer now preserves a separate version1
origin before and after the existing `Forecast_10Day_JSON` publication. Public
detail2, hourly/daily payloads and prediction equations remain unchanged.

The observer retains the exact raw Open-Meteo snapshot, actual corrected detail
bytes, safe original per-hour bias/count/variance and daily correction state,
explicit native2 outdoor policy, actual source/interpreter identity, original
source files, and actual preparation/publication clocks. It uses immutable
owned private files; changed code/policy and inconsistent clocks refuse the
origin. Optional collection failure cannot prevent normal publication or change
learning state. A failed detail PUT creates no completed origin.

Collection is disabled by default. An operator-prepared environment must supply
both `FORECAST_TEMPERATURE_ORIGIN_DIR` (existing owned0700 absolute directory)
and `FORECAST_TEMPERATURE_ORIGIN_POLICY` (absolute private native2 policy). All
six declared runtime sources must be protected against group/other writes.
These settings are intended for the bounded forecast-intel/forecast-json
consumers after exact-head verification; this source change does not install
or enable them. Do not enable training to collect these origins.

`delivery_verified:false` is deliberate: HTTP completion proves neither actual
JDBC persistence nor a later outcome. The next scoring layer must pair the
exact original detail bytes with an actual matching persisted receipt and a
mature qualified native outdoor outcome in the original hardware phase. Until
that collector/evaluator is installed and real outcomes mature, these origins
are prospective input evidence, not correction-skill or release proof. No old
ledger entries are upgraded, and no more complex correction model is released.

The October9 native source cutover is separate from thermal graduation. Its
actual four-stream source2 epoch readback and fresh JDBC selection passed after
OpenHAB completed its operator-reported upgrade restart. The restart gap stays
unqualified. Existing forecast input timers resumed under a shared20%CPU,
256MiB memory, zero swap and24task limit with a nonblocking serial lock; the
legacy trainer remains stopped. The existing displayed thermal output remains
low-confidence shadow output, and no production ML gate has passed.


## Original temperature correction source replay

`forecast_temperature_score.py` evaluates the existing bias correction from
original source packets, without reading current learning state or changing any
prediction. Its separate `earthship-temperature-correction-score-sources/v1`
packet binds the immutable origin digest, actual exact persisted detail bytes
and timestamp, original target, original native-history query interval, actual
assessment clock and complete bounded raw native2 snapshots. A score cache is
not accepted as a source packet.

Only original future targets with exact original publication identity may be
scored. The outcome must mature by five minutes and qualify through the existing
native2 epoch/lifetime/barrier reader under the original policy. Invalid and
expired outcomes are withheld; they never become zero-error observations.
Original raw weather must explicitly use Fahrenheit. Raw and corrected hours
match in original provider order, preserving valid repeated DST offsets and
refusing nonexistent local hours or conflicting UTC targets.

The summary replays raw packets, rejects duplicate issue/target pairs and
stratifies source/interpreter revision, hardware phase, local hour, declared
lead bucket, calendar season and original forecast weather-code category. These
categories describe the original provider forecast, not retrospectively revised
weather. Original adjustment-state strata remain explicit. Multiple issues for
the same actual target in one stratum contribute one metric point, chosen by
earliest original publication rather than smallest error. Metrics give equal
weight to target calendar days after that selection.

`complete_issued_hour_days` requires all expected hourly targets from one
original issue for a whole local day, including23/25hour DST days. It is
**not continuous sensor coverage**, and partial observations cannot establish it.
Raw/qualified observation counts and unique target dates remain separate.
All auxiliary score/summary outputs have `release_authority:false`; they grant
no thermal or correction-model graduation.

For a bounded offline repeat after installation or from the reviewed source
checkout, run the following with the same interpreter/PYTHONPATH and
CPU20%/256MiB/no-swap/task24/nice15/idle-I/O/thread1/90second limits used by the
other local qualification commands. Set the two directories to the owned0700
origin and source-packet archives; readers require owned0600 immutable files.

```python
from pathlib import Path
import json
from forecast_temperature_score import read_sources, summarize_sources

origins = Path("/home/sat/.local/state/forecast-intel/temperature-origins-v1")
sources = Path("/absolute/private/temperature-score-sources")
packets = (read_sources(sources, path) for path in
           sorted(sources.glob("*.temperature-score-sources-v1.json")))
print(json.dumps(summarize_sources(origins, packets), indent=2))
```

The packet writer uses content-addressed immutable files and never overwrites
a conflicting/corrupt existing source. Current real-source development replay
has one short-lead qualified pair and zero complete issued-hour days; its raw
and corrected errors reproduced with network/database connections blocked.
That remains insufficient to claim general improvement. A scheduled source
collector and ongoing evaluator still need integration. Use the already
authorized OpenHAB `serviceId=jdbc` persistence API for exact detail receipts;
existing native database reader permissions need no expansion.


## Explicit original temperature outcome collection

`forecast_temperature_collect.py --config /absolute/private/config.json`
checks configuration only. Add `--collect --origin-sha256 ORIGINAL_DIGEST
--target ORIGINAL_ISO_TIMESTAMP` to collect one explicit as-issued target.
The config schema is `earthship-temperature-correction-collect-config/v1`,
with exactly `schema`, `openhab_base`, `token_file`, `native_db_config`,
`shared_lock`, `origin_directory`, and `output_directory`. All paths must be
absolute and resolved; files are owned single-link0600 and directories0700.
Use the existing Hex token and dedicated weather_temperature_reader config,
and the same existing native-input-consumers lock used by forecast workers.
No database grant is required. Original and outcome directories are separate.

Collection requires actual CPU20%/memory256MiB/zero-swap/24-task/IOWeight10
limits, nice15, one numerical thread, at least1.5GiB available memory and
low memory pressure. Bound the process with timeout90s and idle IO priority.
The command acquires the shared consumer lock internally; do not wrap it
with another flock acquisition on the same file. Pending targets and busy
locks do not issue backend requests. Failure output contains status only.

The read adapters fetch exact original Forecast_10Day_JSON JDBC bytes/time
through the fixed loopback persistence GET and raw native rows through the
existing read-only database role. Native barriers remain authoritative;
NULL/oversized envelopes refuse the collection rather than exposing an older
healthy value. Raw packets are content addressed. The first qualified packet
for an origin/target is retained immutably and replays on subsequent calls;
withheld packets remain diagnostic and may be retried. No model fitting,
Item writes, notifications or release authority are exposed.

This command is an engineering entrypoint. It does not install or schedule
itself, and its existence is not evidence of chronological accuracy or
production thermal qualification. Verify exact-head hosted checks before
installation, then verify a natural raw packet and offline source replay.


`--batch` adds bounded diagnostic collection under the same resource preflight
and shared lock. It samples the earliest archive completion per Denver calendar
day using file metadata as a scheduling hint. Original publication clocks,
model revisions, hardware phases and outcomes remain authoritative in source
replay. Sampling does not assert exhaustive issue or revision coverage.

Each batch attempts at most four mature targets and checks a sixty-second
selection budget; an outer90s timeout bounds the process. At most100000archive
entries and366capture dates are accepted. Pending hours do not issue backend
requests. Invalid selected originals are counted as source errors, while other
valid originals may proceed. A transport failure pauses further attempts for that origin in the current
batch and records a thirty-minute scheduling cooldown. Fresh sampled origins
are visited before retries, with recent capture dates first; expired retries
are ordered by their retry deadline so old failures cannot monopolize the
batch. The failed origin remains retryable. These mutable hints contain no
outcome or qualification claim. Once a raw
qualified or withheld packet is retained, a private attempt hint suppresses
repeated scheduled reads; explicit one-target collection can retry withheld
outcomes. Hints provide no score, support or release authority. Reports must
select original per-target source packets and replay them, avoiding duplicate
attempts for one issue/target.

`openhab/systemd/user/forecast-temperature-score.service` is an uninstalled
template. Render its source placeholder to a reviewed protected exact-head
generation. The matching timer requests a small batch every ten minutes after
the hour's five-minute maturity delay, without missed-run catch-up. The service
uses the existing shared input slice and acquires the shared lock internally.
Verify exact-head hosted checks and actual cgroup limits before enabling it.
This schedule neither fits a model nor publishes or activates a thermal output.

### Existing temperature correction archive report

The existing hourly corrections retain their operational equations. To evaluate
retained attempts offline, use the source-replaying archive report from the
reviewed checkout. Run under the same bounded resource scope as the collector;
this command performs no network reads, fitting, or publication:

```bash
PYTHONPATH=openhab/scripts python3 - <<'PY'
import json
from pathlib import Path
from forecast_temperature_score import report_archive
config = json.loads(Path.home().joinpath('.config/hex/temperature-correction-score.json').read_text())
report = report_archive(config['origin_directory'], config['output_directory'])
print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
PY
```

The version-one archive report replays every matching content-addressed packet,
including retries. For each original issue/normalized target, it selects the
first qualified assessment, breaking equal assessment times by source digest;
if none qualifies, it selects the earliest retained attempt. It never selects
by forecast error. Retry and qualified-target hints have no evidence authority.
Selected source filenames make the summary reproducible. Metrics retain the
scorer's runtime, hardware epoch, hour, lead, season, weather-category, and
adjustment-state stratification and equal target-day weighting.

The report covers all retained raw packets, up to 2,048 attempts and 8,192 total
archive entries. It refuses corruption or excess inventory rather than silently
truncating. It does not promise an atomic snapshot of a concurrently growing
archive: rerun after collection completes for a settled inventory. Counts of
complete issued-hour days describe forecast-target coverage, not continuous
sensor coverage. Neither the report nor its summary has release authority.

### Preserve legacy shadow diagnostics separately

The deployed v4 artifact must remain with its compatible reader. Opening its
registry with the newer v5/v6 reader can quarantine the artifact; switching the
whole shadow runtime merely to enable an origin hook is therefore refused.

`thermal_legacy_origin.py` provides a separate
`earthship-thermal-legacy-shadow-origin/v1` diagnostic contract and optional
wrappers for the existing native reader and forcing-capture writer. It preserves
the original writer's v2 forcing record (including the actual v4 artifact), the
native receipt grid observed at the issue, and the executing runtime identity.
It freezes the receipt proof, checks original clocks, receipt expiry and initial
state binding, and refuses runtime changes across a capture. Extra diagnostic
failures produce a sanitized gap while preserving the original return values
and exceptions. It never opens a model registry or qualifies an artifact.

The runtime fingerprint reads declared original source bytes without executing
them and binds the actual loaded numerical dependency versions, interpreter,
and observer hashes. A guarded integration must supply the complete executing
and worker source closure. Fingerprints alone do not retain a compatible replay
environment. The diagnostic record explicitly makes no claim of retained
runtime bytes, raw native snapshot binding, verified JDBC publication delivery,
or phase-qualified v4 training. These remain separate evidence requirements.

The new graduation readers refuse this legacy diagnostic schema. Keep its
archive separate from native-qualified candidate origins. Installation and
entrypoint integration are still required; importing this module enables no
live collection, publication, model fit, recommendation or household action.

The guarded entrypoint is `thermal_legacy_observe.py`. Its closed private
`earthship-thermal-legacy-observe-config/v1` configuration contains only
`schema`, `legacy_root`, `source_sha256`, `archive`, and `shared_lock`.
Use absolute resolved paths, owned0600 files and owned0700 directories.
The code root is a separate private copy of the compatible original source
closure plus the reviewed observer/entrypoint. Every code file must be declared
and match its full digest; undeclared inventory members are refused. Preserve
the deployed core files, accepted v4 artifact, existing environment and original
shadow behavior. A newer v5/v6 reader cannot replace the compatible v4 reader.

Default invocation verifies configuration/source bytes without loading original
or numerical modules. Only `--observe` requests the literal original
`shadow --publish` cycle. Actual CPU20%, memory256MiB, zero swap,24-task,
IOWeight10 or verified idle I/O, nice15, one numerical thread, no bytecode writes,
1.5GiB memory headroom and low memory pressure are required before protected
imports. It acquires the existing shared consumer lock nonblocking; busy exits75
without running a cycle. Config/source hashes and the held lock inode are checked
again before imports and by the diagnostic runtime provider. A preloaded,
unrelated original-module namespace is refused.

Render `thermal-model-shadow.service.d/zzzz-legacy-origin-observer.conf` only
after exact observer-head hosted checks and deployment review pass. It preserves
the existing shadow cadence/environment and caps the process at90seconds. The
entrypoint does not install units or enable timers. The original forcing archive
and native-v2 environment must remain configured on the shadow service for the
optional wrappers to receive original proof. Configuration verification alone
is not live collection, verified delivery or a thermal qualification result.


### Native base shadow calibration bootstrap

Before a calibrated candidate exists, use an owned private live-config/v1 with
release-inputs/v2 pointing to the source-qualified base candidate/v1 and its
complete raw runtime closure. Set `registration_path` and `original_pairs_path`
to null. In the same capped execution environment, explicitly select:

```sh
python3 openhab/scripts/thermal_installed_intel.py --contract-version 1 --config PRIVATE_BASE_CONFIG --bootstrap-shadow --shared-lock EXISTING_PRIVATE_SHARED_LOCK
```

This route requires native raw source preparation, no registered policy, an
uncalibrated base candidate and a shadow main publication. It refuses a
calibrated candidate, receipt-only profile or registered release before
collecting current inputs. Both actual publication receipts remain required.
Its published origin/v3 and subsequent raw score-sources/v2 can supply the
separate raw calibration/v2 cohort; they cannot activate a forecast. Use the
prospective scorer profile compatible with those base observations. Configure
production live-config/v2 only after the frozen calibrated candidate and its
qualification sources exist. Do not point the production example service at the
base bootstrap configuration.

### Independent explicit withdrawal

Use a separate private `earthship-installed-shade-withdraw-config/v2` file with
exactly `schema`, `openhab_base`, `token_file` and `evidence_directory`. It needs
no candidate, model, weather archive or database configuration, so unavailable
model sources cannot prevent an explicit withdrawal. Within the same capped
publication execution environment, run:

```sh
python3 openhab/scripts/thermal_installed_intel.py --contract-version 2 --config PRIVATE_WITHDRAW_CONFIG --withdraw --reason "operator withdrawal"
```

This sends only unavailable publication/v2 version 5 to `Thermal_Model_JSON`,
requires its exact JDBC receipt and retains an owned private withdrawal/v2
record with the reason. It never sends numeric forecasts or control commands.
Stop the publisher timer before returning to the retained compatible legacy
shadow path; retain its previous accepted artifact/runtime and publication
contract. Restore shadow only after verifying that retained runtime and its
publication receipt. A withdrawal receipt alone does not prove that shadow
publication resumed. Backup and disaster recovery remain separate deferred work.


### Raw prospective scoring and the base calibration cohort

The scorer defaults to contract 2. Use an owned private
`earthship-installed-shade-score-config/v2` with exactly `schema`, `openhab_base`,
`output_directory`, `token_file`, `native_db_config` and `native_policy`. It keeps
the existing private file permissions, read-only database connections, bounded
native acquisition and fixed JDBC GET endpoints. The scorer never publishes,
fits, activates or sends household commands.

Within the reviewed capped execution environment, collect one declared mature
horizon from the original published origin/v5:

```sh
python3 openhab/scripts/thermal_installed_score.py --contract-version 2 --config PRIVATE_SCORE_CONFIG --collect --shared-lock EXISTING_PRIVATE_SHARED_LOCK --origin ORIGINAL_PUBLISHED_ORIGIN_V5 --horizon 24
```

Or use an explicit owned private `earthship-installed-score-jobs/v2` queue with
exactly `schema` and `jobs`. Every job contains only an absolute resolved
`origin_path` and integer `horizon_hours` from 1, 6, 12 or 24. At most 256 jobs are
allowed. Batch collection uses:

```sh
python3 openhab/scripts/thermal_installed_score.py --contract-version 2 --config PRIVATE_SCORE_CONFIG --batch --shared-lock EXISTING_PRIVATE_SHARED_LOCK --queue PRIVATE_RAW_SCORE_QUEUE
```

Both paths retain and replay original native queries as score-sources/v3. The
queue uses separate completion/v2 and cursor/v2 files. Those files guide
scheduling and carry no release authority. Each invocation attempts at most one
mature score; invalid jobs rotate before the next invocation. Completed entries
never force replay of the entire prefix before new work. Idle invocations audit
one completion against its original files; missing proof is withheld rather
than reacquired or replaced. A score is not an independent evidence count or a
qualification pass by itself.

For the preceding uncalibrated base shadow stage, explicitly select
`--contract-version 1` with score-config/v1, an original published origin/v3 and,
for batch work, jobs/v1. That compatibility path retains raw score-sources/v2
for the separate raw calibration/v2 cohort. Do not mix these base observations
with candidate/v3 release scores. The old readers refuse the new schemas and
the raw queue refuses the old queue profile.

The scorer unit files remain inert templates. Their explicit contract 2 must
match their configuration, queue, original capture and source/runtime closure.
Render a separate reviewed contract-1 invocation when collecting the base
calibration cohort; do not silently change a production service's semantics.


### Raw publication display compatibility

The UI accepts the closed publication/v2 version-5 envelope only with release/v2
and original numeric forecast/v3. Historical publication/v1 version 4 retains
its separate forecast/v1 or forecast/v2 reader. Mixed profiles, altered source
identities, missing uncertainty, future assessments and expired publications
suppress forecast display. Version 5 uses the existing forecast, shadow and
unavailable presentation, including model revision, freshness, confidence and
the four original 90% nominal target intervals. It adds no interpolated
uncertainty, venting schedule, action recommendation or automatic actuation.
The backend must independently qualify original sources; structural UI
validation is never release evidence. Approved tablet and laptop layouts are
unchanged.


### Guarded raw calibration and candidate freeze command

`openhab/scripts/thermal_installed_calibrate.py --config PRIVATE_CONFIG` checks
only closed private configuration and source-index structure. The default check
uses standard-library code and never imports numerical libraries, replays a
cohort, fits coefficients or publishes a model. It establishes no support or
release eligibility.

The configuration schema is `earthship-installed-shade-calibration-config/v1`.
Its exact fields are `schema`, `base_candidate_path`, `base_runtime_bundle_path`,
`runtime_bundle_path`, `base_runtime_sha256`, `runtime_sha256`, `raw_sources_path`,
`raw_sources_sha256`, `calibration_start`, `calibration_end`, `regimes`,
`output_directory` and `shared_lock`. Use absolute resolved paths, owned private
0600 files and 0700 directories. Pin the SHA256 of the original raw index bytes
and both original runtime identities. The source index contains only
`raw_score_sources_path` references to original score-sources/v2 archives; scalar
residuals and support summaries are not calibration inputs. Calibration must
follow base training/freeze and precede the final frozen candidate and release
intervals. Creation clocks come from the command, with no date override.

In the same reviewed publication resource scope, explicitly run:

```sh
timeout --kill-after=5s 90s python3 openhab/scripts/thermal_installed_calibrate.py --config PRIVATE_CONFIG --calibrate
```

The preflight precedes source reads. The command holds the existing shared
consumer lock, disables coefficient fitting, verifies original base fit gates,
replays raw calibration sources and retains calibration/v2 with typed readback.
Incomplete independent calibration support returns `calibration_incomplete`
and freezes no candidate. Complete support permits candidate/v3 construction
and immutable typed readback; that candidate remains a development candidate
with no release authority or production installation. A private execution
receipt retains the command source bytes, source/runtime identities and result.

One 85-second budget starts before numerical imports and bounds nested fit
measurement and raw replay. Nested stages cannot renew it. Final calibration,
candidate and receipt publication checks the remaining budget and held lock
immediately before atomic publication, including after temporary-file writes.
The executed budget helper belongs to both historical and raw runtime closures.
A 64-file declared closure must already include its observer, preserving the
existing 64-file manifest bound. Recreate and verify the actual runtime archive
before using this command; an older archive missing the helper is incompatible.

This command neither preregisters policy nor activates a forecast. Thresholds
must still be derived and sealed from original development sources before
untouched evaluation. Only subsequent qualification-report/v5 can support a
release decision; calibration completion alone cannot.

### Guarded raw development policy sealing

After retaining a source-qualified candidate/v3, use
`thermal_installed_register.py --config PRIVATE_CONFIG` for a standard-library,
check-only configuration check. It does not replay evidence or seal thresholds.
Explicit `--register` derives thresholds from original development queries and
seals registration/v3 before the untouched holdout and prospective intervals.

The closed schema is `earthship-installed-shade-registration-config/v1`, with
exact fields `schema`, `candidate_path`, `candidate_sha256`,
`runtime_bundle_path`, `runtime_sha256`, `raw_sources_path`,
`raw_sources_sha256`, `intervals`, `regimes`, `output_directory` and
`shared_lock`. Paths must be absolute, resolved and owned private; files are
0600 and directories 0700. Pin the frozen candidate identity, executing runtime
identity and SHA256 of the original index file bytes. The index contains only
original `raw_score_sources_path` references to score-sources/v2 development
archives. It cannot contain scalar scores or thresholds.

`intervals` contains exactly `development_start`, `development_end`,
`holdout_start`, `holdout_end`, `prospective_start` and `prospective_end`;
only the last may be null. Use aware timestamps. Development must have elapsed;
both release intervals must begin after the actual declaration and seal.
The command accepts no declaration-clock override. Regimes are distinct values
from `warm`, `shoulder`, `winter` matching genuine supported development data.

Within the reviewed serial publication resource scope, run:

```sh
timeout --kill-after=5s 90s python3 openhab/scripts/thermal_installed_register.py --config PRIVATE_CONFIG --register
```

Preflight precedes configuration reads. One shared lock and 85-second budget
cover numerical imports, typed candidate/calibration readback, original-query
replay, derivation, immutable sealing and readback. Runtime, source-index,
candidate and command bytes are rechecked, including through the shared guard
immediately before final atomic writes. Existing statistical support and
baseline-derived thresholds remain unchanged. Actual-clock chronology is
checked again after the private temporary write, so a late seal is refused.

The private execution receipt retains command and configuration-helper source
bytes and original identities. A successful `policy_registered` result has
`release_authorized=false` and `production_installed=false`. Registration
predeclares the criteria; it does not demonstrate candidate skill. Subsequently
collect and replay untouched and prospective evidence through qualification/v5.
No service is enabled and no active publication is made by this command.

The shared operator lock implementation lives in the already-pinned
`thermal_model/capture_guard.py` module. Qualification, training, calibration
and registration import it directly; the scorer preserves its historical
`SharedScoreLock` export. This keeps guard execution inside the declared
runtime without adding a 65th manifest entry or requiring the scorer CLI merely
to acquire the qualification lock. Recreate the executing runtime archive after
this source change. An isolated diagnostic-stage lock is not a production
consumer lock and cannot establish deployment readiness.

Publication and native base bootstrap require the existing private consumer lock
through `--shared-lock EXISTING_PRIVATE_SHARED_LOCK`. They acquire it before
protected module imports, configuration checks, backend construction or source
qualification. A busy lock returns75 without source reads or withdrawal. The
held inode is checked through request pacing, database/HTTP acquisition and
publication callbacks. The forecast service must join `earthship-inputs.slice`;
its archive-local lock additionally protects publication attempts and receipts.
Default configuration checks require no consumer lock. Independent unavailable
withdrawal keeps its minimal token/evidence configuration and archive lock.

Recreate runtime archives after this guard change. These resource checks do not
authorize activation. Original issue-state query retention and replay remain
necessary before claiming complete raw source authority; selected source2
receipt grids alone do not prove original query/barrier selection.

The issue-query replay foundation provides
`build_native_origin_binding` and `replay_native_origin_binding` in
`installed_shade_raw_score_sources`. A binding requires a retained native query
for every modeled temperature role, the exact assessment clock and trailing
288/289-target grid, approved policy and sensor phase. It independently replays
original rows, including carry and invalid barriers, before comparing selected
receipts. Replay requires the original private content-addressed files to remain
available. The binding grants no release authority.

The source binding is now connected to the explicit numeric origin/v6 described
below. Main receipt profiles and acquisition APIs exist, but live routing and
complete source-chain qualification remain unfinished. Existing origin/publication versions
retain their prior meanings. The base shadow bootstrap and original calibration
still need routing to the explicit query-bound base capture described below
before the full chain can claim raw source authority. Rebuild pinned runtimes after integration; passing
these tests does not authorize deployment.


Numeric origin/v6, forecast/v4 and source-scored-pair/v6 bind the original issue
query files through `native_origin_binding`. The output and scored pair expose
its digest. `build_source_calibrated_capture` requires the existing prepared raw
calibrated candidate plus `native_source_paths`, one original private archive
per modeled sensor role. It preserves all current initial-state, weather, action,
runtime, physical and calibrated-interval checks. Prediction and scoring replay
the issue sources before and after numerical work; readback repeats validation.
Immutable storage rechecks the original files immediately before the final
rename, within the shared replay budget. Missing or changed original sources
refuse acceptance, even when a capture is rehashed. Version2/version4 readers
refuse origin/v6. This numeric contract remains shadow-only and grants no
release or actuation authority. The live producer and main publication profile
do not yet select it.


`collect_source_v2` acquires the original bounded native query packet through the
same strict policy/epoch checks and stable read-only transaction as the existing
receipt reader. `SourceLiveBackend` retains a private content-addressed packet
for each modeled role, independently verifies the original issue grid, and
returns `native_source_paths` alongside the established weather/state/action
context. It guards the consumer lock, budget and configuration around reads and
immediately before atomic query-file retention. Defaults still use the existing
receipt-only backend; no CLI or installed service selects this new backend yet.

Base numeric origin/v8, forecast/v5 and scored-pair/v8 expose the query-bound
shadow bootstrap APIs: `build_source_issued_capture`,
`write_source_issued_capture`, `read_source_issued_capture` and
`score_source_issued_capture`. They require the complete declared raw runtime
closure, original query files, unchanged prepared base candidate and unchanged
physical/weather/action/baseline checks. Internal version1 numerical views are
not persisted or presented as original publications; returned identities bind
the actual version8 capture and actual version5 numeric receipt. No calibrated
interval, advice, activation or actuation authority is introduced. Validation
and scoring recheck retained queries after numerical work; immutable capture
retention rechecks them before rename. Original version1 readers refuse the new
capture.

Bootstrap main-publication receipts, queued original scoring, raw calibration,
candidate/registration qualification and the operator/UI profile still need
explicit source-bound routing. Neither the new backend nor these numeric APIs
close that integration gap or prove sufficient independent release evidence.
Rebuild pinned runtime archives after these source changes.


Publication/v3 version6 and release/v3 structurally bind
`nativeOriginBindingSha256` to the unchanged numeric output's query-binding
digest. The validator preserves the existing freshness, physical, action,
interval and authority-field checks. Its private validation projection is never
published or substituted for an original receipt. Base forecast/v5 remains
uncalibrated and cannot activate, even with a qualification marker. Calibrated
forecast/v4 can structurally claim active mode only with the explicit
qualification-report/v6 marker; this marker and a report digest alone confer no
release authority. Complete q6 assessment and the source-aware preparation and
publication factory are still required and not implemented by these shape APIs.

Main origin/v7 records numeric origin/v6; main origin/v9 records base numeric
origin/v8. `build_source_publication_capture`, `write_source_publication_capture`,
`read_source_publication_capture` and `score_source_publication_capture` bind both
actual persisted String Item receipts, exact issue/runtime/candidate identity,
the original query proof and native expiry at the real main-receipt timestamp.
Scored-pair/v7 or v9 returns both actual receipt hashes. Original query loss or
changed/rehashed receipts refuse replay; immutable main capture storage
revalidates immediately before rename. Older main readers refuse these records.
`unavailable_source_installed_publication` carries neither query proof nor a
qualification claim.

No installed producer service, publication operator CLI, prepared factory or UI
selects this new main-publication profile. The explicit scoring CLI profile
described below can consume these original receipts. Calibration/candidate/
registration and complete qualification still need the source-bound chain. Passing these
component tests does not authorize activation or establish natural delivery.


Original-query scoring archives now have explicit profiles:
score-sources/v4 binds base main origin/v9 to numeric origin/v8, and
score-sources/v5 binds calibrated main origin/v7 to numeric origin/v6.
`collect_source_published_score` retains the original issue binding digest,
actual main receipt, seven historical comparator cycles and mature outcome
queries. `read_source_base_score_sources`,
`read_source_calibrated_score_sources` and typed `read_source_score_sources`
independently replay the original issue, comparator and outcome sources before
accepting a score, including a final source recheck after numerical replay.
Immutable scoring writes recheck source files and the caller's configuration
and lock guard after temporary-file retention and before rename. Old archive
readers refuse these versions. These records carry no release authority.

Candidate, development registration and complete qualification still need
explicit routing through the source scoring/calibration profiles below. No installed
scorer or producer selects them yet. Qualified independent support
and natural prospective outcomes remain required before production activation.


The explicit scoring configuration and queue profile are now version3:
`earthship-installed-shade-score-config/v3`,
`earthship-installed-score-jobs/v3`,
`earthship-installed-score-job-completion/v3` and
`earthship-installed-score-cursor/v3`. Configuration retains the same closed
source-path fields; no activation or authority override is accepted. Queue jobs
retain exact original main paths and supported horizons. Old configuration and
queue readers refuse this version. Defaults remain profile2.

`thermal_installed_score.py --contract-version 3` selects source collection7/9
and queue3 explicitly. Configuration checking performs no source acquisition.
Collection or batch requires the existing resource preflight and held shared
consumer lock; config3 backend construction refuses missing/noncallable guards
before private backend reads. Native query writes check the guard and unchanged
configuration after temporary retention, immediately before linking. The read
budget checks the held guard before requests, after pacing and after responses.

`collect_source_queued_score` accepts only main7/9 and raw scoring archives4/5.
Original capture validation, collection and completion replay share the queue's
unchanged 55-second deadline, original queue bytes and backend guard; nested
replay cannot renew that deadline. Acquisition also checks the shared deadline
before HTTP dispatch after pacing, after responses, during native query retention,
and between native SQL statements. HTTP, connection and native statement timeouts
are clipped to the remaining budget; a connection that expires during acquisition
is closed. The source transaction uses optional guards, preserving legacy query
behavior. These bounded in-flight operations still require the outer process cap;
this is not a real-time scheduling guarantee. Configuration verification remains
separate from acquisition checks to avoid recursion through the queue callback.
Completion references remain nonauthoritative
and are retained immutably only after replaying original sources again after
the actual temporary write. A missing completed source withholds the job instead
of querying a replacement. Cursor scheduling remains bounded and separate from
release qualification.

The installed units still select the existing profile. This explicit read-only
scoring entrypoint does not install or activate a source-aware producer, create
qualified calibration support, seal thresholds or authorize production. Source candidate/registration/q6, publication preparation and
UI/operator release routing remain required. Rebuild pinned runtime archives before selecting
changed source bytes; measure and bound raw issue-query archive storage before
installing the producer.


Development calibration now has a separate source-qualified replay profile:
`earthship-installed-shade-calibration/v3` declares
`earthship-installed-shade-score-sources/v4` as its source contract.
`build_source_calibration`, `validate_source_calibration`,
`write_source_calibration` and `read_source_calibration` require base main9
originals with numeric8, the candidate's unchanged numerical training evidence,
and original issue/comparator/outcome query files. Calibration binds the native
issue-query digest alongside actual numeric/main receipt and native-score
bindings. Old calibration1/2 readers refuse this contract; original records
retain their meanings.

`score_source_base_packets` and `score_source_calibrated_packets` replay only
source archives4 and5 respectively. Before numerical work, admission bounds
include every original modeled issue-query file as well as outcome/comparator
queries, with the existing private ownership, per-file, count and aggregate
limits. Reference paths are bounded before encoding and copying. Nested source
replay inherits the local/shared deadline instead of starting an independent
unbounded operation. These scoring ports make no release decision.

The calibration method is unchanged: symmetric absolute-residual order
statistics, at least 35 independent local days/nonoverlapping windows for each
horizon and declared regime, and no coverage guarantee. A dense or sparse
single-day record remains incomplete. Learning and validation replay originals
again after summary computation. Index/record retention checks originals after
the actual temporary write and before immutable rename; typed readback replays
the original numerical fit and original source files. A missing source withholds
calibration rather than fabricating support. Source calibration operations share
one 60-second budget across nested fitting, scoring and retention, clipped by any
outer caller budget.

These component tests establish no operational capacity for a complete qualifying
cohort. Measure and bound original-query storage and full-cohort replay on this
host before installing a producer. Source calibrated
candidate4, development registration, complete q6 qualification, prepared
publication and release operator/UI routing remain unfinished. No live service
selects calibration3 yet, and neither a partial calibration nor a schema/hash
marker grants production authority.
