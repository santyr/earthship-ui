# Season countdown display rule: file-provider candidate

At the September 29 05:09 MDT read-only preflight, the live rule
`update_days_until_season` was still REST-managed (`editable=true`). It has one
`core.ItemStateChangeTrigger` on `Sun_TimeLeft`, no condition, and one JavaScript
action that reads `Sun_TimeLeft` and `Sun_NextSeason` and posts only
`DaysUntilNextSeason`. The live script SHA-256 was
`d43b3f993991966ade5d428bc4ff6af603a253a06f336ff93221cc22cc332311`.
It is a display writer, not a protected control.

The initially source-only file equivalent is
`openhab/file-config/automation/js/update_days_until_season.js`. It keeps the
rule ID, name, description, trigger and action calculation. Five local
no-hardware tests cover metadata and all four season outputs. At this first
checkpoint it had **not** been installed, and the managed rule remained the
sole live writer. The later live cutover is recorded below.

Before cutover, rehearse OpenHAB 5.2.1 JS Scripting file loading, rule UID,
provider readback and managed rollback in a disposable networkless instance.
Then recheck the exact live DTO and hash, save the private managed JSON, and
verify `Sun_TimeLeft`, `Sun_NextSeason` and `DaysUntilNextSeason` contracts.
Remove the managed rule only after the candidate and rollback preflights pass;
install the file atomically with no overlapping writer. Verify one active
trigger, one rule ID, unchanged Item/JDBC identity and a **natural** next
`Sun_TimeLeft` change producing the expected display. On failure, remove the
file first, restore the exact managed JSON, and verify the natural update.
Only after a successful readback should the ownership manifest be changed.
No whole-OpenHAB restart or fabricated Item update is authorized by this
source-only checkpoint.

Official [JS Scripting file-rule documentation](https://www.openhab.org/addons/automation/jsscripting/#rules-created-from-script-files)
documents `automation/js`, `JSRule`, optional IDs and default non-overwrite
behavior; the local provider rehearsal must still prove this host's UID and
reload semantics.

## Isolated provider and rollback rehearsal — 05:14 MDT

`scripts/qualify-season-rule-provider.py` started an owned, networkless,
read-only-root OpenHAB 5.2.1 container with disposable tmpfs configuration,
the cached Graal bundles and JavaScript Scripting add-on. It created a managed
copy of the exact live rule, withdrew it, loaded the Git JS file, and verified
UID `update_days_until_season`, `editable=false`, and the single
`Sun_TimeLeft` state-change trigger. File withdrawal removed that rule, after
which restoring the managed DTO succeeded. The exact labeled container and
volumes were removed. No production rule or Item was touched by the rehearsal;
isolated output behavior was covered separately by the five VM tests.

## Guarded live handoff — 05:17 MDT

The read-only `scripts/migrate-season-countdown-rule.py --check` passed against
the pinned managed script and Git file SHA-256
`d101eff0c4acf86ad900637e28cc7b30c1cf1185c5b3bcd116bef65e2114ed36`.
The attended `--apply` saved the exact managed rule privately at
`/home/sat/.local/state/season-rule-36v4y3r2/managed-rule.json` (directory
0700, file 0600), withdrew the managed rule, and atomically installed only
the verified JS file. Its rollback path was armed for provider or state
failure. Independent readback showed one rule with the exact UID,
`editable=false`, status `IDLE/NONE`, the sole `Sun_TimeLeft` state-change
trigger, the exact installed source hash, unchanged display state
`83 days until Winter ❄️`, and active OpenHAB. No OpenHAB restart, fabricated
Item event, or protected control change occurred. The inventory now reports
38 managed and one non-managed rule with zero ownership issues.
Restricted read-only JDBC registry readback still maps `DaysUntilNextSeason` to
Item 176, `Sun_NextSeason` to Item 84 and `Sun_TimeLeft` to Item 85; the rule
cutover did not transfer or recreate any Item. Two offline transaction tests
cover the guarded success and managed-rollback paths.

Ownership is **provisional** until the next natural `Sun_TimeLeft` *change*
(not its frequent unchanged updates) causes `DaysUntilNextSeason` to post the
expected value. The current event log showed unchanged `Sun_TimeLeft` updates
every roughly 16 seconds; those do not exercise a state-change trigger. Retain
the private managed-rule backup until the natural-update and later restart
checks pass.

## Natural writer qualification — 14:51 MDT

The rotated production event log records `Sun_TimeLeft` changing naturally from
7,171,200 s to 7,084,800 s at 14:51:32.754 MDT, attributed to the Astro
`season#timeLeft` channel. Four milliseconds later the file-owned
`update_days_until_season.js` posted `DaysUntilNextSeason`, changing it from
“83 days until Winter” to “82 days until Winter.” JDBC returned the same
prior/new display sequence and paired new source/display rows three milliseconds
apart. Read-only registry inspection still found one file-owned rule with the
sole `Sun_TimeLeft` state-change trigger, `IDLE/NONE` status, zero inventory
issues, and an installed source hash identical to Git
`d101eff0c4acf86ad900637e28cc7b30c1cf1185c5b3bcd116bef65e2114ed36`.
No Item was forced or OpenHAB restarted. This closes the natural-writer gate;
ownership remains provisional pending a later restart check. Retain rollback.
