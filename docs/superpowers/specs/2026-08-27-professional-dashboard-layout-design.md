# Professional Dashboard Layout Design

**Date:** 2026-08-27
**Status:** Approved for implementation planning
**Reference viewports:** 1340x800 and 1280x720

## Objective

Make the Earthship Console feel more professional, technical, and deliberate
without adding decorative features or increasing visual complexity. The work
is primarily a Home-screen layout correction, supported by a narrow
application-wide spacing and typography consistency pass.

The approved direction preserves the established dark instrument-panel
language, domain colors, fixed-height console, current data, interactions, and
modal behavior.

## Design constraints

- Home must fit at 1340x800 and 1280x720 without page scrolling.
- Outdoor, Indoor, Battery SoC, and Bitcoin are equal-size primary cards.
- Existing domain colors and near-black surfaces remain authoritative.
- No gradients, glass effects, glow, decorative textures, ornamental gauges,
  new animation, or global font-size increase.
- No new data requests, timers, libraries, runtime dependencies, navigation,
  or controls.
- Long, stale, unavailable, and partial-data states remain bounded.
- Existing keyboard interaction, focus treatment, modal behavior, and chart
  accessibility remain intact.

## Screenshot-derived findings

The live 1340x800 and 1280x720 screenshots show a strong overall visual
language but an accidental primary-card hierarchy:

- Outdoor and Battery are approximately two and a half times taller than
  Indoor and Bitcoin.
- Indoor and Bitcoin compress their metrics and charts into shallow strips.
- Outdoor and Battery devote substantial height to low-information chart
  space.
- The Wind card's compass is technically present but its needle, cardinal
  labels, speed, and footer compete within a small low-contrast face.
- The Bitcoin modal and Weather screen are already structurally sound. They
  need consistency corrections, not redesigns.

## Home grid

The existing six-column console grid remains. Its middle rows become an exact
2x2 primary-card block, with compact supporting instruments on the right:

```text
Power flow                        Goat       Greywater
Outdoor          Battery          Wind       Pressure
Indoor           Bitcoin          Rain       Sun/Moon
Solar                            Zones
10-day forecast
```

The grid areas are:

```text
'topbar  topbar  topbar  topbar  goat  greywater'
'outdoor outdoor battery battery wind  baro'
'indoor  indoor  bitcoin bitcoin rain  sunmoon'
'solar   solar   solar   zones   zones zones'
'forecast forecast forecast forecast forecast forecast'
```

The Outdoor, Battery, Indoor, and Bitcoin rows use equal track sizes. Their
cards therefore have equal rendered width and height. The top strip, shallow
Solar/Zones row, and forecast strip retain subordinate heights chosen to keep
the whole console bounded at both reference viewports.

Solar and Zones become two wider supporting strips rather than isolated
one-column remnants. Wind, Pressure, Rain, and Sun/Moon remain compact
one-column instruments.

## Primary-card system

The four primary cards use consistent outer padding, value alignment,
metadata rhythm, and chart allocation. They share structure without forcing
their domain-specific content into identical widgets:

1. A compact top region presents the current value and status.
2. Secondary measurements sit immediately below or beside the value.
3. A consistent lower chart region occupies the remaining height.

### Outdoor

- Condition icon and current temperature remain dominant.
- AQI and UV remain compact chips.
- Feels-like, humidity, and current-day high/low form concise secondary text.
- The sparkline fills the common lower chart region.

### Indoor

- The current compressed horizontal strip becomes a vertical primary-card
  layout aligned with Outdoor.
- Temperature and humidity lead, current-day high/low follows, and the indoor
  sparkline fills the common lower chart region.

### Battery SoC

- The SoC arc remains the domain-specific primary visual but is reduced enough
  to share the upper region cleanly with charging state and runtime details.
- Its history chart uses the common lower chart region.

### Bitcoin

- Price and percentage receive adequate spacing without becoming more visually
  important than household telemetry.
- Candles use the common lower chart region.
- Existing click-to-modal behavior and accessible OHLC description remain
  unchanged.

## Wind compass

The Wind card retains an SVG compass rose. Readability improves through
hierarchy and contrast rather than decoration:

- The rose uses nearly all available card width with reduced internal margin.
- Outer ring and tick contrast increase within the existing neutral palette.
- Cardinal labels use a brighter neutral and stronger weight.
- The heading needle has a thicker, clearly distinguished leading point in the
  wind accent color.
- Center speed and `mph` text increase to a readable hierarchy.
- A text heading below the speed uses a sixteen-point compass abbreviation and
  rounded degrees, for example `ENE · 78°`.
- A separate footer presents `gust 6 · max 9 mph`.
- Missing heading, missing speed, and calm-wind states remain explicit and do
  not imply a direction.

The compass gains no glow, sweep animation, shaded dial, or ornamental detail.

## Shared visual consistency

Normalize existing shared tokens or local styles only where the screenshots
or rendered measurements demonstrate one of these concrete consistency
problems:

- card padding, gap, radius, and subtle border contrast;
- tabular numerals for measurements;
- unit alignment and subordinate unit styling;
- three text levels: primary value, secondary measurement, muted context;
- compact-card header and metadata spacing.

The navigation rail, alert placement, domain palette, page structure, modal
dimensions, period controls, and screen information architecture do not
change. The Bitcoin modal and Weather page receive only spacing or alignment
corrections that follow from shared-token changes.

## Data and component boundaries

This is a presentation-only change. Existing Svelte state, OpenHAB item
subscriptions, persistence requests, refresh coordinators, chart aggregation,
modal stores, and forecast adapters remain authoritative.

Implementation scope is limited to:

- `src/screens/Home.svelte` for grid areas and primary-card internal layout;
- `src/lib/ui/CompassRose.svelte` for compass presentation and direction text;
- existing shared tokens or tile primitives only when required for a verified
  cross-screen consistency correction;
- focused unit and Playwright tests for the new layout contract.

No data-flow or backend change is part of this design.

## Failure and accessibility behavior

- Invalid or unavailable values continue to render an em dash or existing
  unavailable state.
- The compass exposes a truthful accessible label for heading and speed.
- Long values and stale-state labels remain contained without clipping primary
  values.
- Clickable cards retain visible keyboard focus and existing hit targets.
- Chart components continue to resize and dispose through their current
  lifecycle paths.
- The fixed viewport must not hide content, introduce scrollbars, or overlap
  the navigation/header regions.

## Verification

Implementation is accepted only when:

- Outdoor, Indoor, Battery, and Bitcoin have equal rendered width and height
  within normal subpixel tolerance at 1340x800 and 1280x720.
- Home and every card remain bounded at both reference viewports.
- Long, stale, unavailable, and partial-data fixtures remain readable.
- Compass tests cover representative directions, calm wind, missing heading,
  and missing speed.
- The compass exposes a stable sixteen-point abbreviation plus rounded degrees
  when a heading exists.
- Existing chart clicks, modal focus restoration, accessible chart summaries,
  and refresh behavior still pass.
- Focused unit tests, the complete Vitest suite, production build, and Home
  Playwright tests pass.
- Fresh live screenshots are captured at both target viewports and reviewed
  before deployment.

## Explicit non-goals

- No new dashboard cards or metrics.
- No visualization library changes.
- No animated compass, responsive phone redesign, theme selector, user
  customization, or alternate layout modes.
- No modal redesign, navigation redesign, backend work, or OpenHAB changes.
- No attempt to make every secondary card identical; hierarchy remains useful.
