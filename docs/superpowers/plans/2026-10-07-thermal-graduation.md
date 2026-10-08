# Thermal forecast graduation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify and graduate the existing thermal forecast only when a frozen candidate wins on qualified independent untouched and prospective evidence.

**Architecture:** A versioned release contract wraps the existing immutable fit artifact. Source-bound qualification evidence drives one deterministic forecast/advisory decision, version 2 publication and rollback to a compatible shadow pair.

**Tech Stack:** Existing Python/SciPy thermal stack, native receipt readers, Svelte/Vitest UI, existing guarded deployment tooling.

**Spec:** `docs/superpowers/specs/2026-10-07-thermal-graduation-design.md`

## October 8 operator scope update

Backup and disaster-recovery implementation and tests are deferred to a separate
later finishing stage. They are not prerequisites for current ML algorithm work
or forecast deployment. The operator accepts rebuilding from GitHub code and
fresh data after a catastrophe. Preserve existing recovery artifacts and code;
do not expand or execute the recovery/export/restore workstream now.

Prioritize development-only error diagnosis, measured algorithm improvement,
frozen-candidate qualification, and deployment of the ML forecast path. Keep
forecast withdrawal on invalid/stale inputs or baseline regression, host resource
limits, source provenance, and no automatic actuation. These runtime safeguards
remain part of ML behavior, independent of disaster recovery.

Earlier recovery addenda below record completed work and historical requirements;
their recovery prerequisites are superseded by this operator scope update.

## October 8 local execution update

The operator removed the off-host execution requirement. Local fitting and
qualification are permitted; an external runner is optional, not a dependency.
Run one bounded job at a time, inspect current memory/CPU/I/O pressure before
launch, enforce CPU/memory/no-swap/process/time limits, and stop on resource
pressure or limit violations. Avoid full local suites and concurrent numerical
jobs. Preserve training-source integrity and all predictive qualification gates.
Earlier location restrictions are superseded; recovery work stays deferred.

## Global constraints

- PR #2 is merged; PR #3 household-planner architecture remains deferred.
- No WeatherNext/provider migration, automatic actuation, unsolicited messages or safety-policy changes.
- PV/SoC/temperature hardening remains diagnostic; existing equations stay unchanged.
- Source-bound raw evidence is authoritative; no reconstructed action becomes confirmed.
- Final holdout cannot inform thresholds or candidate selection; already inspected outcomes remain development data.
- Legacy artifact/publication schemas remain exact. New release schema is `earthship-thermal-release/v1`; production output is version 2.
- Forecast graduation and action-advice graduation have separate gates.
- Preserve the November no-vent default until the operator changes it.
- Protect the household host: only one small local check in verified CPUQuota=25%, MemoryMax=768M, MemorySwapMax=0, TasksMax=48 and nice15 scope; numerical threads1. Require verified low I/O weight when available, or verified idle I/O priority with mandatory byte pacing when the user I/O controller is not delegated. Run full suites in CI; local model fitting is allowed with verified resource limits and a finite deadline.

## Review focus

- Missing, duplicate or changing source epochs must refuse release evidence.
- Dense or overlapping observations cannot inflate independent support.
- Revised forcing or late origin inputs cannot repair an issued forecast.
- Good pooled scores cannot graduate an insufficient single candidate/regime.
- Caller-supplied active flags, stale proof or incompatible runtime cannot bypass qualification.

## Task 1: Freeze and re-evaluate current qualified evidence

**Files:** `docs/operations/2026-10-07-thermal-graduation-reassessment.md`, `scripts/thermal_qualification_evidence.py`, `scripts/test_thermal_qualification_evidence.py`.

**Interfaces:** `summarize_pairs(pairs, *, horizon_hours, artifact_sha256=None)` returns paired MAE/RMSE/bias/coverage, independent UTC windows, local-day/regime/revision/source support. `verify_capsule(directory)` verifies the immutable acquisition manifest and original receipts/captures. No network or mutable registry access in replay.

- [x] Write boundary tests for non-overlap, revision stratification, native epoch qualification and altered capture/outcome refusal; observe RED.
- [x] Implement pure evidence accounting and immutable source verification using existing capture/native receipt contracts.
- [x] Reproduce the frozen October 7 reassessment; classify each existing blocker as closed, still_blocked, not_required_for_forecast_stage or required_for_advisory_stage. Record development-only status.
- [x] Run focused evidence tests and the tooling suite, then commit. Full suites ran in remote CI, per host safety constraint.

