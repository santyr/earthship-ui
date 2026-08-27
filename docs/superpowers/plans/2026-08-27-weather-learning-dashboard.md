# Weather Learning Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show current-local-day temperature extrema, correct partly-cloudy icons, add the Indoor sparkline, publish learned daily/hourly forecast temperatures, and expand forecast detail to 12 hours.

**Architecture:** Pure UI adapters own history extrema and forecast parsing; `Home.svelte` only orchestrates reads and layout. The OpenHAB producer owns correction/scoring so every consumer receives one corrected forecast, while raw provider values remain quarantined for learning.

**Tech Stack:** Svelte 5, Vitest, ECharts 6, Playwright, Python 3, pytest, OpenHAB REST/persistence.

## Global Constraints

- OpenHAB remains the durable store for measurements and learned forecast state.
- Raw forecasts are the only inputs to scoring; never score corrected values.
- Adjust only temperature and already-learned PV; wind, rain, and radiation remain raw.
- Hourly observations match within plus-or-minus 15 minutes; equal-distance ties use the earlier point.
- Hourly Kalman buckets use `b=0`, `P=10`, `Q=0.10`, `R=9`; blend weight is `min(count / 14, 1)`; published corrections clamp to plus-or-minus 20°F.
- Remove scored targets immediately, prune unscored targets after 72 hours, and retain at most 96 raw targets.
- Version 2 detail payloads contain required `temperatureAdjustment`; the UI remains compatible with version 1.
- Today detail means the next 12 whole hours; future detail means 07:00 through 18:00 local time.
- Preserve keyboard access, stale/partial/unavailable states, and 1340x800 plus 1280x720 layouts.

---

## File map

- Modify `src/lib/ui/homeCardState.js`: normalize current-condition icons and calculate extrema from history plus live value.
- Modify `tests/home-card-state.test.js`: pure adapter coverage.
- Modify `src/screens/Home.svelte`: fetch local-day temperature histories, refresh Indoor sparkline, and revise card markup/CSS.
- Modify `tests/home-tablet-contract.test.js`, `tests/e2e/home-runtime.spec.js`: Home integration and geometry.
- Modify `src/lib/weather/forecastDetail.js`: accept v1/v2 and select 12-hour windows.
- Modify `tests/forecast-detail.test.js`: parser/window/DST coverage.
- Modify `src/lib/ui/WeatherDetailModal.svelte`, `tests/ui/WeatherDetailModal.test.js`, `tests/e2e/weather-detail-modal.spec.js`: 12-hour copy and rendering.
- Modify `openhab/scripts/forecast_intel.py`: daily/hourly correction, capture, scoring, pruning, and v2 publication.
- Modify `openhab/scripts/test_forecast_intel.py`: raw-only learning and payload contract tests.
- Modify `tests/ui/Weather.test.js`, `tests/ui/DailyForecast.test.js`: v2 corrected daily rendering regression.

### Task 1: Pure current-day extrema and condition-icon adapters

**Files:**
- Modify: `src/lib/ui/homeCardState.js`
- Modify: `tests/home-card-state.test.js`

**Interfaces:**
- Produces: `historyExtrema(points, currentValue) -> { high: number|null, low: number|null }`
- Produces: `outdoorConditionIcon(value) -> string`
- Consumes: OpenHAB history rows shaped as `{ time, state }` and existing unit-tolerant `num()`.

- [ ] **Step 1: Write failing adapter tests**

Add tests that exercise units, bad rows, the live fallback, and aliases:

```js
import { historyExtrema, outdoorConditionIcon } from '../src/lib/ui/homeCardState.js';

it('computes extrema from valid persisted states plus the live value', () => {
  expect(historyExtrema([
    { time: 1, state: '68.5 °F' },
    { time: 2, state: 'UNDEF' },
    { time: 3, state: '72.0' },
  ], '66 °F')).toEqual({ high: 72, low: 66 });
  expect(historyExtrema([], 'NULL')).toEqual({ high: null, low: null });
});

it.each([
  ['Partly Cloudy', 'iconify:mdi:weather-partly-cloudy'],
  ['partially cloudy', 'iconify:mdi:weather-partly-cloudy'],
  ['weather-night-partly-cloudy', 'iconify:mdi:weather-night-partly-cloudy'],
])('normalizes current condition %s', (raw, expected) => {
  expect(outdoorConditionIcon(raw)).toBe(expected);
});
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `npm test -- tests/home-card-state.test.js`

Expected: FAIL because `historyExtrema` is not exported and the textual aliases are passed through.

- [ ] **Step 3: Add the minimal pure implementations**

Add beside `maxHistoryValue`:

```js
export function historyExtrema(points, currentValue = null) {
  const values = Array.isArray(points)
    ? points.map((point) => finiteNumber(point?.state)).filter((value) => value !== null)
    : [];
  const current = finiteNumber(currentValue);
  if (current !== null) values.push(current);
  return values.length
    ? { high: Math.max(...values), low: Math.min(...values) }
    : { high: null, low: null };
}

