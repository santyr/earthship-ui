# Home Tablet Grid Rebalance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the four equal Home primary cards more tablet chart space, return Solar PV and Earthship Temperatures to the bottom-right pair, and make the Home SoC percentage fit its arc.

**Architecture:** Preserve the six-column Home grid and existing direct-child cells. Divide the current central allocation into six equal `0.425fr` sub-rows so each primary card spans three and each right-side card spans two; add one CSS custom-property seam to `Arc.svelte` so Home can reduce only its SoC value typography.

**Tech Stack:** Svelte 5, JavaScript ES modules, CSS Grid, Vitest, Testing Library, Playwright, ECharts.

## Global Constraints

- The Lenovo Tab M9 at 1340x800 is the primary design authority.
- Home must fit the tablet viewport without document, card, tile-body, or card content scrolling.
- The 1280x720 laptop floor must remain bounded and usable.
- Outdoor, Indoor, Battery SoC, and Bitcoin must have equal rendered width and height within 1 CSS pixel.
- Preserve the established dark technical console language, domain colors, data, charts, card clicks, keyboard access, modals, and refresh behavior.
- Keep long, stale, unavailable, and partial-data states bounded.
- Add no new data, APIs, timers, dependencies, controls, navigation, effects, or backend/OpenHAB changes.
- Do not change shared design tokens or redesign other screens.
- Solar PV and Earthship Temperatures must be the bottom-right pair.
- The Home SoC value size is exactly `1.45rem`; the shared Arc default remains exactly `1.8rem`.
- All four primary chart regions must be at least 50 CSS pixels high at both supported viewports.
- Do not push, merge, restart services, or deploy without a separate operator instruction after implementation review.

---

## File map

- Modify `src/lib/ui/Arc.svelte`: expose only `--arc-value-size` with a `1.8rem` fallback.
- Modify `tests/ui/Arc.test.js`: pin the shared Arc default without changing value semantics.
- Modify `src/screens/Home.svelte`: apply the Home-only `1.45rem` SoC size and six-sub-row grid.
- Modify `tests/home-tablet-contract.test.js`: pin exact grid areas, row fractions, and local typography.
- Modify `tests/home-card-state.test.js`: pin the Home-only SoC override beside its truthful accessibility contract.
- Modify `tests/e2e/home-runtime.spec.js`: prove primary equality, right-pair alignment, chart height, SoC containment, and both target viewports.

### Task 1: Add the caller-specific Arc value-size seam

**Files:**
- Modify: `src/lib/ui/Arc.svelte:80-85`
- Modify: `tests/ui/Arc.test.js`

**Interfaces:**
- Consumes: optional inherited CSS custom property `--arc-value-size`.
- Produces: `.arc-value { font-size: var(--arc-value-size, 1.8rem); }` while preserving all existing Arc props and value semantics.

- [ ] **Step 1: Write the failing shared-Arc style contract**

Update the imports at the top of `tests/ui/Arc.test.js`:

```js
import { readFileSync } from 'node:fs';
import { cleanup, render, screen } from '@testing-library/svelte';
```

After the `Arc` import, add:

```js
const arcSource = readFileSync(new URL('../../src/lib/ui/Arc.svelte', import.meta.url), 'utf8');
```

Add this test inside the existing `describe` block:

```js
it('keeps a 1.8rem default while accepting a caller-specific value size', () => {
  expect(arcSource).toMatch(
    /\.arc-value\s*\{[^}]*font-size:\s*var\(--arc-value-size,\s*1\.8rem\);/s
  );
});
```

- [ ] **Step 2: Run the focused Arc tests and verify RED**

Run:

```bash
npm test -- tests/ui/Arc.test.js
```

Expected: FAIL because `.arc-value` still declares `font-size: 1.8rem` directly.

- [ ] **Step 3: Implement the minimal CSS custom-property seam**

In `src/lib/ui/Arc.svelte`, replace only the `.arc-value` font-size declaration:

```css
.arc-value {
  font-size: var(--arc-value-size, 1.8rem);
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
```