## Task 2: Preregister a versioned policy and deterministic qualification

**Files:** `openhab/scripts/thermal_model/graduation_policy.py`, `graduation_statistics.py`, `graduation.py`, their focused tests, `scripts/thermal_graduation_evidence.py`, `scripts/thermal_policy_registration.py` and `scripts/qualify-thermal-graduation.py`.

**Interfaces:** `derive_policy(development, *, declared_at, intervals, candidate, regimes)` produces an exact versioned policy, numerical thresholds and derivation references. `qualify(policy, evidence, fit_evidence, *, now)` produces a versioned report with every gate and recommended stage. Unsupported or insufficient data is a refusal, never a fabricated pass.

- [ ] Test missing policy, predeclaration after holdout, candidate/runtime/epoch mismatch, baseline loss, overlapping support, failed conditioning/stability and unqualified action evidence; observe RED.
- [x] Implement numerical caps/support from independent development baselines and declared statistical precision, paired skill against both baselines, and immutable source-backed policy registration. Actual candidate policy registration still requires sufficient qualified development evidence before a future untouched interval.
- [ ] Implement exact validation and deterministic per-horizon/regime qualification, separating forecast and advisory gates. Add forecast-qualified/advisory-ineligible and qualified confirmed-action cases.
- [ ] Generate matching machine/human reports; run focused tests and commit.

## Task 3: Improve and freeze the actual thermal candidate

**Files:** Existing `thermal_model/dynamics.py`, `pipeline.py`, `evaluation.py` and focused thermal tests only if a demonstrated development defect warrants a change; versioned candidate fit evidence and private source-bound development snapshots.

**Interfaces:** A frozen artifact/runtime and explicit independent-day conditioning/stability report consumed by Task 2. No final holdout outcomes enter fitting or selection.

- [ ] Trace current errors using original forcing/origin state and native outcomes; keep action assumptions as issued.
- [ ] If development evidence identifies a useful change, add a meaningful failing test, implement the narrow change and evaluate chronologically on development data.
- [ ] Freeze candidate, runtime and policy before untouched evaluation. Persist all identified sensor/hardware epochs.
- [ ] Run dynamics/artifacts/pipeline/replay suites; commit any source change with development evidence. If support is insufficient, record it and continue remaining engineering.

## Task 4: Versioned production publication and honest UI

**Files:** `thermal_model/release.py`, `thermal_intel.py`, production-output tests, `src/lib/thermal/modelResult.js`, `src/lib/ui/ThermalModelCard.svelte` and their existing tests.

**Interfaces:** `build_release_output(shadow, release, *, now, runtime_revision, sensor_epochs)` returns validated version 2 output. Production modes derive from Task 2 gates. Original v1 validation remains unchanged.

- [ ] Test invalid shadow-to-active transitions and old-reader refusal, explicit unavailable output, stale model/sensors/proof, missing forcing, physical/finite failures and action-ineligible forecast mode; observe RED.
- [ ] Implement version 2 validation and bounded publication with independent baseline/prospective capture continuing. No actuator calls.
- [ ] Update the UI to show validated mode, forecast/action confidence, revision, freshness and intervals; test truthful badges and stale/invalid fallback.
- [ ] Run publication/UI suites and build, then commit.

## Task 5: Prospective withdrawal; recovery work deferred

**Files:** ML release/monitor path, deployment validation and graduation runbook. Existing recovery tooling and tests are retained for the deferred stage.

**Interfaces:** Withdrawal uses current prospective baseline/calibration evidence and source compatibility, independent of household safety alerts. Recovery receipts and restoration transactions are deferred.

- [ ] Test invalid/incompatible artifact refusal, source epoch drift and prospective baseline regression for the deployed ML path. Active-to-shadow recovery and interrupted-restore tests are deferred.
- [ ] Implement release withdrawal for the ML path. Deterministic recovery installation and restoration are deferred.
- [x] Add a versioned current-evidence monitor using the latest policy-required independent prospective days per horizon/regime. Preserve historical statistics v1, require statistics v2 in qualification report v3, and refuse prior v2 reports in release. Test pooled-history masking, regime-specific loss, calibration, sparse/stale support and ordering; guarded installation and live withdrawal remain open.
- Deferred: restored-journal rehearsals, cold recovery, legacy recovery installation and recovery suites. Keep these as a separate later workstream.

## Task 6: Qualification, CI and staged production decision

**Files:** Final JSON/Markdown qualification report, runbook, PR/merge record and private rollout receipts.

