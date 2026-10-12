# Household planner observation

The Household route exposes replay-verified shadow planning evidence, including
an empty selection. It displays original snapshot age, receipt and model
identities, proposed effects with units, hard-check decisions, source quality,
confidence and current-owner policy comparison. No command controls or action
transport are present.

The v1 view supports `unavailable` and `shadow`. Advisory and active-request
modes still require the full program's later qualification and reviewed release.
Unknown effects and policy agreement remain unavailable. Re-verifying or serving
an old receipt does not renew the source or intent expiry. Historical identities
remain inspectable after planning expires.

## Private materialization and public transport

`openhab/scripts/household_observation.py --receipt ORIGINAL --output CACHE`
replays the original model/plan receipt and checks executing/source closures
before producing the curated observation. The original receipt is not changed.
The source and target must be owned regular mode-0600 files, with a mode-0700
cache parent. First creation refuses an existing unknown target; replacement
checks source, runtime and target identity again before publication. It pins
the verified directory descriptor and stages any prior target with Linux
`renameat2(RENAME_NOREPLACE)`. The displaced file must match the original bytes
and identity before installing the new view with a no-clobber link. Changed
unknown files are restored without overwrite; an occupied restoration target
leaves the displaced file private rather than destroying either file. During
the short missing-name transition an HTTP reader may report unavailable.
The observer lives outside the producer module directory, preserving its closure.

The Vite middleware serves only `GET /api/household-observation`. Its default
cache is `~/.local/state/household-intel/observation.json`; the server may select
another fixed cache via `HOUSEHOLD_OBSERVATION_CACHE`. Browser query parameters
cannot select a file. Unsupported methods return 405, query parameters 400,
and unsafe/missing/malformed files 503 with only `{"status":"unavailable"}`.
Responses are never cached. File reads reject symlinks, changed identities,
incorrect ownership/permissions and more than 32,768 bytes. No HTTP request
runs replay, Python, training or a model.

The mounted screen polls every 30 seconds, advances its local clock every second
independently of network polling, and recalculates freshness from original
clocks, bounds response bytes, aborts a request after 10 seconds and cancels
requests/timers when navigating away. Source/raw configuration, owner scripts,
private paths and original source values are excluded from the public schema.

## Current verification

The private materializer and affected pipeline previously passed 118 tests.
The actual original measured-weather v6 view is 10,012 bytes, with 43 source
roles, 11 qualified at the model issue clock and two model identities. Its
receipt identity is `e961059127a0263cfa29fd031965aecc07823dc8cfea7e28d42913df1dc113f6`.
Its original expiry is `2026-10-12T03:00:17.508000+00:00`, and it is currently
historical/unavailable. The browser parser accepts that real curated artifact;
current policy comparison is unavailable and automatic actuation is false.

The focused frontend checks pass 56 tests across parser, real-file HTTP
transport, bounded streaming client, Svelte rendering, polling cleanup and
routing. Duplicate keys, including escaped or nested duplicate names, are
rejected before accepting a view or serving original bytes. Worker counts are explicitly limited for Rolldown, Tokio, Rayon and
Node. These checks ran with CPU20%, memory256MiB, swap0, tasks24, idle I/O and
a 64MiB JavaScript heap.

The full frontend suite was attempted under the same caps and stopped by the
scope's memory guard (`run-u2324.scope`, `oom-kill`). It did not finish and
is not claimed passing. The separate production-build attempt also hit the
256MiB scope limit before completing. The single final static review found two Important issues; one TDD correction
pass addresses duplicate-key privacy and publication races. Its 22 focused
Python cases pass, including both deterministic target/parent substitution
regressions, and the corrected frontend passes 56 cases. Target geometry, deployment and
hosted checks remain pending until their concrete evidence is recorded.

## Deployment boundary