Do not add a Svelte prop, change markup, or alter numeric parsing, clamping, rounding, unavailable handling, SVG geometry, labels, or sublabels.

- [ ] **Step 4: Run the Arc tests and verify GREEN**

Run:

```bash
npm test -- tests/ui/Arc.test.js
```

Expected: all Arc tests PASS, including unavailable and numeric-zero behavior.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/lib/ui/Arc.svelte tests/ui/Arc.test.js
git commit -m "feat: allow local arc value sizing"
```

### Task 2: Rebalance the Home grid for the Lenovo Tab M9

**Files:**
- Modify: `src/screens/Home.svelte:795-815,1087-1110`
- Modify: `tests/home-tablet-contract.test.js:90-125`
- Modify: `tests/home-card-state.test.js:510-525`
- Modify: `tests/e2e/home-runtime.spec.js:260-450,564-680,773-870`

**Interfaces:**
- Consumes: Task 1's inherited `--arc-value-size` hook.
- Produces: six equal `0.425fr` central sub-rows; four equal primary cards spanning three sub-rows; three aligned right-side pairs spanning two sub-rows; Home-only `--arc-value-size: 1.45rem`.

- [ ] **Step 1: Replace the old static grid contract with the failing tablet-first contract**

Replace the current `uses an exact two-by-two primary instrument grid` test in `tests/home-tablet-contract.test.js` with:

```js
it('uses six tablet-first sub-rows with equal primary instruments and right-side pairs', () => {
  expect(home).toContain("'outdoor outdoor battery battery wind baro'");
  expect(home).toContain("'outdoor outdoor battery battery rain sunmoon'");
  expect(home).toContain("'indoor indoor bitcoin bitcoin rain sunmoon'");
  expect(home).toContain("'indoor indoor bitcoin bitcoin solar zones'");
  expect(home.match(/'outdoor outdoor battery battery wind baro'/g)).toHaveLength(2);
  expect(home.match(/'outdoor outdoor battery battery rain sunmoon'/g)).toHaveLength(1);
  expect(home.match(/'indoor indoor bitcoin bitcoin rain sunmoon'/g)).toHaveLength(1);
  expect(home.match(/'indoor indoor bitcoin bitcoin solar zones'/g)).toHaveLength(2);
  expect(home).not.toContain("'solar solar solar zones zones zones'");
  expect(home).toMatch(/grid-template-rows:[\s\S]*0\.38fr[\s\S]*repeat\(6,\s*minmax\(0,\s*0\.425fr\)\)[\s\S]*0\.72fr/);
  expect(home).toMatch(/\.indoor-body\s*\{[^}]*display:\s*flex;[^}]*flex-direction:\s*column;/s);
});
```

Add this assertion to `pins equal-grid primary temperature sizing` in `tests/home-card-state.test.js`:

```js
expect(home).toMatch(/\.battery-arc\s*\{[^}]*--arc-value-size:\s*1\.45rem;/is);
```

Add the same assertion to `pins the requested distance-readable Home typography` in `tests/home-tablet-contract.test.js`.

- [ ] **Step 2: Extend browser geometry for right-side pairs and SoC containment**

Inside the `homeGeometry()` result in `tests/e2e/home-runtime.spec.js`, extend `battery` with:

```js
center: box(document.querySelector('.battery-arc .arc-center')),
value: box(document.querySelector('.battery-arc .arc-value')),
```

Add beside `primaryCards`:

```js
rightCards: Object.fromEntries(
  ['wind', 'baro', 'rain', 'sunmoon', 'solar', 'zones'].map((name) => [
    name,
    box(document.querySelector(`.${name}-cell`)),
  ])
),
```

Add to the `fonts` object:

```js
socValue: parseFloat(getComputedStyle(document.querySelector('.battery-arc .arc-value')).fontSize),
```

Add these helpers after `expectEqualPrimaryCards()`:

```js
function expectAlignedRightPairs(geometry) {
  const { wind, baro, rain, sunmoon, solar, zones } = geometry.rightCards;
  for (const [left, right] of [[wind, baro], [rain, sunmoon], [solar, zones]]) {
    expect(Math.abs(left.top - right.top)).toBeLessThanOrEqual(1);
    expect(Math.abs(left.bottom - right.bottom)).toBeLessThanOrEqual(1);
    expect(Math.abs(left.height - right.height)).toBeLessThanOrEqual(1);
  }
  for (const column of [[wind, rain, solar], [baro, sunmoon, zones]]) {
    const lefts = column.map(({ left }) => left);
    const rights = column.map(({ right }) => right);
    expect(Math.max(...lefts) - Math.min(...lefts)).toBeLessThanOrEqual(1);
    expect(Math.max(...rights) - Math.min(...rights)).toBeLessThanOrEqual(1);
  }
  expect(wind.bottom).toBeLessThanOrEqual(rain.top + 0.5);
  expect(baro.bottom).toBeLessThanOrEqual(sunmoon.top + 0.5);
  expect(rain.bottom).toBeLessThanOrEqual(solar.top + 0.5);
  expect(sunmoon.bottom).toBeLessThanOrEqual(zones.top + 0.5);
}

