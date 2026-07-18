# Earthship UI Tablet Audit and Remediation Design

**Date:** 2026-07-17
**Status:** Approved design; implementation pending
**Primary target:** Lenovo Tab M9 (2023), landscape
**Secondary target:** Full-screen laptop browsers at 1280×720 or larger

## 1. Objective

Audit and repair the complete Earthship household console so that all five
routes are reliable, legible, safe, and fully visible without scrolling on the
actual Lenovo Tab M9 landscape browser viewport and on full-screen laptops at
or above 1280×720.

This is not only a CSS pass. The UI depends on openHAB item types, links, Thing
configuration, and rules. Those integrations are part of the repair whenever
the current openHAB behavior prevents the UI from presenting truthful state or
issuing safe commands.

The finished console must:

- fit every route inside one viewport with no page, panel, or card scrolling;
- keep all required content inside its card, including the Home outdoor
  temperature chart;
- make chart period selection work for 4 h, 24 h, 7 d, and 30 d;
- scale charts and the wind compass from their actual parent dimensions;
- smooth only noisy chart lines while retaining raw values for tooltips;
- distinguish live, stale, offline, unavailable, pending, and failed states;
- expose only controls whose behavior matches their label and ownership model;
- preserve openHAB rules as the authority for safety-gated equipment;
- show current air quality from a numeric current-AQI item;
- orient the Earthship diagram with North Mass on the left and South Glazing on
  the right;
- remove Bitcoin from the header and remove its Home-card sparkline; and
- use the reclaimed header space for a bounded alert summary.

## 2. Scope and Acceptance Targets

### 2.1 In scope

- `Home`, `Energy`, `Weather`, `Earthship`, and `Controls`.
- Shared shell, header, navigation, tiles, charts, chart modal, compass, value
  formatting, data stores, openHAB client, and dimming.
- Related openHAB items, links, Thing settings, and rules needed for AQI,
  feeder, greywater/fountain, override policy, circadian status, and physical
  control confirmation.
- Performance work required to keep the M9 responsive.
- Automated and real-device verification at the two approved target classes.

### 2.2 Explicitly out of scope

- Phone-specific layouts.
- Portrait tablet layouts.
- Split-screen layouts.
- PWA/service-worker and offline-snapshot packaging.
- nginx, Caddy, HTTPS certificate management, immutable release directories,
  or any second UI server.
- A generic matrix of arbitrary mobile or tablet resolutions.
- Remote access, authentication redesign, camera UI, voice control, and new
  analytics beyond the existing console charts.
- Redesigning the chart visual language; the current chart/component aesthetic
  remains.

### 2.3 Target geometry

The Tab M9 panel is nominally 1340×800, but hardware pixels must not be treated
as CSS viewport pixels. Before geometry work begins, the installed browser and
browser mode on the actual tablet will record:

- `window.innerWidth`;
- `window.innerHeight`;
- `window.devicePixelRatio`;
- safe-area or browser-chrome deductions.

Recording these values is a blocking first implementation step: no route-grid
CSS is changed until the measurements are committed to the audit matrix.
Playwright mirrors the exact browser CSS dimensions and device scale factor.

The laptop contract begins at 1280×720 CSS pixels in a full-screen browser.
Automated laptop geometry tests run at that lower bound. Layout rules must
remain fluid above the lower bound, but no arbitrary resolution matrix will be
created.

At every canonical target:

- `documentElement.scrollWidth <= documentElement.clientWidth`;
- `documentElement.scrollHeight <= documentElement.clientHeight`;
- the application main region has no scrollable overflow;
- every card is fully inside the main region;
- no card requires internal scrolling;
- all required text and controls remain visible in live, unavailable, stale,
  offline, pending, failed, outcome-unknown, and long-message fixtures; and
- interactive targets are at least 44×44 CSS pixels.

Clipping may be used as a final paint guard for chart canvases, but it must not
hide required text, values, controls, legends, or status.

## 3. Audited Baseline and Root Causes

The audit found cross-cutting causes rather than isolated visual defects:

| Area | Current fault | Required correction |
| --- | --- | --- |
| Shell | A fixed header plus a second connection banner consumes scarce height and can change layout | Keep status in the fixed header alert region; remove the extra banner row |
| Route layouts | Fixed tracks and fixed chart heights collapse or extend below the fold | Use route-specific compact grids whose tracks resolve from available height |
| Card containment | Several flex/grid children lack `min-width: 0` or `min-height: 0`; chart canvases can retain stale dimensions | Make every sizing boundary shrinkable and parent-driven |
| Home outdoor card | The outdoor temperature sparkline/chart extends beyond the card | Give it a measured content box, resize with the card, and assert its bounds |
| Wind | The compass is capped at roughly 4.6 rem and gust content overlaps | Allocate the largest available square and scale all internal geometry together |
| Chart periods | Modal state synchronization overwrites 7 d and 30 d selections back to 24 h | Give the picker one authoritative period state and one cancellable request |
| Dense history | A 30 d request can return hundreds of thousands of points and stall the main thread | Normalize and downsample before rendering; move dense processing off-thread |
| Values | Numeric parsing accepts malformed strings and can misread scientific notation; duration formatting can emit `1 h 60 m` | Use strict parsers and normalized time arithmetic |
| Rain history | Persisted rain series may contain mixed or contaminated units | Validate units at ingestion, reject incompatible rows, and never join unlike units into one line |
| Connectivity | Global SSE traffic masks per-item staleness, while keepalive events are ignored for transport health | Track transport health and item freshness independently |
| Bootstrap | Cache, initial REST snapshot, and SSE updates can race and overwrite newer state | Buffer live events and merge by timestamps |
| Unknown state | `NULL`, `UNDEF`, missing, or malformed data is shown as plausible zero/OFF/Idle/Fault state | Use a tri-state value model and render unavailable explicitly |
| Controls | A generic toggle conflates binary switches, actions, requests, policy, and read-only actuators | Replace it with typed control primitives and explicit acknowledgements |
| AQI | `Forecast_AQI` is a String linked to an hourly string channel and currently reads `REFRESH`; the UI expects a number | Add and consume a numeric current-AQI item while keeping forecast data separate |
| Earthship | South glazing is drawn on the left and North mass on the right | Reverse the nodes and rebind the heat-flow geometry |
| Bitcoin | BTC history is fetched for a card sparkline and the ticker occupies header space | Keep only price and 24 h change in the Home card; use the header for alerts |
| Accessibility | Modal focus, Escape handling, picker semantics, keyboard holds, and chart descriptions are incomplete | Implement keyboard, focus, and ARIA behavior as part of each primitive |
| Bundle/runtime | Full ECharts and icon libraries are imported; chart work can block the M9 | Use modular imports, bounded point counts, and off-main-thread preprocessing |
| PWA | Offline shell/snapshot and automatic dimming are incomplete | Cache the shell and a read-only aged snapshot; disable all offline commands |

