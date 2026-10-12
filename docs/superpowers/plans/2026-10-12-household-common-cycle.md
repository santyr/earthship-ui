# Household capture within the forecast cycle

> Execute inline under the approved full PR3 architecture. One final immutable review and one Important/Critical correction pass. This stage must deliver an operational source/model/cache feed, not stop at an adapter or fixture.

Goal: capture household originals under the existing forecast lock shortly before its actual issue, combine them with that cycle's verified original thermal/weather publication, and update the private observation cache without renewing source timestamps or granting action authority.

Architecture: use the existing injected backend interface of unchanged provisional_live.publish_cycle. A delegating backend collects household inputs after the parent's original collection and before issue minus a safety margin. An outside-producer driver owns the same SharedScoreLock, invokes the unchanged pinned forecast implementation, then derives/replays the full source/model/plan artifact and curated cache only after verified delivery. Observer failures remain explicit and cannot fabricate a forecast or qualified input. Preserve existing forecast numerical output, source versions and the original candidate runtime. No training or equipment requests.

Files:
- openhab/scripts/household_cycle.py: bounded backend adapter and coordinator/CLI.
- openhab/scripts/household_cycle_sources.py: owned configuration and reusable restricted source collector, outside the household producer directory.
- openhab/scripts/test_household_cycle.py and test_household_cycle_sources.py.
- deploy definitions/guarded installer, operations evidence and canonical program tracker.

Task1: injected collection boundary
- RED integrated actual publisher tests: post-parent/pre-issue collection, original output and delivery parity, bounded remaining time/guard, late-window skip, collector error isolation and parent error propagation.
- Implement adapter and GREEN, with no changes to any of the72 original predictive-runtime files.
- Verify parent provisional tests and source hashes.

Task2: complete source/model/cache coordinator
- RED owned config/read-only source collection under one external issue deadline, independently pinned epochs before/after, byte/runtime/config/registry stability and missing/expired sources remaining unknown.
- Implement measured weather + bank/topology + base/power collection using existing restricted readers and fixed paths. Preserve original records and clocks.
- RED coordinator only accepts exact verified same-cycle original delivery, derives the measured v6 snapshot and model/shadow plan using existing retained parameters, replays exact originals, then publishes the curated cache. Withhold mismatched/late/runtime-changed artifacts and preserve source/intent expiry.
- Implement full private CLI; retain diagnostic originals0600/0700. No source payload stdout, no action/owner request or model execution from HTTP.

Task3: qualification and operational feed
- One final independent immutable review; one Important/Critical TDD correction pass.
- Actual bounded source+model+cache proof against a natural cycle; do not force/restart OpenHAB or original workers.
- Guarded source-pinned service/driver deployment using current credentials, unchanged original forecast numerical/runtime sources and existing limits. Observe natural publication and real UI freshness/expiry, then all exact-head checks/merge/canonical evidence.
- Full PR3 stays active: trajectories, calibration/effects, authority/policy/owners, outcomes and graduation/integration remain required.

Limits: scientific tests and workers CPU20%,memory256MiB,swap0,tasks24,IOWeight10,nice15,idleI/O,BLAS/OMP/MKL1. Browser-only proof may use96 tasks with identical CPU/memory/swap caps and one renderer/CPU affinity. Serialize local numerical jobs. Preserve root thermal UI overlay and all original private artifacts.
