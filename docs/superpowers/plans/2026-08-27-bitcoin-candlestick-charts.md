# Bitcoin Candlestick Charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render honest OHLC candles derived from persisted Bitcoin spot-price observations in both the Home card and the existing history modal.

**Architecture:** A pure Bitcoin candle module validates and aggregates persisted rows, then builds compact/full ECharts options. A focused compact Svelte component renders Home candles; the existing chart store/modal gains an explicit `candlestick` presentation while retaining its current request, cancellation, refresh, period, focus, and error paths.

**Tech Stack:** Svelte 5, ECharts 6, Vitest, Testing Library, Playwright, OpenHAB persistence.

## Global Constraints

- Use only persisted `BTC_USD_Price`; do not add an exchange API or volume claim.
- OHLC means first, maximum, minimum, and last valid local observations in each interval.
- Reject malformed timestamps/states independently; omit empty intervals; never bridge gaps.
- One-sample intervals are neutral zero-body candles.
- Sub-day intervals align to Unix epoch boundaries; daily intervals align to browser-local midnight across DST.
- Home shows the current aligned hour plus the previous 23 hours, up to 24 hourly candles.
- Modal intervals are exactly: 15 minutes for 4h, 1 hour for 24h, 6 hours for 7d, and 1 local day for 30d.
- Up is existing positive green, down is existing negative red, and neutral is Bitcoin orange.
- Keep current price, 24-hour percentage, modal accessibility/lifecycle, and 1340x800 plus 1280x720 layout support.

---

## File map

- Create `src/lib/charts/bitcoinCandles.js`: pure row validation, OHLC aggregation, period selection, accessible summaries, and ECharts option builders.
- Create `tests/bitcoin-candles.test.js`: pure aggregation/option coverage.
- Create `src/lib/ui/BitcoinCandles.svelte`: compact Home renderer.
- Create `tests/ui/BitcoinCandles.test.js`: component lifecycle and colors.
- Modify `src/lib/ui/chartStore.js`, `tests/chart-store.test.js`: carry explicit presentation kind.
- Modify `src/lib/ui/ChartModal.svelte`, `tests/ui/ChartModal.test.js`: render candles through existing modal lifecycle.
- Modify `src/screens/Home.svelte`, `tests/home-tablet-contract.test.js`, `tests/e2e/home-runtime.spec.js`: history refresh, compact chart, and geometry.
- Modify `tests/chart-call-sites.test.js`: pin Bitcoin candlestick call site and preserve line call sites.

### Task 1: Pure OHLC aggregation

**Files:**
- Create: `src/lib/charts/bitcoinCandles.js`
- Create: `tests/bitcoin-candles.test.js`

**Interfaces:**
- Produces: `BITCOIN_CANDLE_COLORS`.
- Produces: `bitcoinCandleInterval(hours) -> { unit: 'minutes'|'day', value: number }`.
- Produces: `aggregateBitcoinCandles(points, { interval, startMs, endMs, localDateParts? }) -> Candle[]`.
- Candle shape: `{ startMs, endMs, open, high, low, close, direction: 'up'|'down'|'neutral', count }`.
- Produces: `describeLatestBitcoinCandle(candles) -> string`.

- [ ] **Step 1: Write the failing pure tests**

Cover unsorted values, unit-suffixed states, exact interval boundaries, invalid rows, gaps, one-sample neutral candles, local-midnight daily grouping through a DST day, and all four period mappings.

```js
it('aggregates sorted observations into honest OHLC candles', () => {
  const candles = aggregateBitcoinCandles([
    { time: 3_000, state: '102 USD' },
    { time: 1_000, state: '100' },
    { time: 2_000, state: '98' },
  ], { interval: { unit: 'minutes', value: 1 }, startMs: 0, endMs: 60_000 });
  expect(candles).toEqual([expect.objectContaining({
    open: 100, high: 102, low: 98, close: 102, direction: 'up', count: 3,
  })]);
});

it.each([[4, 15], [24, 60], [168, 360]])('maps %sh to %s-minute candles', (hours, value) => {
  expect(bitcoinCandleInterval(hours)).toEqual({ unit: 'minutes', value });
});
expect(bitcoinCandleInterval(720)).toEqual({ unit: 'day', value: 1 });
```