function expectSocValueContained(geometry) {
  const { center, value } = geometry.battery;
  expect(value.left).toBeGreaterThanOrEqual(center.left - 0.5);
  expect(value.top).toBeGreaterThanOrEqual(center.top - 0.5);
  expect(value.right).toBeLessThanOrEqual(center.right + 0.5);
  expect(value.bottom).toBeLessThanOrEqual(center.bottom + 0.5);
  expect(geometry.fonts.socValue).toBeCloseTo(23.2, 1);
}

function expectPrimaryChartHeights(geometry) {
  expect(geometry.outdoor.spark.height).toBeGreaterThanOrEqual(50);
  expect(geometry.indoor.spark.height).toBeGreaterThanOrEqual(50);
  expect(geometry.battery.spark.height).toBeGreaterThanOrEqual(50);
  expect(geometry.bitcoin.chart.height).toBeGreaterThanOrEqual(50);
}
```

Call all three helpers after `expectEqualPrimaryCards(geometry)` in the
settled and long/unavailable/stale cases:

```js
expectAlignedRightPairs(geometry);
expectSocValueContained(geometry);
expectPrimaryChartHeights(geometry);
```

Remove the four superseded settled-only `35`-pixel chart-height assertions.

After the existing settled Battery assertions, add an explicit maximum-value containment check:

```js
await runtime.emitState('BMS_SOC', '100');
await expect(page.locator('.battery-arc .arc-value')).toHaveText('100%');
const maximumSocGeometry = await homeGeometry(page);
expectSocValueContained(maximumSocGeometry);
```

This must run before the settled screenshot so the primary M9 artifact shows the worst-case percentage.

- [ ] **Step 3: Run static and browser tests and verify RED**

Run:

```bash
npm test -- tests/ui/Arc.test.js tests/home-tablet-contract.test.js tests/home-card-state.test.js
npm run test:e2e -- tests/e2e/home-runtime.spec.js
```

Expected: static tests fail on the old five-row grid and absent Home override;
all four browser cases fail on the 1.45rem SoC and 50px chart-height
requirements.

- [ ] **Step 4: Implement the exact six-sub-row Home grid**

Replace the Home grid rows and areas in `src/screens/Home.svelte` with:

```css
grid-template-rows:
  minmax(0, 0.38fr)
  repeat(6, minmax(0, 0.425fr))
  minmax(0, 0.72fr);
grid-template-areas:
  'topbar topbar topbar topbar goat greywater'
  'outdoor outdoor battery battery wind baro'
  'outdoor outdoor battery battery wind baro'
  'outdoor outdoor battery battery rain sunmoon'
  'indoor indoor bitcoin bitcoin rain sunmoon'
  'indoor indoor bitcoin bitcoin solar zones'
  'indoor indoor bitcoin bitcoin solar zones'
  'forecast forecast forecast forecast forecast forecast';
