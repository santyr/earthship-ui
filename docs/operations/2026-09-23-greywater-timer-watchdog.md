# Greywater cycle-timer fail-safe — September 23, 2026

## October 3 actual JDBC/JVM recovery and proposed attended replacement

At 22:57Z, `scripts/qualify-greywater-recovery-jdbc.py` passed in disposable
OpenHAB 5.2.1/PostgreSQL 16 containers sharing only a networkless namespace.
The exact candidate action `4c34780e...` used synthetic unlinked Items, the
canonical change-only/restore JDBC strategy and a restricted disposable JDBC
role. Revoking INSERT on only its uniquely identified ledger table retained
the original accepted history through three automatic dispatches and one
native manual command: both outputs stayed OFF and no ON command appeared.
A genuine JVM replacement restored that durable accepted request and a
synthetic orphan ON state; the candidate switched it OFF and kept the hold.
Restoring INSERT allowed exact durable recovery with no same-pass start; the
next eligible pass started exactly one synthetic output, and missing SoC
evidence immediately forced both OFF. Original-action rollback and candidate
return matched exact actions, retained the original JDBC prefix and remained
fail-closed on missing evidence. All owned containers/volumes were removed.

This first harness revision was `b7b5306396e3d362792704fa5b846c11736d50b5bd6cd0f9efdca99d6eecfe3f`.
The follow-up also passed every phase, with explicit exact action/trigger
readback immediately after JVM replacement. Final qualified harness SHA:
`aed5c27f82663453ec8f9d4268724dd2049de920d065c732ae88d98aab7a94bb`.
Its fresh owned containers/volumes were also removed; this was a separate run.
The fixture deliberately omits the automatic cron to avoid unsolicited fault
dispatches. It retains the native manual trigger and exact action; this does
not prove hardware transport, physical flow, every trigger timing or a
production whole-OpenHAB restart. Production remains on the old action.

The default-read-only `scripts/deploy-greywater-durable-recovery.py` pins exact
old/new sources and the original live trigger/managed-provider contract.
It extends the established disable/PUT/readback/enable rollback transaction
with repeated fresh source-bound SoC, healthy Schneider telemetry/voltage,
both explicit OFF states, and (in daylight) five minutes before eligibility.
Private backup retains the exact original rule plus related Item/link
definitions and a fixed last-day REST/JDBC snapshot, including explicit
absence where no history exists. This is bounded continuity, not a full
database backup. Definition/history checks run inside the rollback boundary;
unowned rule or Item drift refuses unsafe overwrite/re-enable. All **47**
affected Python guard/probe/transaction tests pass, including original-source
rollback on enable failure and leaving unowned drift disabled. Read-only
production preflight and all related definition/history reads pass.
Release adapter SHA:
`3ed4f258cc95e451d88d06b2b91d83470b6d3df36979a8bda74b2965ce004030`.

### Exact protected-rule release plan — approval still required

1. Require specific approval of only `hex_southoutlet_cycle` action
   `e697e262...` -> `4c34780e...`, fresh physical attendance and both pumps
   physically OFF. Recheck the live preflight and cooldown immediately before
   applying; do not squeeze the update into an approaching cycle boundary.
2. Use the new adapter with `--apply --attended --physical-pumps-off` only after
   that approval. Privately back up, disable only this managed rule, recheck
   OFF/telemetry/definitions, replace only its action, verify exact disabled
   readback, enable and verify exact enabled source and fixed histories.
3. On an owned transaction failure, restore and verify the exact original
   source. If drift makes recovery unsafe, leave the protected rule disabled,
   report the failure and require operator direction; never overwrite drift.
4. Independently inspect source/status, both pump states and the release log
   window, then require the next natural minute status and unchanged triggers.
   No restart, manual run, synthetic production input or pump command is part
   of this release. Do not force a fault/cycle to manufacture natural evidence.

This repairs managed logic, not a file-provider migration. Keep the sky
provider handoff separately held until the repaired consumer is actually
installed and its remaining scope is requalified. Generic historical adapters
remain pinned/default-off; their pins are not silently broadened.

## October 3 interrupted-ledger durability repair — source only

Recovery qualification reproduced a separate live-source defect without hardware:
with a restored `accepted` request, old independently restored cooldown, fresh
native SoC and otherwise eligible conditions, failed JDBC persistence or bounded
readback still allowed an automatic ON command. `postUpdate` had already changed
the registry to `failed/restart_uncertain`, so subsequent evaluations and manual
requests could also bypass the unresolved durable write. Six of the first nine
regressions failed against the exact production action
`e697e2626a5e1ab4e4d079612c4b85d16dd79178a4ff80a5208b4bb108970d18`.
An additional failing regression demonstrated loss of volatile recovery state
while the terminal registry remained ahead of JDBC.

The staged `southoutlet-cycle-current.js` candidate is
`4c34780e544d80af8eb36d047a949fa30e0198bb50fa57650285052db3c52d9b`.
It retains the exact bounded before/after ledger obligation in shared cache,
rejects unowned replacements including reused request IDs, and clears the hold
only after the existing exact registry/JDBC readback succeeds. It also checks
terminal `restart_uncertain` records against JDBC if volatile state is lost.
Failure forces both outputs OFF; existing BMS/voltage/daylight safety diagnostics
retain priority. New manual requests cannot replace a pending recovery. Automatic
recovery consumes one evaluation before normal eligibility may resume. No SoC
threshold, timing, alternating-pump policy, ledger schema or ordinary automatic
policy for unrelated unreadable ledgers changes.

