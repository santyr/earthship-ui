# Living room lighting and circadian audit — October 12, 2026

Later update on October 12: the operator selected Astro's native 2500–5500 K
curve, and the custom elevation formula was removed. See the
[native temperature cutover](2026-10-12-native-astro-circadian-temperature.md)
for current behavior. The original audit and earlier verification below are
retained as historical evidence.

The living room has three KL125(US) bulbs on the native TP-Link Smart Home
binding. OpenHAB is currently **5.2.3**, upgraded October 10; the older host
AGENTS.md version and python-kasa lighting description are historical.
The existing managed rule `hex_living_room_circadian` now uses the binding's
synchronous `send` action instead of python-kasa subprocesses. Its provider,
identity, Items, channel links, persistence mappings and existing color curve
are preserved. This is a managed exception with reproducible Git source;
there is no file-provider migration or duplicate rule.

## What the system does

`Sun_Position_Elevation` comes from `astro:sun:local:position#elevation`.
The existing Astro Thing uses the household coordinates and a 16-second
interval. The rule uses that source directly:

`targetK = 2500 + round(clamp(elevation, 0, 50) * 80)`

Thus elevation below the horizon gives 2500 K; 25 degrees gives 4500 K;
50 degrees or higher gives 6500 K. Seasonal changes remain Astro's responsibility.
The rule changes white color temperature only. It preserves the bulb's power
and brightness. At the attended check, all three bulbs were ON at 100%
brightness; the old system did not provide evening dimming or a bedtime schedule.
Turning the circadian policy OFF permits manual color/temperature choices.
While enabled, a manual color choice can be replaced by the next solar update.

Queries are normally limited to one pass per four minutes unless the target
changes by at least 100 K. Writes require a difference of at least 100 K from
live bulb readback. Sun changes and the existing five-minute cron drive checks;
bulb ON/ONLINE and startup also trigger recovery. A pending optimistic ON is
retried on a subsequent ON state update rather than waiting for the throttle.

| Room label | Thing | Switch Item | Absolute Kelvin Item |
|---|---|---|---|
| Living room 1 | `tplinksmarthome:kl125:E7FA31` | `living_room_1_Switch` | `living_room_1_ColorTemperatureAbs` |
| Living room 2 | `tplinksmarthome:kl125:E62B6D` | `living_room_2_Switch` | `living_room_2_ColorTemperatureAbs` |
| Living room 3 | `tplinksmarthome:kl125:E7CAD9` | `LED_living_room_1_Switch` | `LED_living_room_1_ColorTemperatureAbs` |

The Switch and Brightness Items deliberately share each bulb's Color channel,
which supports their command types. The absolute Kelvin Items have separate
`colorTemperatureAbs` links. Their current provider and identities are unchanged.

## Findings and fixes