These findings are the starting inventory, not a ceiling. Implementation will
maintain one canonical audit matrix and append any additional reproducible
defect discovered while exercising the five routes.

## 4. Application Layout

### 4.1 Shell

The shell owns the full viewport:

```text
viewport
├── fixed compact navigation rail
└── application column
    ├── fixed 44 px header
    └── one bounded route surface
```

The root uses `height: 100dvh` with a `100vh` fallback and `overflow: hidden`.
Every grid/flex boundary between the root and a chart includes
`min-width: 0` and `min-height: 0`. The route surface receives the remaining
height and cannot grow the document.

The M9 uses a 52 px compact landscape rail containing 44×44 targets and 4 px
route padding/gaps. Laptops use a 60 px rail with 44×44 targets and 8 px route
padding/gaps. Breakpoints are based on the two measured M9 CSS viewports and
the 1280×720 laptop floor, not on generic phone breakpoints. Existing
phone/bottom-tab CSS may remain dormant but receives no new work or acceptance
coverage.

Navigation exposes the active route with `aria-current`, has visible keyboard
focus, and uses accessible names in addition to icon shape. Cards that open
detail views use native buttons/links where possible and support Enter and
Space without duplicate activation.

### 4.2 Tile sizing contract

`Tile` and all tile-like components will:

- fill the grid area assigned by the route;
- expose a bounded header and a `min-height: 0` content region;
- allow children to shrink;
- reserve predictable space for labels, legends, and error messages;
- use container-aware typography and spacing tokens for the two targets; and
- never create their own scrollbar.

Required content is reorganized or compacted before font sizes are reduced.
Ellipsis is permitted only for supplemental narrative whose full text remains
available through an accessible label or detail view.

### 4.3 Route-specific composition

Each route gets its own layout rather than sharing one fixed card grid. Every
required route row uses a bounded `minmax(0, <fraction>fr)` track; required
cards never occupy a content-sized `auto` row:

- **Home:** dense instrument grid; Outdoor and Battery remain hero cards;
  Wind receives a square compass area; the Bitcoin card becomes a compact
  price/change summary; the forecast and Earthship zone information use the
  full width assigned by the current route. The outdoor chart must occupy only
  its card's remaining content height.
- **Energy:** chart rows divide the available height rather than requesting
  fixed 200/160 px canvases. Vitals and forecast summaries use compact side
  columns at the laptop floor and bounded strips on the M9.
- **Weather:** current conditions, hourly chart, daily forecast, measured
  tiles, and AQI share the fixed route height. Forecast rows compact
  vertically instead of flowing below the viewport.
- **Earthship:** the thermal loop is the primary bounded panel; advisories,
  greywater, and humidity occupy fixed companion regions. Long status text
  wraps only within an allocated line budget.
- **Controls:** control groups use a landscape board sized to the route.
  Action, policy, status, and binary controls remain visually distinct and do
  not force a lower card off-screen.

Route geometry is validated with both normal data and worst-case content
fixtures. A screenshot looking correct is not enough if DOM measurements
report hidden overflow.

### 4.4 Required content and row budgets

The following content is required at both targets and cannot be deleted to
obtain a no-scroll result:

- **Home:** advisory-or-Power Flow, Greywater, Outdoor temperature/condition/
  feels-like/humidity/high-low/AQI/inline temperature trend, Indoor
  temperature/humidity/high-low, Battery SoC/current/direction/runtime/basis/
  trend, Bitcoin price/24 h change, Wind compass/speed/gust/daily max, Baro
  pressure/trend, Rain day total/footer, Sun & Moon, Solar actual/predicted/
  current/curtailment, three Zones, and seven-day Forecast with high/low and PV.
- **Energy:** Battery history plus predicted trough and current SoC; Solar PV
  actual/predicted/accuracy plus history; Runtime and basis; Curtailment value
  and bar; seven-day PV outlook; and Battery Vitals for temperature, cycles,
  capacity, communications, and device presence.
- **Weather:** Current Conditions, numeric current AQI, 14-hour strip,
  seven-day forecast with high/low/precipitation/PV, and measured Wind, Rain,
  and Pressure.
- **Earthship:** Thermal Advisory and tomorrow high/low, the full three-node
  thermal loop, Thermal Mass detail, Thermal Buffering, Greywater status and
  last cycle, and North/Room/South humidity.
- **Controls:** Lights, Appliances & Outlets, Water & Policy, correlated action
  results, circadian health, and read-only feeder/greywater actuator status.

After subtracting the 44 px header, rail, route padding, and gaps, the M9 route
height is allocated with these normalized rows:

| Route | Bounded row template | Required placement |
| --- | --- | --- |
| Home | `0.38fr 1.2fr 1.0fr 0.9fr 0.72fr` | status strip; hero row; hero companion row; compact instruments; forecast |
| Energy | `1.25fr 0.9fr 0.55fr 0.55fr` | battery; PV/runtime/curtailment; outlook; vitals |
| Weather | `0.75fr 1.05fr 1.2fr 0.55fr` | current/AQI; hourly; seven-day rows; measured tiles |
| Earthship | `0.55fr 1.65fr 0.9fr` | advisory; loop plus analytic companions; greywater/humidity |
| Controls | `1fr 1fr 1fr` | lights; appliances/actions; water/policy/status |

The implementation may tune fractions after the two real M9 measurements, but
it may not add an `auto` row, a scrollbar, or remove required content. Any
fraction change is accompanied by geometry evidence in the audit matrix.

Core labels, current values, units, states, and denial/error reasons are
required text. Supplemental narrative has these deterministic visible budgets:

- header alert: one line, ellipsized after the available width;
- Home/Earthship advisory: two lines, up to 96 fixture characters;
- `SouthOutlet_AutoStatus` or correlated rule result: one line, up to 64
  fixture characters;
- control failure/denial: two lines, up to 96 fixture characters; and
- all other captions: one line, up to 48 fixture characters.

Ellipsized text is available in the alert/detail view and accessible name. It
does not expand the card. The separate Thermal Mass companion is an analytic
detail card, not part of the left-to-right physical diagram, and must be styled
so its placement cannot be read as a fourth spatial node.

