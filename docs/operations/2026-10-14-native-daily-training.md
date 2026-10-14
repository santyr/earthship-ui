# Native daily training

The selected native model needs its own training schedule. The legacy
`thermal-model-train.timer` runs a different trainer and cannot advance the
native candidate selected by the UI.

`thermal-native-daily.timer` invokes the native pipeline at 06:50 America/Denver,
including after daylight-saving changes. A missed morning runs after startup.
Failures retry after 15 minutes, with at most three starts in three hours. The
service records a private `last-result.json` and also emits its result to the
journal. A current model exits successfully without capture, fitting or handoff.

The cutoff is the start of the current local day. The worker captures only
missing intervals, retaining seven days of adjacent raw measurements (plus an
interval crossing the rolling boundary). Captures are at most two days each and
persist in a fingerprinted index. Assembly refreshes the environmental journal
across the whole interval. Native Astro geometry, the existing feature builder,
fitter, candidate validator and model receipt APIs remain authoritative.

After fitting and numerical admission, the worker packages a new source-backed
family and preserves the existing historical score selections. It waits for the
three serving workers to become idle, checks that the selected model has not
changed, and uses the existing five-file transaction. Only that handoff briefly
quiesces the serving timers. The normal preparer and forecast schedule publish
the model; the daily trainer does not issue qualification probes or actuate any
device. A failed capture or fit cannot reach the handoff.

The immutable production checkout is
`/home/sat/earthship-ui/.worktrees/native-daily-production`. Development edits in
other worktrees cannot make this checkout dirty and prevent daily packaging.
The private configuration is
`/home/sat/.local/state/thermal-intel/native-daily/config.json`, containing:

- `state_directory`: private captured inputs, model generations and status;
- `capture_config`: existing approved read-only capture configuration;
- `seed_parts`: original raw snapshots, never an assembled snapshot;
- `staging_inputs`: existing parameters, observation cache and owned unit paths;
- `timezone`: `America/Denver`.

Production admission uses available RAM and worker memory isolation. Occupied
host swap and unrelated paging do not reject a run. The current 20% CPU,
256 MiB memory and zero worker swap profile already completed the real refresh
with a measured maximum of 121 MiB. It is retained as a working initial profile,
not a universal production requirement. The whole daily job has 30 minutes;
existing individual capture and fitting API bounds remain intact. Development
checks run serially in their own capped scopes.

Validation: eight date, rollover, idempotency and failure-order tests first
failed before implementation. Eleven scheduler/pipeline tests plus six production
RAM-admission tests pass. The pipeline test executes the real native fit on
synthetic measurements and verifies its original evidence before packaging.
The next natural morning execution still requires live evidence; unit tests
alone do not establish its completion.

Remaining limitation: the existing serving dispatch retains at most 31 historical
stages. Daily automation preserves that invariant. Retiring fully settled model
history is still required before that bound is reached; no retained score evidence
is silently discarded by this worker.

At 2026-10-14 18:05 UTC, the production checkout was clean at `fb3cbe9`.
The installed unit bytes matched the committed templates. The daily service
exited successfully with `already_current` in 3.394 seconds and did not fit or
change the selected model. The timer was enabled and active, with its next
trigger at October 15, 06:50 MDT. The obsolete legacy timer was disabled and
inactive. The three forecast/score/preparer timers remained active.

The first installation check exposed a missing private daily lock; a regression
test now covers first-run creation, concurrent exclusion and inode preservation.
The production checkout also inherited group-writable files from the shell
umask; installation removed group/other write permission from its tracked files.
Use umask 0022 or stricter when updating this checkout. Both setup issues were
corrected before enabling the timer.