**Interfaces:** All Tasks 1–5 feed the same deterministic decision. Neither a UI badge nor an artifact file enables production.

- [ ] Run normal CI, ML hardening, thermal delivery, dynamics/artifacts/pipeline, qualification, prospective scoring and deployment/UI/fail-safe checks. Recovery-specific suites are deferred.
- [ ] Review the complete branch; correct material findings with RED/GREEN evidence. Merge only with passing required checks.
- [ ] If real release gates pass, deploy Stage A with parallel baseline scoring and verify natural publication; Stage B only if separate action gates pass.
- [ ] If physical evidence is insufficient, keep activation closed and state exact missing independent frozen-candidate/regime/action observations. Do not claim this goal achieved merely from code/CI completion.


## Task 5 implementation boundary: preserve the real v4 recovery pair

The retained pre-graduation artifact is v4. Current rollback snapshot v1 uses the
v5 artifact decoder and runtime bundle v1 requires an origin-capture observer.
Direct checks against the retained v4 inputs refuse both interfaces. Neither
restriction may be relaxed or repaired by relabeling the old artifact or adding
an observer to its historical source closure.

Implement a separate versioned legacy recovery generation within Task 5:

- Preserve the original artifact/publication bytes, complete declared source
  closure, ordered runtime revision, interpreter identity and required environment
  bundle identities. Use the retained library bindings and ancillary data.
- Keep existing v1 snapshot/runtime contracts exact. An old reader must refuse
  the new generation schema; preparation must explicitly select the legacy path.
- Validate legacy artifact eligibility with its own pinned reader in the isolated
  retained environment. A cached successful receipt or caller-supplied boolean
  does not authorize installation or replace fresh byte checks.
- Prepare a new private generation atomically, with an explicit rollback reason.
  Never overwrite a destination or republish its historical output as fresh.
- Prove both missing-input refusal and exact original available-forecast replay.
  These existing private rehearsals establish compatibility for the tested cases,
  not restored-journal qualification, predictive skill or production readiness.
- Complete genuine restored-journal compatibility, guarded installation and
  schedule reconciliation before calling rollback complete. Keep host-specific
  archives, inventory and receipts private; heavy restore checks remain off-host.

All preparation flags remain closed until their corresponding actual checks pass.
This addendum does not change the model graduation gates or add household-planner
scope.

### Task 3 addendum: pre-fit transfer boundary

The current proof snapshot is written after optimization. Host protection requires
a separate input-capture boundary before fitting can run elsewhere. The versioned
`training_inputs` component retains the original series, journal events and native
temperature grids; reconstruction must reproduce the captured dataset manifest
and bind post-cutover raw values directly to receipts. Collection and restored
interval expansion must be bounded before I/O/building. No capture flag grants
fitting, installation or release authority.

The input component, offline fitter integration and bounded capture transport
and native-history budget adapter are implemented and tested. The guarded
capture command integrates the bounded backends. Actual private capture with a
verified source tree and complete development support, the designated
Resource-bounded execution and genuine measured candidate fitting remain required. No Task 3
completion or production qualification follows from component tests alone.


### Task 3 addendum: bounded multi-run acquisition

A full development interval can exceed the safe duration of one paced capture.
Assemble adjacent original measurement snapshots under the same byte, point and
interval caps, while reading the correction-aware journal over the full interval.
Keep native receipts and missing barriers exact. Bind original snapshot hashes,
measurement/assembly code identities and final input identity in a versioned
private assembly record. Retain and verify that lineage when fitting.
The assembly library, guarded command and downstream fitting lineage verification
are implemented and tested. The fitter retains original parents, combined input
and assembly binding before promotion using fit binding v2. Actual guarded
full-interval assembly and independent lineage verification are recorded in private
staging. Genuine measured fitting remains open. This changes input preparation,
not the model or graduation gates.


### Task 6 whole-branch review findings

Independent review of the integrated branch found these blockers; scoped component
tests did not prove their combined runtime behavior. Resolve with focused failing
regressions, then rerun hosted suites and review before rollout:

- [x] Provide a supported default-off observational path to acquire first original
  shadow forecasts under the full frozen release runtime without requiring existing
  qualified pairs. Preserve the original v1 schema and low-confidence shadow
  semantics; test first-origin acquisition and native outcome scoring. The current
  ordinary shadow path binds a different source closure, while release refuses
  publication captures until the source-pair gate passes. The explicit
  `observe-candidate` command now defaults to preview, pins actual candidate and
  full release runtime hashes, simulates only baseline assumptions, and retains
  accepted v1 originals plus the same full runtime bundle. First-pair source
  scoring and failure-order tests pass; independent review confirms the path.
  This does not provide real qualification observations or enable production.