### 4.5 Home distance-readability hierarchy

Home uses a target-specific typography hierarchy for legibility across the
room:

- the primary Outdoor and Indoor temperature numerals are pure white
  (`#ffffff`) against the near-black tile background; amber remains the
  temperature tile accent and chart-line color;
- Indoor's primary temperature is at least 2.4 rem on both M9 modes and
  2.6 rem at the laptop floor, while its humidity/high-low metadata is at
  least 0.85 rem;
- only the Home Rain card receives a scoped reduction from the shared
  `StatTile` sizing: its primary value is 2.15 rem and its footer is 0.72 rem,
  so the value, unit, and full footer remain visible;
- Sun & Moon rows target 0.82 rem on the M9 and 0.86 rem at the laptop floor.
  If 0.82 rem fails canonical M9 geometry, spacing is reduced first; the
  recorded fallback may not be smaller than 0.8 rem.

These changes do not alter Weather/Earthship typography or the shared
`StatTile` default. Automated checks assert the computed colors/font sizes and
card containment. Real-M9 sign-off includes reading Outdoor, Indoor, Rain, and
Sun & Moon from the normal household viewing distance.

## 5. Header and Alerts

`BtcTicker` is removed from the shell and is not used as a fallback header
element. The former connection banner is also removed.

The header retains the clock/date and connection affordance, then gives the
remaining single-line region to an alert summary:

```ts
type ConsoleAlert = {
  id: string;
  severity: 'critical' | 'warning' | 'advisory' | 'info';
  shortText: string;
  fullText: string;
  route: 'home' | 'energy' | 'weather' | 'earthship' | 'controls' | null;
  dedupeKey: string;
};
```

Alert priority is:

1. openHAB offline;
2. critical BMS communication or battery alarm;
3. stale essential telemetry;
4. `close_up_tomorrow` thermal warning;
5. predicted SoC trough below 40% (critical at or below 12%);
6. unhealthy AQI;
7. `vent_tonight` thermal advisory; and
8. failed, unconfirmed, or outcome-unknown control action.

Alert sources are limited to explicit contracts: connection state;
`BMS_Comms_Status`, `BMS_DevicePresent`, current SoC at or below 12%, existing
rule-produced battery alarms, `Thermal_Advisory`, predicted SoC trough, current
US AQI at 101 or above, and correlated control outcomes. Thermal code
`close_up_tomorrow` maps to warning, `vent_tonight` to advisory, `none` to
no alert, and an unknown non-empty code to warning plus a diagnostics entry.
The client does not invent voltage/current thresholds. Routine curtailment is
tile-local and does not enter the header.

Equivalent connection, battery, thermal, AQI, or control alerts are deduplicated
by `dedupeKey`. Ties resolve by severity, the fixed priority list above, newest
transition time, then stable `id`. Alerts are deterministic projections: state alerts clear with their source;
control-outcome alerts are replaced by the next outcome for that control and
expire after 15 minutes. They cannot be dismissed or persisted. The connection
lamp remains icon-only; connection text appears only in the deduplicated
alert. The header shows the winner plus `+N`; activating the winner
navigates when `route` is non-null, while a global alert or `+N` opens the
compact full list. Closing the list does not acknowledge an alert.

The alert never wraps, rotates automatically, or changes the 44 px header
height. When no alert is active, the region is visually blank and exposes the
accessible status `No active alerts`. The full alert text is available to
assistive technology. Routine transitions use `aria-live="polite"`; only new
offline or critical states use assertive announcement.

## 6. Chart System

### 6.1 One shared history pipeline

Inline history charts, Home sparklines, and `ChartModal` use the same data
pipeline. One chart request generation captures a single `now`, owns one
`AbortController` and timeout, and may contain one openHAB persistence fetch
per configured series. All series therefore share identical time boundaries.
The generation:

1. validates every item, series policy, and requested period;
2. fetches its N series with bounded concurrency and the shared cancellation;
3. retains original response order long enough to resolve duplicate timestamps
   by last occurrence, then sorts;
4. discards invalid timestamps, unavailable/non-numeric values, and rows with
   incompatible units;
5. segments data at gaps defined by that series policy;
6. pairs every retained display point with its nearest raw source sample;
7. optionally smooths only the display series;
8. downsamples to the measured plot width; and
9. commits only if the request generation is still current.

The supported history periods are exactly 4 h, 24 h, 7 d (168 h), and 30 d
(720 h). A history series requests the inclusive interval
`[now - selectedHours, now]`. A forecast series declares an independent
`lookaheadHours` and requests `[now, now + lookaheadHours]`; forecast
lookahead is not silently changed by the history picker. A mixed chart labels
both domains, for example `7 d history + tonight forecast`. The Energy battery
title becomes period-neutral and shows the selected range in its picker/legend
rather than hard-coding `24h`.

Opening a modal seeds its selected period once. Close/reopen seeds from the
card's configured initial period again. Reactive effects cannot copy that
initial value back over a user choice. A new selection, modal close, route
change, or superseding resize aborts the old generation and clears its loading
or error result.

A multi-series chart renders surviving series when at least one succeeds and
shows a non-blocking `N series unavailable` warning. It becomes a full error
only when every required series fails. Loading, no-data, timed-out,
superseded, partial-provider-error, and full-provider-error states are distinct;
a stale prior chart cannot masquerade as the newly selected period.

Each series policy declares its expected cadence and maximum gap. A gap starts
when adjacent samples differ by more than three expected cadences. If cadence
is not configured, it is inferred once from the median positive interval and
recorded in diagnostics; no tooltip, smoothing operation, or line segment may
cross that boundary.

### 6.2 Smoothing

Smoothing applies to chart lines only and never changes cards, control logic,
alerts, thresholds, or tooltip values. ECharts interpolation smoothing remains
disabled so the pipeline is the only smoothing layer.

The initial registry enables smoothing only for:

- outdoor, indoor, and Earthship-zone temperatures;
- barometric pressure;
- sustained wind speed, but not gust or maximum values; and
- the non-operational overview line for `MPPT60_PV_Power`.

It is disabled for battery SoC, battery/current safety steps, wind gusts,
switches, accumulated rain, curtailment transitions, discrete modes,
forecasts, control/status data, and any operationally meaningful step series.
Adding another item requires an explicit registry entry and test.

Inside each continuous segment, zero-, one-, and two-point segments are left
unchanged. For longer segments:

