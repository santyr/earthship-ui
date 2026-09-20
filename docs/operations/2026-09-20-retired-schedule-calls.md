# Retired-rule schedule calls repaired

The recurring 09:00 and 21:00 RuleEngine errors were calls to deliberately
disabled child rules, not a failed replacement owner. Live configuration showed:

- `b1501047a9` (09:00 Override OFF) commanded `OverrideSwitch OFF`, then called
  disabled `e647476610` (legacy Cistern Pump ON).
- `1f692c798b` (21:00 Override ON) commanded `OverrideSwitch ON`, then called
  disabled `ab8a59e1da` and `4e234eabea`, alongside the existing `GoatCamOff` call.
- `hex_night_load_override` already handles the OverrideSwitch commands and
  owns the replacement load matrices. The three child rules remain retired.

The repair removed only references to those three retired IDs. The now-empty
morning RunRuleAction was removed; the evening RunRuleAction still calls
`GoatCamOff` with its original settings. Both schedules, OverrideSwitch commands,
conditions and all unrelated definitions were preserved. No coupling or feeder
rule was edited, enabled or executed.

Four tests cover schedule/coupling preservation, empty-call removal, wrong-owner
refusal, module wiring refusal and idempotence. Live apply occurred outside the
schedule windows with exact before-state guards and private backup at
`/tmp/retired-schedule-repair-sn8pdzn4`. Readback verified both schedules IDLE,
all other rule definitions unchanged and retired children still DISABLED.
No runnow, synthetic Item event or hardware command was used as a test.

The exact resulting managed definitions are tracked under
`openhab/file-config/managed-exceptions/`. Their provider remains managed; they
are not a completed file migration. The next natural 21:00/09:00 executions must
still be observed to confirm absence of these log errors. Rollback uses the exact
private before definitions through REST, not re-enabling the retired children.
