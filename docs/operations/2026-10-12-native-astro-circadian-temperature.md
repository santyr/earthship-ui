# Native Astro circadian temperature cutover

October 12 2026. The operator selected Astro's native **2500–5500 K** curve
instead of the custom elevation-to-Kelvin curve. The existing living-room owner
continues to preserve manual power/brightness and verify physical bulb state.

`Sun_Circadian_Temperature` is a new file-owned `Number:Temperature` Item linked
to `astro:sun:local:circadian#temperature`. Its explicit `unit="K"` prevents
locale-dependent conversion; autoupdate is false and the display is read-only.
Canonical definition: `openhab/file-config/items/astro-circadian-temperature.items`.
Installed definition: `/etc/openhab/items/astro-circadian-temperature.items`.
The ownership manifest records the sole Item and link provider.

The managed `hex_living_room_circadian` rule now triggers on changes to this
native target rather than `Sun_Position_Elevation`. It validates the source's
Kelvin unit, 2500–5500 K range, Astro ONLINE status and update age at most two
minutes. Missing, stale or invalid input withholds writes. The old
`2500 + round(clamp(elevation,0,50) * 80)` formula and elevation parsing are
removed; there is no fallback to the old curve.

The owner retains its existing enable switch, diagnostics, readback verification,
100 K write threshold, four-minute query throttle, per-bulb backoff and recovery.
Temperature-only raw TP-Link requests still omit power and brightness. Physical
readback allows the bulbs' full 2500–6500 K hardware range so existing manual
settings can be measured before applying the narrower native target.
Native brightness remains unlinked; brightness is still manual.

## Verification

The first natural source state was **4884 K**, with a noneditable Item/link,
Kelvin units and read-only metadata. The deployed rule independently verified
**4884 K on all three bulbs**, and reported `source=astro:circadian` and IDLE.
No new deployment ERROR/Exception was recorded. Source and trigger readback
matched the rendered canonical definition.

Regression tests first failed against the old curve, then passed against the
native source. They exercise native target endpoints and an intermediate target,
independence from missing elevation, invalid/untyped/differently typed/out-of-range
input, source freshness and all existing OFF/enable/write-verification/backoff
and recovery safeguards. **37 focused tests and 2137 full-suite tests passed**.
Independent review found no defects in the scoped change.

The Astro 5.2.3 handler recalculates circadian values during positional updates
and publishes linked channels even when their value is unchanged. Thus a
constant nighttime target can remain fresh under the existing 16-second source
cadence; the owner does not require a state change to establish update freshness.
This source behavior is defined in pinned
[SunHandler](https://github.com/openhab/openhab-addons/blob/5.2.3/bundles/org.openhab.binding.astro/src/main/java/org/openhab/binding/astro/internal/handler/SunHandler.java)
and [AstroThingHandler](https://github.com/openhab/openhab-addons/blob/5.2.3/bundles/org.openhab.binding.astro/src/main/java/org/openhab/binding/astro/internal/handler/AstroThingHandler.java).

## Recovery

Private before-state and deployment receipts:
`/home/sat/.local/state/native-circadian-cutover/20261012T161628Z/`.
`original-rule.json` preserves the prior managed rule. For rollback, disable the
current owner, restore that saved definition through the same rule UID after
removing runtime status/editable/templateState fields, and re-enable it. Remove
only the newly owned `astro-circadian-temperature.items` file if withdrawing
its Item/link. Retain diagnostic and historical Item identities and JDBC data.
No whole OpenHAB restart is required.

The resource renderer remains
`python3 openhab/scripts/render_living_room_circadian.py`; it generates the
managed rule DTO with the current canonical source. Do not install a second
file rule or bind a bulb actuator directly to Astro.