All **15** no-hardware durability regressions and the full **2,089-test** UI/
OpenHAB suite pass. The **18** affected Python historical-release/probe tests
also pass. The historical SoC deployment helper still pins its original release
hash and refuses the new source before REST access; the sky consumer qualification
likewise still pins the old action rather than accepting this candidate silently.

At this earlier source-only checkpoint it was **not deployed or real-JDBC/full-JVM qualified**. Read-only production
inspection at approximately 22:43Z found the old hash, `IDLE/NONE`, both pump
Items OFF, healthy BMS communications and an ordinary cooldown. No production
request, pump command, rule run, restart or rollback was performed. Next require
an isolated actual OpenHAB/JDBC failure/readback/restart/rollback rehearsal,
an exact reviewed protected-rule replacement transaction, private recovery,
fresh operator attendance and physical OFF confirmation. Keep the sky provider
handoff on hold pending these checks. Earlier timer evidence below is historical,
not qualification of this new candidate.

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

## Same-day last-second completion guard

Review found a remaining race: an external OFF during the final seconds before
the scheduled callback might occur after the last one-minute evaluation. A new
regression reproduced a false `SouthOutlet_LastCycle` receipt when the pump was
OFF just before the callback. The callback now checks that its own pump is
still ON before issuing OFF or recording completion. If it is not, it reports
`cycle_interrupted`, leaves `LastCycle` untouched, and fails an accepted manual
request with that reason. The existing token-ownership check still runs first.

Commit `272d51f` is pushed to origin/main. Focused greywater tests passed
93/93, all 1,634 UI/OpenHAB tests and the production build passed. The
second guarded transfer used the first release hash
`358c5c1131b731ee944c7cd45769cbc29b191fe42d28186d5020345fed1ff0ab`
as its exact live baseline and installed
`312cf24ceba5c63e30c4ecd0104bbf3bcf646f1e203b8c6c9c964e58dd7b84df`.
The immediate rollback copy is private at
`/home/sat/.local/state/greywater-rule-release/timer-guard-7fe65cj5`
(0700 directory, 0600 file). Both pump Items were OFF before and after, the
rule was `IDLE/NONE` at readback, and its one-minute plus manual triggers
remained unchanged. No manual cycle or pump command was issued for this
qualification. The 11:16 MDT natural minute evaluation then reported a
low-SoC hold under the final installed hash, with both pumps OFF and the rule
`IDLE/NONE`. A naturally interrupted cycle under the final revision remains
unobserved.

## Natural full-cycle follow-up

At 13:23 MDT on September23, the final installed revision naturally started
the East pump. Its exact live rule-script SHA256 remained
`312cf24ceba5c63e30c4ecd0104bbf3bcf646f1e203b8c6c9c964e58dd7b84df`.
The rotated and current OpenHAB event logs together show the pump's OFF→ON
transition at13:23:00.014 and ON→OFF at13:38:00.017, with no intervening
state-change-to-OFF event in that interval. The rule-origin OFF command was
at13:38:00.016; `SouthOutlet_LastCycle` advanced to19:38:00.015Z and
`SouthOutlet_AutoStatus` reported `cycle_completed`, nextPump=south and
nextEligibleAt=20:23:00.013Z. Both pump Items were OFF at readback and the
rule was IDLE/NONE. This is controller/Item evidence for a normal full cycle,
not independent flow measurement and not a test of the early-OFF or lost-timer
fallback. No manual run or test command was issued.

## September 23 natural daylight cutoff

Read-only September 24 JDBC reconstruction under the final deployed rule hash
`312cf24ceba5c63e30c4ecd0104bbf3bcf646f1e203b8c6c9c964e58dd7b84df`
found a South cycle completed at 18:43 MDT, with its pump switched OFF and
`SouthOutlet_LastCycle` advanced. Minute status remained `cooldown_wait` through
18:55, then changed to `after_dark,sunElev=-0.1,scheduling=blocked` at 18:56.
The next eligible cycle was 19:28; minute statuses at 19:26–19:31 all remained
`after_dark`, and neither persisted pump switch changed between 18:56 and
20:00. Live rule readback matched the tracked source, had two triggers, and
was `IDLE/NONE`. This verifies the natural **no-new-cycle after-dark gate**
under the final revision. The South pump was already OFF when the gate changed,
so an active-cycle sunset interruption and the early-OFF/lost-callback fallback
remain unobserved. No pump command or manual rule run was issued by this audit.

The same read-only status history shows the September 23 **sunrise gate** under
this final rule: minute evaluations at 06:40–06:55 MDT reported `after_dark`
as sun elevation rose from −3.1° to −0.2°. At 06:56, the reason changed to
`low_soc` with 85% SoC, a 98% threshold and `sky=TWILIGHT`; subsequent minute
checks remained blocked by the separate SoC/sky policy. Neither pump switch
changed in the bounded 06:40–07:20 window. This verifies dynamic removal of
the night block before the old 08:00 fixed start, not a pump start at sunrise
or permission to bypass battery and sunlight gates.
