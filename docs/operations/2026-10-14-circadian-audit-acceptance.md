# Circadian audit A09 integration and acceptance

The native temperature policy was already selected by the operator, implemented
and deployed on October 12. The PR3 branch omitted those two commits. It now
includes the existing implementation through `5a8bcd1` and `6a4b52d`, originating
from `61a9625` and `02e3fcb`. The ownership-manifest conflict was resolved by
preserving PR3 entries and adding only the lighting owner and native target.

The policy is Astro's native 2500–5500 K temperature, with manual brightness.
The managed `hex_living_room_circadian` owner remains responsible for freshness,
enablement, manual OFF, measured readback, hysteresis, backoff and recovery.
This work neither redeployed the rule nor sent commands to bulbs.

## Live verification

At 19:29:32 UTC on October 14, all six rendered rule fields matched live REST
readback exactly: UID, name, description, triggers, conditions and actions.
The rule was IDLE and Astro ONLINE. `Sun_Circadian_Temperature` was 5459 K,
file-owned, read-only, explicitly `Number:Temperature` with unit K and autoupdate
false. Exactly one native circadian link exists, to temperature. Native
brightness is unlinked. The installed Item file matches the canonical file.

All three bulbs were OFFLINE. The existing owner reported a recent degraded
receipt and skipped them. This readback verifies current source/provider and
owner behavior; it does not claim a fresh physical bulb trial. The original
October 12 cutover record retains the attended physical verification. The
integrated UI source also matches the currently deployed main checkout.

## Seasonal comparison and a native boundary limitation

`scripts/java/NativeCircadianComparison.java` invokes the installed Astro
`SunCalc` and `CircadianCalc` directly in an isolated JVM. It makes no provider,
network or actuator requests. The fixture binds all six installed library hashes
and the calculator script hash. Coordinates are the household site, timezone is
America/Denver, and altitude is unspecified. This is a controlled algorithm
comparison, not a claim about observed lighting on future dates.

Twenty actual native outputs cover June 21 and December 21, each at civil
midnight, sunrise +/-1 second, sunrise, morning midpoint, solar transit,
sunset +/-1 second, sunset and solar midnight. Retained fixture:
`tests/fixtures/native-circadian-5.2.3.json`.

| Instant | Native summer / winter K | Previous elevation curve summer / winter K |
| --- | --- | --- |
| Civil midnight | 2500 / 2500 | 2500 / 2500 |
| One second before sunrise | 2500 / 2500 | 2500 / 2500 |
| Exact sunrise | 5500 / 5500 | 2500 / 2500 |
| One second after sunrise | 2500 / 2500 | 2500 / 2500 |
| Morning midpoint | 4750 / 4750 | 5776 / 4090 |
| Solar transit | 5500 / 5500 | 6500 / 4754 |
| Sunset | 2500 / 2500 | 2500 / 2500 |

**Known upstream limitation:** Astro 5.2.3 has a discontinuity at the exact
sunrise timestamp. Its strict day-interval inequalities route equality through
the evening parabola, yielding 5500 K and 100% suggested brightness. One second
before/after produces 2500 K and 0%. This was discovered when the comparison's
expected 2500 K sunrise assertion failed; the actual output was preserved.
See the pinned [upstream calculator](https://github.com/openhab/openhab-addons/blob/5.2.3/bundles/org.openhab.binding.astro/src/main/java/org/openhab/binding/astro/internal/calc/CircadianCalc.java).

This limitation is not fixed here. Acceptance means that the chosen native
policy, its differences, and its owner safeguards have been evaluated and
verified. It does not certify that the upstream curve is continuous. The owner
consumes the native temperature and never forwards native brightness or power,
including at this boundary. No substitute curve or undocumented smoothing was
introduced. A future binding correction or explicit policy change should revise
the fixture deliberately.

## Regression evidence

There are 113 distinct passing affected cases: 57 owner cases (including the
20 native seasonal rows), 38 control-state cases and 18 rendered UI cases.
The original owner cases retain malformed/stale/missing source rejection,
explicit Kelvin validation, manual-OFF and disablement races, failed-write
readback, recovery and backoff checks. The seasonal cases assert temperature-only
requests, with neither `on_off` nor `brightness` fields.

The first combined run passed the 75 original non-UI cases but could not start
the UI worker. A dependency-path repair alone did not resolve it. Inspection
then found a real `pids.events max 1` event at TasksMax48, with about103 MiB RAM
in use. Raising the development thread allowance to96 resolved startup; the UI
file passed in3seconds. CPU remained one core, memory512MiB and swap0. The
subsequent combined run passed56 control/UI cases but exposed a new fixture
file-reader typo; correcting that typo and rerunning the owner file passed57.
Private logs and readback hashes are retained in the canonical program tracker.

A09 is complete for the selected native-temperature policy, with the upstream
boundary limitation explicitly recorded. A10, A11 and the full household PR3
program remain incomplete. No new actuator authority is granted.
