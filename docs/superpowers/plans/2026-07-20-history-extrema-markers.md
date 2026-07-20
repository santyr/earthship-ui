# History Extrema Markers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reusable selected-period High and Low markers to the measured Outdoor Temperature and Battery SoC history modals.

**Architecture:** A pure chart utility computes deterministic extrema from normalized selected-window points and creates explicit ECharts `markPoint` records plus matching accessible text. `buildHistoryOption()` applies that utility only when a series opts in with `markers`, while `ChartModal` derives its screen-reader summary from the exact rendered marker records. Home enables the shared contract for measured Outdoor and Battery SoC only.

**Tech Stack:** Svelte 5, JavaScript ES modules, ECharts 6, Vitest, Testing Library, Playwright

## Global Constraints

- High and Low come from the history returned for the currently selected 4h, 24h, or 7d period.
- Outdoor markers apply only to measured Outdoor data, never to Forecast.
- Battery markers apply to `BMS_SOC`.
- The reusable series contract is `markers: ['min', 'max']` plus `markerUnit`.
- Series without `markers` retain their current rendering.
- Visual and accessible extrema values must come from the same marker records.
- Do not add openHAB requests, fixed 24-hour extrema items, or synthetic history series.
- Preserve existing history normalization, downsampling, gaps, tooltips, forecasts, refreshes, and partial-failure behavior.
- Validate the household targets at 1340x800 and 1280x720.

---

## File Structure

- Create `src/lib/charts/extremaMarkers.js`: pure extrema selection, marker construction, value formatting, and accessible marker description.
- Create `tests/chart-extrema-markers.test.js`: focused contract tests for the shared utility.
- Modify `src/lib/charts/options.js`: attach reusable marker output to opted-in rendered series.
- Modify `src/lib/charts/echarts.js`: register tree-shaken `MarkPointComponent` support.
- Modify `tests/chart-options.test.js`: verify marked and unmarked series behavior.
- Modify `tests/chart-imports.test.js`: verify marker component registration.
- Modify `src/lib/ui/ChartModal.svelte`: announce the exact extrema currently rendered.
- Modify `tests/ui/ChartModal.test.js`: verify period-dependent marker and accessibility updates.
- Modify `src/lib/ui/chartStore.js`: document the optional series marker fields.
- Modify `src/screens/Home.svelte`: opt measured Outdoor and Battery SoC into min/max markers.
- Modify `tests/chart-call-sites.test.js`: lock the two Home configurations and measured-only Outdoor boundary.
- Modify `tests/e2e/home-runtime.spec.js`: verify and capture visible marker pins at both household viewports.

### Task 1: Reusable Extrema Marker Utility

**Files:**
- Create: `src/lib/charts/extremaMarkers.js`
- Create: `tests/chart-extrema-markers.test.js`

**Interfaces:**
- Produces: `formatHistoryValue(value: unknown) -> string`.
- Produces: `findHistoryExtrema(points: Array<object>) -> { min: object|null, max: object|null }`.
- Produces: `buildExtremaMarkPoint(points: Array<object>, options: object) -> object|undefined`.
- Produces: `describeExtremaMarkers(renderedSeries: Array<object>) -> string`.

- [ ] **Step 1: Write the failing utility tests**

Create `tests/chart-extrema-markers.test.js`:

