# WeatherNext publication runtime preparation

Status: library and operational caller prepared; no live publisher, CLI or timer installed.

`weather_learning.production_runtime.run_publication` now connects the existing
Google-only provider and commit-last publication mechanics to bounded REST,
shared-lock admission and retained attempt evidence. The future cutover caller
must supply its qualified release/file-ownership decision and existing resource
guard. Missing or false admission refuses before HTTP or evidence writes. This
component creates no release grant, fits no model and reads no legacy state.

The runtime opens only an existing read-only Google archive and holds the existing
private shared writer-lock inode throughout the transaction. Admission is checked
after request pacing, before requests reach the server. Available state writes
freshly check the original archive digest and source age. Source failure prevents
an available detail commit while still allowing owned withdrawal attempts.
Replaced lock inodes or revoked admission prevent further state updates.

The transport accepts only eleven existing forecast Item state endpoints, plus
GET requests for their metadata and the channel-link inventory. Preflight checks
the declared types, non-editability and absence of links. Actual file-provider
identity and exclusion of competing writers remain the caller's admission
responsibility. Ownership refusals retain a fixed reason code and known Item
name; arbitrary exception text and credentials are excluded. Requests have the
existing pacing/deadline behavior, disabled proxies/redirects, bounded responses
and an 8 MiB aggregate read budget with a single-byte overflow probe.

Before the first state update, an immutable private attempt records the exact
prepared provider, all states and their identity, decision and code revision.
The result records the verified state-readback outcome or refusal. Both records
retain `release_authorized=false` and `automatic_actuation=false`. A state readback
is not a persisted JDBC receipt or scientific qualification. Record size, object
count, disk headroom and directory ownership are bounded; no source data or audit
is silently deleted.

## Lightweight shared I/O

`openhab_runtime_io.py` provides the existing `ReadBudget`, redirect handler and
`SharedScoreLock` without importing thermal numerical code. Existing thermal
imports re-export the same primitives. Budget/redirect class ASTs are unchanged;
the lock differs only in importing the equivalent neutral private-directory
validator. CPU, RAM, swap, pressure, request-pacing and deadline policies are
unchanged. The native base manifest includes the helper and now contains 83
sources. Fresh source-bound fitting remains required before release.

## Verification

- Fourteen runtime cases pass, with observed RED-to-GREEN checks for the missing
  runtime, aggregate transfer bound, cold imports and ownership diagnostics.
  Coverage includes actual file locking, retained pre-write states, source
  mutation, complete withdrawal, revoked admission after pacing, fixed endpoint
  restrictions, transfer-budget exhaustion and cold import without thermal,
  NumPy or SciPy dependencies.
- All **196 WeatherNext package tests passed in 7.031 seconds** in the pinned
  Earth Engine environment. The first full run exposed the unwanted NumPy import;
  the neutral extraction fixed it without adding numerical dependencies.
- Existing capture/lock/pacing tests: **55 passed in 5.59 seconds**.
- Immutable native-input, actual fresh fourteen-parameter fitting, Google backend
  and deployment checks: **84 passed in 19.91 seconds**.

A retained real 360-hour / 4,320-point Google snapshot was replayed through the
final immutable implementation (`164cb27d89313adc4a0553e41cb6a351cc7928fe`) and a local
HTTP simulator. It prepared 337 provider hours and all eleven states, made 36
simulated requests and received 51,716 bytes. Original source, state and result
identities matched. This replay used the original capture-completion-plus-one-
second decision; execution time was separately retained. It made no live HTTP
request and establishes neither prospective execution nor live ownership,
JDBC persistence, skill or release qualification. Evidence remains private.

A separate actual OpenHAB probe used an explicitly GET-only opener and the
existing approved identity. All eleven declared Item types/non-editability checks
passed. The twelfth request, for links, correctly refused `Forecast_Radiation`
with `CHANNEL_LINK_PRESENT`. The probe received 132,297 bytes and sent zero state
updates. This confirms the transport's live REST contract and a required cutover
step; the current binding/links remain unchanged.

The qualified operational caller/configuration, final source retirement, fresh
Google/local model qualification and coordinated service/binding cutover remain
unfinished. Existing production provider, model, services and actuator authority
were not changed by this work.

## Operational caller prepared

The [production worker](2026-10-18-weathernext-production-worker.md) now supplies
the explicit private reviewed-release/configuration boundary, installed Item-file
identity, original gate-report pins, incumbent-unit checks and existing resource
guard. The default CLI is read-only; publication requires `--publish`. Prepared
service/timer sources are not installed. All 211 WeatherNext tests passed in
8.738 seconds. Actual release evidence, reviewed private configuration and the
coordinated source/service/provider cutover remain required.
