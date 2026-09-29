# Sky-condition display rule: file-provider candidate

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