- [ ] **Step 2: Run the new test and confirm RED**

Run: `npm test -- tests/bitcoin-candles.test.js`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement validation and interval mapping**

Use the existing strict `num()` parser. Normalize valid rows to `{ timeMs, value, ordinal }`, sort by time then ordinal, and filter to `startMs <= time < endMs`.

```js
export function bitcoinCandleInterval(hours) {
  if (hours === 4) return { unit: 'minutes', value: 15 };
  if (hours === 24) return { unit: 'minutes', value: 60 };
  if (hours === 168) return { unit: 'minutes', value: 360 };
  return { unit: 'day', value: 1 };
}
```

- [ ] **Step 4: Implement fixed and local-day buckets**

For minute buckets use `Math.floor(timeMs / intervalMs) * intervalMs`. For daily buckets use `new Date(y, m, d).getTime()` and the next local midnight for `endMs`. Accumulate first/high/low/last/count; emit only non-empty buckets sorted by start.

- [ ] **Step 5: Implement direction and accessible summary**

Direction is neutral for count one or equal open/close, up when close is greater, and down otherwise. Format the latest summary as `Latest candle: open $X, high $Y, low $Z, close $W.` using `en-US` whole-dollar formatting.

- [ ] **Step 6: Run focused tests and confirm GREEN**

Run: `npm test -- tests/bitcoin-candles.test.js`

Expected: all tests PASS.

- [ ] **Step 7: Commit the aggregation slice**

```bash
git add src/lib/charts/bitcoinCandles.js tests/bitcoin-candles.test.js
git commit -m "feat: aggregate persisted bitcoin candles"
```

### Task 2: ECharts candle options and compact component

**Files:**
- Modify: `src/lib/charts/bitcoinCandles.js`
- Modify: `tests/bitcoin-candles.test.js`
- Create: `src/lib/ui/BitcoinCandles.svelte`
- Create: `tests/ui/BitcoinCandles.test.js`

**Interfaces:**
- Produces: `buildBitcoinCandleOption({ candles, compact=false }) -> EChartsOption`.
- Component props: `{ points=[], startMs, endMs, interval={ unit:'minutes', value:60 } }`.

- [ ] **Step 1: Write failing option tests**

Assert ECharts order `[open, close, low, high]`, category timestamps, correct `color/color0/borderColor/borderColor0`, compact hidden axes/tooltip/animation, and full formatted OHLC tooltip.

```js
expect(option.series[0]).toMatchObject({
  type: 'candlestick',
  data: [[100, 102, 98, 103]],
  itemStyle: {
    color: HOME_STATE_COLORS.positive,
    color0: HOME_STATE_COLORS.negative,
  },
});
```

- [ ] **Step 2: Run option tests and confirm RED**

Run: `npm test -- tests/bitcoin-candles.test.js`

Expected: FAIL because `buildBitcoinCandleOption` is absent.

- [ ] **Step 3: Implement compact and full options**

Reuse `echartsTheme` and escaped tooltip text. Use category values from `startMs`, `scale:true`, no data zoom, and `animation:false`. Encode neutral candles with per-data-item `itemStyle` set to Bitcoin orange while global up/down colors remain green/red.

- [ ] **Step 4: Write failing compact component test**

Mock `getEcharts` as existing Sparkline tests do. Render three points and assert `echarts.init(..., { renderer:'svg' })`, a candlestick series, ResizeObserver resize, and dispose on unmount.

- [ ] **Step 5: Run component test and confirm RED**

Run: `npm test -- tests/ui/BitcoinCandles.test.js`

Expected: FAIL because the component does not exist.

- [ ] **Step 6: Implement `BitcoinCandles.svelte`**

Follow `Sparkline.svelte` lifecycle exactly: initialize lazily, observe size, rebuild candles/options reactively, set the compact option with replacement, and dispose on destroy. Render only:

```svelte
<div bind:this={el} class="bitcoin-candles" aria-hidden="true"></div>

<style>
  .bitcoin-candles { width:100%; height:100%; min-width:0; min-height:0; overflow:hidden; }
</style>
```

