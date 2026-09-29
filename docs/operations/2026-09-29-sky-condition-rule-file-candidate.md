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

Before a live cutover, add a sky-specific guarded backup and rollback adapter,
recheck the pinned live/script hashes and all output Item identities, and
transfer the single writer without overlap or OpenHAB restart. Verify one
file-owned rule and the next natural two-minute invocation against expected
SkyCondition/Icon and rate-limited diagnostic values. Only then add a
provisional ownership manifest entry; keep the private managed rollback until
natural and restart checks pass. No live cutover is claimed here.
