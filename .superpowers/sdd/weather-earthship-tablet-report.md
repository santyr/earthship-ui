# Weather and Earthship tablet verification

## Scope

Weather and Earthship only, at the exact tablet/laptop targets 1340x800 and 1280x720. Phone layouts, Home, Header, Shell, alerts, chart internals, controls, OpenHAB integration, and external systems were excluded.

Implementation commit: pending (the exact SHA is added in the follow-up report commit because a Git commit cannot contain its own hash).

## Root causes

- Weather used intrinsic grid rows (`auto minmax(11rem, auto) minmax(13rem, auto) auto`) plus `overflow-y: auto`. At 1280x720 the 658 px grid needed 673 px; current content extended about 3.7 px below its card, and rain/pressure cards measured 82 px client vs 96 px scroll height.
- The hourly chart caller supplied a fixed 150 px height even when the fractional row was shorter.
- Seven 1.5 rem forecast icons plus row gaps imposed more intrinsic height than the 1280x720 daily row could supply.
- Weather numerically consumed categorical `Forecast_AQI=REFRESH`, which cannot honestly represent current air quality.
- Earthship used intrinsic minimum rows and a scrolling grid. Its passive loop, history series, and humidity list also duplicated a reversed three-zone order.
- The final live-item requirement expanded the passive loop to four temperatures: North Mass, Room Air, South Wall, and Outdoor.

## Implementation

- Weather now uses four bounded fractional rows, hidden overflow, zero-min-size grid children, a flex-filled hourly chart caller, and a compact seven-day list that keeps all days visible.
- Current AQI reads only numeric `Current_US_AQI`. Missing, sentinel, or non-numeric state renders explicit `Unavailable — Current sensor not configured`; categorical `Forecast_AQI` is ignored.
- Earthship now uses three bounded fractional rows with clipped card children and compact advisory/greywater text.
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

GREEN:

- `npm test -- tests/ui/Weather.test.js tests/ui/Earthship.test.js tests/ui/ThermalLoop.test.js tests/aqi-consumption.test.js` -> 4 files, 6 tests passed.
- `npx playwright test tests/e2e/weather-earthship-layout.spec.js --workers=1` -> 4 tests passed across both exact viewports.
- `npm run build` -> production build passed; only the pre-existing Vite chunk-size advisory remained.
- `git diff --check` -> clean for all scoped files.

## Live Chromium geometry

| Viewport | Route | Document client/scroll | Grid client/scroll | Overflow | Cards fit | Route-specific proof |
| --- | --- | --- | --- | --- | --- | --- |
| 1340x800 | Weather | 1340x800 / 1340x800 | 1267x735 / 1267x735 | hidden/hidden | yes | rows 148, 207, 236, 108; current contained; AQI unavailable |
| 1340x800 | Earthship | 1340x800 / 1340x800 | 1267x735 / 1267x735 | hidden/hidden | yes | 4 SVG zones contained; exact label order; no console errors |
| 1280x720 | Weather | 1280x720 / 1280x720 | 1210x658 / 1210x658 | hidden/hidden | yes | rows 131, 184, 210, 96; current contained; AQI unavailable |
| 1280x720 | Earthship | 1280x720 / 1280x720 | 1210x658 / 1210x658 | hidden/hidden | yes | 4 SVG zones contained; exact label order; no console errors |

The mocked E2E fixture additionally asserts the exact four displayed temperatures `67°, 69°, 72°, 68°` in item order and verifies every SVG node lies within the loop SVG and card. Live local data displayed `68°, 70°, 67°, 55°` in that same order.

Final PNGs were produced at both targets (plus Playwright test artifacts). The local image-view helper could not open them because the host bubblewrap helper failed with `RTM_NEWADDR: Operation not permitted`; Chromium visibility, bounds, scroll, label/value, containment, console-error assertions, and PNG dimensions were all independently verified.

## Scope hygiene

`HourlyStrip.svelte` was intentionally not edited or staged. No Home, Header, Shell, Tile, StatTile, Sparkline, alert, chart-pipeline, control, OpenHAB, external-system, or generated `test-results` file is included.
