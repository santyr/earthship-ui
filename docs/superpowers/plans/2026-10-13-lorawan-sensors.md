# LoRaWAN Sensor Infrastructure Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. The mission explicitly authorizes implementation without stopping at planning.

**Goal:** Deliver a tested local sensor-to-OpenHAB-to-UI evidence path and staged hardware deployment.
**Architecture:** One registry, append-only originals, transactional state, inbound MQTT Items and existing SSE. Pure optional ventilation evidence extends canonical snapshots without changing forecasts.
**Tech Stack:** Python, PostgreSQL, Mosquitto, ChirpStack v4, Redis, Svelte/Vite, OpenHAB, Docker Compose.
**Spec:** `docs/superpowers/specs/2026-10-13-lorawan-sensors-design.md`

## Global Constraints

- No production installation/activation, live host configuration edits, control or forecast changes.
- Keep concurrent work intact; branch from merged origin/main.
- US915_1 means channels 8–15 + 65; device sub-band naming must be verified.
- Synthetic observations never become qualified household/model evidence.

## Review Focus

Counter reset without a trusted join; replay refreshing supervision; status-only heartbeat refreshing contact; lost publisher leaving apparently current retained Items; history crossing offline gaps.

### Task 1: Transport-independent registry, sensor contracts and journal

Files: `services/observations/{registry,contract}.py`, `services/lorawan/{registry,decoders,engine,storage,history}.py`, tests in `services/lorawan/tests/`.
Consumes: ChirpStack JSON MQTT envelopes, exact bytes and local receipt clock.
Produces: Engine.ingest(raw, topic, received_at, retained=False), Engine.snapshot(now), transactional journal/state and normalized v1 observations.

- [x] Write and run failing tests for all three documented decoders, mapping, replay/order/session barriers, invalid inputs and expiry.
- [x] Implement decoders, strict registry, normalized processing and SQLite/offline + PostgreSQL runtime storage.
- [x] Test durable restart, history daily boundaries and interruptions; run complete Python suite.

### Task 2: Deployment and OpenHAB path

Files: `deploy/lorawan/`, `services/lorawan/{runtime,simulate,generate_openhab,provision}.py`, container integration tests.
Consumes: Task 1 registry and Engine; private secret files.
Produces: private configuration and file-staged Things/Items/rules; authenticated, isolated Compose and host-service-reuse production template.

- [x] Write failing tests for generation, credential/identity safety and MQTT processing.
- [x] Implement reconnecting ingestion, persistence-before-publish, supervision sweep, 15-device scenario simulator and config generators.
- [x] Run real disposable MQTT/PostgreSQL/OpenHAB container path, restart/reconnect/ACL and invalid-history checks; stage ChirpStack regional/gateway profiles without physical forwarder startup.

### Task 3: Ventilation presentation and canonical adapter

Files: `src/lib/sensors/`, `src/screens/Ventilation.svelte`, `src/{App.svelte,routes.js}`, `src/lib/ui/Shell.svelte`, `openhab/scripts/household/ventilation.py`, UI/Python/browser tests.
Consumes: normalized JSON OpenHAB Item and existing SSE store; exact original registry/evidence and immutable HouseholdSnapshot.
Produces: qualified display counts/history and opt-in immutable ventilation snapshot extension.

- [x] Write failing frontend tests for stale/closed separation and rendering, and adapter tests for digest/epoch/synthetic/expiry checks.
- [x] Implement bounded tablet route, pagination, perimeter grouping and optional pure adapter; preserve existing models.
- [x] Run full frontend suite/build, adapter tests and tablet browser geometry/SSE checks.

### Task 4: Operational qualification

Files: `docs/operations/lorawan-sensors.md`, `docs/operations/lorawan-validation.md`.

- [x] Document sources, firmware limits, onboarding, secrets, health, logs, outage/recovery, backup/restore, US915 and physical commissioning gates.
- [x] Review full diff, run final checks, record exact outcomes and limitations, commit only this work; leave isolated branch reviewable.

## Ledger

2026-10-13: origin/main 3d118d6 includes household PRs; local main dirty and behind. Baseline 145 files / 2232 tests pass. Host Mosquitto authenticated on 1883; PostgreSQL 16 on loopback 5432; unrelated Redis 6379. No production mutation authorized. Implementation inline; self-review until final independent skill review.

Expanded mission ruling: generic registry and typed normalized observations reside in services/observations; LoRaWAN is a transport plugin. Add tested water/environmental fixtures, nonlinear volume calibration and chronologically split evaluation scaffolding; do not change any production model. Publish grouped commits to a review PR, without merging. Existing schema-specific observation journals remain authoritative; the new dedicated observation schema stores new sensor originals only, with immutable parent references for existing providers.

Final ledger: unified registry/types and new-sensor journal implemented; optional current-supervision-bound canonical attachment leaves native models unchanged. Full frontend2238, Python77 (including existing canonical regressions), real containers11 and tablet browser2 pass. Independent review findings corrected and re-reviewed. Fresh disposable DB bootstrap passed. Vendor station schema/startup inspected without starting a forwarder. Production unchanged; publish grouped commits to a review PR only.