1. keep the first and last raw samples as median-stage endpoints;
2. replace each interior value with the numeric median of previous/current/next;
3. initialize EMA output from the first median-stage value; and
4. calculate subsequent values as
   `0.25 * current + 0.75 * previousEma`.

Every display point carries the timestamp/value of its selected raw source
sample. Tooltips show that raw pair, never the smoothed value, and refuse a
match farther away than the series maximum-gap policy.

### 6.3 Downsampling, memory, and responsiveness

For a plot width `W` CSS pixels, one series may contribute at most
`floor(2W)` points and the complete chart may contribute at most
`floor(4W)` points. Multi-series charts allocate the total budget evenly,
then distribute unused capacity by remaining sample count. Each segment keeps
its first/last point and chronological display minimum/maximum per bucket.
Equal extrema keep the earliest occurrence. If mandatory segment endpoints
alone exceed the allocated hard cap, the series reports
`data too fragmented for this range` instead of exceeding the budget.

Persistence reads use pages of at most 5,000 rows and reject an individual
decoded page above 5 MiB or a series above 300,000 raw rows. Each page is
validated and packed into numeric typed arrays, transferred to the worker, and
released on the main thread. The worker incrementally maintains segment,
filter, raw-tooltip, and extrema state; the full dense object graph is never
copied into ECharts. Exceeding a cap produces a range-specific error and
suggests a shorter period rather than freezing or crashing the console.

Normalization, smoothing, and downsampling run in a Web Worker for dense
series. Short series use the same pure functions on the main thread. Worker
crash, timeout, cancellation, and stale completion have explicit outcomes.
Request generation checks prevent old results from committing.

A debounced material width change (at least 8 CSS pixels after 100 ms)
re-downsamples retained worker aggregates and calls `resize` without
refetching. A zero-sized plot waits for a positive measurement.

Real-M9 budgets are:

- no chart-preprocessing main-thread task longer than 50 ms;
- chart-loading input response at or below 100 ms at the 95th percentile;
- a capped 30 d worker result within 3 s after its final persistence page;
- no more than 64 MiB incremental heap for one open 30 d chart;
- no more than `floor(4W)` total rendered points; and
- at most 1 MiB gzip of initial JavaScript, with no full-library ECharts or icon
  import.

ECharts and icons are imported by required modules only.

### 6.4 Parent-driven geometry

All charts use a `ResizeObserver` on their immediate content box. Width and
height props become optional constraints rather than fixed canvas sizes.
Observers and chart instances are disposed on unmount.

The Home Outdoor card contains two separate chart surfaces:

- an inline, fixed-24 h temperature sparkline with no period picker; and
- the full `ChartModal`, opened from the card, with all four periods.

With populated history, the inline plot is at least 120×44 CSS pixels on the
M9 and 160×64 on laptops, has a visibly rendered line, and consumes only the
height left below current/high/low content. Its wrapper, canvas/SVG, and backing
store all remain inside the card after mount, route navigation, browser/PWA
mode restoration, and resize. The full modal is tested independently for period
changes. A zero-height or fully clipped plot does not satisfy containment.

`overflow: clip` or `hidden` on the chart paint box is a final guard, not the
primary sizing mechanism, and cannot hide required card content.

### 6.5 Modal and accessibility

`ChartModal`:

- traps focus while open;
- moves initial focus to the close button or active period;
- closes on Escape and overlay activation;
- returns focus to the card that opened it;
- exposes the active period with `aria-pressed` or equivalent semantics;
- provides a concise text description of series, period, state, and most recent
  value; and
- uses 44×44 minimum close and period targets.

Tooltip content is created through safe text/DOM APIs or escaped formatting;
openHAB labels and values are never injected as unchecked HTML.

## 7. Wind Compass

The current small fixed cap is removed. `CompassRose` receives a square box
computed from the smaller of the card's available content width and height.
The observer-driven size controls:

- SVG view box and rendered dimensions;
- compass ring and cardinal-label radius;
- needle length and stroke;
- speed numeral and unit scale;
- center hub; and
- spacing to gust/max rows.

Gust and daily maximum move into dedicated, non-overlapping rows outside the
needle's square when necessary. The compass remains centered and legible at
both canonical targets. Geometry tests assert that the rose uses the expected
available size, remains square, and does not intersect gust/max text.

## 8. Truthful State and Offline Behavior

### 8.1 Bootstrap and transport

Startup follows one ordered merge:

1. load the last local read-only snapshot and mark it cached;
2. open SSE and buffer item events;
3. fetch the REST item snapshot with an abortable timeout;
4. merge REST and buffered SSE values by source timestamp/arrival generation;
5. publish the reconciled state; and
6. continue live SSE processing.

Reconnect repeats a REST reconciliation so missed events cannot leave
indefinitely stale values.

All SSE traffic, including `ALIVE` keepalives, updates transport health.
Per-item timestamps separately determine item freshness. A busy stream from one
sensor cannot make a silent critical item appear fresh.

Essential item freshness policies are declared centrally. They may vary by
source cadence, but every tile receives the same value envelope:

```ts
type ItemValue<T> =
  | {
      kind: 'value';
      value: T;
      updatedAt: number;
      freshness: 'live' | 'stale' | 'cached';
    }
  | {
      kind: 'unavailable';
      reason: 'missing' | 'NULL' | 'UNDEF' | 'invalid' | 'timed-out';
      updatedAt?: number;
    };
```

Unknown values display an em dash and an unavailable/stale treatment. They do
not become zero, OFF, Idle, or Fault unless the source explicitly reported that
state.

Freshness is semantic. Telemetry uses its expected update cadence. A stable
binary switch does not become stale merely because it has not changed; it
remains trustworthy while its Thing/channel is ONLINE and the SSE/REST
transport is healthy. A provider or Thing health loss makes that switch
unavailable.

### 8.2 Parsing

Numeric parsing uses an anchored grammar that supports sign, decimals, and
scientific notation, followed only by an allowed unit suffix. It rejects
embedded digits or arbitrary trailing text. Unit conversion is explicit per
item rather than inferred from any number-like substring.

Runtime/duration formatting performs carries before output, so 60 minutes
becomes one additional hour. Invalid or negative durations render unavailable
unless a specific domain contract defines them.

Persistence rows are checked against the series' declared unit. Compatible
units are normalized explicitly; incompatible or unitless-contaminated rain
rows are rejected and counted in diagnostics rather than connected into the
same line.

### 8.3 Fetch lifecycle

