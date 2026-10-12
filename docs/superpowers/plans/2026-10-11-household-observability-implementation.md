# Read-only household planner observability implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. The full PR3 architecture and continuing implementation are approved. Use one final independent immutable review and one Important/Critical TDD correction pass. This panel is one stage of the full program, not completion of PR3.

**Goal:** Let an operator inspect a verified shadow plan, its age, models, proposals, effects, hard blockers and uncertainty even when no action is selected.

**Architecture:** A bounded private CLI replays the existing sealed model/plan receipt before producing a curated public observation. A fixed server-side file endpoint serves only the closed observation schema, and a read-only Svelte panel presents that artifact with freshness recalculated from original clocks. Original source contexts, owner scripts, configuration, paths and credentials never enter the observation. Current-owner policy agreement stays explicitly unavailable until qualified comparison inputs exist.

**Tech Stack:** Existing Python replay APIs, bounded owned-file reads, Node/Vite middleware, Svelte5, Vitest and current UI tokens.

**Spec:** docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md, phase9 and stageA. Source contract stabilized by merged PR26; publication of this stage depends on PR27 exact-head checks and merge.

## Global constraints

- Read-only inspection; planner authority none, automatic actuation false, no owner request, notification, training, recovery or device-write path.
- Preserve all existing receipt and model versions. New observer modules live outside the household producer directory so observing a receipt does not silently change its original producer closure.
- One source receipt <=1048576 bytes; one public observation <=32768 bytes; at most8 proposals,32 hard checks per proposal and40 source-quality rows. Closed schema and bounded enum/digest/timestamp fields.
- Replay time does not renew original source/intent expiry. Expose original snapshot/decision clocks, verification time and explicit currently-expired status. Unavailable or malformed views cannot render a recommendation or active authority.
- Do not claim current policy agreement from a no-action plan or declared coordination bounds. Preserve unavailable/unknown expected effects, calibrated energy, rainfall rate and causal benefit.
- Fixed same-origin GET endpoint /api/household-observation. Browser arguments cannot choose a file. Server-configured cache path is bounded, owned, regular and non-symlink; no request-time model execution.
- Serial local CPU20%, memory256MiB, swap0, tasks24, IOWeight10, nice15, idleI/O, one numerical thread. Keep original receipts/private staging0600/0700 and preserve the root's dirty thermal UI overlay.

## Review focus

1. A tampered/resealed or incomplete original receipt must fail replay before any public file is produced.
2. Re-verification of an old receipt must show its original age and expiry, not make the plan current.
3. Empty selection must remain inspectable, and unknown owner-policy comparison must not become agreement.
4. No registry script, original config, raw source text, credential or private path may appear in the public view or an endpoint error.
5. Endpoint/model/parser errors and unsupported versions must fail to unavailable without changing existing UI controls or sending a request.

### Task1: Curated replay-verified observation and private materializer

**Files:** Create openhab/scripts/household_observation.py and openhab/scripts/test_household_observation.py.

**Interfaces:** observe_pipeline(receipt,*,runtime_manifest,thermal_runtime,observed_at) -> closed earthship-household-observation/v1 dict, <=32768 bytes. It calls existing replay_pipeline before projection. Private CLI --receipt PATH --output PATH validates executing/source closures before and after replay, then atomically writes only the curated view to an owned private cache directory. No stdout receipt/source payload; report only status and identities.

**Public fields:** schema, receipt_sha256, snapshot_id, snapshot_as_of, decision_at, verified_at, valid_until, planner_mode, planner_version, authority, automatic_actuation, plan_status, model_identities, candidate_generation, proposals, source_quality, confidence, effects_qualified, policy_comparison. All original clocks remain explicit. Proposals include only typed intent identity/type, selected flag, confidence, stable reasons, expected-effect values/units and hard-check decisions. Policy comparison is unavailable with its original reason; no fabricated actual-policy result.

- [ ] RED no-action view, real proposal/constraint extraction, exact model identities, original expiry under later verification, privacy markers excluded, resealed original corruption, unsupported schemas and no live reads.
- [ ] Implement pure observer and GREEN meaningful fixtures; preserve original numerical/receipt outputs.
- [ ] RED private materializer on real source-backed receipts, unsafe files, source/runtime drift and atomic output bounds; implement and GREEN.
- [ ] Commit verified observer and record exact coverage.

### Task2: Bounded file endpoint and read-only operator panel

**Files:** Create src/lib/household/observation.js, observationServer.js, corresponding tests and src/screens/Household.svelte; update routes.js, App.svelte, Shell.svelte and vite.config.js.

**Interfaces:** parseHouseholdObservation(raw,{nowMs}) validates a closed observation and derives snapshot age, current expiry and effective unavailable/shadow mode. Server plugin handles only exact GET /api/household-observation, reads one bounded owned cache file, validates the public schema and returns no internal details on failure. Household screen fetches on mount and every30s while mounted; abort/cleanup prevents continuing work after navigation. It provides no command controls.

- [ ] RED fresh/expired/malformed/no-selection views, policy comparison unknown, effect unknown, privacy/closed-shape boundaries and endpoint GET-only/path/file protections.
- [ ] Implement parser/transport and GREEN; never execute Python/replay from an HTTP request.
- [ ] RED component presentation of all eight phase9 requirements and route/navigation reachability, including no action and unavailable data.
- [ ] Implement readable bounded layout using existing tokens; verify unit tests/build and target tablet/laptop geometry with the existing resource boundaries.
- [ ] Commit verified public interface.

### Task3: Actual artifact, review, deployment and publication

**Files:** docs/operations/household-observability.md and canonical docs/operations/household-program-progress.json.

- [ ] Materialize the actual PR26 source-backed receipt and verify the public artifact contains only curated data. An old receipt is historical/expired; do not claim current operational planning from it.
- [ ] One final independent immutable review, then one Important/Critical TDD correction pass.
- [ ] Deploy only reviewed UI/endpoint files without overwriting the signed-off dirty overlay; verify actual endpoint and rendered unavailable/historical/no-action states under caps. No OpenHAB restart.
- [ ] Publish after parent PR27 merge, require all exact-head checks, merge and record canonical evidence.

## Remaining full-program requirements

Common-cycle operational capture, rolling PV/load/energy trajectories, calibrated usable energy where required, daylight and authority/owner inputs, policy baselines, correlated owner migrations, causal outcomes/resource effects, per-intent graduation and staged integration remain required. This panel must expose those limits rather than hide them or declare the program complete.
