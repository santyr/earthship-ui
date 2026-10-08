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

Origin/outcome and native shadow proofs, graduation/runtime sensor bindings,
production publication and live installation still need coordinated migration.
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
no household v2 capture or receiver policy change has been performed. Origin/outcome proofs and qualification/runtime/publication migration remain open.
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
on synthetic original receipts. Original issue/outcome/native-shadow proofs,
graduation/runtime/publication bindings and live adoption still need migration.
No measured candidate, statistical qualification or production activation is
claimed. Outdoor shades remain installed and current data still lack the
unshaded support required by the existing full model.
