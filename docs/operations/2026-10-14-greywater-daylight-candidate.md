# Greywater daylight candidate — October 14, 2026

A11 has an implemented, tested candidate; it is not deployed or complete.
The live managed owner still matches its original source exactly. Both pumps
were OFF, the owner IDLE and Astro ONLINE at the 19:49:58 UTC readback.
No pump command, telemetry injection, rule replacement or restart was performed.

## Problem and narrow change

The current positive-elevation check can admit a stale/restored value even when
Astro is offline or today's daylight window has ended. The isolated harness
reproduced 26 failing cases against the original source; the two valid-daylight
cases passed before the change.

The candidate extends the existing shared safety gate. Both automatic and manual
paths require:

- Astro `astro:sun:local` ONLINE.
- Finite elevation greater than zero and no greater than 90 degrees.
- `lastStateUpdateInstant` present, not future-dated and younger than 120 seconds.
- Offset-bearing native `Sun_Daylight_Start` and `Sun_Set_Start` instants,
  ordered less than 24 hours apart and containing the current instant.
- Both bounds on the current America/Denver calendar date, including when the
  Item timestamp is represented in UTC or across DST changes.

Failure retains the existing `after_dark` reason and adds a diagnostic daylight
field. The existing force-OFF path invalidates cycle ownership so its old
completion callback cannot report a completed cycle. Detection remains on the
existing minute evaluation; no faster actuator schedule is introduced.

The BMS receipt, comms, voltage and SoC gates retain their order and values.
The 15-minute cycle, 60-minute start gap, 24-hour fallback, hourly pump alternation,
manual-request ledger, restart/cooldown semantics and trigger/condition DTOs
are unchanged. This is an existing-owner candidate, not a provider migration or
new planner authority.

The native update timestamp is a freshness observation, not a source-provenance
receipt. Current-day bounds independently prevent a recently restored positive
value from authorizing operation outside the daylight window. This patch does
not claim to distinguish every possible same-day restore event from a binding
update.

## Verification and artifacts

All 198 affected cases in 13 files pass in 2.52 seconds. They include 35 dedicated
Astro cases covering automatic/manual rejection, missing/future/stale timestamps,
wrong-day and invalid bounds, UTC equivalence, both DST changes, the precise
age boundary and running-cycle shutdown. Existing pump, feeder, night-load,
ledger and timestamp regressions also pass after the shared harness gained
explicit Thing-status and Item-update-time interfaces.

Existing greywater fixtures explicitly model a healthy advancing Astro source;
the new freshness suite supplies timestamps and bounds independently. This
avoids making freshness tests pass through automatically refreshed fixtures.
The development scope used one core, 512 MiB, no worker swap and at most 96 tasks.

Baseline source SHA256:
`4c34780e544d80af8eb36d047a949fa30e0198bb50fa57650285052db3c52d9b`.
Candidate source SHA256:
`693b65b8af55e8d3935b116fd697aaa558f70f41a80507a4305decd66c4c23bb`.
The exact original and candidate managed DTOs are retained privately under
`.superpowers/sdd/2026-10-13-native-model-serving-receipt/` as
`a11-original-rule.json` and `a11-candidate-rule.json`. Their only action change
is the reviewed script. The canonical tracker binds readback and test-log hashes.

## Live handoff remains pending

The source explicitly states: “Protected-control source. Changes require
attended qualification before a live rule replacement.” The imported Astro
audit also requires an isolated harness before any attended control change.
The harness prerequisite is satisfied; operator attendance and live runtime
qualification remain pending. In particular, Node harness tests do not prove
the installed OpenHAB JavaScript engine's timestamp and Intl behavior.

An attended handoff must re-read the exact live baseline and pump states,
qualify the native inputs/date formatting without commands or fabricated
telemetry, and use the same managed owner UID. Any replacement must preserve
normal cooldown/ledger state and verify the resulting rule and natural owner
behavior. Retain the exact original DTO for immediate per-rule rollback.
This does not reopen deferred host backup/recovery work or require an OpenHAB
restart. Do not apply the earlier timer-guard deployment script: its immutable
source hashes describe a different historical repair.

While attendance is unavailable, continue the ML and household work. A11 remains
incomplete and the full PR3 goal remains active.
