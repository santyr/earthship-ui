# Original bank configuration and household AC load implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, with one independent final whole-branch review and one Important/Critical TDD fix pass.

**Goal:** Retain original physical-bank configuration and the existing operator-attested topology, bind current household AC load to its original inverter receipt, and make the daily energy capacity parameter traceable without promoting nominal capacity to physical calibration.

**Architecture:** A bounded immutable configuration context stores exact original bank/topology bytes, digests and availability clocks. A new snapshot/v5 extends the existing weather-bound snapshot at its original common clock, while pipeline/plan/v4 retain and restore its complete original contexts. Existing numerical equations and old receipt versions remain unchanged. Nominal bank capacity remains declared configuration; calibrated current usable energy stays unavailable.

**Tech Stack:** Existing canonical JSON, Python frozen dataclasses, physical-bank validation, fixed read-only source collection and operational runtime closure.

**Spec:** docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md, Phases1/2/3/7.

## Global constraints

- Serial local CPU20%, memory256MiB, swap0, tasks24, nice15, idle I/O and one numerical thread. Common collection deadline15s; strict SQL statement2s/lock1s. No recovery work or training.
- No actuator/control writes, new owner, grants, credential changes, vent calculations or forecast equation changes. Existing inverter-only/no-bypass/no-generator attestation remains valid until the user reports a change.
- Exact bank raw bytes65536 maximum, topology raw4096, configuration context73728; retain original bytes and refuse oversize. Snapshot256KiB, plan512KiB, pipeline1MiB remain unchanged.
- Physical bank identity is a declared asset/configuration interval, never a software restart UUID. Nominal capacity is not measured usable energy. Inverter AC load is scoped to the attested topology and cannot be subtracted from DC PV to invent battery balance or conversion efficiency.
- Projection, snapshot binding and replay perform no I/O. Collection reads fixed configured files with before/after bytes/metadata checks. Missing/invalid sources remain explicit independently; one missing policy cannot discard another valid original.
- All existing v1/v2/v3 receipt branches and v1/v2/v3/v4 snapshot branches preserve their structures and numerical behavior. Full architecture scope remains active.

## Review focus

- A nominal configuration or software epoch must not become calibrated physical capacity or an actionable source reference.
- A topology interval must not authorize load outside its original cutover/effective interval; AC expiry and future availability remain authoritative.
- A missing/invalid topology source must not suppress a valid original bank source, or fall back to a different policy.
- Root, distinct candidate and enclosing outcome replay must retain the new context and check its complete producer/dependency closure.
- New schema dispatch must not change old receipt shapes, drop candidate/original documents, or manufacture current source clocks.

### Task 1: Frozen original configuration context

**Files:** Create `openhab/scripts/household/energy_configuration.py`, `openhab/scripts/test_household_energy_configuration.py`.

**Interfaces:** `PreparedEnergyConfiguration(content:bytes)`; `prepare_energy_configuration(*,bank_config_raw,ac_policy_raw,bank_available_at,topology_available_at,as_of,created_at)`; `project_energy_configuration(context,*,as_of=None)`.

The closed schema `earthship-household-energy-configuration/v1` contains `bank_source`, `load_topology_source`, `as_of`, `created_at` and `configuration_sha256`. Each fixed source contains `source_identity`, `raw`, `sha256`, `available_at`; raw/digest may both be null. Identities are `Solar_PV/config/system-epochs.json` and `Solar_PV/config/ac-evidence.json`. Complete exact raw bytes remain unchanged; availability must precede the collection as-of, and creation follows within15s.

Pure projection reuses the existing complete physical-bank validator for all epoch intervals, selects the explicit current physical epoch only inside its boundary and retains declared nominal Ah/kWh. The exact existing topology schema, basis, cutover and effective interval are parsed from retained raw bytes; no I/O loader is called. Absent/invalid sources yield independent explicit unavailability. Projection names the declared configuration basis and keeps physical calibration, action effects and automatic actuation false. A later projection as-of cannot precede original configuration availability or turn an ended bank/topology interval into current state.