export function outdoorConditionIcon(value) {
  const raw = value == null ? '' : String(value).trim();
  if (!raw || raw === 'NULL' || raw === 'UNDEF') return 'iconify:mdi:weather-partly-cloudy';
  const normalized = raw.toLowerCase().replaceAll('_', '-').replace(/\s+/g, '-');
  if (normalized.includes('night') && /part(?:ly|ially)-cloudy/.test(normalized)) {
    return 'iconify:mdi:weather-night-partly-cloudy';
  }
  if (/part(?:ly|ially)-cloudy/.test(normalized)) return 'iconify:mdi:weather-partly-cloudy';
  return raw;
}
```

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run: `npm test -- tests/home-card-state.test.js tests/ui/wmo-colors.test.js tests/wmo.test.js`

Expected: all tests PASS.

- [ ] **Step 5: Commit the adapter slice**

```bash
git add src/lib/ui/homeCardState.js tests/home-card-state.test.js
git commit -m "feat: add current-day weather adapters"
```

### Task 2: Current-day extrema and Indoor sparkline on Home

**Files:**
- Modify: `src/screens/Home.svelte`
- Modify: `tests/home-tablet-contract.test.js`
- Modify: `tests/e2e/home-runtime.spec.js`

**Interfaces:**
- Consumes: `historyExtrema(points, currentValue)` from Task 1.
- Produces: reactive `outdoorToday`, `indoorToday`, `indoorSpark`; refreshed every five minutes.

- [ ] **Step 1: Write failing source-contract and runtime tests**

Replace the old Bitcoin-history assertion only in the Bitcoin plan; here add:

```js
it('uses local-day temperature extrema and renders an Indoor sparkline', () => {
  expect(home).toContain("fetchHistoryRange('AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature'");
  expect(home).toContain("fetchHistoryRange('AmbientWeatherWS2902A_IndoorSensor_Temperature'");
  expect(home).toContain("fetchHistorySafe('AmbientWeatherWS2902A_IndoorSensor_Temperature', 6)");
  expect(home).toContain('<Sparkline data={indoorSpark}');
  expect(home).not.toContain('OutdoorTemp_24h_High');
  expect(home).not.toContain('IndoorTemp_24h_High');
});
```

Extend the Home Playwright REST fixture with current-day history values and assert the rendered `H`/`L` text reflects those values rather than the fixture's 24-hour items. Assert `.indoor-spark` has positive width and does not intersect `.indoor-reading` or `.indoor-meta` at both configured viewports.

- [ ] **Step 2: Run tests and confirm RED**

Run: `npm test -- tests/home-tablet-contract.test.js && npm run test:e2e -- tests/e2e/home-runtime.spec.js`

Expected: contract failure for missing Indoor sparkline and runtime extrema/layout failures.

- [ ] **Step 3: Implement Home history state and refresh**

Import `historyExtrema`, add `indoorSpark`, `outdoorTodayHistory`, and `indoorTodayHistory`, then use one refresh:

```js
async function refreshTemperatureHistory() {
  const range = localDayHistoryRange(new Date());
  const [outdoorDay, indoorDay, indoorSixHours] = await Promise.all([
    fetchHistoryRange('AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', range.starttime, range.endtime),
    fetchHistoryRange('AmbientWeatherWS2902A_IndoorSensor_Temperature', range.starttime, range.endtime),
    fetchHistorySafe('AmbientWeatherWS2902A_IndoorSensor_Temperature', 6),
  ]);
  outdoorTodayHistory = outdoorDay;
  indoorTodayHistory = indoorDay;
  indoorSpark = indoorSixHours;
}

const outdoorToday = $derived(historyExtrema(outdoorTodayHistory, outdoorTemp));
const indoorToday = $derived(historyExtrema(indoorTodayHistory, indoorTemp));
```

Call it on mount and in the existing five-minute refresh. Keep `refreshOutdoorSpark()` for the six-hour outdoor chart.

- [ ] **Step 4: Revise card markup and CSS**

Use `outdoorToday.high/low` and `indoorToday.high/low`. Change Indoor to a reading/meta column plus:

```svelte
<div class="indoor-spark">
  <Sparkline data={indoorSpark} color={indoorIconColor} lineWidth={2} />