```js
import { describe, expect, it } from 'vitest';
import {
  buildExtremaMarkPoint,
  describeExtremaMarkers,
  findHistoryExtrema,
} from '../src/lib/charts/extremaMarkers.js';

describe('history extrema markers', () => {
  it('selects the earliest matching extrema without mutating normalized points', () => {
    const points = [
      { time: 300, value: 9, rawValue: 9.1234 },
      { time: 100, value: 9, rawValue: 9 },
      { time: 200, value: 1, rawValue: 1.25 },
      { time: 400, value: 1, rawValue: 1 },
    ];
    const snapshot = structuredClone(points);

    expect(findHistoryExtrema(points)).toEqual({
      min: { time: 200, value: 1, rawValue: 1.25 },
      max: { time: 100, value: 9, rawValue: 9 },
    });
    expect(points).toEqual(snapshot);
  });

  it('ignores unusable points and returns no marker config for empty data', () => {
    expect(findHistoryExtrema([
      { time: 1, value: Number.NaN },
      { time: Number.NaN, value: 5 },
    ])).toEqual({ min: null, max: null });
    expect(buildExtremaMarkPoint([], { markers: ['min', 'max'] })).toBeUndefined();
  });

  it('builds High and Low pins with units and matching accessible text', () => {
    const markPoint = buildExtremaMarkPoint([
      { time: 100, value: 62, rawValue: 62 },
      { time: 200, value: 87.5555, rawValue: 87.5555 },
      { time: 300, value: 41.25, rawValue: 41.25 },
    ], {
      markers: ['min', 'max'],
      unit: '%',
      color: '#22c55e',
    });

    expect(markPoint.data).toEqual([
      { name: 'High', coord: [200, 87.5555], value: 87.5555, markerUnit: '%' },
      { name: 'Low', coord: [300, 41.25], value: 41.25, markerUnit: '%' },
    ]);
    expect(markPoint.itemStyle.color).toBe('#22c55e');
    expect(markPoint.label.formatter({
      name: 'High',
      value: 87.5555,
      data: markPoint.data[0],
    })).toBe('High\n87.556%');
    expect(describeExtremaMarkers([{ name: 'SoC', markPoint }]))
      .toBe('SoC: High 87.556%, Low 41.25%.');
  });

  it('supports either marker independently', () => {
    const points = [
      { time: 100, value: 10, rawValue: 10 },
      { time: 200, value: 20, rawValue: 20 },
    ];

    expect(buildExtremaMarkPoint(points, { markers: ['min'] }).data)
      .toEqual([{ name: 'Low', coord: [100, 10], value: 10, markerUnit: '' }]);
    expect(buildExtremaMarkPoint(points, { markers: ['max'] }).data)
      .toEqual([{ name: 'High', coord: [200, 20], value: 20, markerUnit: '' }]);
  });
});
```

- [ ] **Step 2: Run the utility tests and verify RED**

Run:

```bash
npm test -- tests/chart-extrema-markers.test.js
```

Expected: FAIL because `src/lib/charts/extremaMarkers.js` does not exist.

- [ ] **Step 3: Implement the pure utility**

Create `src/lib/charts/extremaMarkers.js`:

```js
export function formatHistoryValue(value) {
  if (!Number.isFinite(value)) return '—';
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(3)));
}

function candidate(point) {
  const time = point?.time;
  const value = point?.value;
  if (!Number.isFinite(time) || !Number.isFinite(value)) return null;
  const rawValue = point?.rawValue;
  return {
    time,
    value,
    rawValue: Number.isFinite(rawValue) ? rawValue : value,
  };
}

export function findHistoryExtrema(points = []) {
  let min = null;
  let max = null;
  for (const point of points) {
    const next = candidate(point);
    if (!next) continue;
    if (!min || next.value < min.value || (next.value === min.value && next.time < min.time)) {
      min = next;
    }
    if (!max || next.value > max.value || (next.value === max.value && next.time < max.time)) {
      max = next;
    }
  }
  return { min, max };
}

function markerRecord(name, point, unit) {
  return {
    name,
    coord: [point.time, point.value],
    value: point.rawValue,
    markerUnit: unit,
  };
}

export function buildExtremaMarkPoint(points = [], {
  markers = [],
  unit = '',
  color,
} = {}) {
  const enabled = new Set(markers);
  const extrema = findHistoryExtrema(points);
  const data = [];
  if (enabled.has('max') && extrema.max) {
    data.push(markerRecord('High', extrema.max, unit));
  }
  if (enabled.has('min') && extrema.min) {
    data.push(markerRecord('Low', extrema.min, unit));
  }
  if (!data.length) return undefined;
  return {
    symbol: 'pin',
    symbolSize: 52,
    ...(color ? { itemStyle: { color } } : {}),
    label: {
      color: '#f8fafc',
      fontSize: 10,
      lineHeight: 12,
      formatter: ({ data: marker, name, value }) => (
        `${name}\n${formatHistoryValue(value)}${marker?.markerUnit ?? unit}`
      ),
    },
    data,
  };
}

export function describeExtremaMarkers(renderedSeries = []) {
  return renderedSeries.flatMap((series) => {
    const markers = series?.markPoint?.data;
    if (!Array.isArray(markers) || !markers.length) return [];
    const values = markers.map((marker) => (
      `${marker.name} ${formatHistoryValue(marker.value)}${marker.markerUnit || ''}`
    ));
    return [`${series.name}: ${values.join(', ')}.`];
  }).join(' ');
}
```