Config, snapshot, history, and command requests have bounded timeouts and
abort signals. Superseded requests are silent; real failures populate the
appropriate tile, chart, header alert, or control error. No rejected promise is
left unhandled.

### 8.4 PWA and offline mode

The service worker caches the static application shell. The item snapshot is
stored separately with its capture time and is always labeled cached when used.
Offline charts show cached data only when the period and item are known;
otherwise they show unavailable.

All controls are disabled while transport is offline or their required state is
unavailable/stale. No command is queued for later replay.

Automatic dimming uses the existing astro solar-elevation/sun-phase data, with
measured solar radiation as a supplemental input when available. Hysteresis
prevents flapping near the threshold. Dimming changes palette intensity only;
it cannot reduce contrast below legibility or hide alerts.

## 9. Air Quality

The current `Forecast_AQI` path is not a valid current-AQI source:

- it is a String item;
- it is linked to the hourly `us-aqi-as-string` forecast channel;
- its observed state is `REFRESH`; and
- the UI parses it as a number.

The source is the Open-Meteo air-quality Thing
`openmeteo:air-quality:local:aq`, not the general weather Thing. Its
configuration enables current data and numeric air-quality indicators. The
implementation waits for the Thing to be ONLINE and for its dynamic channel
`openmeteo:air-quality:local:aq:current#us-aqi` to exist before creating the
link.

A new Number item `Current_US_AQI` links to that exact current channel. Home,
Weather, and alerts consume only `Current_US_AQI` for the current scalar.
`Forecast_AQI` is retained only as the hourly categorical forecast series:
all commands to it are removed, its optimistic `REFRESH` contamination is
cleared by the supported unlink/relink or provider refresh sequence, and it is
never parsed as current AQI.

The shared adapter rounds a non-negative provider value to the nearest integer
before classification:

| Rounded US AQI | Band | Console treatment |
| ---: | --- | --- |
| 0–50 | Good | green |
| 51–100 | Moderate | yellow |
| 101–150 | Unhealthy for sensitive groups | orange |
| 151–200 | Unhealthy | red |
| 201–300 | Very unhealthy | purple |
| 301–500 | Hazardous | maroon |
| Above 500 | Beyond AQI / hazardous | critical maroon |

Malformed, non-numeric, or negative values render unavailable; extreme positive
values never disappear into unavailable. Because the provider cadence is 60
minutes, a current value is live through 75 minutes, stale from more than 75
through 150 minutes, and unavailable after 150 minutes unless shown explicitly
as an aged offline snapshot. The UI labels the source `Modeled US AQI` and
alerts at 101 or above.

Verification waits for the Thing, channel, Number item, and link; then requires
a numeric openHAB state, an event timestamp, correct freshness, and correct Home
and Weather mapping. Boundary tests cover -1, malformed, 0, 50, 51, 100, 101,
150, 151, 200, 201, 300, 301, 500, and 501. A direct upstream API response may
aid diagnosis but is not proof that openHAB and the UI are repaired.

## 10. Earthship Thermal Diagram

The horizontal physical model is:

```text
North Mass  ⇄  Room Air  ⇄  South Glazing
left            center            right
```

DOM, SVG, chart-legend, humidity, and keyboard order are always North Mass,
Room Air, South Glazing. Heat-flow physics use these exact rules:

- left corridor delta is `mass - room`; positive points right
  (North Mass → Room Air), negative points left, zero shows a neutral connector;
- right corridor delta is `glazing - room`; positive points left
  (South Glazing → Room Air), negative points right, zero shows a neutral
  connector;
- arrow magnitude uses `abs(delta)` with the existing visual cap; and
- a missing endpoint shows an unavailable neutral connector with no inferred
  direction.

Amber means heat moving into Room Air; blue means heat moving out toward mass
or glazing; neutral/unavailable uses the subdued label color. Swapping positions
must move node coordinates and rebind deltas, direction, color, legend,
humidity, and focus order together.

Tests cover positive, negative, zero, and unavailable values for both
corridors, exact DOM/legend/humidity/keyboard order, and geometry at both M9
modes and the laptop floor.

## 11. Bitcoin Presentation

Bitcoin is absent from the header.

The Home Bitcoin card keeps:

- current USD price;
- 24 h percentage change;
- positive/negative color treatment; and
- keyboard/touch activation to open the full history modal.

It removes the inline sparkline and the recurring Home-card history fetch.
Home mount, SSE refresh, and route return issue no BTC persistence request. The
first BTC history request occurs only when the card is activated. Tests retain
price, signed change, sign color, focus/keyboard behavior, and modal opening at
both M9 modes and the laptop floor.

## 12. Typed Controls

### 12.1 Control primitives and outcome model

The generic `Toggle` is replaced by four explicit primitives:

- **Binary control:** persistent ON/OFF item with provider-confirmed state.
- **Action control:** one-shot correlated rule request.
- **Safety request:** asks a rule to evaluate/act; the physical actuator remains
  read-only.
- **Status control:** read-only equipment/rule state.

Every commandable primitive supports `ON`, `OFF`, `UNAVAILABLE`, `PENDING`,
`FAILED`, and `OUTCOME_UNKNOWN` where applicable. `OUTCOME_UNKNOWN` is
distinct from failure: it means transport was lost after submission and the UI
cannot safely infer whether the action occurred. It never offers automatic
retry.

All commands require:

- visible 600 ms hold progress;
- pointer, touch, Space, and Enter operation;
- keyboard-repeat suppression;
- cancellation on early release, pointer cancel, blur, route change, second
  pointer, or state invalidation;
- one in-flight request per control;
- a generated request ID for rule-owned actions;
- bounded acknowledgement timeout;
- visible denial/failure/outcome-unknown reason plus header alert; and
- a 44×44 minimum target.

Unavailable or offline controls are disabled and explain why. Telemetry
staleness disables a control only when that telemetry is a rule prerequisite;
a stable switch state is governed by Thing/channel health rather than elapsed
time since its last change. An HTTP 2xx response confirms transport acceptance,
not equipment success.

Correlated rule results use this logical schema, encoded in a parseable openHAB
String item:

```ts
type RuleOutcome = {
  requestId: string;
  status: 'accepted' | 'denied' | 'running' | 'complete' | 'failed';
  reason: string;
  at: string; // ISO-8601
};
```

Unknown request IDs never resolve the UI's pending request.

### 12.2 Exact control mapping