</div>
```

Define `.indoor-body` as a two-column grid matching Outdoor, give `.indoor-spark` `min-width:0; min-height:0; overflow:hidden`, and add viewport-specific gaps/font reductions only where Playwright proves necessary.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run: `npm test -- tests/home-card-state.test.js tests/home-tablet-contract.test.js && npm run test:e2e -- tests/e2e/home-runtime.spec.js`

Expected: all tests PASS at 1340x800 and 1280x720.

- [ ] **Step 6: Commit the Home temperature slice**

```bash
git add src/screens/Home.svelte tests/home-tablet-contract.test.js tests/e2e/home-runtime.spec.js
git commit -m "feat: show current-day temperature trends"
```

### Task 3: Twelve-hour forecast selection

**Files:**
- Modify: `src/lib/weather/forecastDetail.js`
- Modify: `tests/forecast-detail.test.js`
- Modify: `src/lib/ui/WeatherDetailModal.svelte`
- Modify: `tests/ui/WeatherDetailModal.test.js`
- Modify: `tests/e2e/weather-detail-modal.spec.js`

**Interfaces:**
- Produces: `selectForecastWindow(result, date, { nowMs }) -> { mode, hours, missingHours }` with expected count 12.
- Consumes: normalized offset-aware hourly records from `parseForecast10Day`.

- [ ] **Step 1: Change pure-window tests to the approved 12-hour contract**

Assert Today at 20:32 returns 21:00 through 08:00 (12 rows), future dates return 07:00 through 18:00, partial 07:00-14:00 reports `missingHours: 4`, and repeated DST hours remain instant-sorted.

```js
expect(selected.hours).toHaveLength(12);
expect(selected.hours.map(({ at }) => at.slice(11, 13))).toEqual([
  '07', '08', '09', '10', '11', '12', '13', '14', '15', '16', '17', '18',
]);
```

- [ ] **Step 2: Run parser tests and confirm RED**

Run: `npm test -- tests/forecast-detail.test.js`

Expected: FAIL with existing 10-hour length and 08:00 start.

- [ ] **Step 3: Implement the exact window constants**

In `forecastDetail.js` define:

```js
export const FORECAST_DETAIL_HOURS = 12;
const FUTURE_DAY_START_HOUR = 7;
const FUTURE_DAY_END_HOUR = 18;
```

Use 12 in rolling slicing and missing counts. Filter future hours inclusively by local timestamp hour 7 through 18; do not synthesize absent periods.

- [ ] **Step 4: Update modal component tests and copy**

Make the fixture generate 12 hours beginning at 07:00. Assert 12 rendered periods and partial status `7 of 12 hours available`. Replace hard-coded ten-hour accessibility/copy expectations in `WeatherDetailModal.svelte` with `FORECAST_DETAIL_HOURS`.

- [ ] **Step 5: Run modal tests and confirm GREEN**

Run: `npm test -- tests/forecast-detail.test.js tests/ui/WeatherDetailModal.test.js tests/ui/weather-icon-colors.test.js`

Expected: all tests PASS.

- [ ] **Step 6: Update and run modal browser coverage**

Change the fixture and assertions in `tests/e2e/weather-detail-modal.spec.js` to 12 periods and 07:00-18:00. Run:

`npm run test:e2e -- tests/e2e/weather-detail-modal.spec.js`

Expected: PASS.

- [ ] **Step 7: Commit the 12-hour slice**

```bash
git add src/lib/weather/forecastDetail.js tests/forecast-detail.test.js src/lib/ui/WeatherDetailModal.svelte tests/ui/WeatherDetailModal.test.js tests/e2e/weather-detail-modal.spec.js
git commit -m "feat: expand forecast detail to twelve hours"
```

### Task 4: Version 2 corrected daily forecast contract

**Files:**
- Modify: `openhab/scripts/forecast_intel.py`
- Modify: `openhab/scripts/test_forecast_intel.py`
- Modify: `src/lib/weather/forecastDetail.js`
- Modify: `tests/forecast-detail.test.js`
- Modify: `tests/ui/Weather.test.js`
- Modify: `tests/ui/DailyForecast.test.js`

**Interfaces:**
- Produces: `build_forecast_payloads(snapshot, pv_per_day, now, temperature_adjustment=None)`.
- Produces: detail v2 root field `temperatureAdjustment` with `highCorrectionF`, `lowCorrectionF`, `hourlyMethod`, and `hourBuckets`.
- Consumes: daily corrections where correction equals negative learned bias.

- [ ] **Step 1: Add failing producer contract tests**

Construct corrections `highCorrectionF=2.5`, `lowCorrectionF=-9.0`, and assert both legacy daily and v2 detail summaries are adjusted while precip, wind, radiation, and raw snapshot objects are byte-for-byte unchanged.

```python
legacy_hourly, legacy_daily, detail = fi.build_forecast_payloads(
    snapshot, [6.4], now, temperature_adjustment=adjustment
)
assert detail["version"] == 2
assert detail["temperatureAdjustment"] == adjustment
assert legacy_daily[0]["hi"] == round(raw_hi + 2.5)
assert detail["days"][0]["summary"]["lowF"] == raw_lo - 9.0
assert snapshot == original_snapshot
```

- [ ] **Step 2: Run producer tests and confirm RED**

Run: `pytest -q openhab/scripts/test_forecast_intel.py`

Expected: FAIL because the fourth argument and v2 contract do not exist.

- [ ] **Step 3: Add correction plumbing without hourly learning**

Add a normalizer that defaults missing/non-finite corrections to zero, creates the required provenance object, and applies daily corrections only to copied output values. `build_json_items()` loads `kalman.hi.b` and `kalman.lo.b` on standalone refresh and passes their negations. Main passes the same post-scoring state. Do not alter `st["predictions"]` raw `hi`/`lo` writes.

- [ ] **Step 4: Add failing v1/v2 UI parser tests**

Assert v1 still parses, v2 requires a valid `temperatureAdjustment`, unsupported version 3 rejects, and v2 exposes normalized provenance without changing day values.

- [ ] **Step 5: Implement dual-version parsing**

Refactor the version guard to accept 1 or 2. For v2 validate finite corrections, `hourlyMethod` in `['daily-fallback', 'hourly-blend']`, and a 24-entry count/weight array. Return `temperatureAdjustment: null` for v1 and the frozen normalized object for v2.

- [ ] **Step 6: Run producer and UI contract tests**

Run: `pytest -q openhab/scripts/test_forecast_intel.py && npm test -- tests/forecast-detail.test.js tests/ui/Weather.test.js tests/ui/DailyForecast.test.js`

Expected: all tests PASS.

- [ ] **Step 7: Commit the daily contract slice**

```bash
git add openhab/scripts/forecast_intel.py openhab/scripts/test_forecast_intel.py src/lib/weather/forecastDetail.js tests/forecast-detail.test.js tests/ui/Weather.test.js tests/ui/DailyForecast.test.js
git commit -m "feat: publish learned daily forecast values"
```

### Task 5: Raw hourly capture and bias learning

**Files:**
- Modify: `openhab/scripts/forecast_intel.py`
- Modify: `openhab/scripts/test_forecast_intel.py`

**Interfaces:**
- Produces: `hourly_model_seed()`, `capture_next_day_hourly(snapshot, now)`, `score_hourly_targets(state, now)`, and `hourly_temperature_correction(raw, raw_low, raw_high, low_correction, high_correction, bucket)`.
- Consumes: OpenHAB outdoor persistence and additive state keys `hourly_temp_model`, `hourly_temp_targets`.

- [ ] **Step 1: Write failing pure learning tests**

Cover 24 seeded buckets, nearest observation/tie behavior, `raw-measured` innovation, count increments, no correction feedback, 14-sample full weight, plus-or-minus 20°F clamp, target pruning, 96-target bound, and DST offset-aware keys.

```python
def test_hourly_blend_moves_from_daily_fallback_to_bucket_bias():
    bucket = {"b": 4.0, "P": 1.0, "count": 7}
    # raw 50 is halfway from daily 40..60; fallback correction is (-8 + 2)/2 = -3
    assert fi.hourly_temperature_correction(50, 40, 60, -8, 2, bucket) == -3.5