- [ ] **Step 4: Run the utility tests and verify GREEN**

Run:

```bash
npm test -- tests/chart-extrema-markers.test.js
```

Expected: `4 passed`.

- [ ] **Step 5: Commit the utility**

```bash
git add src/lib/charts/extremaMarkers.js tests/chart-extrema-markers.test.js
git commit -m "feat: add reusable history extrema markers"
```

### Task 2: ECharts History Option Integration

**Files:**
- Modify: `src/lib/charts/options.js:1-130`
- Modify: `src/lib/charts/echarts.js:1-13`
- Modify: `tests/chart-options.test.js`
- Modify: `tests/chart-imports.test.js`

**Interfaces:**
- Consumes: `buildExtremaMarkPoint(points, { markers, unit, color })` from Task 1.
- Produces: opted-in ECharts line options with `markPoint`; unchanged options for unmarked series.

- [ ] **Step 1: Add failing option and registration tests**

Append to `tests/chart-options.test.js` inside the existing `describe` block:

```js
  it('adds selected-window extrema only to an opted-in series', () => {
    const option = buildHistoryOption({
      series: [
        {
          name: 'Outdoor',
          label: 'Outdoor',
          color: '#f59e0b',
          markers: ['min', 'max'],
          markerUnit: '°',
        },
        { name: 'Forecast', label: 'Forecast', color: '#8b5cf6' },
      ],
      pointsPerSeries: [
        [
          { time: 100, state: 54 },
          { time: 200, state: 82.5 },
          { time: 300, state: 41 },
        ],
        [
          { time: 100, state: 50 },
          { time: 200, state: 90 },
        ],
      ],
      widthPx: 800,
    });

    expect(option.series[0].markPoint.data).toEqual([
      { name: 'High', coord: [200, 82.5], value: 82.5, markerUnit: '°' },
      { name: 'Low', coord: [300, 41], value: 41, markerUnit: '°' },
    ]);
    expect(option.series[1]).not.toHaveProperty('markPoint');
  });
```

Add this assertion to `tests/chart-imports.test.js` after the `BarChart` assertion:

```js
    expect(adapter).toMatch(/MarkPointComponent/);
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
npm test -- tests/chart-options.test.js tests/chart-imports.test.js
```

Expected: the option test fails because `markPoint` is absent, and the import test fails because `MarkPointComponent` is not registered.

- [ ] **Step 3: Attach extrema markers in the shared option builder**

At the top of `src/lib/charts/options.js`, add:

```js
import { buildExtremaMarkPoint, formatHistoryValue } from './extremaMarkers.js';
```

Delete the private `formatRawValue()` function and replace its tooltip use with `formatHistoryValue(entry.data[2])`.

Replace `lineOption()` with:

