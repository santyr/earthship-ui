# Earthship UI Astro binding efficiency audit

The next coding work should restore the existing Astro forecast context, reuse
native season and current moon data in the UI, and consolidate solar geometry
through a versioned adapter. Astro already supplies most current celestial data.
Its calculations should become the shared astronomical authority while weather
observations, trained models, control policies and device verification keep their
existing responsibilities.

**Status:** report only. No application code, OpenHAB definitions, systemd units,
Item states or equipment commands were changed by this audit. The tasks below
are implementation handoffs, not completed fixes.

## Current system and inventory

The registry snapshot is from **October 12 2026 at 09:36 MDT**
(`2026-10-12T15:36:35.869047Z`). The main checkout starts at
`61a9625ceab2d28cd7605ba53968d93db2bd14d9`, including the verified lighting changes.
Installed Astro is **5.2.3**, confirmed through `/rest/addons/binding-astro`, not
inferred from old documentation or the overall OpenHAB version.

| Resource | Current inventory | Meaning for this audit |
|---|---:|---|
| Registered Items | 446 | All are included in the companion inventory |
| Things | 83 | Two Astro Things, both ONLINE |
| Item channel links | 268 | 55 links attach 55 distinct Items to Astro |
| Registered rules | 42 | Complete definitions inspected, including file-owned rules |
| Native Astro Item split | 27 sun and 28 moon | Includes phase text and separately transformed phase icons |
| Literal Item names in current frontend source | 97 | Only 5 directly linked Astro Items have literal frontend mentions |
| Literal Item names in backend source | 192 | Includes source candidates; a mention does not prove deployment |
| Item names mentioned in registered rules | 191 | Trigger/action/script references; a mention does not prove an executed branch |

The [Item inventory](2026-10-12-astro-binding-item-inventory.csv) records each
Item's type, editability, declared ownership/source, channels/profiles, source
mentions, registered rule references and Astro assessment. It intentionally
omits raw telemetry and credential-bearing configuration. References are an
inventory aid, not proof that a dynamically addressed Item is unused. Do not
delete Items, links or persistence tables based only on an empty reference cell.

| Astro Thing | Provider | Configuration | Available channels |
|---|---|---|---:|
| `astro:sun:local` | Managed, editable | `38.3739919,-105.7744609`, interval 16 seconds, `useMeteorologicalSeason=false` | 82 |
| `astro:moon:local` | File, noneditable | Same coordinates, interval 300 seconds | 34 |

The installed moon definition is `/etc/openhab/things/astro-moon.things`.
Its source still says “Staged only”; that comment is historical. Similar staged
comments remain in installed icon/season sources. Current registry ownership and
`openhab/file-config/ownership.json` determine deployment, not those comments.
The five frontend Astro mentions are `Sun_Rise_Start`, `Sun_Set_End`,
`Moon_MoonPhaseName`, `MoonPhaseicon` and `SunPhaseIcon`.

## Astro capabilities and reuse boundaries