- [ ] **Step 7: Run focused tests and commit**

Run: `npm test -- tests/bitcoin-candles.test.js tests/ui/BitcoinCandles.test.js`

Expected: all tests PASS.

```bash
git add src/lib/charts/bitcoinCandles.js tests/bitcoin-candles.test.js src/lib/ui/BitcoinCandles.svelte tests/ui/BitcoinCandles.test.js
git commit -m "feat: render compact bitcoin candles"
```

### Task 3: Candlestick presentation in chart store and modal

**Files:**
- Modify: `src/lib/ui/chartStore.js`
- Modify: `tests/chart-store.test.js`
- Modify: `src/lib/ui/ChartModal.svelte`
- Modify: `tests/ui/ChartModal.test.js`
- Modify: `tests/chart-call-sites.test.js`

**Interfaces:**
- `openChart({ title, series, presentation='line', initialHours, hours })`.
- `chartStore.presentation` is exactly `'line'` or `'candlestick'`.
- Consumes: `aggregateBitcoinCandles`, `bitcoinCandleInterval`, `buildBitcoinCandleOption`, `describeLatestBitcoinCandle`.

- [ ] **Step 1: Write failing store tests**

Assert default line behavior, explicit candlestick behavior, and normalization of an unknown presentation back to line.

```js
openChart({ title: 'Bitcoin', presentation: 'candlestick', series: [{ name: 'BTC_USD_Price' }] });
expect(get(chartStore).presentation).toBe('candlestick');
```

- [ ] **Step 2: Run store tests and confirm RED**

Run: `npm test -- tests/chart-store.test.js`

Expected: FAIL because presentation is not stored.

- [ ] **Step 3: Add the backward-compatible store field**

Seed `presentation:'line'`; normalize only the exact `candlestick` value; retain it when closing. Existing callers require no edits.

- [ ] **Step 4: Write failing modal tests**

Open the modal with Bitcoin history and `presentation:'candlestick'`. For each 4h/24h/7d/30d selector, assert the expected interval reaches the option builder, `series[0].type` is `candlestick`, and the screen-reader description contains latest open/high/low/close. Retain existing cancellation, route, focus, resize, and dispose assertions.

- [ ] **Step 5: Run modal tests and confirm RED**

Run: `npm test -- tests/ui/ChartModal.test.js`

Expected: FAIL because ChartModal always calls `buildHistoryOption`.

- [ ] **Step 6: Branch only the render adapter**

In `renderLatest`, when presentation is candlestick, aggregate `pointsPerSeries[0]` using `bitcoinCandleInterval(activeHours)` and build the full option. Set the accessible candle summary from the same candle array. Otherwise execute the current line option/extrema code unchanged. Clear candle summary on close, load, empty, and error.

- [ ] **Step 7: Pin call-site compatibility**

In `tests/chart-call-sites.test.js`, assert only Bitcoin passes `presentation:'candlestick'`; Outdoor, Indoor, Battery, Wind, Rain, Solar, and Pressure remain implicit line charts.

- [ ] **Step 8: Run focused tests and commit**

Run: `npm test -- tests/chart-store.test.js tests/ui/ChartModal.test.js tests/chart-call-sites.test.js tests/chart-options.test.js`

Expected: all tests PASS.

```bash
git add src/lib/ui/chartStore.js tests/chart-store.test.js src/lib/ui/ChartModal.svelte tests/ui/ChartModal.test.js tests/chart-call-sites.test.js
git commit -m "feat: add bitcoin candle modal mode"
```

### Task 4: Bitcoin candles on Home

**Files:**
- Modify: `src/screens/Home.svelte`
- Modify: `tests/home-tablet-contract.test.js`
- Modify: `tests/e2e/home-runtime.spec.js`

**Interfaces:**
- Consumes: `BitcoinCandles` component and existing `fetchHistoryRange`.
- Produces: `btcHistory`, refreshed at mount and every five minutes; Bitcoin modal opens with `presentation:'candlestick'`.

- [ ] **Step 1: Replace the obsolete no-inline-history contract test**