def test_hourly_correction_clamps():
    assert fi.hourly_temperature_correction(50, 40, 60, -50, -50, {"b": 0, "P": 1, "count": 0}) == -20
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `pytest -q openhab/scripts/test_forecast_intel.py -k hourly`

Expected: FAIL because hourly model functions are absent.

- [ ] **Step 3: Implement state defaults, migration, capture, and pruning**

Add 24 string-keyed buckets, raw targets keyed by offset-aware ISO timestamp, next-local-day capture only, immediate scored removal, 72-hour stale pruning, and newest-96 bounding. Merge missing keys through existing `load_state()` defaults without overwriting prior state.

- [ ] **Step 4: Implement observation matching and Kalman updates**

Query persistence once for the elapsed target span. Normalize rows to instants, choose the closest point within 900 seconds with `(absolute distance, timestamp)` ordering, update only the local-hour bucket from `raw - measured`, increment count once, and remove only successfully scored targets.

- [ ] **Step 5: Implement deterministic fallback/blending**

Use:

```python
position = clamp((raw - raw_low) / (raw_high - raw_low), 0.0, 1.0) if raw_high > raw_low else 0.5
fallback = low_correction + position * (high_correction - low_correction)
learned = -bucket["b"]
weight = min(bucket["count"] / 14.0, 1.0)
return round(clamp(fallback * (1 - weight) + learned * weight, -20.0, 20.0), 1)
```