- [x] Write RED tests for independent bank/topology selection, exact raw bytes/digests, boundary dates and open-ended attestation, nullable missing sources, invalid/overlapping/ambiguous bank intervals, invalid topology/cutover, future availability, resealed invalid sources, output immutability, bounds and no reads.
- [x] Run the new file under strict caps; expected FAIL because module is missing.
- [x] Implement the three interfaces and closed bounded validation, with original-source semantics above.
- [x] Run the new file and the affected household suite; expected zero failures. Commit the boundary with measured RED/GREEN evidence.

### Task 2: Source-bound snapshot and energy replay

**Files:** Create `household/energy_source_snapshot.py`, `test_household_energy_source_pipeline.py`; modify `model_snapshot.py`, `energy_model.py`, `intents.py`, `planning.py`, `pipeline.py`, `household_pipeline.py`, `household_plan.py`, `household_outcomes.py`.

**Interfaces:** `EnergySourceSnapshot(WeatherSnapshot)` retains `original_energy_configuration:bytes`; `bind_energy_source_snapshot(*,source_receipt,source_runtime_manifest,weather_context,energy_configuration,code_revision)`; `restore_energy_source_snapshot(document,context)`; explicit snapshot/v5 and source-context/v1 containing original power receipt, weather inputs and configuration.

Rebuild the unchanged weather root first. Add physical-bank identity and nominal capacity with retained-configuration quality and explicit provenance; `usable_battery_kwh` remains unavailable without calibrated evidence. Map `estimated_load_w` from the original qualified inverter-output row only within the attested topology, preserving original observed/received/available/expiry clocks, AC units and parent digests. Label the AC basis, preserve source expiry at the common model clock, and add capability-specific load completeness without upgrading full-energy completeness.

Prepared energy/v2 binds the unchanged daily `bank_kwh` argument to the retained nominal configuration when available; mismatch is refused. Missing bank configuration remains explicit and does not silently claim a binding. Overall energy input qualification remains not_assessed because resource/demand/calibration sources remain incomplete. Pipeline/plan/v4 restoration deduplicates originals and distinct candidate contexts with complete source closure, and enclosing outcome replay uses actual version dispatch. Earlier versions remain unchanged.

- [x] RED then GREEN exact source/model clocks, nominal-versus-usable distinction, valid/expired/future AC, ended/unknown topology, mismatched numerical capacity, forged/resealed snapshots and contexts, candidates, outcomes and disabled translator.
- [x] Verify pure/no-read replay, full operational CLI closure, partial runtime refusal and unchanged historical versions; run the complete affected suite under serial caps.
- [x] Commit measured integration and update the canonical full-scope progress record.

### Task 3: Bounded configuration acquisition and actual proof

**Files:** Create `household/energy_configuration_capture.py`, `test_household_energy_configuration_capture.py`; add operational documentation and an explicit read-only collection option to `household_capture.py` only if its existing output contracts can be preserved.

Read only the two fixed companion configuration paths, owned regular non-symlink files, bounded exact bytes; file permissions are observed without changing them. Verify before/after metadata, bytes, source code, registry and current source clocks. Keep one15s common collection deadline and require unchanged current original owner bindings. Private actual packets use0600 files in0700 staging. Absent/invalid files are explicit source records; transport/identity changes abort rather than fabricate a qualified context.

- [ ] RED then GREEN collection bounds, fixed paths, missing sources, replacement/symlink/identity change, deadline and independent original-source retention.
- [ ] Complete full affected suite; collect actual committed source/configuration under existing caps without forcing a publisher. Bind to a normal naturally delivered original model issue, or retain a precise refusal without changing origin/expiry guards.
- [ ] Verify pure/private operational CLI equality, qualification limits and zero action authority; one final independent review, one Important/Critical TDD fix pass, publish and require all exact-head hosted checks before merge.

## Scope audit

This implements original declared bank/load inputs and provenance, advancing the required cross-domain snapshot and energy model boundary. Qualified actual usable capacity, rolling energy/PV trajectories, observed weather/daylight, authority/owners, policy/action outcomes, resource effects, read-only UI and independent release gates remain required under the full PR #3 program; no smaller goal is substituted.