- [x] Make Stage A forecast numbers use the stated baseline/as-issued assumptions.
  Clearing candidate/advice metadata after simulating an optimized hypothetical
  action schedule does not produce that forecast. Preserve existing default v1
  behavior; test a real pipeline fixture where candidate and baseline differ.
  Release now disables candidate search and preserves all baseline trajectory,
  extrema and interval values. The converter refuses candidate-conditioned input.
  Real simulation regressions at 24/72 hours preserve default v1 optimization and
  existing winter baseline behavior; independent review confirms this fix.
- [x] Refuse mixed non-null sensor epochs across trailing origin receipts before
  latent mass-state construction. Validate every receipt against the declared
  epoch; test changing a non-latest receipt to a different valid UUID, including
  rebuilt outer hashes and release refusal. Native collection and both archive
  versions now reject mixed histories before emitting state/proof or computing
  latent mass. Missing barriers and distinct uniform epochs across roles remain
  valid. Fifteen regression cases reproduced the gap before the fix; focused
  origin/capture/native-receipt checks passed. Hosted full suites remain required.

These are implementation defects, separate from the still-missing real fitting,
untouched/prospective evidence, restored-journal qualification, guarded recovery
installation and confirmed-action advisory path. Activation remains closed.


### Task 5 addendum: separate journal export from off-host restore

The existing live journal qualification command couples a household export with
Docker restore on the same machine. Host protection requires separating those
steps before a genuine restore rehearsal can run on the designated off-host worker.

The versioned private `thermal_journal_transfer` component binds a supplied custom
archive to explicit exporter declarations: schema, role, table row digests, source
code identity and clocks. It retains exact bytes under streaming size/pacing bounds
and verifies immutable private membership and content addresses. It does not query
a source, authenticate declarations, inspect SQL objects, run PostgreSQL/Docker or
claim restore/consumer/install/release qualification. All corresponding flags stay
false. The source exporter and off-host restorer must still bind one genuine
read-only source snapshot, validate dump contents, compare restored row proofs,
execute the compatible consumer and prove disposable cleanup before qualifying
journal recovery. No Task 5 completion follows from package tests.

The transferred-journal off-host worker and CLI now implement archive inventory
inspection, explicit interpreter/consumer pins, declaration-to-restored row checks,
read-only consumer rehearsal and token-labelled disposable cleanup before proof
publication. They do not connect to the household source. The legacy same-host
helper only gains an optional ownership label; its existing callers remain exact.
Source authentication and full cold environment remain separate closed report
gates. Mocked orchestration checks run under host caps; real v1/v2 disposable
restore/consumer checks run only in hosted CI. A trusted bounded source exporter,
actual approved off-host worker, genuine legacy rehearsal and guarded installation
still remain required.


### Task 6 integrated review: published timestamp precision

- [x] Preserve full-precision frozen artifact identity while matching the existing
  whole-second publication metadata. The real training path retains fractional
  seconds, so comparing published clocks directly to exact artifact clocks
  rejected otherwise valid candidates. Release now uses the original capture
  contract's UTC whole-second comparison semantics. Published fractional clocks,
  a different published second and mismatched artifact hashes still refuse.
  Regressions use a fractional artifact and real pipeline metadata conversion;
  three cases reproduced the failure before the fix. Focused release checks pass;
  hosted full CI and genuine qualification remain required.


The source-export row-proof component now adds read-only repeatable-read
verification, bounded table/UTF-8 row preflights and paced aggregate CSV hashing.
It preserves original digest semantics and existing restore callers. Genuine
PostgreSQL parity and oversized-row tests are hosted-only. This component does
not open a connection or dump a source; the guarded source exporter and trusted
receipt remain open implementation steps.


A separate dump transport bounds stdout before retention, paces pipe reads and
owns process-group/partial-file cleanup. It leaves the existing live restore
helper unchanged. Its component tests do not establish source export provenance;
connect/audit/snapshot/row-proof/dump/package receipt orchestration remains an
open guarded-exporter step before genuine off-host journal qualification.


The guarded source export command now joins the tested components under the fixed
ninety-second guardian: restricted read-only snapshot/schema/role audit, row proofs,
dump, exact retained-byte binding, stable source/configuration and private atomic
generation. Source file bounds are enforced before descriptor reads, and the
schema-audit helper participates in code identity. A nested dump remains in the
outer guardian's process group. Dump supervision is a wall-clock bound; pg_dump
resets SQL statement timeouts, so audited-connection limits do not transfer to it.

