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
checks source, runtime and target identity again before atomic publication.
The observer lives outside the producer module directory, preserving its closure.

The Vite middleware serves only `GET /api/household-observation`. Its default
cache is `~/.local/state/household-intel/observation.json`; the server may select
another fixed cache via `HOUSEHOLD_OBSERVATION_CACHE`. Browser query parameters
cannot select a file. Unsupported methods return 405, query parameters 400,
and unsafe/missing/malformed files 503 with only `{"status":"unavailable"}`.
Responses are never cached. File reads reject symlinks, changed identities,
incorrect ownership/permissions and more than 32,768 bytes. No HTTP request
runs replay, Python, training or a model.

The mounted screen polls every 30 seconds, recalculates freshness from original
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

The focused frontend checks pass 50 tests across parser, real-file HTTP
transport, bounded streaming client, Svelte rendering, polling cleanup and
routing. Worker counts are explicitly limited for Rolldown, Tokio, Rayon and
Node. These checks ran with CPU20%, memory256MiB, swap0, tasks24, idle I/O and
a 64MiB JavaScript heap.

The full frontend suite was attempted under the same caps and stopped by the
scope's memory guard (`run-u2324.scope`, `oom-kill`). It did not finish and
is not claimed passing. The separate production-build attempt also hit the
256MiB scope limit before completing. Final review, target geometry, deployment and
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