Deployment must copy only reviewed new observation/UI files and the route,
App, Shell and Vite changes. Preserve the root checkout's existing thermal UI
overlay. No OpenHAB restart or owner-policy change is needed. A historical
cache is not a live planner; common-cycle capture/publication remains part of
the full PR3 objective.

This stage does not complete PR3. Operational trajectories, qualified effects,
actual policy baselines, correlated owner migration, causal outcomes and
per-intent graduation/integration remain required by the approved architecture.

The reviewer also noted existing-cache recognition validates only its top-level
envelope. Complete nested recognition remains a Minor follow-up; HTTP serving
already rejects all unsupported nested fields. No full-program completion or
production accuracy is inferred from these stage checks.

The expanded six-file Python run reached its 75s and 180s deadlines without
finishing and is not claimed passing. After correction, the actual CLI refused
the test virtual environment as a mismatched original runtime; the exact
production interpreter/dependencies passed unchanged replay verification.
The resulting original receipt identity and expiry are unchanged. A bounded
real-file HTTP read returns 200, no-store and the 10,012-byte, 43-source,
two-model expired view. Current observation SHA-256 is
`6ebb27a7de2dcadff343b358fa9dcd7918cc650cf2a0fe27937a809118aaaf6f`.

The core pure pipeline regression completes separately: 98 tests pass in
14.80s. With the 22 corrected observer/materializer tests, this gives 120
completed affected Python checks; it does not substitute for the unfinished
expanded six-file run or the full hosted project suite.

A safe live canary identified that Vite's filesystem route could serve private
staging despite mode-0600/0700 permissions. The configuration now preserves
Vite's default sensitive-file exclusions and denies .superpowers, .codex and
.aws paths. A real Vite HTTP regression uses the actual configuration and
checks direct, filesystem-alias and encoded-dot requests. It fails without the
configuration guard and passes with it. The complete focused frontend group
now passes 56 tests in 32.10s.

Only this private-path guard is installed in the live root configuration so
far. Both tested live staging aliases return403; the public REST receipt remains
available for October11. Six protected thermal UI overlay files match their
original hashes. No actual credential was fetched by the canary test, and no
credential rotation, OpenHAB restart or equipment request occurred.

Draft PR28 contains this stage. Its pre-filesystem-guard head49073f0 passed the
hosted frontend suite and production build; full CI was still running when
that job was inspected. The final guarded head must pass all hosted checks
before merge/deployment. Bounded browser attempts have not yet produced
viewport evidence; geometry and full panel deployment remain pending.

## Merged deployment qualification

PR28 merged October12 at06:06:33UTC as3d118d6439f692efb94564203865e33bd4fb820d.
Its exact source head10e440ac1131d8b95c9491a580d5ec6116c75b04 passes all four
hosted checks. Full CI run38208393534/job114676873602 completes frontend,
build, completion, OpenHAB/disposable PostgreSQL and operational regressions.

Eight reviewed files and the private cache are deployed. Live endpoint returns
200/no-store,10,012bytes,43sources/two models with the original e9610591 receipt
identity and original expiry. The live cache SHA-256 is
582ebc7455c1eff5813d0822e83cd80a35af50a0add3da4b93fee3bd58b9fca3.
The actual route passes1280x800 and1340x800 checks with no outer overflow,
page errors, command controls or attempted mutations. It shows the original
expired plan, no selected action and unavailable current-policy comparison.
Six signed-off thermal overlay files remain unchanged;OpenHAB was not restarted.

Browser qualification uses CPU20%,memory256MiB,swap0 and one renderer/CPU
affinity. Chromium needs a96-task cap;scientific tests/materialization retain24.
An initial24/48-task browser could not start reliably;the standard bounded
96-task browser exits successfully with all children closed. No off-host
execution requirement is introduced.

Earlier pending statements above describe the pre-qualification checkpoints.
This read-only stage is now merged/deployed;the full PR3 architecture remains
incomplete, including operational common-cycle capture, trajectories, effects,
policy baselines, owner migration, outcomes and per-intent release/integration.
