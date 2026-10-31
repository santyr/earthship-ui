# Suggestion refresh evidence — 2026-10-29

## Source and scope

Signed source commit `0b52dc1` on isolated branch
`fix/suggestion-refresh-20261029`, worktree
`.worktrees/suggestion-refresh-20261029`. The three changed runtime files were
byte-identical between native parent `39b0070` and the actual deployed UI before
editing. The candidate was assembled from the actual current UI release, not by
replacing its unrelated layout/model-consumer changes with the branch parent.

Generation already runs every five minutes. The change replaces the shared
30-second advice GET poll with a five-minute fallback and fixed publication
notifications. Opening, visibility/page restoration, network/stream reconnection,
and saved human records cause early reads. The single server directory watcher
only emits an `update` signal for declared files; it never runs models or devices.
The last subscriber/server shutdown releases watchers, streams and timers.

Last validated advice survives a failed/invalid read without changing original
clocks. The header displays evaluation age and stale status, details show actual
evaluation time, and expired or failed-refresh actions are withheld. Domain/source
expiry remains authoritative. No numerical model, radio validity, native forecast
selector, generation timer or equipment control was changed.

## Qualified candidate

Retained evidence directory: `artifacts/suggestion-refresh-20261029.local/`.

- `candidate-a03-source-delta.json` and `candidate-a03-package-integrity.json`:
  2,591 original source/test/config files, exact declared 12-file delta (three
  runtime files plus tests, fixtures and one operator document), 2,600 resulting
  files. All unrelated deployed source/config bytes are preserved.
- `candidate-a03-focused.json`: **49 passed**, zero failed tests or suites.
  Seven affected test files cover actual atomic-file notifications and multiple
  clients, shared subscriptions, 300-second timing, resume/reconnect, failed and
  malformed reads, deadlines, cleanup, feedback, original expiry, source-bound
  provisional expiry, age and retained text.
- `candidate-a03-build-resources.json`: build passed within 1 GiB / 96 tasks,
  peak 881,225,728 bytes / 11 tasks; zero new memory or task events.
- `candidate-a03-unit-resources.json`: tests passed within 1 GiB / 64 tasks,
  peak 450,760,704 bytes / 17 tasks; zero new events.
- `candidate-a03b-preview-browser.json`: Chromium passes 1280×720, 960×600 and
  893×533. It verifies no periodic reads before 300 seconds, the five-minute
  fallback, publication and online refresh, source expiry on a quiet stream,
  age/stale display, no writes/runtime exceptions, no page overflow, 44px header,
  64px time and time left of energy.
- `candidate-a03b-preview-browser-resources.json`: browser passes within 1 GiB /
  96 tasks, peak 325,922,816 bytes / 76 tasks; zero new events. Screenshots are
  `candidate-a03-{width}.png`.

The earlier source-worktree run passed 47 tests. The first package's missing
fixtures caused three suite-resolution errors (11 tests passed, not package
qualification). Corrected packages explicitly include the two original fixtures
and corresponding maintained tests. Original failed candidate/logs remain.
An early build was stopped by host resource admission. Initial combined browser
workloads exceeded the 96-task cap. The final checks use already-qualified bounded
Rolldown/V8 worker settings and the built app, with identical assertions and the
same resource caps. One browser assertion was corrected to distinguish the
legitimate initial opening/page-show reads from periodic polling; the complete
300-second no-poll interval remains asserted. Original failures are retained.

## Deployment

`qualified-release.json` identifies immutable
`ui-release-suggestions-20261029-a03`, copied from the tested candidate with exact
runtime and public connection-config hashes. `deployment-before.json` retains
previous working directory, dedicated selector identity, main-index hash and
native forecast selector. `deployment-result.json` confirms activation/readback
at 13:42:45 UTC: advice API 200, notification endpoint `text/event-stream`, original
connection configuration, main index and native selector preserved. Only the UI
user service was restarted. The signed source branch preserves the dirty main
checkout and the separately deployed numerical release.

Rollback: remove only
`~/.config/systemd/user/earthship-ui.service.d/zzzzzzzzzzzzzzzzzz-suggestion-refresh.conf`
while its SHA-256 still matches `deployment-before.json`, then run
`systemctl --user daemon-reload` and `systemctl --user restart earthship-ui.service`.
The previous selector/release is unchanged.

## Actual live publication

`live-suggestions.json` passes all three actual landscape views with zero runtime
exceptions or attempted writes, one shared notification connection per page,
44px header, 64px time left of energy, visible age/stale status and no overflow.
The observer used actual OpenHAB data and no fixture routes or fabricated clocks.

An already-open 893px page observed report
`7054630a7a72c69310af10c09ab507a4df4d4a3a0c3be9db523447169e3edfed`
evaluated at 13:40:41.507003 UTC, then automatically received report
`19582b07e77588ca95feec1d544072e260a8e6fb47f778bca25839b464443275`
evaluated at 13:45:41.668650 UTC. The browser saw the new issue at
13:45:42.984 UTC: **1.316 seconds after its evaluation timestamp**. That is a
300.162-second natural generation interval. This arrived before the browser's
five-minute fallback was due, proving actual publication-driven refresh rather
than a manual reload. The header reset to `just now` using the new report's real
evaluation timestamp. `live-natural-publication.png` retains the visible result.

`deployed-live-browser-resources.json` passes within 1 GiB / 96 tasks, peak
393,633,792 bytes / 66 tasks and zero new resource events. Browser/server cleanup
completed and the launcher collected its job. No additional full sensor topology
qualification is claimed or needed for these UI-only transport changes. OpenSpec
strict validation passes. No security scan or Superpowers workflow was invoked.
