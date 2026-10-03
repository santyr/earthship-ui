# Sky-condition control-input rule: file-provider candidate

## October 3 later recovery finding — handoff held

The subsequent interrupted-ledger fault tests exposed an automatic-start
durability defect in the copied live pump source. The source-only correction
is now in `southoutlet-cycle-current.js`, but is not deployed or actual-JDBC/
full-JVM qualified. Keep this sky handoff held pending that separate protected
repair and recovery checks; the earlier missing/expired/comms experiment below
does not cover the defect. Its action pin remains `e697e262...` and intentionally
refuses the new source rather than silently qualifying a different candidate.
See [exact candidate, tests and next release boundary](2026-09-23-greywater-timer-watchdog.md#october-3-interrupted-ledger-durability-repair--source-only).

## October 3 isolated consumer/restart/rollback qualification

Production remains **managed**, and `RELEASE_READY['sky']` remains false.
The extended, networkless provider harness now includes the exact current
`hex_southoutlet_cycle` consumer rather than classifying the sky output from
its name. Both live action pins were independently checked:

- Managed sky action: `d99c01c15682b1cda7ed29d1255b877630ff1e329e08c12ba3ce26b59e11fd0c`.
- Pump action at that experiment: `e697e2626a5e1ab4e4d079612c4b85d16dd79178a4ff80a5208b4bb108970d18`,
  then identical to `openhab/rules/southoutlet-cycle-current.js` (now advanced
  by the later source-only repair above).
- Staged sky file: `6921170816d665062ff934c7a3e1b371b6ed565d35c081ec89ff4338859b4320`.

Run the scoped experiment with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/qualify-season-rule-provider.py \
  --kind sky --restart --sky-control-probe
```

The flag refuses any other rule scope or omission of `--restart` before live
reads. The cached OpenHAB 5.2.1 image is run read-only, networkless, unprivileged,
with no production mounts, devices, ports or channel links, a 2-CPU/2-GiB cap
and no container swap. Only copied rule definitions and synthetic Items enter
the container; its ephemeral administrator token is never printed.

The actual October 3 experiment passed **file hot load -> full JVM process
replacement -> original managed rollback**. In each phase, held numeric SoC
100 and calculated CLEAR sky did not bypass missing source evidence, expired
source evidence or stale BMS communications: both synthetic outputs stayed OFF
and the command log contained no pump ON event. Each phase also passed a
fresh-receipt positive control (receipt SoC 95): the exact action started only
one **unlinked** synthetic pump, with an actual ON command trace, then the
real missing-evidence safety path immediately returned both outputs OFF.
This prevents a disabled/broken action or absent logger from passing vacuously.

All **43** affected Python provider/probe/handoff tests and **148** focused
sky/current-pump/daylight/recovery JavaScript tests pass. Qualified harness SHA:
`e1bbc6062cfe7a28cf567bbf705d788d7eab4f2e606bcfd7c88027bd4c24033f`;
probe SHA: `822a73ee3f450e3299c5566045e08768f76e04e5d39a5d8f497661e802713386`.
The labeled container and its ephemeral volumes were removed on completion;
the previously cached image remains. At 22:22:04Z the production inventory has
zero issues, both original actions remain managed/IDLE/NONE with exact pins,
the watched sky file is absent and OpenHAB PID remains 1696.

This qualifies the stated cold/missing/expired/comms and positive paths only.
It does not prove restored interrupted-ledger/orphan-device recovery, JDBC
recovery, physical feedback/transport, all protected controls or a production
whole-JVM restart. Existing broader control-recovery requirements remain.

### Proposed attended control-input hot handoff

This scope needs specific operator review; it is not released by the successful
isolated test. No production whole-OpenHAB restart is included.

1. Recheck exact sky/pump actions, five sky triggers, single managed provider,
   absent watched file and committed source; confirm operator attendance and
   both pumps **physically** OFF immediately before any mutation. Require fresh
   source-bound SoC, healthy Schneider/BMS telemetry and weather input evidence,
   and a cooldown window clear of the next eligible pump transition.
2. Take a private, mode-0700/0600 current managed-rule/source recovery point.
   Pin all unrelated rule and relevant Item/link definitions, output JDBC
   identities 172/173/540/541 and original history prefixes. Treat naturally
   changing telemetry as data, not configuration drift; never replay old values
   into live control inputs to force equality.
3. Use an individually guarded transaction to withdraw only the managed sky
   rule, atomically install only its exact file, verify one healthy original UID
   and all five triggers, exercise original managed rollback, then return to the
   exact file provider. The pump rule/commands and all other owners stay untouched.
4. Independently verify unchanged definitions/history/PID and fresh controls.
   Require a natural source-attributed file timer/output and matching JDBC receipt;
   do not run the production rule manually or fabricate telemetry/pump activity.
5. Declare file ownership only after readback. On failure, withdraw only the
   exact owned file before restoring the private managed original. Refuse unowned
   edits, duplicate providers and unsafe rollback; retain the qualified backup.

The generic adapter stays default-off. A specific tested guarded transaction,
remaining protected-recovery checks and fresh reviewed attendance must precede
execution. Later production whole-JVM recovery stays a separately approved gate.

At the September 29 05:23 MDT live preflight,
`sky-condition-calculator` was REST-managed (`editable=true`, `IDLE/NONE`).
Its 4,677-byte JavaScript action had SHA-256
`d99c01c15682b1cda7ed29d1255b877630ff1e329e08c12ba3ce26b59e11fd0c`.
It has four Item-state-change triggers on `Sun_SunPhaseName`,
`Sun_TotalRadiation`, `AmbientWeatherWS2902A_SolarRadiation` and
`WeatherData_HealthStatus`, plus `0 0/2 * * * ?` as a two-minute fallback.
It writes only the SkyCondition/Icon and rate-limited diagnostic display Items;
it does not command hardware.

The source-only JS Scripting file
`openhab/file-config/automation/js/sky-condition-calculator.js` preserves
that UID, trigger set, action logic, weather-freshness boundary, moon-phase
night icon and change-only/rate-limited output behavior. Its SHA-256 is
`6921170816d665062ff934c7a3e1b371b6ed565d35c081ec89ff4338859b4320`.
Five no-hardware tests cover the triggers, partly-cloudy icon, nighttime moon,
stale/degraded weather and unchanged output. The post-stage full JS suite
passed 1,850 tests in 125 files.

The existing networkless OpenHAB 5.2.1 rule-provider harness was generalized
to accept this candidate. In an owned, disposable container it created a
managed copy, withdrew it, loaded the exact Git file, observed UID
`sky-condition-calculator` with `editable=false` and all five exact triggers,
then removed the file and restored the managed definition. The labeled
container and volumes were removed. Production readback remained
`editable=true`, `IDLE/NONE`, with five triggers; the watched sky file was
absent. No production output or control changed.

## Guarded live handoff — 05:32 MDT

The existing display-rule handoff adapter was parameterized for exact sky
identity, source hashes, all five triggers, eleven input/output Item types and
the two stable output states. Four offline success/rollback tests pass for
both display rules. Its read-only sky `--check` passed against the managed
production rule. The guarded `--apply` saved the exact managed JSON at
`/home/sat/.local/state/sky-rule-vxz_cwr2/managed-rule.json` (directory
0700, file 0600), removed the managed provider, and atomically installed the
Git file. Independent REST readback found one `sky-condition-calculator` rule
with `editable=false`, `IDLE/NONE`, all four Item-change triggers and the
unchanged two-minute cron, exact installed SHA-256 and active OpenHAB. The
display remained `TWILIGHT` with the current sunrise icon, consistent with
`Sun_SunPhaseName=ASTRO_DAWN` and theoretical radiation zero. The ownership
manifest is provisionally file-owned. No whole-OpenHAB restart, fabricated
Item event, or control change occurred.
Restricted read-only JDBC registry lookup still maps `SkyCondition` to Item
172, `SkyConditionIcon` to 173, `SkyCondition_LastEval` to 540 and
`SkyCondition_Diagnostic` to 541. No Item was recreated by this rule handoff.

The 05:32 `SkyCondition_LastEval` post preceded the file's 05:32:41 install;
it was **not** proof of the file rule executing. The natural 05:34 timer then
posted `SkyCondition_LastEval` at 05:34:00.254, and `events.log` attributed
that state change and the rate-limited diagnostic change specifically to
`org.openhab.automation.jsscripting$file:sky-condition-calculator.js`.
The unchanged `TWILIGHT` condition and sunrise icon were correctly not
reposted. The rule remained `IDLE/NONE`. This closes the natural post-file
timer/diagnostic gate; a later full restart still needs verification. Retain
the private managed rollback until that check passes.

## Safety reclassification and managed rollback — 05:40 MDT

The earlier description of this rule as display-only was wrong:
`SkyCondition` is also the live `hex_southoutlet_cycle` greywater eligibility
input. Read-only inspection of that **live** rule found two `SkyCondition`
references and the `CLEAR` gate; this is not inferred only from a Git source
candidate. Although the exact file rule ran correctly, a change to its provider
is therefore a protected-control *input* migration. Its isolated provider
test and one natural timer are insufficient to qualify control recovery after
a whole-OpenHAB restart. No restart was attempted.

With both `SouthOutlet_Outlet2_Switch` and
`East_Bed_Socket_Outlet_2_Power` reporting OFF and `SkyCondition=TWILIGHT`,
`scripts/rollback-sky-condition-rule.py` verified the exact private original
and installed hashes, withdrew only the sky JS file to
`/home/sat/.local/state/sky-rule-vxz_cwr2/withdrawn-file.js`, then restored
the managed DTO. Independent readback found exactly one rule under the
original UID, `editable=true`, `IDLE/NONE`; the watched sky JS file is absent.
Both pumps remained OFF, `SkyCondition=TWILIGHT`, the sunrise icon and active
OpenHAB remained unchanged. The file-ownership manifest claim was removed.

The source candidate and isolated rehearsal remain useful, but **production
sky-rule ownership is managed**. Do not reapply the file cutover until the
protected-control restart/rollback behavior and a specifically reviewed
control-input migration plan are qualified. The distinct
`SkyConditionIcon` *Item* remains file-owned; this rollback did not alter it
or its natural Item 173 history.
