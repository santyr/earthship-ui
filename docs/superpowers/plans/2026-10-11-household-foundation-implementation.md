# Household Foundation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline and test-driven-development for each task. Review the whole branch once at completion.

**Goal:** Implement the behavior-neutral foundation authorized by PR #3: exact evidence references, immutable snapshots, a descriptive capability registry and deterministic offline capture replay.

**Architecture:** Pure Python modules in `openhab/scripts/household` adapt original validators rather than introduce live readers. The registry is a validated projection of the existing managed-resource manifest with explicit descriptive contract annotations. A bounded local-file CLI assembles and replays snapshots; it has no provider or request transport.

**Tech Stack:** Python standard library, existing BMS/PV/native-temperature validators, pytest. No new dependencies.

**Spec:** `docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md`, phases 1, 2, descriptive 2B and section 13.

## Global Constraints

- Existing receipts and owner rules remain authoritative.
- Missing/stale/invalid evidence fails closed; original epochs and exact digests survive adaptation.
- No planner, live reader, request sender, provider writes, notifications, timer or installed service.
- Water inventory remains explicitly unknown. No windows/skylights or shade state is inferred from coarse vent observations.
- Local checks run serially with CPU 20%, memory 256 MiB, swap 0 and one numerical thread.
- Snapshot requirements and age/skew limits are explicit pinned configuration, not implicit authorization.

## Review Focus

- Caller mutation after freezing must not alter the snapshot or its identity.
- Currentness must be checked again when building a later snapshot.
- Wrong epoch/digest or a future source clock must never produce a qualified value.
- Duplicate field roles and conflicting owner declarations must be refused.
- Offline replay must reject changed source bytes, policy, registry or runtime rather than retain an old sealed identity.

### Task 1: Exact evidence references and source adapters

**Files:** `openhab/scripts/household/{__init__,evidence,adapters}.py`, `openhab/scripts/test_household_evidence.py`.
**Interfaces:** Frozen `EvidenceRef`, `Observation`; BMS SoC, PV-day counter and native-v2 temperature source-packet adapters. Each accepts explicit original bytes/digest, source identity, epoch, persistence/as-of clocks; native adapter replays original raw query rather than trust selected temperatures. Weather and thermal use the same native validator with explicit stream/role identity.

- [x] Write failing tests for valid original adapters, digest and epoch mismatches, future/expired sources, explicit missing evidence and duplicate observations.
- [x] Run the focused tests and observe failure before implementation.
- [x] Implement bounded exact-byte adaptation with original validators and frozen scalar observations.
- [x] Run tests and commit.

### Task 2: Immutable snapshot and temporal policy

**Files:** `openhab/scripts/household/snapshot.py`, `openhab/scripts/test_household_snapshot.py`.
**Interfaces:** `build_snapshot(observations, *, as_of, created_at, code_revision, config_revision, requirements, max_age_seconds, max_skew_seconds)` returns immutable snapshot with canonical digest and per-capability completeness. Caller maps are copied into immutable tuples. No completeness field authorizes action; planner authority remains none.

- [x] Write failing mutation, ordering, expiry-at-boundary, future-clock, skew, duplicate-role and optional-domain tests.
- [x] Implement source re-assessment and deterministic normalization; retain original qualification separately from snapshot availability.
- [x] Run tests and commit.

### Task 3: Registry from existing ownership manifests

**Files:** descriptive additions in `openhab/managed-resources.json`; `openhab/scripts/household/capabilities.py`; `openhab/scripts/test_household_capabilities.py`.
**Interfaces:** explicit request/result/actuator/safety bindings in existing subsets; `build_registry(managed, ownership)` returns deterministic descriptive-only registry pinned to both manifests. Preserve existing owner UID, provider path and protected dependencies; all planner authority is none. Do not invent capabilities for unrepresented devices.

- [x] Write failing tests for actual feeder/greywater/night-load declarations, duplicate owners, wrong ingress and any planner authority.
- [x] Add annotations and validate them against existing command triggers, declared Items and protected dependencies.
- [x] Run focused existing OpenHAB manifest checks where practical plus new tests; commit.

### Task 4: Bounded original-input snapshot/replay tool

**Files:** `openhab/scripts/household/replay.py`, `openhab/scripts/household_snapshot.py`, `openhab/scripts/test_household_replay.py`, operations documentation.
**Interfaces:** closed JSON bundle of original source bytes and contexts, frozen clocks and temporal configuration; current runtime/source manifest and both existing ownership manifests are sealed into the output receipt. CLI reads local files only, writes canonical JSON to stdout and optionally compares an original sealed receipt. Original malformed or altered bundles fail without values.

- [x] Write failing round-trip, input/policy/runtime/registry drift, oversized and forbidden-field tests using synthetic source data.
- [x] Implement read-only offline CLI with bounded input, source count and output. No capture of live Items in this stage.
- [x] Run focused suite and CLI round-trip under caps; commit.
- [ ] Complete whole-branch review and resolve material findings.

Live deployment, domain forecast changes, typed optimizer intents, owner v2 migrations and planner authority remain later separately scoped work. This first stage provides offline assembly from already-captured originals rather than installing a collector.