Source snapshot observations do not independently authenticate the exporter.
Receipts keep external authentication and all recovery/install/release authority
closed. Trusted receipt verification/pinning, actual private source acquisition
when headroom passes, and genuine off-host restored legacy rehearsal remain open.


Original source receipt integrity verification now requires independent receipt
and exporter-code pins, exact private generation membership, immutable original
hashes and transfer/schema/role/row-proof/clock binding. A file's self-declared
positive flag does not authenticate it. The helper opens no connection or restore
and keeps external authentication and release closed; actual off-host integration
and trusted source handoff still remain open.


The off-host restorer now optionally verifies the original source generation and
independent pins before backend work and after owned cleanup. Exact nested package
identity is required. Source-bound restore reports use version 2; original version
1 remains exact without these options. Verified receipt integrity is distinct from
external source authentication, complete cold recovery and installation/release
qualification, which remain closed. Actual approved off-host execution and genuine
legacy recovery are still required.


## Current execution dependency

The current integrated branch has passing hosted repository, ML hardening and
thermal delivery checks. These tests include synthetic disposable source exports,
restores and consumer compatibility; they do not establish household model skill.
The retained live publication remains shadow, and no new measured candidate has
been installed. A bounded development fit was attempted and refused by the existing rank gate; no candidate was saved.

The next scientific steps are the sensor-identity migration and evidence-driven
algorithm improvement. The operator confirms outdoor shades remain installed;
current native development inputs have no unshaded solar support. The existing
full physical model therefore cannot identify its unshaded gain from these inputs. Local execution is
permitted under the resource constraints above; a private off-host destination is
not required. Keep household inputs private, freeze the improved candidate/runtime
and register its policy before untouched/prospective release evaluation.
ML installation, schedule reconciliation and the positive confirmed-action
advisory path remain open. Backup and recovery work is deferred and does not block
this stage. Code/CI success does not replace real model qualification.

## Native sensor identity correction: source-side v2 boundary

The receiver's `streamEpoch` is a process/session UUID, rotated on initialization,
worker fork and clock rollback. It must not be treated as a persistent hardware
phase. A v2 receiver policy explicitly declares `sensor_epoch` for each existing
stream/model/sensor-ID policy. New source snapshots retain the collector UUID
and add the declared `sensorEpoch` to each newly received v2 record. Restart
clears all values and requires a fresh packet while retaining the declared phase.

The v2 grid reader requires that declared phase, verifies device/policy identity,
and preserves the original invalidation, expiry and no-copy restart barriers.
Legacy v1 receiver policies and reader APIs retain their existing semantics; old
readers refuse v2 snapshots. Old receipts are never retroactively relabelled.

This source boundary does not complete the graduation correction. Thermal/native
history, origin/outcome proofs, training-source validation and qualification still
need coordinated versioned v2 identity integration. Do not enable a v2 policy on
the live receiver or claim a production candidate until the consuming paths are
qualified together. Missing physical shade support remains a separate data gap.

### Native reader and retained-history v2 integration

`fetch_temperature_grid_v2` uses the same bounded read-only SQL transaction and
source snapshot/carry queries as v1, but requires the declared sensor phase.
`thermal_temperature_runtime.collect_v2` and explicit `--read-v2` requests bind
the request phase to the private v2 policy before opening a connection. Fixed
thermal model/sensor/range/expiry identities remain required.

`configured_history_v2` pins complete role bindings into each worker request.
`QualifiedTemperatureHistoryV2` retains original receipt metadata and emits a
version 2 temperature evidence manifest. It preserves missing-point barriers and
refuses old receipts, phase mismatches and pre-cutover legacy temperatures. The
v1 history, worker, manifest validator and current production paths are unchanged.

This completes the source-to-native-history boundary on synthetic original source
snapshots and replaced SQL transports. Versioned artifact/training-input/source
formats, origin/outcome proof migration and graduation sensor binding remain open.
Do not enable v2 in live policies before those consumers are verified together.

### Model and frozen training evidence v2 integration

Model schema `earthship-thermal-model/v6` requires temperature evidence manifest
version 2. Frozen input/source schemas use version 2 and retain both the original
collector session and declared hardware phase. Model v5 and input/source v1
remain exact and refuse these newer evidence contracts. Physical constraints,
rank, conditioning, coefficient stability and eligibility checks remain intact.

