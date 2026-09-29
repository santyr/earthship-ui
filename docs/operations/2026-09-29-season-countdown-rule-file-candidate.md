# Season countdown display rule: file-provider candidate

At the September 29 05:09 MDT read-only preflight, the live rule
`update_days_until_season` was still REST-managed (`editable=true`). It has one
`core.ItemStateChangeTrigger` on `Sun_TimeLeft`, no condition, and one JavaScript
action that reads `Sun_TimeLeft` and `Sun_NextSeason` and posts only
`DaysUntilNextSeason`. The live script SHA-256 was
`d43b3f993991966ade5d428bc4ff6af603a253a06f336ff93221cc22cc332311`.
It is a display writer, not a protected control.

The source-only file equivalent is
`openhab/file-config/automation/js/update_days_until_season.js`. It keeps the
rule ID, name, description, trigger and action calculation. Five local
no-hardware tests cover metadata and all four season outputs. The source file
has **not** been installed under `/etc/openhab/automation/js`, and
`ownership.json` deliberately still has no file claim for this rule. The
existing managed rule remains the sole live writer.

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