| UI label | Source/target | Type | Confirmation |
| --- | --- | --- | --- |
| Living Room 1 | `living_room_1_Switch` | Binary | Target-state provider event after command start |
| Living Room 2 | `living_room_2_Switch` | Binary | Target-state provider event after command start |
| Living Room 3 | `LED_living_room_1_Switch` | Binary | Target-state provider event after command start |
| Circadian Lighting | `LivingRoomCircadian_Enable` | Binary policy | Virtual target state plus separate `LivingRoomCircadian_LastResult` health |
| Dishwasher | `Dish_Washer_Power` | Binary | Provider event; disabled while override owns it |
| Shureflo Pump | `ShurefloPump_Power` | Binary | Provider event; disabled while override owns it |
| Goat Cam | `Goat_Plugs_Outlet1_Switch` | Binary | Provider event plus visible feeder-policy side effect |
| Feed once | `GoatFeeder_ManualRequest` → rule `88bd9ec4de` | Action | Matching `GoatFeeder_ManualResult`, count increment, outlet OFF |
| Request circulation | `SouthOutlet_ManualRequest` | Safety request | Matching `SouthOutlet_ManualResult` |
| Night Load Override | `OverrideSwitch` | Policy | Matching `NightLoadOverride_Result` |
| Feeder actuator | `Goat_Plugs_Outlet2_Switch` | Status | Read-only |
| Greywater actuator | `SouthOutlet_Outlet2_Switch` | Status | Read-only |

`LED_living_room_1_Switch` is relabeled Living Room 3 because that is the
actual device. `UNDEF`, `NULL`, missing, or offline lights are unavailable,
not falsely OFF, and cannot be commanded.

Circadian enablement and health are separate. `Enabled · degraded` is shown
when the rule is enabled but bulbs are unknown/backing off. Turning the policy
OFF remains available whenever the virtual item/transport is available even if
bulbs are unhealthy. Turning it ON is blocked only when the rule or enable item
itself is unavailable; bulb degradation is shown as a warning, not disguised.

The existing Goat Cam coupling remains behaviorally intact: Goat Cam ON clears
`FeederOverride`; Goat Cam OFF sets it. The resulting feeder-policy state is
shown beside Goat Cam so the effect is no longer hidden. Rule consolidation may
remove duplicate commands but cannot change those external semantics.

### 12.3 Hardware acknowledgement

For each bidirectional physical channel, implementation first proves provider
readback, records the Thing UID, and disables optimistic openHAB autoupdate. A
binary request is confirmed only by:

1. Thing/channel health remaining ONLINE;
2. a target-state event whose receive time is after command start; and
3. no contradictory provider event before the acknowledgement window closes.

An unrelated external state change, an event predating the request, or HTTP
success does not confirm it. Disconnect-after-POST becomes
`OUTCOME_UNKNOWN`; a late matching event may resolve it, but the UI does not
retry automatically. Channels without reliable readback show
`Command sent · unconfirmed` and end in `OUTCOME_UNKNOWN`, never a false
success.

Virtual policy items may update immediately, but their correlated orchestration
or health result is tracked separately.

## 13. openHAB Rule and Item Corrections

### 13.1 Mutation, backup, and authority boundary

All openHAB mutations use supported REST/configuration interfaces; live JSONDB
files are never hand-edited. Before mutation, a restore manifest captures:

- GET endpoint and resource UID;
- exact sanitized restore endpoint/method/body, not the raw GET wrapper;
- SHA-256 of each payload;
- dependency order;
- pre-change readback; and
- post-restore verification request.

Covered resources include Things (`/rest/things/{uid}`), items
(`/rest/items/{name}`), links (`/rest/links` with item/channel identity),
rules (`/rest/rules/{uid}`), and affected MainUI components
(`/rest/ui/components/{uid}`). Restore order is Thing configuration, wait for
ONLINE/dynamic channels, item, link, rule, then UI component. Idempotent PUT/
create/delete behavior is rehearsed against temporary test UIDs or by restoring
an unchanged resource and verifying checksum/readback. Runtime item state and
persistence are not claimed as restorable configuration.

The Earthship UI and household MainUI pages remove every direct feeder and
greywater actuator control. Administrative REST/MainUI access remains an
explicit operator bypass outside the household UI threat model; the UI does not
pretend that openHAB has per-client item ACLs.

Configuration backup/readback, UI deployment, and pure rule simulation are
authorized implementation steps. Any live command that may move equipment or
change household loads—feeder, greywater pump, lights, dishwasher, Shureflo,
Goat Cam, or override—requires contemporaneous user confirmation and physical
presence. There is no "guaranteed denial" exception based on mutable live
telemetry.

### 13.2 Feeder

Create unlinked String items `GoatFeeder_ManualRequest` and
`GoatFeeder_ManualResult`; the request has `autoupdate=false`. After the
600 ms hold, the UI commands a generated request ID to the request item. The
existing canonical `Feeder Timer` rule (`88bd9ec4de`) receives that command
and remains the only owner of:

- five-second cooldown;
- one-second physical outlet pulse;
- outlet reset to OFF in a `finally` path;
- `GoatFeedings` increment; and
- existing payment/manual accounting.

The result item emits matching `accepted`, `denied`, `running`,
`complete`, or `failed` outcomes. Cooldown and busy are explicit denial
reasons. Simultaneous request IDs are serialized; a request received while one
is running is denied as busy. Completion requires the same invocation to
increment the counter and observe/command the actuator OFF. An unrelated count
change cannot confirm the request.

Direct Earthship/MainUI commands to `Goat_Plugs_Outlet2_Switch` are removed.
No live feeder invocation occurs without the user present and explicitly
authorizing that action.

### 13.3 Greywater/fountain

Create unlinked String items `SouthOutlet_ManualRequest` and
`SouthOutlet_ManualResult`; the request has `autoupdate=false` and carries a
request ID. Add its received-command trigger to `hex_southoutlet_cycle`.
`SouthOutlet_Outlet2_Switch` remains read-only in all household UI surfaces.

The rule evaluates a request in deterministic denial order:

1. already running or another request in flight;
2. BMS communication/freshness;
3. valid SoC and voltage;
4. low-SoC cutoff;
5. cooldown;
6. hydrology/timer constraint;
7. curtailment/energy-availability policy; and
8. existing run-duration/force-off prerequisites.

Every path emits a matching result and clears the request item's display state
in `finally`. Acceptance emits `accepted`, then `running`, then `complete`
or `failed`. Denial includes the first failed gate. Duplicate request IDs
return the prior result and do not start another cycle. Cron/request collision,
restart/orphan recovery, and exception paths cannot leave the relay or request
latched.