The explicit `train-thermal-snapshot.py --receipt-version 2` path reconstructs
original native grids, validates phase bindings, and persists source v2 plus
training input binding v3 before candidate saving. Default invocation remains
v1. A v2 input with a legacy assembly binding is refused; explicit assembly
v2 provides the separately versioned lineage contract. Local fitting remains an explicit opt-in
under enforced resource limits.

Native private shadow origin/outcome proof APIs are integrated below;
graduation/runtime bindings, production publication and live installation
still need coordinated migration.
Keep the live receiver policy v1 until consuming paths are qualified together.
Synthetic checks establish contract behavior, not model skill or release readiness.
Historical v1 receipts cannot be relabelled as v2 hardware evidence. Outdoor
shades remain installed; no physical shade changes are requested for experiments.

### Guarded native capture v2 integration

`capture-thermal-inputs.py --receipt-version 2` explicitly selects the v2
policy, native collector/history and frozen input writer. Default v1 invocation
refuses a v2 policy; explicit v2 refuses a v1 policy. Both retain the same closed
private configuration, source-code pin, fixed physical sensor identities,
request/byte pacing, read-only transactions, resource preflight and 90-second
outer deadline. Native v2 binds each request to the initially declared hardware
phase and refuses phase drift before connecting. Capture workers require both
qualification-fit opt-ins to be off. Check-only performs no source reads.

Tests use real source-v2 receipts and native parsing with synthetic SQL transport;
no household v2 capture or receiver policy change has been performed.
Qualification/runtime/publication migration remains open.
The latest operator confirmation keeps outdoor shades installed. The physical
model still lacks unshaded training support; capture compatibility cannot supply
that missing evidence or authorize graduation.

### Adjacent native assembly v2 and training lineage integration

Explicit assembly v2 combines two to eight adjacent source-v2 input snapshots.
Every part must share the original measurement-code revision, cutover, fixed
physical identity and declared hardware phase. Collector sessions may differ
while their original receipt metadata remains unchanged. Counts and grid hashes
are recomputed from retained originals; missing receipts remain null barriers.
Journal labels come from one freshly read full-window view, preserving their
source/confidence. A hardware-phase change or mixed input version refuses
assembly before journal access. Legacy APIs remain strict v1.

`assemble-thermal-inputs.py --receipt-version 2` selects these readers/writers
and propagates the explicit version to its bounded worker. Both fitting flags
must be off for assembly. `train-thermal-snapshot.py --receipt-version 2` can
verify or explicitly fit a v2 snapshot with its assembly-v2 binding and original
`--input-part` files. Source v2, all parent inputs, the assembled input, assembly
binding v2 and input binding v4 persist before candidate saving. Standalone v2
training continues to use input binding v3. Rehashed or mismatched lineage
cannot reach fitting or repair source evidence.

This completes the offline capture/assembly/training sensor-identity boundary
on synthetic original receipts. Qualification/runtime/publication bindings and
live adoption still need migration; the private origin/outcome API is below.
No measured candidate, statistical qualification or production activation is
claimed. Outdoor shades remain installed and current data still lack the
unshaded support required by the existing full model.

### Native private shadow origins and outcomes

`shadow_temperatures_v2` and explicit `configured_shadow_temperatures_v2` preserve
original source-v2 receipts across collector sessions while validating one
declared hardware phase per role. Their private proof is
`earthship-thermal-origin-temperatures/v2`; it retains the same trailing grid,
missing barriers and current receipt clocks. The configured reader shares fixed
physical policy checks and the existing 90-second read budget.

Private origin capture v3 requires model v6, checks hardware bindings against
the fitted manifest and preserves exact forcing, initial/latent state, runtime,
publication clock and content digests. Legacy origin v1 and release capture v2
remain strict and refuse the new native sensor contract. The observed reader
explicitly validates v3 before scoring. New source-scored pair v2 validates
outcomes and original recent-cycle receipts against the declared hardware phase;
collector-session changes do not impersonate hardware changes. Same-origin
persistence and the seven-cycle baseline keep the original issue clock, target
selection, elapsed-duration and source-freshness rules. Scoring grants neither
release authority nor confirmed action-response evidence.

This step is verified with real synthetic source-v2 packets/parser grids,
including a collector reset. Live publisher selection, production release
capture, qualification consumers and live policy adoption remain open. Historical
v1 records are not relabelled, and no real model fit or activation occurred.

### Native qualification and preregistration

