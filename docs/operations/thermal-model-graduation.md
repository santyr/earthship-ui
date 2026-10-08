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

Origin/outcome proofs, graduation/runtime bindings and publication consumers
still require coordinated migration before live v2
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