- [ ] **Step 6: Run hourly tests and confirm GREEN**

Run: `pytest -q openhab/scripts/test_forecast_intel.py -k 'hourly or state'`

Expected: all selected tests PASS.

- [ ] **Step 7: Commit the learning engine**

```bash
git add openhab/scripts/forecast_intel.py openhab/scripts/test_forecast_intel.py
git commit -m "feat: learn hourly site temperature bias"
```

### Task 6: Apply hourly corrections to every forecast surface

**Files:**
- Modify: `openhab/scripts/forecast_intel.py`
- Modify: `openhab/scripts/test_forecast_intel.py`
- Modify: `tests/ui/HourlyStrip.test.js`
- Modify: `tests/ui/WeatherDetailModal.test.js`

**Interfaces:**
- Consumes: hourly functions/state from Task 5 and v2 contract from Task 4.
- Produces: identical corrected temperature for a timestamp in legacy hourly JSON and detail v2 JSON.

- [ ] **Step 1: Write failing end-to-end payload tests**

Use one snapshot with known daily range and populated buckets. Assert legacy `t` equals rounded corrected detail `tempF`; daily summary uses daily correction; raw precipitation/radiation/wind/code remain equal to the provider; standalone refresh reads state but does not update bucket count or targets.

- [ ] **Step 2: Run producer tests and confirm RED**

Run: `pytest -q openhab/scripts/test_forecast_intel.py -k 'payload or refresh or correction'`

Expected: FAIL because hourly output remains raw.

- [ ] **Step 3: Apply correction once during payload construction**

For each provider hour, compute one corrected value from its day's raw low/high and local-hour bucket, then reuse it in both legacy/detail output objects. Populate `temperatureAdjustment.hourBuckets` with `{hour, count, weight}` and set `hourlyMethod` to `hourly-blend` when any count is positive, otherwise `daily-fallback`.

- [ ] **Step 4: Add UI rendering regression assertions**

Feed corrected v2 values to `HourlyStrip` and `WeatherDetailModal`; assert the exact corrected text appears and no client-side correction item is read or added.

- [ ] **Step 5: Run the complete focused weather suite**

Run: `pytest -q openhab/scripts/test_forecast_intel.py && npm test -- tests/forecast-detail.test.js tests/home-card-state.test.js tests/home-tablet-contract.test.js tests/ui/HourlyStrip.test.js tests/ui/DailyForecast.test.js tests/ui/WeatherDetailModal.test.js tests/ui/Weather.test.js tests/ui/weather-icon-colors.test.js tests/ui/wmo-colors.test.js`

Expected: all tests PASS.

- [ ] **Step 6: Commit corrected hourly publication**

```bash
git add openhab/scripts/forecast_intel.py openhab/scripts/test_forecast_intel.py tests/ui/HourlyStrip.test.js tests/ui/WeatherDetailModal.test.js
git commit -m "feat: display learned hourly forecasts"
```

### Task 7: Weather integration verification

**Files:**
- Modify only if a failing assertion identifies a real defect: files already listed above.

**Interfaces:**
- Consumes: all weather tasks.
- Produces: verified weather/temperature subsystem.

- [ ] **Step 1: Run Python syntax and producer tests**

Run: `python3 -m py_compile openhab/scripts/forecast_intel.py && pytest -q openhab/scripts/test_forecast_intel.py`

Expected: syntax succeeds and all tests PASS.

- [ ] **Step 2: Run the full unit suite**

Run: `npm test`

Expected: all Vitest tests PASS with no unhandled errors.

- [ ] **Step 3: Run production build**

Run: `npm run build`

Expected: Vite exits 0 and writes `dist/`.

- [ ] **Step 4: Run weather/Home browser checks**

Run: `npm run test:e2e -- tests/e2e/home-runtime.spec.js tests/e2e/weather-detail-modal.spec.js tests/e2e/weather-earthship-layout.spec.js`

Expected: all checks PASS at the specified viewports, with 12 forecast periods and no Indoor/Outdoor overlap.

- [ ] **Step 5: Inspect the final diff and commit any verified integration fix**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only intentional files appear. If verification required a fix, stage only that fix and commit `fix: close weather dashboard integration gaps`.
