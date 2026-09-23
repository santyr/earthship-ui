# Greywater cycle-timer fail-safe — September 23, 2026

## Observed gap

A read-only query of the existing `SouthOutlet_AutoStatus` JDBC history found
10 starts / 10 completions on September 20, 10 / 9 on September 21, and
9 / 9 on September 22. The unmatched September 21 South start was at
12:04:00.470 MDT. The pump Item changed `ON` at 12:04:00.469 and `OFF` at
12:10:41.898, about 6 minutes 42 seconds into the nominal 15-minute cycle.
There was no `SouthOutlet_LastCycle` row in that window. Status was
`cycle_active` at 12:10 and `cooldown_wait` at 12:11. The available history
does not identify who or what caused the early OFF; no manual-result row was
found in the three-minute window around it.

The original timer callback was due at 12:19. The retained OpenHAB log records
that exact scheduled job failing with `The Context is already closed` at
12:19:00.465. A rule-context replacement is consistent with that error, but
the log does not establish why the context closed. The old automatic path
treated any one active pump plus a non-null busy token as `cycle_active`, with
no token-age bound. It also left the token valid when a pump went OFF early.
Had the old callback run after the observed early OFF, it could have posted a
false completion; if a callback was lost while a pump stayed ON, the minute
rule had no duration-based OFF fallback.

## Repair and release

The rule now invalidates a valid busy token and reports `cycle_interrupted`
when both pumps are OFF well before the 15-minute deadline. Its old timer
callback then has no authority to report completion. If one pump remains ON
more than five seconds beyond the deadline, the next minute evaluation forces
both pumps OFF and reports `cycle_timer_expired`; an unparseable or materially
future-dated token with a pump ON fails closed as `cycle_timer_invalid`.
Neither fallback writes `SouthOutlet_LastCycle` or claims a completed run.
The normal callback remains the only completion writer. The UI labels these
new statuses as an interruption or safety hold, without inventing a next run.

Three reproducing regressions failed before the repair. Focused greywater tests
passed 91/91, the full UI/OpenHAB suite passed 1,632/1,632, and the production
build passed with its preexisting chunk-size warning. The deployment source is
`openhab/rules/southoutlet-cycle-current.js`, commit `4c86655` on origin/main.
The guarded release helper pinned the exact previous live SHA-256
`de49ccfafbdf1263da6691d653c4bd6dde7c607f7d33f934c9abc17431eebe09`
and new SHA-256
`358c5c1131b731ee944c7cd45769cbc29b191fe42d28186d5020345fed1ff0ab`.
The preexisting source/live difference was one comment, not executable code.

The attended production preflight found both pump Items explicitly OFF, the
rule `IDLE/NONE`, and a low-SoC hold. The original REST rule is privately
backed up at
`/home/sat/.local/state/greywater-rule-release/timer-guard-qkmqqila`
under mode-0700/0600 permissions. The rule was disabled, updated, read back
exactly, then re-enabled; no pump command, manual request, forced cycle or
OpenHAB restart was issued. Independent REST readback at 11:11 MDT found the
new script hash, `IDLE/NONE`, the original manual plus one-minute timer
triggers, both pumps OFF and a natural low-SoC minute status. No error or
exception appeared in the checked release log window.

This is a bounded controller fail-safe, not an independent hardware cutoff.
Its fallback requires OpenHAB and the one-minute rule itself to run. A
naturally interrupted post-release cycle and the earlier requested sunset
interruption case remain unobserved under this revision; do not force a pump
run solely to close those evidence gates.