```js
function lineOption(source, data, {
  name,
  dashed = false,
  markPoint,
} = {}) {
  return {
    name: name || source.label || source.name,
    type: 'line',
    showSymbol: false,
    smooth: false,
    connectNulls: false,
    dimensions: ['time', 'display', 'raw'],
    encode: { x: 'time', y: 'display' },
    lineStyle: {
      width: 2,
      color: source.color,
      ...(dashed ? { type: 'dashed' } : {}),
    },
    itemStyle: { color: source.color },
    ...(markPoint ? { markPoint } : {}),
    data,
  };
}
```

Immediately after each `prepared` value is created inside `series.forEach`, add:

```js
    const markPoint = buildExtremaMarkPoint(prepared.raw, {
      markers: source.markers,
      unit: source.markerUnit,
      color: source.color,
    });
```

Pass `{ markPoint }` to the primary `lineOption()` in both branches. In the forecast branch, keep the projected `(forecast)` line unmarked:

```js
      renderedSeries.push(lineOption(
        source,
        flattenSegments(split.solid),
        { markPoint },
      ));
```

```js
      renderedSeries.push(lineOption(
        source,
        flattenSegments(prepared.displaySegments),
        { markPoint },
      ));
```

- [ ] **Step 4: Register ECharts mark-point support**

In `src/lib/charts/echarts.js`, replace the components import with:

```js
import {
  GridComponent,
  LegendComponent,
  MarkPointComponent,
  TooltipComponent,
} from 'echarts/components';
```

Add `MarkPointComponent` to the `echarts.use([...])` list.

- [ ] **Step 5: Run focused chart tests and verify GREEN**

Run:

```bash
npm test -- tests/chart-extrema-markers.test.js tests/chart-options.test.js tests/chart-imports.test.js
```

Expected: all focused tests pass.

- [ ] **Step 6: Commit shared chart integration**

```bash
git add src/lib/charts/options.js src/lib/charts/echarts.js tests/chart-options.test.js tests/chart-imports.test.js
git commit -m "feat: render selected-period extrema markers"
```

### Task 3: Accessible Period-Dependent Modal Updates

**Files:**
- Modify: `src/lib/ui/ChartModal.svelte:1-175`
- Modify: `tests/ui/ChartModal.test.js`

**Interfaces:**
- Consumes: `describeExtremaMarkers(renderedSeries)` from Task 1.
- Produces: the modal description announces extrema from the exact latest ECharts option.

- [ ] **Step 1: Write the failing period-update test**

Append this test to `tests/ui/ChartModal.test.js`:

```js
  it('recomputes and announces extrema when the selected period changes', async () => {
    mocks.getHistory
      .mockResolvedValueOnce([
        { time: 100, state: '62 %' },
        { time: 200, state: '71 %' },
      ])
      .mockResolvedValueOnce([
        { time: 100, state: '41 %' },
        { time: 200, state: '88 %' },
      ]);

    render(ChartModal);
    openChart({
      title: 'Battery SoC',
      series: [{
        name: 'BMS_SOC',
        label: 'SoC',
        color: '#22c55e',
        markers: ['min', 'max'],
        markerUnit: '%',
      }],
      hours: 24,
    });

    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(1));
    let option = mocks.chart.setOption.mock.calls.at(-1)[0];
    expect(option.series[0].markPoint.data.map((marker) => marker.value))
      .toEqual([71, 62]);

    const dialog = screen.getByRole('dialog', { name: 'Battery SoC' });
    const description = document.getElementById(dialog.getAttribute('aria-describedby'));
    expect(description.textContent).toMatch(/SoC: High 71%, Low 62%/);

    await fireEvent.click(screen.getByRole('button', { name: '7d' }));
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(2));
    option = mocks.chart.setOption.mock.calls.at(-1)[0];
    expect(option.series[0].markPoint.data.map((marker) => marker.value))
      .toEqual([88, 41]);
    expect(description.textContent).toMatch(/SoC: High 88%, Low 41%/);
  });
```

- [ ] **Step 2: Run the modal test and verify RED**

Run:

```bash
npm test -- tests/ui/ChartModal.test.js
```

Expected: FAIL because the accessible description does not contain extrema.