These channels are present in the installed Thing definitions. The action
contracts below are supported by the pinned 5.2.3 implementation and the
[official Astro documentation](https://www.openhab.org/addons/bindings/astro/).
Existing linked Items should be reused before adding another publisher.

| Requirement | Native source or action | Existing implementation and boundary |
|---|---|---|
| Current solar position | `position#elevation`, `position#azimuth` | `Sun_Position_Elevation`, `Sun_Azimuth` already linked; lighting, fan, pump and battery rules use elevation |
| Position at a specified instant | `getElevation(ZonedDateTime)`, `getAzimuth(ZonedDateTime)` | Existing future-context publisher uses them; suitable inputs for historical/future geometry after a cached adapter is qualified |
| Current sunrise and sunset | `rise#start/end`, `set#start/end` | All four linked; UI and pre-dusk producer already consume them |
| Future or historical solar event | `getEventTime(phase, date, START/END)` | Existing ten-day publisher delegates to this; date is interpreted as the requested local day |
| Daylight and twilight | `daylight`, `civilDawn/Dusk`, `nauticDawn/Dusk`, `astroDawn/Dusk`, duration/event channels | Daylight start/duration and Astro dusk end already linked; select endpoints explicitly |
| Solar transit | `noon#start/end`; version-specific `getEventTime('NOON', ...)` | Noon channel is unlinked; 5.2.3 enum and handler support NOON even though the documentation's phase list is narrower; qualify the action before relying on it |
| Current astronomical season | `season#name/nextName/timeLeft`, four season timestamps | Already linked; UI independently calculates season instants instead |
| Current lunar phase | `phase#name`, illumination, age/angle/percent | Already linked; native `MoonPhaseicon` includes a MAP profile |
| Lunar event calendar | next quarters/new/full moon, rise/set, eclipses, perigee/apogee | Already linked; retain only consumer-required presentation, not another calculation |
| Date-specific lunar phase | No public moon-illumination/phase-at-date action in 5.2.3 `AstroActions` | Today's moon Item cannot replace future forecast-hour phases; keep the narrow future calculation until an accepted supplier exists |
| Clear-sky solar reference | `radiation#direct/diffuse/total`; `getTotalRadiation(ZonedDateTime)` | All three linked; reference is calculated, not measured station radiation or cloud-aware PV prediction |
| Suggested light temperature | `circadian#temperature`, `Number:Temperature` | Present but unlinked; native curve differs from the living-room curve |
| Suggested brightness | `circadian#brightness`, `Dimmer` | Present but unlinked; adding it would introduce brightness/power policy |
| Solar-relative scheduling | Range event channels, per-channel offset and earliest/latest settings | Can simplify sunset-relative scheduling; preserve retries, catch-up, idempotency and source checks |

The inventory also records resolved file-owned writer references when the
registered action uses a captured constant; the 191-name census above counts
literal registry mentions only.

The public actions are defined in
[AstroActions 5.2.3](https://github.com/openhab/openhab-addons/blob/5.2.3/bundles/org.openhab.binding.astro/src/main/java/org/openhab/binding/astro/internal/action/AstroActions.java).
They are not APIs named `getPos` or `getEphemerisDay`, and there is no public
season-next-date or future lunar-phase action there. Position/radiation actions
return typed quantities; event time returns a timezone-bearing date/time.
The additional NOON phase is confirmed in pinned
[SunPhase](https://github.com/openhab/openhab-addons/blob/5.2.3/bundles/org.openhab.binding.astro/src/main/java/org/openhab/binding/astro/internal/model/SunPhase.java)
and [SunHandler](https://github.com/openhab/openhab-addons/blob/5.2.3/bundles/org.openhab.binding.astro/src/main/java/org/openhab/binding/astro/internal/handler/SunHandler.java),
not by invoking a new rule during this audit.

## Findings and agent tasks

### A01 Restore the shared future solar context

**Priority P1. Verified current failure.**
`openhab/file-config/automation/js/astro-forecast-context.js:62` and its identical
installed file return unless the Astro bundle version is exactly `5.2.1`.
`openhab/scripts/astro_forecast_context.py:46`, also identical to deployed code,
requires `calculationVersion='openhab-astro-5.2.1'`.

The live `Astro_Forecast_Context_JSON` was recorded at
`2026-10-09T06:10:00.941048708Z` and expired at `2026-10-10T06:00:00Z`.
The publisher is registered and IDLE, but its version guard prevents refresh on
5.2.3. An ONLINE Thing or IDLE rule is insufficient proof of a current receipt.

**Impact:** optional solar diagnostic context is omitted. This does not stop the
existing energy forecasts. Deployed `forecast_intel.py:1486–1491` treats the
adapter as optional; actual PV resource still uses weather
`shortwave_radiation_sum` at line 1499 and learned gain at line 1504.

**Task:** qualify 5.2.3 actions, then revise producer and validator together.
Keep exact site/timezone, ordered dates, units, issue-time availability and
provenance. Use an explicit compatibility policy or qualified version set with
an actual calculation version in the receipt; do not accept arbitrary versions
or disable freshness checks. Report withheld publication with a bounded reason
so future upgrades cannot silently freeze it. Reuse this publisher rather than
creating a second future-solar authority. Its three `noon*` fields currently
mean local civil **12:00** (`astro-forecast-context.js:68,75–77`), not solar
transit; preserve that meaning during this repair or version a deliberate change.

**Acceptance:** native action/unit fixtures, supported and unsupported versions,
expired/restored input, wrong site/timezone, civil-noon field semantics,
missing actions, source unavailable at startup, first natural daily publication, issue-time consumer readback, and
no change in the existing forecast fallback or measured-weather authority.
Ten dated rows still expire at the next local midnight; they are not ten days
of permission to reuse an expired receipt.

### A02 Replace the browser season ephemeris

**Priority P1. Redundant calculation.**
`src/lib/ui/SeasonCountdown.svelte:3–9` calls `nextSeasonEvent`, implemented with
polynomial season/JD coefficients in `src/lib/ui/homeCardState.js:164–209`.
This is its only runtime caller. The existing `DaysUntilNextSeason` Item is not
consumed by `src`; its file-owned writer already reads `Sun_TimeLeft` and
`Sun_NextSeason` at `openhab/file-config/automation/js/update_days_until_season.js:9–18`.

On the snapshot date, both show 70 days. Their season instants differ: the UI
computes winter at `2026-12-21T20:53:51.117Z`; `Sun_Winter` reports
`2026-12-21T20:51:22.403571844Z`, **about 149 seconds earlier**. The benefit of
consolidation is one chosen authority, not a claim that either algorithm has
been independently established as the more accurate ephemeris.

**Task:** either consume the existing season display Item, or retain UI wording
using native season values. Decide day-count semantics first. In 5.2.3,
[Season.getTimeLeft](https://github.com/openhab/openhab-addons/blob/5.2.3/bundles/org.openhab.binding.astro/src/main/java/org/openhab/binding/astro/internal/model/Season.java)
returns a whole-day-truncated duration, while the UI counts browser-local calendar
dates and retains “today” for the event's calendar day. Native zero days is not
proof that the event is today. Current native season timestamp Items show the
current year's dates; native nextName/timeLeft cross the year boundary, but an
exact next-year event timestamp needs qualification. Never derive an exact
season instant by adding the truncated timeLeft to now.

The existing writer parses a numeric token as seconds and divides by 86400.
That matches the current `Sun_TimeLeft` state (`6048000 s`), but assumes units
and does not explicitly handle invalid input. It triggers only on timeLeft
changes while also reading next-season name; qualify rollover update ordering
so the display cannot combine a new countdown with an old season name. If
reused, improve the display adapter as part of the later task, not the native calculation.

**Acceptance:** NULL/UNDEF/stale states, seconds/days unit variants, wording and
singular/zero-day cases, season-instant versus calendar-day rollover,
December-to-next-year coverage, nextName/timeLeft update ordering,
browser UTC versus household Denver, DST and hemisphere policy. Remove the polynomial only after the replacement covers
those cases. Preserve existing Item identities and history.

### A03 Reuse the current native moon phase

**Priority P1. Redundant current calculation.**
Home's Sun and Moon tile already displays `MoonPhaseicon` and
`Moon_MoonPhaseName` (`src/screens/Home.svelte:445–447,779–786`). Current sky
icons on Home and Weather instead pass through `outdoorConditionIcon` and
`contextualSkyIcon`, which calls SunCalc's `getMoonIllumination` at night
(`Home.svelte:343–345`, `Weather.svelte:66–68`,
`src/lib/weather/celestial.js:1–16,31–38`).

**Task:** supply native current phase/icon to the shared current-condition
presentation path. Reuse the existing store/SSE hydration and `astro.map`; do
not add a separate browser ephemeris fetch. Preserve icon normalization and
condition distinctions: clear night uses a moon, partly cloudy uses its night
icon, and rain, snow, fog and storms keep their weather symbols.

**Acceptance:** all eight native phases, `THIRD_QUARTER` mapping to
`moon-last-quarter`, unavailable phase, valid versus stale daily sun context,
twilight/boundary policy, and both Home and Weather consumers.

### A04 Preserve future forecast lunar context

**Priority P2. Required capability gap.**
`HourlyStrip.svelte:171` and `WeatherDetailModal.svelte:292–296` pass each
forecast hour's `at` and `isDay` into `wmoIcon`. SunCalc supplies phase for that
hour's timestamp. The detailed snapshot contains 240 forecast hours, all with
boolean `isDay`; the legacy hourly snapshot has 14 rows, also all with booleans.
Daily rows intentionally omit that flag.

**Task:** after A03, retain SunCalc for forecast-hour timestamps unless a bounded,
date-specific lunar context supplier is introduced or generic forecast-night
icons are explicitly chosen. The installed public Astro action interface does
not provide future moon illumination. Do not apply today's `MoonPhaseicon` to
all ten forecast days or remove the dependency prematurely. SunCalc `2.0.2`
has one current source import, in `celestial.js`.

**Acceptance:** differing phases across the forecast horizon, a phase boundary
between current conditions and a later forecast hour on the same household day,
equivalent instants across UTC offsets, cross-midnight/DST hours, unavailable context,
provider `isDay` precedence, and unchanged whole-day forecast summaries.

### A05 Choose the daylight interval explicitly

**Priority P2. Behavior difference at a proposed replacement.**
`src/screens/Home.svelte:285–295,448` subtracts `Sun_Rise_Start` from
`Sun_Set_End`. Native daylight duration uses rise **end** to set **start**.

| October 12 interval | Seconds | Current rounding |
|---|---:|---|
| UI rise start to set end | 40862.510 | 11h 21m |
| Native daylight | 40533.905 | 11h 16m |
| Difference | 328.605 | 5m 28.605s |

**Task:** use `Sun_Daylight_Duration` if the product adopts native daylight
semantics; otherwise retain the explicitly defined outer-edge interval as
presentation. Reuse `splitRoundedMinutes` for display. `num()` strips units;
it does not convert seconds, minutes and hours.

**Acceptance:** the two snapshot intervals, supported quantity units,
invalid/zero/negative duration, rounding carry, and current-day event validation.
Do not substitute `Sun_Night_Duration` for sunset-to-next-sunrise: native NIGHT
runs from Astro dusk END to next Astro dawn START. Neither equals the thermal
horizon threshold or the battery's calibrated overnight scoring window.

### A06 Share household time formatting

**Priority P2. Inconsistent timezone ownership.**
`Home.svelte:262` formats sunrise/set using browser timezone;
`homeCardState.js:179–185` also uses browser-local dates for seasons. The same
sunrise becomes 07:10 in Denver and 13:10 in UTC. At
`2026-09-22T18:00:00Z`, the UI polynomial labels autumn “today” in Denver but
“1 day” away in UTC. Existing forecast parsing explicitly uses
`America/Denver` (`forecastDetail.js:135`), as does the temperature-history
calendar logic (`homeCardState.js:77–110`).

**Task:** reuse the household timezone policy for celestial labels and calendar
selection; keep user locale separate from site timezone. Preserve offset-bearing
instants and DST-aware boundaries. This is shared formatting, not new astronomy.

**Acceptance:** identical site labels on Denver/UTC browsers, both DST changes,
local midnight, equivalent offset representations and invalid timestamps.

### A07 Consolidate thermal solar geometry through a replayable adapter

**Priority P2. Genuine independent astronomy with model dependencies.**
`openhab/scripts/thermal_model/solar.py:33–64` implements a NOAA fractional-year
solar approximation using the same site coordinates as Astro. Native elevation
at explicit timestamps can supply that geometry, but today's elevation Item
cannot replace historical or future samples. The current Astro context has only
one civil-noon position per day and is insufficient for hourly thermal forcing.

The geometry contract is embedded in dataset reconstruction and artifact
validation (`thermal_model/dataset.py:82–87,205–212`,
`behavior.py:111–122`, `pipeline.py:252`, `artifacts.py:423`). The helper called
`is_astronomical_night` means elevation at or below **0 degrees**, not
astronomical darkness at minus 18 degrees. Replacing it with Astro NIGHT changes
training rows, missing-radiation treatment and behavior features.

**Task:** extend the shared observational adapter or provide a bounded geometry
cache for the exact historical/future timestamps required by models. Record
site, timezone, algorithm/binding version, requested instants and source digest.
Replay must work without live OpenHAB. Compare both geometries near the horizon,
then version/refit/revalidate affected datasets and model artifacts. Do not make
one synchronous binding call per historical row or change only the main source
while leaving staged deployed publishers on the previous contract.

**Acceptance:** historical/future coverage, DST/leap days, exact requested
instants, missing geometry, offline replay, horizon disagreements, artifact
compatibility, replay parity and prediction comparisons before promotion.
Consolidation reduces duplicated authority and maintenance; CPU savings are not
established, and repeated binding calls could make it slower.

### A08 Keep irradiance and sky inference as separate models

**Priority P2. Similar purpose does not mean equivalent output.**
Native radiation is already used by the sky-condition rule alongside measured
`AmbientWeatherWS2902A_SolarRadiation`, station health and age
(`openhab/file-config/automation/js/sky-condition-calculator.js:47–97`). Its
ratio thresholds classify observed sky conditions. Astro does not observe
clouds or replace that station's acquisition evidence.

The thermal model separately normalizes irradiance with
`1050 × sin(elevation)^1.15` and a bounded fraction up to 1.30
(`thermal_model/solar.py:12–14,72–98`); shade forcing consumes that fraction.
[Native RadiationCalc 5.2.3](https://github.com/openhab/openhab-addons/blob/5.2.3/bundles/org.openhab.binding.astro/src/main/java/org/openhab/binding/astro/internal/calc/RadiationCalc.java)
uses a different atmospheric reference and sets the incident reference to zero
at elevation at or below 3 degrees. Swapping normalization changes low-angle
behavior and the meaning of model coefficients. The configured site has latitude
and longitude only; qualify altitude and reference assumptions rather than
inventing an altitude.

**Task:** reuse Astro position first. Treat adoption of native radiation as a
separate model experiment with comparison/refitting. Keep actual station
radiation, forecast shortwave radiation, PV observations and evidence coverage
as independent source contracts.

**Acceptance:** low sun, missing/stale station data, zero denominator, bounded
fractions, cloud transients, model refit and measured-versus-calculated lineage.

### A09 Evaluate native circadian targets without removing the owner

**Priority P2. Available feature with deliberate behavior choices.**
Unlinked `astro:sun:local:circadian#temperature` and `circadian#brightness` are
present in the installed Thing. The
[CircadianCalc 5.2.3](https://github.com/openhab/openhab-addons/blob/5.2.3/bundles/org.openhab.binding.astro/src/main/java/org/openhab/binding/astro/internal/calc/CircadianCalc.java)
uses time relative to sunrise, sunset and solar transit; native temperature
ranges from 2500 to **5500 K**. The living-room policy instead uses
`2500 + round(clamp(elevation,0,50) × 80)`, potentially reaching **6500 K**,
and preserves existing brightness. Rescaling native temperature is not parity
with the existing seasonal elevation curve.

**Task:** if adopting native suggestions is desired, add separately owned
observational target Items, explicit Kelvin metadata/conversion, and a selected
policy mode. Continue routing decisions through `hex_living_room_circadian`.
Native brightness can reach zero and would introduce dimming/OFF behavior; it
is not an automatic efficiency cleanup.

Preserve fresh source/status checks, enable/OFF handling, raw TP-Link requests
that omit power/brightness, measured readback, hysteresis, backoff and recovery.
Do not bind an actuator Item directly to both Astro and TP-Link or replace the
verified owner with an unconditional relay. The six-line target arithmetic is
cheap; device I/O and safety semantics dominate this path.

**Acceptance:** explicit choice of target curve and brightness policy, typed
Kelvin, missing source, midnight/sunrise/transit/sunset, winter/summer comparisons,
manual OFF and enablement races, and all existing lighting regressions.

### A10 Simplify pre dusk scheduling while retaining retry semantics

**Priority P3. Native event opportunity.**
Deployed `forecast_pre_dusk.py:119–131` already reads `Sun_Set_Start`, requires
that day's event and a 60–90 minute lead, and rechecks after I/O. Its user timer
polls `14..20:02/10:45 America/Denver` to allow repeated opportunities around
native-input lock contention.

**Task:** consider an isolated sunset event with a negative offset to begin the
issue attempt, followed by bounded retries/catch-up. Preserve the script's
same-day idempotency, issue window, atomic SoC, freshness and original sunset
receipt. Do not add an offset to the shared `set#start` channel: other readers
need its unshifted astronomical sunset. Check exact trigger-channel configuration
scope before introducing an isolated event or scheduling from a native timestamp.

**Acceptance:** contention, restart/catch-up, sunset changes, missed trigger,
window expiration, duplicate opportunities and stable unshifted sunset inputs.
Keep the canonical 20:00-to-next-day-11:00 trough
(`advisory_windows.py:49–55`) and other calibrated load intervals unchanged.

### A11 Keep protected control daylight gates explicit

**Priority P1 for a separate protected-control review. Source-derived risk.**
Live `hex_southoutlet_cycle` matches
`openhab/rules/southoutlet-cycle-current.js`. Its curfew at lines 511–520 checks
only finite positive `Sun_Position_Elevation`. A held/restored positive value
can therefore continue passing that gate if Astro stops updating; this is an
inference from the source, not a fault injected into equipment.

The fan's `daylight()` uses elevation freshness plus daily event bounds
(`/etc/openhab/automation/js/south-planter-fan.js:48–64`), and the lighting owner
checks Astro ONLINE plus update age (`living-room-circadian.js:26–37`). A native
channel does not replace those authorization checks. Both native update-time
properties used by these rules exist in the installed JS library.

**Task:** review and qualify the pump daylight freshness/bounds separately from
UI consolidation. Preserve BMS/voltage gates, hydrological timings, alternation,
manual-request semantics and fail-closed OFF behavior. Follow the existing
protected-control restore/rollback requirements in `/etc/openhab/AGENTS.md`.

**Acceptance:** restored positive elevation, Astro OFFLINE, stale timestamp,
wrong-day bounds, crossing the curfew while running, manual and automatic paths,
plus original SoC, voltage, comms and pump-timing regressions. Use an isolated
harness before any attended control change.

## Shared implementation contracts

Use three explicit layers:

1. **Astronomy:** native current Items and a shared versioned adapter for
   requested future/historical instants. Reuse the current provider and stable
   source IDs. Add only genuinely missing channels or adapter outputs.
2. **Interpretation:** formatting, weather classification, circadian policy,
   thermal/PV models and calibrated forecast windows. They can consume native
   geometry without becoming part of Astro.
3. **Execution and evidence:** qualified physical telemetry, decision gates,
   command ownership, hardware readback and source-bound receipts. Calculated
   astronomy must never qualify freshness or coverage of weather, BMS or loads.

Every shared adapter should declare timezone, coordinates and optional altitude,
units, event endpoint meanings, requested instants/date coverage, schema and
calculation version, availability/expiry, and digest/provenance. Keep computed
geometry distinct from measured observations. Prefer a bounded batch cache to
independent browser or service calculations and per-row live RPCs.

An Item's update timestamp describes its registry update, not by itself proof of
hardware acquisition. Static daily event timestamps and continuously changing
position data have different freshness needs. Validate today's event interval
and source health rather than applying a two-minute position TTL blindly to a
once-daily sunrise date. Never use today's event or moon phase for an unrelated
forecast date. Preserve native seconds/days/Kelvin and explicit conversions.

The existing Item store (`src/lib/openhab/store.js:42–55,92`) already hydrates
and updates native values. Share parsers/presentation through that path rather
than introducing another browser polling subsystem. Native Astro events may
reduce display scheduling polls, but control watchdogs and retry loops have
separate reasons to exist.

## Deployment targets for later coding agents

| Component | Actual runtime location | Consequence |
|---|---|---|
| Astro future context | `/etc/openhab/automation/js/astro-forecast-context.js`; canonical `openhab/file-config/automation/js/astro-forecast-context.js` | File-owned; edit canonical source and use its qualified deployment path |
| Season display and sky classification | File-owned rules under `/etc/openhab/automation/js` | Keep one provider; staged comments are not ownership evidence |
| Living-room owner | Managed `hex_living_room_circadian`; canonical `openhab/rules/living-room-circadian.js` | Use the existing renderer/REST source contract; no file duplicate |
| Forecast and pre-dusk | `/home/sat/openhab/scripts/forecast_intel.py`, `forecast_pre_dusk.py` | Resolved user systemd services run deployed copies |
| Thermal training | `/home/sat/openhab/scripts/thermal_intel.py train` | Existing reconstruction/artifact contracts apply |
| Thermal shadow | Private `legacy-shadow-runtime-e738cdf/sources/thermal_legacy_observe.py` override | Main source alone is not the installed publisher |
| Provisional thermal forecast | `.worktrees/household-observability-20261011/.superpowers/sdd/2026-10-12-household-common-cycle/stage-1e25f33/sources/openhab/scripts/household_cycle.py` override | Resolve the current stage and configuration before changing deployment |

Verified source hashes at audit time:

| Source | SHA256 | Runtime comparison |
|---|---|---|
| Astro context JS | `f8f78077a802934754cb171e86dba3fff02b313cab7632ae02463bf733b8d3d4` | Canonical source equals installed file |
| Context validator Python | `c65f647befed00c9a00922583544ecb0a8675624f218ed3ff69b1ea63427ac04` | Canonical source equals deployed file |
| Thermal solar helper | `abb5f8d1db8eeb31cc42d4110582f249e35d7628e0ce05dbbb5920c9ca50c08d` | Main, legacy deployed helper and current household stage match |
| Main forecast script | `1b902853bc155b404bc18dc352545ea214632de4053ff295f8683e31574c5d1b` | Different from deployed script |
| Deployed forecast script | `c52016bfe65ba23198a6e290cd7c3793e3031f5283428d6ecf1a7442c7718328` | Actual forecast service target |
| Pump owner | `4c34780e544d80af8eb36d047a949fa30e0198bb50fa57650285052db3c52d9b` | Current canonical source equals live rule script |
| Lighting owner | `d6801133884735e94b998721a2dbf2d4f78d1e22570c57fcae6b21f7b56fc48e` | Canonical source equals live rule script |

## Coding order and completion evidence

Start with A01 so the existing shared future context works again. A02, A03 and
A06 can then be separate UI tasks sharing typed site-time/quantity adapters.
Resolve A05's daylight meaning before changing its display. A04 controls whether
SunCalc can eventually be removed. A07/A08 require versioned model experiments;
A09 requires a behavior choice, not an automatic replacement. A10 is lower
priority scheduling cleanup. Keep A11 on its own protected-control track.

Each implementation should inventory its exact provider/consumers first, keep
stable identities and history, test the named acceptance cases, compare native
output with the intended semantics, verify the deployed artifact and natural
writer, and record rollback. Removing a calculation is complete only when all
its current and future-date consumers use an accepted replacement. An expired
receipt, green rule status or source file alone does not establish live delivery.

The source-only solar-ablation and sunset-profile experiments are not production
solar suppliers. Preserve cyclic statistical date features, precipitation/cloud
forecasts, thermal dynamics, learned gains, irradiance observations and battery
coverage; none is replaced by astronomical timing alone.

This updates the current-state conclusions in the
[September Astro forecast audit](2026-09-30-astro-forecast-input-audit.md).
The [October lighting audit](2026-10-12-living-room-circadian-audit.md) remains
the evidence for the implemented TP-Link owner and its hardware behavior.
Read-only validation for this report used current source inspection, registry
GETs, resolved service definitions, pinned binding source and pure date/geometry
calculations. It did not run rules or command equipment.

Final read-only verification matched all 1199 pre-existing worktree files and
kept Git HEAD unchanged. All 42 rule definitions, 446 Item descriptors, 268
links and 83 Thing configurations matched the captured registry. Only this
report and the companion CSV were added. The CSV covers every captured Item
exactly once, including all 55 native Astro links. Telemetry may continue to
update naturally; this audit did not fabricate or command it.
