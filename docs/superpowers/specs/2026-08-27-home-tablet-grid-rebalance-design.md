# Home Tablet Grid Rebalance Design

**Date:** 2026-08-27

**Status:** Approved in conversation

**Primary display:** Lenovo Tab M9 landscape, 1340x800 CSS pixels

**Secondary regression target:** Laptop floor, 1280x720 CSS pixels

## Goal

Give the Home Outdoor, Indoor, Battery SoC, and Bitcoin cards more vertical
room while keeping those four primary instruments exactly balanced. Move Solar
PV and Earthship Temperatures back into the two right-hand columns, and reduce
only the Home Battery SoC percentage so every possible percentage fits inside
its smaller arc.

The result should resemble the earlier Home organization without restoring its
large Outdoor/Battery versus shallow Indoor/Bitcoin imbalance.

## Constraints

- The Lenovo Tab M9 at 1340x800 is the primary design authority.
- Home must fit the tablet viewport without document, card, tile-body, or card
  content scrolling.
- The 1280x720 laptop floor must remain bounded and usable.
- Outdoor, Indoor, Battery SoC, and Bitcoin must have equal rendered width and
  height within 1 CSS pixel.
- Preserve the established dark technical console language, domain colors,
  data, charts, card clicks, keyboard access, modals, and refresh behavior.
- Keep long, stale, unavailable, and partial-data states bounded.
- Add no new data, APIs, timers, dependencies, controls, navigation, effects,
  or backend/OpenHAB changes.
- Do not change shared design tokens or redesign other screens.

## Layout

Keep the existing six equal Home columns. Replace the three central content
rows with six equal sub-rows:

```text
Outdoor  Outdoor  SoC      SoC      Wind     Pressure
Outdoor  Outdoor  SoC      SoC      Wind     Pressure
Outdoor  Outdoor  SoC      SoC      Rain     Sun/Moon
Indoor   Indoor   Bitcoin  Bitcoin  Rain     Sun/Moon
Indoor   Indoor   Bitcoin  Bitcoin  Solar PV Earthship
Indoor   Indoor   Bitcoin  Bitcoin  Solar PV Earthship
```

Outdoor, Battery SoC, Indoor, and Bitcoin each span two columns and three
central sub-rows. They therefore remain exactly equal while each receives half
of the entire central region. Compared with the current two-primary-row plus
support-strip arrangement, each primary card gains roughly 27 percent more
height.

The right two columns form three compact aligned pairs. Wind and Pressure span
the upper two sub-rows, Rain and Sun/Moon span the middle two, and Solar PV and
Earthship Temperatures span the lower two. No new wrapper or nested grid is
introduced; the existing cells remain direct children of the Home grid.

The existing top status row and forecast strip remain unchanged. The six
central sub-rows divide only the height currently allocated to the two primary
rows and supporting strip, so the page remains fixed to the existing viewport
shell.

## Battery SoC Typography

The recent primary-card rebalance reduced `.battery-arc` from 36 percent with
an 8rem maximum to 30 percent with a 6.25rem maximum, while the shared
`Arc.svelte` percentage remained 1.8rem. This mismatch causes the percentage
to crowd or escape the arc on the tablet.

Reduce the percentage only in the Home Battery card to exactly 1.45rem.
The Gallery and any future default Arc users retain the shared 1.8rem value.
Use a CSS custom property on `Arc.svelte` with a 1.8rem default rather than a
broad global selector or duplicated Arc markup. The Home `.battery-arc`
wrapper supplies the 1.45rem value.

The displayed value, rounding, color bands, unavailable state, current
sublabel, accessible card label, and chart behavior remain unchanged. The
largest normal display value, `100%`, must fit comfortably inside the arc.

## Component and Data Boundaries

- `Home.svelte` owns the six-sub-row grid areas and the Home-only SoC size.
- `Arc.svelte` exposes only the CSS custom property required for a
  caller-specific value size; its rendering and value semantics do not change.
- Existing chart components, history requests, OpenHAB stores, modal
  components, and other screens remain untouched.
- Solar PV and Earthship Temperatures retain their current data and content;
  only their Home grid placement changes.

## Verification

Use a strict test-first change.

Static contracts must pin:

- six equal central sub-rows;
- the exact grid-area arrangement shown above;
- equal spans for all four primary cards;
- Solar PV and Earthship Temperatures in the bottom-right pair;
- a Home-only SoC percentage size of exactly 1.45rem while the Arc
  default remains 1.8rem.

Rendered Home checks must cover settled and long/unavailable/stale fixtures at
both 1340x800 and 1280x720. They must prove:

- the four primary cards are equal within 1 CSS pixel;
- all four chart regions are contained and at least 50px high, with the
  Outdoor chart prioritized for tablet readability;
- the six right-side cards form three aligned, bounded pairs;
- `100%` and unavailable SoC text remain inside the arc center;
- no required text overlaps or becomes accidentally clipped;
- neither the document nor any Home card gains scrolling.

Fresh screenshots must be captured and reviewed at both viewports, with the
1340x800 Lenovo Tab M9 result evaluated first. Automated geometry is necessary
but does not replace final operator visual confirmation on the physical M9.

The completion gate includes focused Home and Arc tests, the full Vitest suite,
the production build, and Home/Weather/Earthship Playwright regressions. A live
service restart requires separate operator approval after implementation and
review.

## Out of Scope

- Rebalancing any non-Home screen.
- Changing Arc value formatting or telemetry semantics.
- Redesigning the primary cards, right-side card contents, modals, charts, or
  navigation.
- Supporting portrait, phone, split-screen, or an arbitrary viewport matrix.
- Deploying or restarting the household service as part of implementation.