- [ ] **Step 3: Feed rendered extrema into the accessible description**

In `src/lib/ui/ChartModal.svelte`, add:

```js
  import { describeExtremaMarkers } from '../charts/extremaMarkers.js';
```

Add state beside the existing error and loading state:

```js
  let extremaDescription = $state('');
```

In the `description` derived value, append extrema before the latest-value sentence:

```js
    const extrema = extremaDescription ? `${extremaDescription} ` : '';
    return `${labels}. ${period} selected. ${stateText}. ${extrema}${latest}.`;
```

In `loadAndRender()`, clear stale extrema immediately after clearing `errorMessage`:

```js
    extremaDescription = '';
```

In `renderLatest()`, build the option once, derive the summary from that exact option, and then render it:

```js
      const option = buildHistoryOption({
        series: latestSeries,
        pointsPerSeries,
        widthPx,
        nowMs: latestNowMs,
        grid: { left: 52, right: 24, top: 56, bottom: 40 },
        legendTop: 8,
        legendFontSize: 12,
      });
      extremaDescription = describeExtremaMarkers(option.series);
      chart.setOption(option, true);
```

- [ ] **Step 4: Run modal and shared chart tests and verify GREEN**

Run:

```bash
npm test -- tests/ui/ChartModal.test.js tests/chart-extrema-markers.test.js tests/chart-options.test.js
```

Expected: all focused tests pass.

- [ ] **Step 5: Commit modal accessibility behavior**

```bash
git add src/lib/ui/ChartModal.svelte tests/ui/ChartModal.test.js
git commit -m "feat: announce history extrema in chart modal"
```

### Task 4: Enable Outdoor and Battery Markers and Verify Viewports

**Files:**
- Modify: `src/lib/ui/chartStore.js:5-9`
- Modify: `src/screens/Home.svelte:345-368`
- Modify: `tests/chart-call-sites.test.js`
- Modify: `tests/e2e/home-runtime.spec.js`

**Interfaces:**
- Consumes: optional series fields `markers: Array<'min'|'max'>` and `markerUnit: string`.
- Produces: measured Outdoor markers in degrees and Battery SoC markers in percent.

- [ ] **Step 1: Add the failing Home call-site contract test**

Append to `tests/chart-call-sites.test.js`:

```js
describe('Home extrema marker call sites', () => {
  it('marks measured Outdoor and Battery SoC without marking Forecast', async () => {
    const source = await readFile('src/screens/Home.svelte', 'utf8');
    const outdoor = source.slice(
      source.indexOf('function openOutdoorChart()'),
      source.indexOf('function openIndoorChart()'),
    );
    const battery = source.slice(
      source.indexOf('function openBatteryChart()'),
      source.indexOf('function openWindChart()'),
    );

    expect(outdoor.match(/markers:\s*\['min', 'max'\]/g)).toHaveLength(1);
    expect(outdoor).toContain("markerUnit: '°'");
    expect(battery).toContain("markers: ['min', 'max']");
    expect(battery).toContain("markerUnit: '%'");
  });
});
```

- [ ] **Step 2: Run the call-site test and verify RED**

Run:

```bash
npm test -- tests/chart-call-sites.test.js
```

Expected: FAIL because neither Home series has marker configuration.

- [ ] **Step 3: Enable markers at the two Home call sites**

Update the measured Outdoor series in `openOutdoorChart()`:

```js
        {
          name: 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature',
          color: colors.temperature,
          label: 'Outdoor',
          markers: ['min', 'max'],
          markerUnit: '°',
        },
```

Keep the Forecast series unchanged.

Replace `openBatteryChart()` with:

```js
  function openBatteryChart() {
    openChart({
      title: 'Battery SoC',
      series: [{
        name: 'BMS_SOC',
        color: socColor,
        label: 'SoC',
        markers: ['min', 'max'],
        markerUnit: '%',
      }],
      hours: 24,
    });
  }
```