`verify_sensor_training_sources` validates source v2 against model v6 and its
frozen declared phases. Original sample digests, complete native grids, missing
barriers, receipt clocks and the causal latent-mass reconstruction remain
authoritative. Its source assessment is version 2 with explicit
`declared_hardware_phase` semantics. The legacy source verifier remains v1.

Native `register_sensor_policy` / `read_sensor_registered_policy` use private
registration v2. They replay original capture-v3 / source-pair-v2 development
packets and retain actual registration chronology, before untouched/prospective
intervals, original source copies and digests. Legacy registrations cannot
provide native preregistration solely through matching UUID strings. Threshold
derivation and the version 1 numerical policy are unchanged.

`qualify_sensor_candidate` requires model v6, native registration v2, original
capture v3 and source-scored pair v2. It emits qualification report v4 with
explicit phase semantics. Version 3 reports and the default qualifier remain
legacy-only. `load_sensor_qualification_inputs` requires release-input reference
v2 and rereads the actual candidate, sources and pairs on every evaluation.
`qualify-thermal-graduation.py --receipt-version 2` writes matching machine/human
reports, including failed gates when evidence is absent.

The 35 independent-day floor, positive skill against both baselines, absolute
error/bias/calibration caps, original-source, measured-fit and freshness gates
are unchanged. Advice and automatic actuation remain withheld. Controlled
classifier tests prove gate routing, not real statistical graduation. Live
publication/report-v4 consumers and production capture are integrated below;
no actual native candidate or policy was frozen/registered in this step.

### Explicit native runtime publication and truthful UI

Native publication is version 3 with `earthship-thermal-release/v2` metadata
and explicit `sensorEpochSemantics=declared_hardware_phase`. It consumes native
qualification report v4 through its trusted evaluator. Default version 2
publication remains exact and refuses this contract. Native shadow and active
outputs require all three nonzero canonical hardware phases; unavailable output
may have no bindings. Missing evidence produces honest unavailable version 3.

`thermal_intel.py release --receipt-version 2` explicitly selects native sensors,
release-input reference v2, report v4 and version 3 output. The default command
remains legacy. Forecast-only grade/mode still derives from all scientific
gates, current regime support and exact frozen artifact/runtime/phases. Native
expiry and runtime identity are rechecked before writing/delivery. Preview
performs no transport. Accepted output is archived as private origin capture v4;
native scoring, qualification and preregistration explicitly accept it alongside
private shadow capture v3.

Frozen `observe-candidate --receipt-version 2` remains low-confidence public
shadow while retaining typed private capture v3. It checks model v6 and fitted
hardware compatibility before any prediction is written or delivered, in
addition to frozen digests and receipt validity. The UI explicitly validates
publication v3, its schema/phase bindings, flags, digests and clocks before
displaying a forecast badge; action advice remains withheld.

These are staged code paths verified against synthetic original receipt,
transport and classifier boundaries. Live receiver/consumer installation,
measured model improvement, sufficient native evidence, genuine candidate/policy
freeze and natural qualification/publication remain open. No source policy or
production mode was changed, and backup/recovery work remains deferred.


### Native point/window readers and hourly learning

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

### Separate source-bound installed-shade uncertainty calibration

The operator reconfirms that outdoor shades remain installed until changed.
`thermal_model/installed_shade_calibration.py` now learns development uncertainty
from original source-replayed issued observations in a separate interval after
base coefficient fitting and creation. The new closed calibration namespace
retains the base candidate/runtime/hardware-phase identity, exact method,
calibration dates, independent-window selections and original source bindings.

The fixed 90 percent symmetric absolute-residual order statistic is one-based
`ceil((n+1)*0.90)`, with no interpolation or clipping. The existing 35 independent
day/window floor applies to all required horizons and every declared regime;
regime bands use subsets of the same globally selected daily sample. Incomplete
cells expose no usable radius. Correlated thermal time series confer no claimed
coverage guarantee: unchanged untouched/current prospective coverage, width,
bias and both-baseline skill gates remain mandatory.

Private immutable storage retains original native-v2 inputs, core candidate/fit
proof, captures and source-packet index before the calibration record. Reads
replay these sources against an independently expected runtime. Numerical/source
checks do not claim optimizer execution or legitimate household qualification.
The existing uncalibrated schemas and publications remain unchanged; a new
calibrated candidate/issuance adapter must bind these bands before release scoring.
See [the calibration contract](../../operations/2026-10-08-installed-shade-calibration.md).

