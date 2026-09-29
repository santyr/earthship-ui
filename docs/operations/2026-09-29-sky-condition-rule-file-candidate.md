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
