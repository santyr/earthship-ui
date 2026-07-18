# Home Seasonal Countdown and Goat Feeding Design

## Scope

Add two compact, read-only Home dashboard features without changing the page height:

- A Goat Feedings card between Power Flow and Greywater.
- A local-calendar countdown to the next northern-hemisphere equinox or solstice in Sun & Moon.

The exact supported layouts remain the Lenovo Tab M9 at 1340×800 CSS pixels and laptops at 1280×720 CSS pixels. Neither viewport may gain page, card, or card-content overflow.

## Goat Feedings

The card reads only:

- `GoatFeedingsToday`, a Number item managed by OpenHAB.
- `Goat_Plugs_Outlet2_Switch`, a Switch item that reflects feeder-motor state.

It must never import a command client, call `sendCommand`, or otherwise expose a control.

The steady display uses the bundled feed icon and the text `N feedings today`. A valid non-negative Number is rounded to a whole daily count; `1` uses the grammatically correct singular. Missing or invalid data renders `Feedings unavailable`.

A pure reducer owns motor-transition semantics. It normalizes only `OFF` and `ON` as known states. Its first known state initializes the tracker without activating, so an initial `ON` snapshot never produces feedback. Only a later observed `OFF` to `ON` transition activates; repeated `ON`, unknown values, and `ON` after an unknown state do not.

Activation swaps the normal bundled feed icon for the exact Unicode goat glyph (`🐐`) for about 1.8 seconds because the installed MDI bundle has no goat icon. The glyph remains visible without animation when reduced motion is requested; otherwise it may use a subtle pulse. A first pointer or key interaction best-effort creates and resumes a Web Audio context. A later activation plays one quiet synthesized sine chime lasting about 250 ms only when that context was armed. Unsupported, blocked, suspended, or failed audio never prevents visual feedback. Component teardown clears its timer, listeners, and audio context.

## Layout

The existing five-row Home grid remains unchanged in height. The top row changes from five Power Flow columns plus Greywater to:

`topbar topbar topbar topbar goat greywater`

The Goat card is a one-line, vertically centered, clipped card with bounded text and no wrapping. Exact-size browser tests must prove Power Flow remains legible and that the top row, each tile, and each tile body stay within their boxes.

## Seasonal Countdown

A pure helper calculates the next March equinox, June solstice, September equinox, or December solstice. It uses the standard polynomial approximation for years 2000–3000 and has no network or runtime package dependency.

The event instant is converted to the browser's local year, month, and date. Both the current local date and event local date are then normalized to UTC midnight before subtraction, making the integer calendar-day count independent of daylight-saving transitions.

The helper returns compact northern-hemisphere wording:

- `66 days to autumn equinox`
- `1 day to winter solstice`
- `summer solstice today`

Sun & Moon renders this through a focused fourth-row component. The component refreshes its browser-local date at a bounded hourly interval, so a long-running tablet advances across midnight without a reload, and clears that interval on teardown. The row remains centered and ellipsized; existing rise/set, moon phase, and daylight lines remain.

## Outdoor Temperature Sparkline

The Outdoor sparkline consumes the same live temperature-band color value as the Outdoor condition icon. There is one shared threshold calculation, so the icon and line cannot drift apart as temperature changes. Every band color must retain at least 3:1 non-text contrast against the `#11151c` card background; the coldest purple is lightened only as much as needed to satisfy that floor.


## Testing

Testing follows red-green-refactor:

- Pure tests cover count formatting, invalid values, reducer initialization, duplicate states, unknown states, OFF-to-ON activation, seasonal ordering, year rollover, event-day wording, and DST-safe calendar-day differences.
- Pure and source-contract tests prove all Outdoor temperature bands meet the contrast floor and the sparkline consumes the same derived color as the icon.
- Component tests cover the steady card, initial snapshot suppression, visual activation/expiry, audio gesture gating, audio failure tolerance, reduced-motion markup, cleanup, and the absence of command behavior.
- A fake-clock component regression crosses local midnight and proves the seasonal label advances without a reload; teardown leaves no interval behind.
- Source-contract tests pin the 4/1/1 grid and read-only item wiring.
- Playwright runs both 1340×800 and 1280×720 fixtures, asserts no page/tile/content overflow, verifies Power Flow is not clipped, confirms no activation on initial `ON`, then drives `OFF` to `ON` and observes the goat icon.

AC Metrics remains excluded from Battery.
