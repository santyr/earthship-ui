# Feature report: forecast rain amounts

Branch: `build/rain-amounts` (worktree `/home/sat/earthship-ui/.worktrees/rain-amounts`)

## Summary

Added forecasted precipitation amounts (inches) alongside the existing
precipitation probabilities, per the operator-approved design. Amounts
render only when strictly positive (two decimals + typographic
double-prime, e.g. `0.24″`), colored with `colors.rain` (`#3b82f6`) from
`src/lib/ui/tokens.js`. Zero/null/missing amounts render nothing —
verified by explicit absence assertions in every new test.

## Data layer (`src/lib/weather/forecastDetail.js`)

- `normalizeHour`: parses `precipIn` (nullable number), defaulting missing
  input to `null` via `raw.precipIn ?? null` before the existing
  `nullableNumber` guard, so older Forecast_10Day_JSON payloads without the
  field parse cleanly instead of throwing.
- `normalizeDay`: parses `summary.precipSumIn` the same way.
- `parseLegacyDailyForecast`: maps legacy `"a"` → `summary.precipSumIn`
  using the existing null-tolerant `legacyNumber` helper (mirrors how `"p"`
  maps to `precipPct`).

## Shared formatter (`src/lib/openhab/values.js`)

Added `rainAmountText(value)`: returns `null` for non-positive/absent
values, otherwise `"${n.toFixed(2)}″"`. Re-exported from
`src/lib/openhab/index.js`. Used by all three display sites below so the
format/threshold rule lives in exactly one place.

## Display sites

- `DailyForecast.svelte` (both `variant="home"` and `variant="weather"`,
  since it's one shared component): amount rendered next to the existing
  precip-percent span in `.day-meta`, sourced from
  `day.summary.precipSumIn` — works for both the 10-day path and the
  legacy path since `forecastDetail.js` normalizes both into the same
  shape. `data-testid="day-rain-amount"`.
- `HourlyStrip.svelte`: added a small amount readout under each hour's WMO
  icon in `.hs-icon-col`, sourced from raw `row.a` (via `num()`/
  `rainAmountText()`, so it tolerates the field being absent on legacy
  Forecast_Hourly_JSON rows). Bars/axes untouched — still probability-only.
  `data-testid="hour-rain-amount"`.
- `WeatherDetailModal.svelte`: day-summary header line gains the amount
  next to "N% precip" (`selectedDay.summary.precipSumIn`,
  `data-testid="day-rain-amount"`); per-hour strip gains
  `hour.precipIn` next to `.hour-precip` (`data-testid="hour-rain-amount"`,
  `.hour-rain` class, `font-size: 0.6rem` to stay within the existing
  card bounds — no geometry/layout changes).

No layout or geometry changes were made anywhere; all additions are inline
text within existing flex/grid rows.

## Tests (TDD: RED confirmed before each GREEN)

- `tests/values.test.js`: `rainAmountText` — formats positive values to
  two decimals + `″`; returns `null` for 0, negative, `null`, `undefined`.
- `tests/forecast-detail.test.js`: `precipSumIn`/`precipIn` parsed when
  present; parsed as `null` (no throw) when absent from an
  otherwise-valid payload; legacy `"a"` → `precipSumIn`, defaulting to
  `null` when the legacy row omits `"a"`.
- `tests/ui/DailyForecast.test.js`: renders `data-testid="day-rain-amount"`
  with the rain color when `precipSumIn` is positive; renders none of that
  testid and no `″` anywhere in the container for zero/null/missing across
  three days in one render.
- `tests/ui/HourlyStrip.test.js` (new file): renders
  `data-testid="hour-rain-amount"` for a positive `row.a`; renders none for
  zero/null/missing `row.a` across three hours.
- `tests/ui/WeatherDetailModal.test.js`: two new tests assert the day
  summary and per-hour amounts render when positive and are wholly absent
  otherwise. Both use `vi.useFakeTimers()` pinned to a fixed timestamp
  before the fixture's forecast date, specifically so they don't inherit
  the same real-wall-clock-date coupling that makes the two pre-existing
  tests in this file flaky (see Concerns).

## Verification

- `npx vitest run`: 742 passed, 2 failed — both are the pre-existing
  `WeatherDetailModal` tests ("renders a complete ten-hour icon/value
  strip and SVG chart" and "announces stale and partial forecast
  coverage"). Confirmed identical failures on the unmodified base commit
  (`git stash` + rerun) before attributing them to time-of-day: today's
  real date (2026-07-19) now matches the fixture's hardcoded forecast
  date, which flips `selectForecastWindow` from `'daytime'` mode (all 10
  hours) to `'rolling'` mode (fewer hours, filtered by current wall-clock
  hour) — pre-existing coupling to `Date.now()`, unrelated to this change.
- `npm run test:e2e -- --workers=1`: 17/17 specs passed.
- `npm run build`: succeeded (pre-existing chunk-size warning only, not
  introduced by this change).

## Concerns

- The two pre-existing `WeatherDetailModal.test.js` tests are genuinely
  time-of-day/date flaky (not touched by this change, but now
  demonstrably failing due to the real clock date). Worth a follow-up to
  either fake the clock in those tests or parameterize the fixture date
  relative to `Date.now()`.
- `HourlyStrip.svelte` had no prior dedicated test file; added
  `tests/ui/HourlyStrip.test.js` net-new rather than extending an
  existing suite.