```js
it('shows Bitcoin candles and opens the candle modal', () => {
  expect(home).toContain("import BitcoinCandles from '../lib/ui/BitcoinCandles.svelte'");
  expect(home).toContain("fetchHistoryRange('BTC_USD_Price'");
  expect(home).toContain('<BitcoinCandles points={btcHistory}');
  expect(home).toMatch(/openBitcoinChart[\s\S]*presentation:\s*'candlestick'/);
});
```

- [ ] **Step 2: Add failing browser assertions**

Return several alternating up/down BTC history observations from the existing REST fixture. Assert `.btc-candles` has positive width/height and does not overlap price/change. Open the modal and assert a candlestick series is rendered, period controls remain usable, and closing restores focus.

- [ ] **Step 3: Run Home tests and confirm RED**

Run: `npm test -- tests/home-tablet-contract.test.js && npm run test:e2e -- tests/e2e/home-runtime.spec.js`

Expected: failures for absent component/history and line modal mode.

- [ ] **Step 4: Implement aligned Home history refresh**

Add `btcHistory` state and:

```js
async function refreshBitcoinHistory() {
  const now = Date.now();
  const currentHour = Math.floor(now / 3_600_000) * 3_600_000;
  btcHistory = await fetchHistoryRange(
    'BTC_USD_Price',
    new Date(currentHour - 23 * 3_600_000).toISOString(),
    new Date(now).toISOString(),
  );
}
```

Call on mount and in the five-minute timer. A failed request returns `[]` through the existing safe helper and leaves price/change visible.

- [ ] **Step 5: Add compact chart and modal kind**

Place `<BitcoinCandles>` in a `.btc-candles` area subordinate to `.btc-price`. Update `openBitcoinChart()` with `presentation:'candlestick'` and retain `initialHours:24`, title, and `BTC_USD_Price` series.

- [ ] **Step 6: Adjust card CSS at both viewports**

Use a two-column or stacked grid based on measured space; pin `min-width:0`, `overflow:hidden`, and a nonzero chart height. Do not reduce current price below the existing readable floor unless Playwright demonstrates an unavoidable collision.

- [ ] **Step 7: Run focused tests and confirm GREEN**

Run: `npm test -- tests/home-tablet-contract.test.js tests/bitcoin-candles.test.js tests/ui/BitcoinCandles.test.js tests/chart-call-sites.test.js && npm run test:e2e -- tests/e2e/home-runtime.spec.js`

Expected: all tests PASS at 1340x800 and 1280x720.

- [ ] **Step 8: Commit the Home Bitcoin slice**

```bash
git add src/screens/Home.svelte tests/home-tablet-contract.test.js tests/e2e/home-runtime.spec.js
git commit -m "feat: show bitcoin candles on home"
```

### Task 5: Bitcoin and combined-dashboard verification

**Files:**
- Modify only if a failing assertion identifies a real defect: files listed above or in the weather plan.

**Interfaces:**
- Consumes: completed Bitcoin tasks and completed weather plan.
- Produces: verified combined Home dashboard and modal behavior.

- [ ] **Step 1: Run all focused candle tests**

Run: `npm test -- tests/bitcoin-candles.test.js tests/ui/BitcoinCandles.test.js tests/chart-store.test.js tests/ui/ChartModal.test.js tests/chart-call-sites.test.js tests/chart-options.test.js tests/home-tablet-contract.test.js`

Expected: all tests PASS.

- [ ] **Step 2: Run the complete unit suite**

Run: `npm test`

Expected: all Vitest tests PASS with no unhandled errors.

- [ ] **Step 3: Run production build**

Run: `npm run build`

Expected: Vite exits 0 and writes `dist/`.

- [ ] **Step 4: Run combined browser verification**

Run: `npm run test:e2e -- tests/e2e/home-runtime.spec.js tests/e2e/weather-detail-modal.spec.js tests/e2e/weather-earthship-layout.spec.js`

Expected: all tests PASS; indoor and Bitcoin compact charts fit, candles use green/red/orange semantics, Bitcoin modal period changes work, and weather detail shows 12 hours.

- [ ] **Step 5: Inspect final repository state**

Run: `git diff --check && git status --short --branch`

Expected: no whitespace errors or unrelated edits. If verification required a fix, stage only the intended files and commit `fix: close dashboard chart integration gaps`.