Update the series contract comment in `src/lib/ui/chartStore.js` to:

```js
// series: [{ name, color, label, markers?, markerUnit? }]
// `markers` supports reusable per-series extrema such as ['min', 'max'].
```

- [ ] **Step 4: Add visible marker checks to the Home viewport test**

In the settled-layout test in `tests/e2e/home-runtime.spec.js`, before the final page-error assertions, add:

```js
    await page.getByRole('button', { name: 'Open Outdoor temperature chart' }).click();
    let dialog = page.getByRole('dialog', { name: 'Outdoor Temp' });
    await expect(dialog.locator('svg')).toBeVisible();
    await expect(dialog.locator('text').filter({ hasText: 'High' })).toHaveCount(1);
    await expect(dialog.locator('text').filter({ hasText: 'Low' })).toHaveCount(1);
    await page.screenshot({ path: testInfo.outputPath('outdoor-extrema.png') });
    await page.getByRole('button', { name: 'Close chart' }).click();

    await page.getByRole('button', { name: /Open Battery chart/ }).click();
    dialog = page.getByRole('dialog', { name: 'Battery SoC' });
    await expect(dialog.locator('svg')).toBeVisible();
    await expect(dialog.locator('text').filter({ hasText: 'High' })).toHaveCount(1);
    await expect(dialog.locator('text').filter({ hasText: 'Low' })).toHaveCount(1);
    await page.screenshot({ path: testInfo.outputPath('battery-extrema.png') });
    await page.getByRole('button', { name: 'Close chart' }).click();
```

- [ ] **Step 5: Run focused call-site and modal tests**

Run:

```bash
npm test -- tests/chart-call-sites.test.js tests/chart-options.test.js tests/ui/ChartModal.test.js
```

Expected: all focused tests pass.

- [ ] **Step 6: Run the full unit suite and production build**

Run:

```bash
npm test
npm run build
```

Expected: all Vitest tests pass and the Vite production build exits `0` without errors.

- [ ] **Step 7: Run both household viewport checks**

Run:

```bash
npm run test:e2e -- tests/e2e/home-runtime.spec.js
```

Expected: all Home runtime tests pass at `m9-1340x800` and `laptop-1280x720`, producing Outdoor and Battery extrema screenshots for each settled-layout case.

- [ ] **Step 8: Inspect the four marker screenshots**

Use the local image viewer on each generated `outdoor-extrema.png` and
`battery-extrema.png`. Verify both pins are visible, labels are readable,
the High pin is not clipped at the top, the Low pin is not clipped at the
bottom, the Forecast line has no pin, and the modal controls remain usable.

- [ ] **Step 9: Commit Home enablement and viewport coverage**

```bash
git add src/lib/ui/chartStore.js src/screens/Home.svelte tests/chart-call-sites.test.js tests/e2e/home-runtime.spec.js
git commit -m "feat: mark outdoor and battery history extrema"
```

### Task 5: Final Verification and Durable Outcome

**Files:**
- Verify only; no production files added.

**Interfaces:**
- Consumes: all preceding task outputs.
- Produces: fresh completion evidence and an operator-approved Hexmem outcome.

- [ ] **Step 1: Re-run the complete verification battery**

Run:

```bash
npm test
npm run build
npm run test:e2e -- tests/e2e/home-runtime.spec.js
```

Expected: every command exits `0`.

- [ ] **Step 2: Verify repository scope**

Run:

```bash
git status --short
git log -5 --oneline
```

Expected: only pre-existing user-owned `test-results/` artifacts may remain untracked; no intended source or test file is uncommitted.

- [ ] **Step 3: Record the verified outcome in Hexmem**

Record that selected-period, reusable High/Low markers are enabled for
measured Outdoor Temperature and Battery SoC; Forecast remains unmarked;
accessible values use the same marker records; and include the fresh test,
build, and viewport evidence. Do not store tokens, credentials, or raw
runtime payloads.