| Finding | Impact | Implemented correction |
|---|---|---|
| CLI prints “Setting color temperature” before awaiting the device operation; the rule treated that text or any target-number occurrence as success | A failed operation could claim success and publish the target as measured ActualK | Validate structured device errors, then independently query the bulb and publish only measured white temperature |
| Invalid solar elevation silently became zero | Bad input could issue an unintended 2500 K write | Require valid elevation, ONLINE Astro and a native update timestamp no older than two minutes; reject impossible/future data |
| Successful state query cleared failure counters before a failed temperature write | Repeated write failures never reached backoff | Reset failures only after a confirmed result or normal OFF; include write and verification failures in per-bulb backoff |
| Two separate CLI processes per changed bulb, text parsing, hardcoded IPs and UDP-discovery sensitivity | More timeout, dependency and parsing failure points | Native binding action and existing Thing identities; reuse the binding's connection and configured device identity/address |
| Live-ON query followed by a power-on temperature command | A manual OFF between query and write could be undone | Raw temperature-only request omits `on_off` and `brightness`; all three actual bulbs passed OFF/brightness preservation trials |
| Policy OFF was checked only at run start | A slow request could continue applying later temperature writes after disablement | Recheck policy after queries and before each write; OFF stops the remaining work |
| No ON/ONLINE recovery triggers, and optimistic ON can precede physical ON | A recovered bulb could wait several minutes | Add recovery triggers and a bounded pending-ON retry on the next actual state update |
| Invalid-to-valid solar recovery retained the throttle | Target stayed UNDEF and health stayed unavailable after the source recovered | Clear throttle when solar health becomes unavailable |
| A timeout after an attempted write retained the pre-write ActualK | A pre-write reading could be presented after an ambiguous operation | Clear ActualK to UNDEF until independent readback succeeds |
| Boolean overlap guard could lose recovery notifications | A concurrent recovery could miss its immediate opportunity | Atomic guard plus retained recovery marker consumed by the next Astro/cron evaluation |
| UI blanket `skip` matcher classified normal OFF as degraded while missing CLI `temp-exc`/`state-unknown` | Health display disagreed with actual failure state | Explicit healthy/degraded/unavailable/disabled interpretation; OFF is normal |
| Historical success could remain Healthy indefinitely | Restored or stalled execution looked current | Successful/degraded receipts carry checkedAt; UI expires them after ten minutes with its own five-second clock; un-timestamped legacy success is unqualified |
| OFF/RGB/failing bulbs retained apparent white-temperature readings | Stored preset or old temperature could look like a current white measurement | ActualK becomes UNDEF when OFF, RGB, offline, in backoff, or an operation is ambiguous |

## Why the binding can be used

The binding is already installed and all three bulbs were ONLINE. It supports
KL125 and absolute Kelvin control. Its normal Kelvin command builds a light
transition with `on_off=1`, so using only an Item ON state check would retain a
race with manual OFF. `REFRESH` may also return the binding's internal cache.

The documented direct request action returns a synchronous JSON response:
`actions.get('tplinksmarthome', thingUid).send(jsonCommand)`.
We use live `get_light_state`, a temperature-only `transition_light_state`,
and another independent `get_light_state`. The write includes `ignore_default:1`,
`color_temp` and zero transition duration; it includes neither power nor brightness.
It leaves an OFF bulb OFF even if OFF happens after the initial query. A request
while OFF is ignored by this firmware, preserving its stored ON-state settings.