Verification: initial missing-module failure, then 19 passing source/numerical
checks; private storage missing-API failure, then 21 passing checks. Expanded
calibration/policy/statistics verification: 65 passed, one hosted-only synthetic
multiweek source integration skipped locally, under CPU 20 percent, 256 MiB,
zero swap allowance, 24 tasks, one numerical thread and a hard 90-second deadline.
Review found that the synthetic multiday baseline fixture incorrectly shifted
UTC days across fall DST. Two targeted failures reproduced it. The fixture now
uses the existing local-clock/elapsed-duration/31-day rules and acquires an extra
date while omitting unsupported origins; no comparator rule changed. Scoped
re-review found no remaining material issues. The multiday positive
source fixture is explicitly synthetic and cannot count as natural release data.
No household fit, service change, publication or activation occurred.

Next: separately versioned calibrated candidate, original-issued uncertainty and
qualification bindings, production publication/UI and live entry point, genuine
native fitting/preregistration and sufficient untouched/prospective observations.
Outdoor-installed and November no-vent assumptions persist; PR3 and recovery work
remain separate. No absent unshaded coefficient is invented for this domain.

### Versioned calibrated candidate, issuance and qualification

The installed-shade aggregate candidate is now explicitly
`earthship-installed-shade-candidate/v2`. It binds the unchanged original core,
original source-replayed calibration, both runtimes and the extended learning
cutoff. The calibrated runtime preserves every original source/dependency/
interpreter/observer pin and includes the new modules. Public creation,
preparation, private storage and reading replay the original source packages;
compact radius metadata cannot override the original calibration.

New forecast/origin/source-scored-pair namespaces are version 2. Their original
1/6/12/24-hour bands bind the actual target, declared origin regime, nominal
coverage and calibration identity. Missing calibration support or an unsupported
origin regime refuses issuance. Later scores measure those actually issued bands,
retain the actual v2 capture/publication/aggregate hashes, and reuse unchanged
native/weather/physical/recent-cycle checks through an internal numerical view.
That view never claims a fabricated v1 publication. Old readers refuse v2.

The new registration namespace is installed-shade-policy-registration/v2. Its
baseline-only development sources may retain typed original v1 or v2 captures;
release rows require one exact frozen v2 aggregate/runtime/hardware phase. The
installed-shade-qualification-report/v2 reader connects genuine core/calibration
source replay, actual preregistration, archived runtime and original issued
intervals to the unchanged independent support and current statistical gates.
The exact rank/conditioning, day-block stability, 35-day/window horizon/regime
support, positive paired baseline skill, coverage, width, bias and freshness
limits remain unchanged. Candidate/calibration presence alone never activates.

`python3 scripts/qualify-installed-shade.py --contract-version 2` selects the
calibrated contract; the default preserves v1. Matching private machine/human
reports include frozen cutoffs/evaluation intervals, thresholds, core numerical
conditioning/support/stability, calibration, independent counts, baseline/error/
coverage metrics, latest prospective monitoring, expiry and original source hashes.
The clock is actual UTC and there is no date or active override. Exit zero means
an honest report was written. Reports remain caches, not production authority.

Verification: missing aggregate module RED, then 18 passing source/runtime/
issuance checks; expanded 23 passing checks including public incomplete-source
preparation, private original-source aggregate storage and old-reader refusal.
Missing v2 pair adapter RED, then 20 passing new/old qualification checks.
Missing detailed human view RED, then 7 passing v2 report/actual-CLI checks.
A combined compatibility run reached the unchanged 90-second guard without a
reported test failure. Smaller serial compatibility scope completed 69 checks.
Thus 99 checks completed across the final artifact/origin, v2 qualification and
legacy/native compatibility scopes, under CPU 20 percent, memory 256 MiB, zero
swap allowance, 24 tasks, one numerical thread and hard 90-second limits.
Scoped module, registration/gate, hosted-test and renderer reviews found no
remaining material issues. The hosted-only multiday synthetic fixture now also
exercises public aggregate build/write/read/preparation and v2 issuance; it was
not run locally. Mathematical shape fixtures and mocked seal/loader orchestration
are explicitly not household qualification or actual registration.

The preceding calibration commit passed all three hosted workflows. Fresh live
metadata still exposes source schema v1, the native rollout manifest is unapplied,
and the trainer is inactive. No service, fit, live publication, model registry or
household control changed. Production publication/UI/live entry-point integration,
genuine native candidate fitting, actual preregistration and sufficient untouched/
prospective outcomes remain required. Outdoor shades stay installed; November
no-vent, no actuation, WeatherNext/PR3/recovery deferral and local resource limits
remain unchanged.