Add `SouthOutlet_LastCycle` for the most recent completed cycle of any origin.
Automatic cycles continue to update `SouthOutlet_LastAutoRun` and also update
`SouthOutlet_LastCycle`; manual cycles update only `SouthOutlet_LastCycle`.
The UI uses the truthful field for its label.

Gate evaluation is extracted into a pure function and tested with captured
state fixtures. Live unattended verification is read-only; it never sends a
manual request, even when a denial appears likely. A positive live pump test
requires the user present and explicitly authorizing that specific test.

### 13.4 Night load override

Scheduled and manual activation route through one orchestration rule. The
schedule commands only `OverrideSwitch`; the same rule handles either source
and writes `NightLoadOverride_Result`.

The target matrix is exact:

| Override transition | Dishwasher | Shureflo | Goat Cam |
| --- | --- | --- | --- |
| ON | command OFF | command OFF | command OFF |
| OFF | leave last confirmed state | command ON | leave last confirmed state |

While ON, the override owns all three loads and their direct Earthship controls
are disabled with `Owned by Night Load Override`. On OFF, it performs the
matrix above and releases ownership to normal equipment rules. Repeated
same-state commands are idempotent. The result names partial device failures
rather than claiming complete success.

Existing schedule, dishwasher, Shureflo, Goat Cam, and override rules are
reviewed together to remove loops and duplicate/contradictory commands. Tests
compare manual and scheduled event traces for identical outcomes. Household
MainUI controls follow the same ownership presentation; administrative direct
commands remain an explicit operator bypass.

### 13.5 Circadian lighting

The circadian rule remains a policy toggle, but its dependencies are audited:

- all three bulb items/Things are correctly mapped;
- offline/backoff conditions are surfaced;
- retry/backoff does not flap commands;
- enable OFF remains possible during bulb degradation; and
- `LivingRoomCircadian_LastResult` distinguishes disabled, healthy, degraded,
  and failed outcomes.

The repair is not accepted merely because the enable item is ON.

## 14. Error Handling and Safety

- A failed initial config or snapshot request produces an actionable offline
  state, not a blank application.
- Cached values always show age and cannot authorize a command.
- Stale critical data produces an alert without expanding the header.
- History failures remain local to the chart unless they indicate global
  transport failure.
- Control failures preserve the last confirmed state and show the attempted
  target separately.
- Safety requests report accepted, denied-with-reason, timed-out, failed, and
  outcome-unknown distinctly.
- Unknown actuator state never enables a control or implies OFF.
- Reconnect does not replay a user command.
- Rule changes are idempotent under duplicate commands/events.

## 15. Verification Strategy

### 15.1 Canonical audit matrix

Implementation creates one version-controlled
`docs/qa/ui-audit-matrix.csv`. It is the authoritative queue for all audited
features and defects, with these fields:

```text
id,route,component,integration,target,state_fixture,expected,test_or_evidence,status
```

The matrix begins with every issue in this specification. Newly discovered
defects are added before being fixed. An item closes only after a post-fix test
or captured live-device/runtime result is recorded.

### 15.2 Unit tests

Unit coverage includes:

- strict numeric/unit/scientific-notation parsing, rain-unit rejection, and
  duration carries;
- tri-state adaptation, telemetry freshness, stable-switch health, SSE
  keepalives, timestamp merge order, and reconnect reconciliation;
- AQI rounding/freshness and boundaries at malformed, -1, 0, 50, 51, 100, 101,
  150, 151, 200, 201, 300, 301, 500, and 501;
- exact ISO start/end ranges for 4/24/168/720 h, one captured `now`, independent
  forecast lookahead, and invalid initial periods;
- duplicate last-arrival tie-breaking, cadence gaps, unit filtering, and partial
  multi-series failure;
- smoothing for 0/1/2-point segments, endpoints, gaps, EMA initialization, and
  a registry proving SoC/rain/switch/forecast/gust/operational steps remain raw;
- hard point budgets, equal extrema, many gaps, width zero, resize
  re-downsampling, and segment-safe raw tooltip lookup;
- worker/main parity, abort, crash, timeout, stale completion, pagination caps,
  and oversized-response behavior;
- alert priority, ties, deduplication, clearing, global navigation, and `+N`;
- control hold/cancel/repeat/multi-pointer behavior and correlated
  pending/denied/failed/outcome-unknown/late-acknowledgement transitions;
- feeder cooldown, busy/concurrent request, unrelated counter change, exception
  reset, and correlated completion;
- every greywater denial gate and precedence, duplicate/concurrent request,
  already-running, cron collision, restart/orphan recovery, and `finally`
  cleanup;
- exact override ON/OFF matrix, repeated state, partial failure, competing
  commands, and manual/scheduled trace equivalence; and
- Earthship left/right arrow direction, magnitude, color, zero, and unavailable
  fixtures.

### 15.3 Component and integration tests

Component tests cover:

- every visible period picker retaining 4 h, 24 h, 7 d, and 30 d and issuing
  only its current generation;
- initial seed, close/reopen reseed, modal close, route change, period change,
  and resize cancellation;
- partial-series warning and all loading/no-data/timeout/error states;
- modal focus trap, Escape, focus return, and accessible period state;
- the Outdoor inline 24 h line remaining visibly nonzero and contained after
  mount/navigation/resize, independently from its full modal;
- wind compass scale and gust/max non-overlap;
- Header priority, alert clearing, global alerts, deterministic `+N`, and
  one-line long content;
- unavailable values never becoming valid zero/OFF states;
- exact North/Room/South DOM, legend, humidity, keyboard, and SVG order;
- Bitcoin causing no history request on Home mount/refresh/return and causing
  its first request only on activation;
- Home Outdoor/Indoor primary temperatures computing to `rgb(255, 255, 255)`,
  Indoor/metadata meeting their minimum sizes, Rain using only its scoped
  smaller sizes, and Sun & Moon meeting its target or recorded 0.8 rem floor;
- all typed controls with pointer/keyboard holds, disconnect-after-POST, late
  acknowledgement, contradictory provider state, and no automatic retry;
- circadian OFF eligibility during bulb degradation;
- override ownership disabling conflicting loads; and
- feeder/greywater actions never posting to their actuator items.

Static integration checks search the Earthship source and exported household
MainUI components to prove neither surface directly commands
`Goat_Plugs_Outlet2_Switch` or `SouthOutlet_Outlet2_Switch`. The openHAB
client is tested against mocked REST/SSE contracts before any live command is
considered.

### 15.4 Geometry tests