```

Do not change the six equal columns, `0.55rem` gap, fixed height, or hidden overflow.

- [ ] **Step 5: Apply the Home-only SoC percentage size**

Add the custom property to the existing `.battery-arc` rule without changing its width constraints:

```css
.battery-arc {
  width: 30%;
  max-width: 6.25rem;
  --arc-value-size: 1.45rem;
}
```

Do not change Gallery, Arc markup, Battery data, the current sublabel, or accessible card text.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```bash
npm test -- \
  tests/ui/Arc.test.js \
  tests/home-tablet-contract.test.js \
  tests/home-card-state.test.js \
  tests/ui/CompassRose.test.js \
  tests/ui/BitcoinCandles.test.js
npm run test:e2e -- tests/e2e/home-runtime.spec.js
```

Expected: all focused tests PASS. At both viewports the four primary cards differ by no more than 1 CSS pixel, all four chart regions are at least 50px high, the right cards form three aligned pairs, and `100%` plus unavailable SoC remain contained at 1.45rem.

- [ ] **Step 7: Commit Task 2**

```bash
git add \
  src/screens/Home.svelte \
  tests/home-tablet-contract.test.js \
  tests/home-card-state.test.js \
  tests/e2e/home-runtime.spec.js
git commit -m "feat: restore tablet-first home proportions"
```

### Task 3: Verify the primary tablet and cross-screen regressions

**Files:**
- Verify only: all files changed by Tasks 1-2.
- Generated artifacts: Playwright PNGs under `test-results/`; do not commit them.

**Interfaces:**
- Consumes: completed Arc and Home changes.
- Produces: fresh automated, build, scope, and visual evidence; no product interface.

- [ ] **Step 1: Run the complete focused UI contract**

```bash
npm test -- \
  tests/ui/Arc.test.js \
  tests/home-tablet-contract.test.js \
  tests/home-card-state.test.js \
  tests/ui/CompassRose.test.js \
  tests/ui/BitcoinCandles.test.js \
  tests/chart-call-sites.test.js
```

Expected: all selected Vitest files PASS with zero failures and no new warnings.

- [ ] **Step 2: Run Home browser verification and inspect the Lenovo artifacts first**

```bash
npm run test:e2e -- tests/e2e/home-runtime.spec.js
```

Expected: four tests PASS. Inspect the screenshots in this order:

1. `home-settled.png` at `m9-1340x800`;
2. `home-long-unavailable-stale.png` at `m9-1340x800`;
3. `home-settled.png` at `laptop-1280x720`;
4. `home-long-unavailable-stale.png` at `laptop-1280x720`.

For each, confirm that the four primary cards are visibly equal; Outdoor and
the other three charts have useful vertical space; `100%` or `—` stays inside
the SoC arc; the three right-side pairs align; Solar PV and Earthship
Temperatures occupy the bottom-right pair; and no content overlaps, scrolls,
or appears accidentally clipped. Treat the M9 screenshots as the primary
decision surface.

- [ ] **Step 3: Run the full unit suite and production build**

```bash
npm test
npm run build
```

Expected: the complete Vitest suite and production build PASS. The existing
Vite chunk-size advisory is non-blocking; accept no new warning.

- [ ] **Step 4: Run cross-screen layout regressions**

```bash
npm run test:e2e -- \
  tests/e2e/home-runtime.spec.js \
  tests/e2e/weather-detail-modal.spec.js \
  tests/e2e/weather-earthship-layout.spec.js
```

Expected: all selected Playwright checks PASS at 1340x800 and 1280x720.
Weather, Earthship, and modal structures remain unchanged.

- [ ] **Step 5: Verify scope and cleanliness**

Set `BRANCH_BASE` to the commit immediately before Task 1, then run:

```bash
git diff --check "$BRANCH_BASE"..HEAD
git diff --name-status "$BRANCH_BASE"..HEAD
git status --short --branch
```

Expected: no whitespace errors or uncommitted product changes. Only
`Arc.svelte`, `Home.svelte`, and their four focused test files differ from the
implementation base. Do not push, merge, restart services, or deploy without
a new operator instruction after review.
