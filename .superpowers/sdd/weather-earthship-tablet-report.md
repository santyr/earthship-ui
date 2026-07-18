# Weather and Earthship tablet verification

## Scope

Weather and Earthship only, at the exact tablet/laptop targets 1340x800 and 1280x720. Phone layouts, Home, Header, Shell, alerts, chart internals, controls, OpenHAB integration, and external systems were excluded.

Implementation commits: `db5d9e3f91363a376f5fc1e8ac85f5ae68b3e92c` and scoped footer follow-up `ed86851e69f05f044ebdec9601c48b118b81168a` (base `219d15006644e04cbf63548297c3abbae9d58f11`). Review follow-up commit: pending exact SHA.

## Root causes

- Weather used intrinsic grid rows (`auto minmax(11rem, auto) minmax(13rem, auto) auto`) plus `overflow-y: auto`. At 1280x720 the 658 px grid needed 673 px; current content extended about 3.7 px below its card, and rain/pressure cards measured 82 px client vs 96 px scroll height.
- The hourly chart caller supplied a fixed 150 px height even when the fractional row was shorter.
- Seven 1.5 rem forecast icons plus row gaps imposed more intrinsic height than the 1280x720 daily row could supply.
- Weather numerically consumed categorical `Forecast_AQI=REFRESH`, which cannot honestly represent current air quality.
- Earthship used intrinsic minimum rows and a scrolling grid. Its passive loop, history series, and humidity list also duplicated a reversed three-zone order.
- The final live-item requirement expanded the passive loop to four temperatures: North Mass, Room Air, South Wall, and Outdoor.

## Implementation

- Weather now uses four bounded fractional rows, hidden overflow, zero-min-size grid children, a flex-filled hourly chart caller with a bounded 96 px fallback, and a compact seven-day list that keeps all days visible.
- Current AQI reads only numeric `Current_US_AQI`. Missing, sentinel, or non-numeric state renders explicit `Unavailable — Current sensor not configured`; categorical `Forecast_AQI` is ignored.
- Earthship now uses three bounded fractional rows with overflow-bounded card children and compact advisory/greywater text.
- The passive loop is left-to-right `North Mass -> Room Air -> South Wall -> Outdoor`. It receives:
  - `AmbientWeatherWS2902A_WH31E_193_Temperature`
  - `AmbientWeatherWS2902A_IndoorSensor_Temperature`
  - `Shelly_HT1_Indoor_Temperature`
  - `AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature`
- Mass-to-room and wall-to-room arrows preserve the existing inward-gain convention. Wall-to-outdoor points from warmer to cooler: outward loss is blue/rightward; outdoor gain is amber/leftward. The zone history series and humidity labels use the same physical naming/order.

## TDD evidence

RED:

- `npm test -- tests/ui/Weather.test.js` -> 2 failed: missing explicit modeled AQI/unavailable state and numeric Current_US_AQI contract.
- `npx playwright test tests/e2e/weather-earthship-layout.spec.js --workers=1` -> 4 failed: scrolling grids, Weather overflow, and reversed Earthship order.
- `npm test -- tests/ui/ThermalLoop.test.js` -> 1 failed: South Glazing/Room/North order instead of North/Room/South.
- After the binding four-node update, `npm test -- tests/ui/ThermalLoop.test.js tests/ui/Earthship.test.js` -> 3 failed: missing South Wall, Outdoor, third arrow, and fourth chart series.
- First bounded browser rerun exposed a narrower residual issue: Weather daily cell scroll height 244/236 at 1340x800 and 232/210 at 1280x720. Compacting only the daily icon/gap/padding closed it.
- A detached clean-commit run then exposed a footer issue masked by concurrent shared Tile/Shell work: rain was 91 px client vs 96 px scroll height at 1280x720. Increasing only the Weather footer row from 0.55fr to 0.6fr closed it; the clean candidate rerun passed all four viewport tests.
- Review-driven RED: both Weather viewport tests failed when the new contract required a nonzero inline fallback (received 0). Changing only the Weather caller to a bounded 96 px fallback made both tests pass with 14 icon columns, at least 14 visible axis labels, at least 14 visible SVG paths, and rendered chart height above 64 px.

GREEN:

- Detached clean implementation range: `npm test -- tests/ui/Weather.test.js tests/ui/Earthship.test.js tests/ui/ThermalLoop.test.js` -> 3 files, 5 tests passed.
- Detached clean implementation range: `npx playwright test tests/e2e/weather-earthship-layout.spec.js --workers=1` -> 4 tests passed across both exact viewports.
- Detached clean implementation range: `npm run build` -> production build passed; only the pre-existing Vite chunk-size advisory remained.
- Shared integration tree (where the separately owned alert module exists): the focused suite including `tests/aqi-consumption.test.js` passed 4 files and 6 tests.
- `git diff --check` -> clean for all scoped files.

## Live Chromium geometry

| Viewport | Route | Document client/scroll | Grid client/scroll | Overflow | Cards fit | Route-specific proof |
| --- | --- | --- | --- | --- | --- | --- |
| 1340x800 | Weather | 1340x800 / 1340x800 | 1267x735 / 1267x735 | hidden/hidden | yes | rows 146, 204, 233, 117; current contained; AQI unavailable |
| 1340x800 | Earthship | 1340x800 / 1340x800 | 1267x735 / 1267x735 | hidden/hidden | yes | 4 SVG zones contained; exact label order; no console errors |
| 1280x720 | Weather | 1280x720 / 1280x720 | 1210x658 / 1210x658 | hidden/hidden | yes | rows 130, 182, 207, 104; current contained; AQI unavailable |
| 1280x720 | Earthship | 1280x720 / 1280x720 | 1210x658 / 1210x658 | hidden/hidden | yes | 4 SVG zones contained; exact label order; no console errors |

The mocked E2E fixture additionally asserts the exact four displayed temperatures `67°, 69°, 72°, 68°` in item order and verifies every SVG node lies within the loop SVG and card. Live local data displayed `68°, 70°, 67°, 55°` in that same order.

Final PNGs were produced at both targets (plus Playwright test artifacts). The local image-view helper could not open them because the host bubblewrap helper failed with `RTM_NEWADDR: Operation not permitted`; Chromium visibility, bounds, scroll, label/value, containment, console-error assertions, and PNG dimensions were all independently verified.

## Independent review

A bounded exact-range review returned `With fixes` for one Important test gap, one Minor test gap, and the known cross-agent dependency:

- Weather now supplies `height={96}` as a bounded nonzero fallback while flex layout fills the available row. The E2E contract requires 14 icon columns, visible SVG axis labels and paths, a rendered chart over 64 px high and 100 px wide, and containment within the hourly card at both targets. Live rendered heights were about 138 px and 116 px.
- ThermalLoop now tests both directions and colors for all three arrows, including mass/room and room/wall inversions.
- The separate alert dependency remains pending below; no out-of-scope alert edit was made.

## Integration dependency

At implementation HEAD `ed86851`, the handed-off cross-surface `tests/aqi-consumption.test.js` intentionally references `src/lib/alerts/consoleAlerts.js`, which belongs to the active Home/Header commit and is absent from this commit range. A detached run therefore fails with ENOENT for that one file, while all five commit-local component tests, all four browser tests, and the build pass. The AQI cross-surface status remains dependency-pending until the alert-owner commit lands and the integrated six-test suite is rerun. No alert file was staged here.

## Scope hygiene

`HourlyStrip.svelte` was intentionally not edited or staged. No Home, Header, Shell, Tile, StatTile, Sparkline, alert, chart-pipeline, control, OpenHAB, external-system, or generated `test-results` file is included.