Playwright runs all five routes at exactly:

1. measured M9 Chrome/WebView landscape CSS viewport and DPR;
2. measured installed-PWA landscape CSS viewport and DPR; and
3. 1280×720 laptop CSS pixels.

If the two M9 measurements are identical, they share one geometry project but
retain separate real-device smoke rows. No layout implementation starts until
the measurements are in the audit matrix.

Each route runs normal, unavailable, stale/offline, pending/failed, and
long-content fixtures. Tests assert document, main region, every required card,
every required child, chart canvas, modal, rail, header, and control bounds.
They check pairwise overlap for required siblings, minimum plot sizes, 44×44
targets, the bounded row templates, and absence of scrollable overflow. Weather
and Earthship specifically assert every forecast/humidity/status row rather
than only their aggregate card.

No phone, portrait, split-screen, or arbitrary viewport screenshots are
generated.

### 15.5 Performance and build

- Existing unit tests remain green.
- Production build completes without new warnings.
- Initial JavaScript is at most 1 MiB gzip and has no full ECharts/icon import.
- Each chart obeys the `floor(4W)` total rendered-point cap.
- On the real M9, chart preprocessing creates no main-thread task over 50 ms,
  input response remains at or below 100 ms p95 during loading, one capped 30 d
  chart adds at most 64 MiB heap, and its worker completes within 3 s after the
  final page.
- Route navigation and SSE updates remain responsive while dense history loads.
- Worker and main-thread output are identical for the same fixture.
- `git diff --check` passes and no token/config secret is tracked.

### 15.6 Live openHAB verification

Live verification is read-only by default. For each affected integration it:

- verifies item, type, link, Thing, channel, rule, and UI-component UIDs;
- exports and checksums a restore manifest;
- applies only the approved configuration mutation;
- reads back resulting configuration;
- inspects rule status/events without triggering physical action;
- validates pure/dry-run rule logic outside the actuation path;
- verifies unavailable/error UI behavior with mocks or non-actuating state; and
- records result and rehearsed rollback evidence.

AQI must reach a numeric Number item through openHAB and the UI. Rule simulation
must prove feeder, greywater, and override outcomes without moving loads.
Physical light/plug, feeder, greywater, override, dishwasher, Shureflo, and Goat
Cam commands are skipped unless the user is presently available, explicitly
approves the specific command, and can observe the equipment. When authorized,
physical binary success requires a provider event after command start, not HTTP
success.

### 15.7 Real-device sign-off

The actual Tab M9 browser in landscape is the final visual authority and
exercises:

- all five routes without scrolling or overlap;
- required content inventory and long/offline/unavailable fixtures;
- across-room readability of white Outdoor/Indoor temperatures, enlarged
  Indoor text, contained Rain text, and enlarged Sun & Moon rows;
- Outdoor inline-chart containment and visible line;
- modal 4 h, 24 h, 7 d, and 30 d selection;
- modal focus/close and touch targets;
- wind compass scale;
- 600 ms holds and cancellation without requiring a physical command;
- dim mode; and
- recovery after openHAB/SSE interruption.

Laptop sign-off uses a full-screen browser at the 1280×720 lower bound.

## 16. Rollout and Rollback

The Vite development server is the intentional production server for the few
household LAN clients. It runs from `/home/sat/earthship-ui` on port 5190 under
one versioned user-level `earthship-ui.service`. No nginx, immutable release
server, HTTPS/PWA origin, or service-worker rollout is part of this design.

1. Record the M9 browser geometry; create the canonical matrix and fixtures.
2. Remove/disable unsafe direct controls and verify explicit fail-closed
   `RELEASE_MODE` handling in the same Vite runtime.
3. Capture/rehearse openHAB restore manifests.
4. Implement and verify truthful state, shared primitives, charts, route
   layouts, and typed controls against mocks.
5. Apply/read back AQI items/links and correlated feeder/greywater/override rule
   changes while the UI remains in explicit maintenance mode.
6. Install/enable the user unit, restart it into the verified intended mode,
   and run post-deploy read-only smoke checks at the same LAN URL.
7. Complete real M9 and laptop sign-off and close the audit matrix.

The pre-audit build with raw actuator toggles is never a rollback target. UI
rollback returns Git to the last verified safe commit and restarts the same user
service. Server-side rule safety and removal of household MainUI raw controls
remain in force. If openHAB configuration must also roll back, restore in
manifest dependency order and read back every checksum/state contract before
enabling any control. MainUI remains available for administration.

## 17. Definition of Done

The work is complete only when:

- every canonical audit-matrix row is closed with evidence;
- the measured M9 landscape browser and the 1280×720 laptop floor show all five
  routes with no document/card scrolling, overlap, or omitted required content;
- the Home Outdoor inline line is visible and contained, and all other charts
  remain inside their cards;
- Home Outdoor/Indoor primary temperatures are white, Indoor text is enlarged,
  Rain text is scoped smaller without content loss, and Sun & Moon is enlarged
  to its passing target/floor;
- every chart period picker works in its inline or modal context, with exact
  request ranges and cancellation;
- only the approved analog registry is smoothed and tooltips remain raw;
- dense 30 d charts meet point, memory, worker, and interaction budgets;
- the wind compass scales to its card without gust/max overlap;
- `Current_US_AQI` is numeric, current, correctly rounded/banded through values
  above 500, and freshness-aware;
- North Mass is left and South Glazing right with correct physics, DOM, legend,
  humidity, and keyboard order;
- no Bitcoin content remains in the header, no Bitcoin sparkline/history fetch
  occurs on Home, and card activation opens history;
- alerts fit the 44 px header and obey source/priority/lifecycle contracts;
- controls use correct labels, types, ownership, correlation, hold behavior,
  provider acknowledgement, and outcome-unknown handling;
- Earthship UI and household MainUI cannot directly command feeder or
  greywater actuator items;
- feeder, greywater, circadian, and override rule behavior passes pure/mocked
  verification, with no unapproved physical actuation;
- manual and scheduled override paths have identical orchestration semantics;
- openHAB configuration is backed up, checksummed, corrected, read back, and
  rollback-rehearsed;
- automated tests, production build, and performance budgets pass;
- actual M9 browser and laptop sign-off pass;
- the user-level Vite service starts at login, restarts cleanly, owns port 5190,
  serves the LAN URL, and exposes only the explicitly selected safety mode; and
- Git-plus-service-restart UI rollback is rehearsed without weakening OpenHAB
  safety or reintroducing raw MainUI actuator controls.