References: [binding documentation](https://www.openhab.org/addons/bindings/tplinksmarthome/),
[installed-version command builder](https://github.com/openhab/openhab-addons/blob/5.2.3/bundles/org.openhab.binding.tplinksmarthome/src/main/java/org/openhab/binding/tplinksmarthome/internal/Commands.java),
[direct action](https://github.com/openhab/openhab-addons/blob/5.2.3/bundles/org.openhab.binding.tplinksmarthome/src/main/java/org/openhab/binding/tplinksmarthome/internal/handler/TPLinkSmartHomeActions.java).
Hardware behavior was verified independently rather than inferred from these sources.

## Astro and weather data reuse

The existing Astro source supplies elevation, solar timing and seasonal variation;
no replacement ephemeris or external weather lookup is required. The local station
already supplies `AmbientWeatherWS2902A_SolarRadiation` in W/m² and
`AmbientWeatherWS2902A_UVIndex`, plus its existing health diagnostics. These are
available if brightness automation is subsequently designed.

Outdoor radiation is not indoor illuminance. A future dimming feature should
use the existing fresh station data alongside Astro timing, a chosen minimum
brightness and manual override, and qualify the relation to this room. It should
not infer a new bedtime or brightness preference from elevation alone. The
current fix preserves the existing brightness behavior.

Operational improvements: maintain stable DHCP/device identities and Wi-Fi
coverage; powered-off-at-wall bulbs cannot receive commands. Requalify the
power-preserving request after bulb firmware or protocol changes. Record and
choose an evening brightness/bedtime policy if fuller circadian lighting is wanted.
The current 2500 K lower limit is the bulb's supported white-temperature limit.

## Deployment, verification and recovery

Canonical sources are `openhab/rules/living-room-circadian.js` and
`openhab/living-room-circadian-resources.json`. To render a complete, secret-free
REST rule DTO, including expansion of `scriptSource` into `configuration.script`:

```sh
cd /home/sat/earthship-ui
python3 openhab/scripts/render_living_room_circadian.py > /tmp/living-room-circadian-rule.json
python3 -m json.tool /tmp/living-room-circadian-rule.json > /dev/null
```

The resource JSON is a source descriptor; do not PUT it without this expansion.
Hot deployment replaces only `/rest/rules/hex_living_room_circadian` via REST,
with the affected rule disabled while replacing it and enabled afterward.
Credentials remain in `/home/sat/.config/hex/openhab.env`; never put them in Git
or receipts. Do not edit JSONDB or install a duplicate file rule.

Private pre-change backup and native receipts:
`/home/sat/.local/state/living-room-circadian-release/20261012T150417Z/`.
`original-rule.json` is the exact pre-audit rule. For rollback, remove its runtime
`status`, `editable` and `templateState` fields, disable the current rule, PUT
that saved definition to the same UID, and enable it. The compatible UI recognizes
legacy errors but does not qualify untimestamped legacy success as current health.
Neither deployment nor rollback requires an OpenHAB service restart. Re-fetch
and compare the action/triggers, confirm IDLE and live Items, and inspect new logs.

Attended hardware evidence on October 12:

- Direct binding state queries succeeded on all three actual bulbs.
- Each bulb stayed OFF when a temperature-only request arrived while OFF;
  stored brightness remained 100%, and the test restored its original ON state.
- The installed owner then independently verified **4165 K on all three bulbs**
  after applying its computed target. Subsequent native binding channel polls
  provide the ordinary UI Item synchronization, which can lag raw readback by
  the configured 30-second interval.
- Rule identity/provider and all other rule definitions were checked; only the
  intended circadian rule changed. Two Shureflo rules were already deliberately
  DISABLED before this work. No whole-service restart was performed.

Automated regressions execute the actual managed-rule source with controlled
external device responses. They cover invalid/stale Astro, power/brightness
payload invariants, OFF/disable races, optimistic acknowledgements, device errors,
backoff/recovery, RGB/off measurement semantics, overlap recovery, invalid-to-valid
solar recovery and UI expiry without subsequent event traffic.

Production whole-JVM restart and future firmware behavior are not qualified by
these attended hot-update tests. The startup trigger uses the existing native
sources and fails closed until they are valid; retain the private original backup.

Final reviewed revision verification at 09:18–09:19 MDT:

- Deployed script SHA-256: `d6801133884735e94b998721a2dbf2d4f78d1e22570c57fcae6b21f7b56fc48e`;
  action bytes and all 13 triggers match the rendered canonical source.
- The final owner applied and independently verified **4340 K on all three**;
  their normal binding Kelvin Items subsequently converged to 4340. All Switch
  Items remain ON and all Brightness Items remain 100. Policy is ON, rule IDLE.
- `npm test`: **137 files, 2136 tests passed**; focused lighting/control tests:
  **92 passed**. `npm run build` passed with the existing chunk-size advisory.
- `CHOKIDAR_USEPOLLING=true CHOKIDAR_INTERVAL=10000 npx playwright test tests/e2e/controls-layout.spec.js`:
  **2 passed** at tablet/laptop sizes. The first attempt exceeded the host's
  file-watcher limit; polling solved the runner issue without production changes.
- Live Vite serves both updated modules (HTTP 200); the native nanosecond UTC
  receipt parses as Healthy. No new deployment ERROR/Exception, no remaining
  diagnostic rules, and only the circadian rule definition changed.
- Independent review's four recovery/freshness findings were reproduced,
  corrected and re-tested; final review found no blocking defects.

Final private receipts: `final-rule.json`, `final-result.json`,
`final-native-qualification.json` and `final-log.txt` in the backup directory.
The earlier 4165 K trial remains in `first-native-qualification.json`.
