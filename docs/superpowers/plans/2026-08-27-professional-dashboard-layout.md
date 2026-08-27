# Professional Dashboard Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebalance the Home console into four equal primary cards and make the Wind compass immediately readable while preserving the existing restrained instrument-panel design.

**Architecture:** Keep the six-column, fixed-height Home grid and existing data flow. Add one pure compass-presentation adapter, have `CompassRose.svelte` render that contract, and change only Home-local grid/card styles plus focused markup needed for the approved hierarchy. Existing stores, history requests, chart components, modal behavior, and other screen structures remain unchanged.

**Tech Stack:** Svelte 5, JavaScript ES modules, Vitest, Testing Library, Playwright, SVG, CSS Grid, ECharts.

## Global Constraints

- Home must fit at 1340x800 and 1280x720 without page scrolling.
- Outdoor, Indoor, Battery SoC, and Bitcoin must have equal rendered width and height within 1 CSS pixel.
- Preserve existing domain colors, near-black surfaces, current data, card clicks, modal behavior, keyboard focus, and accessible chart descriptions.
- Add no gradients, glass effects, glow, textures, ornamental gauges, animation, global font-size increase, API calls, timers, libraries, dependencies, navigation, or controls.
- Keep long, stale, unavailable, and partial-data states bounded.
- Do not redesign Weather, modal structure, navigation, alerts, or backend/OpenHAB behavior.
- Do not modify shared tokens unless a rendered regression proves a specific shared inconsistency; the approved screenshots show none requiring a token change.

---

## File map

- Create `src/lib/ui/compassPresentation.js`: pure normalization, calm-state, sixteen-point heading, display text, and accessible-label logic.
- Create `tests/compass-presentation.test.js`: boundary and unavailable-state tests for the pure compass contract.
- Modify `src/lib/ui/CompassRose.svelte`: consume the pure contract and render the approved hierarchy and SVG contrast.
- Modify `tests/ui/CompassRose.test.js`: pin component delegation and visual/semantic structure.
- Modify `src/screens/Home.svelte`: equal grid areas, primary-card internal layout, supporting-strip placement, and Wind footer copy.
- Modify `tests/home-tablet-contract.test.js`: pin the intended grid and Home-local presentation contract.
- Modify `tests/e2e/home-runtime.spec.js`: assert exact primary-card equality, chart containment, compass readability, long-state containment, and screenshot output at both viewports.

### Task 1: Pure compass presentation contract

**Files:**
- Create: `src/lib/ui/compassPresentation.js`
- Create: `tests/compass-presentation.test.js`

**Interfaces:**
- Consumes: raw `degrees` and `speed` values supplied by Home/OpenHAB.
- Produces: `compassPresentation(degrees, speed) -> { hasHeading, heading, point, headingText, hasSpeed, speedText, calm, ariaLabel }`.

- [ ] **Step 1: Write the failing pure contract tests**

Create `tests/compass-presentation.test.js`:

```js
import { describe, expect, it } from 'vitest';
import { compassPresentation } from '../src/lib/ui/compassPresentation.js';

describe('compassPresentation', () => {
  it.each([
    [0, 'N · 0°'],
    [22.5, 'NNE · 23°'],
    [78, 'ENE · 78°'],
    [180, 'S · 180°'],
    [270, 'W · 270°'],
    [348.75, 'N · 349°'],
    [360, 'N · 0°'],
    [-10, 'N · 350°'],
  ])('formats %s degrees as a sixteen-point heading', (degrees, headingText) => {
    expect(compassPresentation(degrees, 4).headingText).toBe(headingText);
  });

  it.each([null, undefined, '', 'NULL', 'UNDEF', 'north', Number.NaN])(
    'does not invent a direction for %s',
    (degrees) => {
      const result = compassPresentation(degrees, 4);
      expect(result.hasHeading).toBe(false);
      expect(result.heading).toBe(0);
      expect(result.point).toBe(null);
      expect(result.headingText).toBe('DIR —');
      expect(result.ariaLabel).toBe('Wind direction unavailable, speed 4 mph');
    }
  );

  it('treats zero speed as calm and suppresses the heading', () => {
    expect(compassPresentation(78, 0)).toEqual({
      hasHeading: false,
      heading: 0,
      point: null,
      headingText: 'CALM',
      hasSpeed: true,
      speedText: '0',
      calm: true,
      ariaLabel: 'Wind calm, speed 0 mph',
    });
  });

  it.each([null, undefined, '', 'NULL', 'UNDEF', 'fast', Number.NaN, -1])(
    'shows unavailable speed without corrupting a valid heading for %s',
    (speed) => {
      const result = compassPresentation(78, speed);
      expect(result.hasHeading).toBe(true);
      expect(result.headingText).toBe('ENE · 78°');
      expect(result.hasSpeed).toBe(false);
      expect(result.speedText).toBe('—');
      expect(result.ariaLabel).toBe('Wind direction ENE, 78 degrees, speed unavailable');
    }
  );
});
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
npm test -- tests/compass-presentation.test.js
```

Expected: FAIL because `src/lib/ui/compassPresentation.js` does not exist.

- [ ] **Step 3: Implement the pure adapter**

Create `src/lib/ui/compassPresentation.js`:

```js
const POINTS = [
  'N', 'NNE', 'NE', 'ENE',
  'E', 'ESE', 'SE', 'SSE',
  'S', 'SSW', 'SW', 'WSW',
  'W', 'WNW', 'NW', 'NNW',
];

function finiteTelemetry(value) {
  if (
    value === null
    || value === undefined
    || value === ''
    || value === 'NULL'
    || value === 'UNDEF'
  ) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function compassPresentation(degrees, speed) {
  const rawHeading = finiteTelemetry(degrees);
  const rawSpeed = finiteTelemetry(speed);
  const hasSpeed = rawSpeed !== null && rawSpeed >= 0;
  const calm = hasSpeed && rawSpeed === 0;
  const normalized = rawHeading === null ? null : ((rawHeading % 360) + 360) % 360;
  const hasHeading = normalized !== null && !calm;
  const point = hasHeading
    ? POINTS[Math.floor((normalized + 11.25) / 22.5) % POINTS.length]
    : null;
  const roundedHeading = hasHeading ? Math.round(normalized) % 360 : 0;
  const speedText = hasSpeed ? String(rawSpeed) : '—';
  const headingText = calm ? 'CALM' : hasHeading ? `${point} · ${roundedHeading}°` : 'DIR —';

  let ariaLabel;
  if (calm) {
    ariaLabel = `Wind calm, speed ${speedText} mph`;
  } else {
    const direction = hasHeading
      ? `Wind direction ${point}, ${roundedHeading} degrees`
      : 'Wind direction unavailable';
    const speedLabel = hasSpeed ? `speed ${speedText} mph` : 'speed unavailable';
    ariaLabel = `${direction}, ${speedLabel}`;
  }

  return {
    hasHeading,
    heading: hasHeading ? normalized : 0,
    point,
    headingText,
    hasSpeed,
    speedText,
    calm,
    ariaLabel,
  };
}
```

- [ ] **Step 4: Run the pure tests and verify GREEN**

Run:

```bash
npm test -- tests/compass-presentation.test.js
```

Expected: all compass-presentation tests PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/lib/ui/compassPresentation.js tests/compass-presentation.test.js
git commit -m "feat: define readable compass presentation"
```

### Task 2: Compass hierarchy and Wind footer

**Files:**
- Modify: `src/lib/ui/CompassRose.svelte`
- Modify: `src/screens/Home.svelte:662-681,1188-1215`
- Modify: `tests/ui/CompassRose.test.js`
- Modify: `tests/e2e/home-runtime.spec.js`

**Interfaces:**
- Consumes: `compassPresentation(degrees, speed)` from Task 1.
- Produces: `.compass-heading` visible text, truthful SVG `aria-label`, accent needle/hub, four cardinal labels, and Home footer text `gust <value> · max <value> mph`.

- [ ] **Step 1: Replace source-only compass expectations with delegation and hierarchy expectations**

Add these assertions to `tests/ui/CompassRose.test.js`, replacing expectations tied to the old inline derived values and needle geometry:

```js
it('delegates direction, calm and accessibility text to the pure adapter', () => {
  expect(compass).toContain("import { compassPresentation } from './compassPresentation.js'");
  expect(compass).toMatch(/const\s+presentation\s*=\s*\$derived\(compassPresentation\(degrees,\s*speed\)\)/);
  expect(compass).toMatch(/aria-label=\{presentation\.ariaLabel\}/);
  expect(compass).toContain('{presentation.headingText}');
});

it('renders a stronger but restrained instrument hierarchy', () => {
  expect(compass).toContain('class="compass-heading"');
  expect(compass).toContain('points="50,23 43.5,53 50,48 56.5,53"');
  expect(compass).toMatch(/\.dir-label\s*\{[^}]*font-size:\s*13px;[^}]*fill:\s*#d7dee6;/s);
  expect(compass).toMatch(/\.compass-speed\s*\{[^}]*font-size:\s*1\.8rem;/s);
});
```

In the settled Home Playwright test, replace the existing exact Wind image
label assertion and add the heading/footer assertions:

```js
await expect(page.locator('.compass-heading')).toHaveText('N · 0°');
await expect(page.locator('.wind-meta')).toHaveText('gust 18 · max 18 mph');
await expect(
  page.getByRole('img', { name: 'Wind direction N, 0 degrees, speed 11 mph', exact: true })
).toBeVisible();
expect(geometry.fonts.compassCardinal).toBeCloseTo(13, 1);
```

In the unavailable-state test, replace the existing exact unavailable Wind
image label assertion and add:

```js
await expect(
  page.getByRole('img', { name: 'Wind direction unavailable, speed 11 mph', exact: true })
).toBeVisible();
await expect(page.locator('.compass-heading')).toHaveText('DIR —');
await expect(page.locator('.wind-meta')).toHaveText('gust 18 · max 18 mph');
expect(geometry.fonts.compassCardinal).toBeCloseTo(13, 1);
```

Remove both old `toBeCloseTo(12, 1)` cardinal-font assertions. Keep the
existing weight, containment, cardinal-count, needle-color, and missing-needle
assertions.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
npm test -- tests/compass-presentation.test.js tests/ui/CompassRose.test.js
npm run test:e2e -- tests/e2e/home-runtime.spec.js
```

Expected: component/source assertions fail because `CompassRose.svelte` still uses inline heading logic; Playwright fails on the missing `.compass-heading` and old accessible label/footer copy.

- [ ] **Step 3: Make CompassRose consume the pure contract**

In `src/lib/ui/CompassRose.svelte`, import the helper and replace the current `hasHeading`, `heading`, `hasSpeed`, `speedText`, and `compassLabel` derived blocks with:

```js
import { compassPresentation } from './compassPresentation.js';

const presentation = $derived(compassPresentation(degrees, speed));
```

Update the SVG and center markup to use the contract:

```svelte
<svg viewBox="0 0 100 100" class="compass-svg" role="img" aria-label={presentation.ariaLabel}>
  <circle cx="50" cy="50" r="46" fill="none" stroke="#334155" stroke-width="1.5" />
  <circle cx="50" cy="50" r="34" fill="none" stroke="#273244" stroke-width="1" />
  <!-- retain the existing eight tick loop and four cardinal labels -->
  {#if presentation.hasHeading}
    <g transform="rotate({presentation.heading} 50 50)">
      <polygon class="compass-needle" points="50,23 43.5,53 50,48 56.5,53" fill={accent} />
    </g>
    <circle class="compass-hub" cx="50" cy="50" r="3.5" fill={accent} />
  {/if}
</svg>

<div class="compass-center">
  <div class="compass-speed">{presentation.speedText}</div>
  <div class="compass-unit">mph</div>
  <div class="compass-heading">{presentation.headingText}</div>
</div>
```

Keep the existing `showGust` API for non-Home callers. Update only these presentation rules:

```css
.dir-label {
  font-size: 13px;
  fill: #d7dee6;
  font-weight: 800;
}
.compass-speed {
  font-size: 1.8rem;
  font-weight: 700;
  line-height: 0.95;
  font-variant-numeric: tabular-nums;
  color: #f8fafc;
}
.compass-unit {
  font-size: 0.72rem;
  color: #aab4c2;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.compass-heading {
  margin-top: 0.12rem;
  font-size: 0.68rem;
  font-weight: 700;
  color: #d7dee6;
  letter-spacing: 0.035em;
  white-space: nowrap;
}
```

Use `#94a3b8` for tick strokes and preserve `accent` for the needle and hub.

- [ ] **Step 4: Make the Home Wind footer one readable technical line**

Replace the two Wind footer spans in `src/screens/Home.svelte` with:

```svelte
<div class="wind-meta">
  <span class="wind-gust" style="color: {windGustColor}">gust {windGustR === null ? '—' : windGustR}</span>
  <span class="wind-separator" aria-hidden="true">·</span>
  <span class="wind-max" style="color: {windMaxColor}">max {windGustMaxToday === null ? '—' : Math.round(windGustMaxToday)} mph</span>
</div>
```

Add:

```css
.wind-separator {
  color: #64748b;
}
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
npm test -- tests/compass-presentation.test.js tests/ui/CompassRose.test.js tests/home-tablet-contract.test.js
npm run test:e2e -- tests/e2e/home-runtime.spec.js
```

Expected: all focused Vitest and both-viewport Home Playwright cases PASS; compass is square, contained, and has no needle/hub when direction is unavailable or wind is calm.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/lib/ui/CompassRose.svelte src/screens/Home.svelte tests/ui/CompassRose.test.js tests/e2e/home-runtime.spec.js
git commit -m "feat: improve wind compass readability"
```

### Task 3: Equal primary-card grid and internal hierarchy

**Files:**
- Modify: `src/screens/Home.svelte:795-1215`
- Modify: `tests/home-tablet-contract.test.js`
- Modify: `tests/home-card-state.test.js`
- Modify: `tests/e2e/home-runtime.spec.js`

**Interfaces:**
- Consumes: existing Home markup, chart components, card click handlers, and fixed six-column shell.
- Produces: equal `.outdoor-cell`, `.indoor-cell`, `.battery-cell`, and `.bitcoin-cell` geometry at both target viewports; wider Solar/Zones supporting strips; vertically structured Indoor chart.

- [ ] **Step 1: Add the static equal-grid contract**

Add to `tests/home-tablet-contract.test.js`:

```js
it('uses an exact two-by-two primary instrument grid', () => {
  expect(home).toContain("'outdoor outdoor battery battery wind baro'");
  expect(home).toContain("'indoor indoor bitcoin bitcoin rain sunmoon'");
  expect(home).toContain("'solar solar solar zones zones zones'");
  expect(home).not.toContain("'outdoor outdoor battery battery rain sunmoon'");
  expect(home).toMatch(/grid-template-rows:[\s\S]*0\.38fr[\s\S]*1fr[\s\S]*1fr[\s\S]*0\.55fr[\s\S]*0\.72fr/);
  expect(home).toMatch(/\.indoor-body\s*\{[^}]*display:\s*flex;[^}]*flex-direction:\s*column;/s);
});
```

Update the typography assertions in both `tests/home-tablet-contract.test.js` and `tests/home-card-state.test.js` to pin local primary values at `4rem`, not the old `4.4rem`:

```js
expect(home).toMatch(/\.big-temp\s*\{[^}]*font-size:\s*4rem/is);
expect(home).toMatch(/\.indoor-temp\s*\{[^}]*font-size:\s*4rem/is);
```

- [ ] **Step 2: Add rendered geometry and chart-containment assertions**

In `homeGeometry()` inside `tests/e2e/home-runtime.spec.js`, add:

```js
primaryCards: Object.fromEntries(
  ['outdoor', 'indoor', 'battery', 'bitcoin'].map((name) => [
    name,
    box(document.querySelector(`.${name}-cell`)),
  ])
),
bitcoin: {
  top: box(document.querySelector('.btc-top')),
  chart: box(document.querySelector('.btc-candles')),
},
```

Add a helper beside `expectBounded()`:

```js
function expectEqualPrimaryCards(geometry) {
  const cards = Object.values(geometry.primaryCards);
  const widths = cards.map(({ width }) => width);
  const heights = cards.map(({ height }) => height);
  expect(Math.max(...widths) - Math.min(...widths)).toBeLessThanOrEqual(1);
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1);
}
```

Call `expectEqualPrimaryCards(geometry)` in both the settled and long/unavailable tests. Add settled assertions:

```js
expect(geometry.outdoor.spark.height).toBeGreaterThanOrEqual(35);
expect(geometry.indoor.spark.height).toBeGreaterThanOrEqual(35);
expect(geometry.battery.spark.height).toBeGreaterThanOrEqual(35);
expect(geometry.bitcoin.chart.height).toBeGreaterThanOrEqual(35);
expect(geometry.fonts.outdoor).toBeCloseTo(64, 1);
expect(geometry.fonts.indoor).toBeCloseTo(64, 1);
```

- [ ] **Step 3: Run static and browser tests and verify RED**

Run:

```bash
npm test -- tests/home-tablet-contract.test.js tests/home-card-state.test.js
npm run test:e2e -- tests/e2e/home-runtime.spec.js
```

Expected: static tests fail on old grid rows/areas and `4.4rem`; browser tests fail because Outdoor/Battery remain taller than Indoor/Bitcoin.

- [ ] **Step 4: Implement the exact grid**

Replace the Home grid rows and areas with:

```css
grid-template-rows:
  minmax(0, 0.38fr)
  minmax(0, 1fr)
  minmax(0, 1fr)
  minmax(0, 0.55fr)
  minmax(0, 0.72fr);
grid-template-areas:
  'topbar topbar topbar topbar goat greywater'
  'outdoor outdoor battery battery wind baro'
  'indoor indoor bitcoin bitcoin rain sunmoon'
  'solar solar solar zones zones zones'
  'forecast forecast forecast forecast forecast forecast';
```

Do not change the six equal columns, `0.55rem` gap, fixed height, or hidden overflow.

- [ ] **Step 5: Implement the equal-card internal hierarchy**

Change only Home-local primary styles to:

```css
.big-temp,
.indoor-temp {
  font-size: 4rem;
}

.outdoor-body,
.battery-body,
.bitcoin-body {
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.indoor-body {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  min-height: 0;
  gap: 0.35rem;
  overflow: hidden;
}

.indoor-copy {
  width: 100%;
  justify-content: space-between;
  gap: 0.65rem;
  flex: 0 0 auto;
}

.outdoor-spark,
.indoor-spark,
.battery-spark,
.btc-candles {
  min-width: 0;
  min-height: 2.2rem;
  overflow: hidden;
  position: relative;
}

.indoor-spark {
  width: 100%;
  flex: 1;
}

.battery-arc {
  width: 30%;
  max-width: 6.25rem;
}

.btc-price {
  font-size: 1.65rem;
}
```

Preserve existing `flex: 1` or `minmax(..., 1fr)` chart growth rules. Remove the superseded duplicate declarations for these properties instead of stacking overrides at the end of the style block.

Do not edit `tokens.js`, `Tile.svelte`, Weather, modal components, chart data, or refresh logic.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```bash
npm test -- tests/home-tablet-contract.test.js tests/home-card-state.test.js tests/ui/CompassRose.test.js tests/compass-presentation.test.js tests/ui/BitcoinCandles.test.js
npm run test:e2e -- tests/e2e/home-runtime.spec.js
```

Expected: all focused tests PASS at both target viewports; four primary cards differ by no more than 1 CSS pixel in width or height; all four chart regions are at least 35 px high.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/screens/Home.svelte tests/home-tablet-contract.test.js tests/home-card-state.test.js tests/e2e/home-runtime.spec.js
git commit -m "feat: balance home instrument cards"
```

### Task 4: Screenshot review and complete verification

**Files:**
- Verify only: all files changed by Tasks 1-3.
- Screenshot artifacts: Playwright output under `test-results/`; do not commit generated PNG files.

**Interfaces:**
- Consumes: completed Home and Compass changes.
- Produces: fresh automated evidence and side-by-side screenshots for both target viewports; no new product interface.

- [ ] **Step 1: Run the complete focused UI contract**

```bash
npm test -- \
  tests/compass-presentation.test.js \
  tests/ui/CompassRose.test.js \
  tests/home-tablet-contract.test.js \
  tests/home-card-state.test.js \
  tests/ui/BitcoinCandles.test.js \
  tests/chart-call-sites.test.js
```

Expected: all selected Vitest files PASS with zero failures.

- [ ] **Step 2: Run the Home browser suite and inspect its screenshots**

```bash
npm run test:e2e -- tests/e2e/home-runtime.spec.js
```

Expected: four tests PASS: settled and long/unavailable/stale states at 1340x800 and 1280x720. Inspect each generated `home-settled.png` and `home-long-unavailable-stale.png` and confirm:

- the four primary cards are visibly equal;
- no card reads as an accidental leftover strip;
- Outdoor and Battery charts are still legible;
- Indoor and Bitcoin charts have useful space;
- Wind direction, speed, heading text, gust, and maximum are readable without overlap;
- Solar and Zones read as intentional supporting strips;
- no content is clipped or crowded.

- [ ] **Step 3: Run full unit and production-build verification**

```bash
npm test
npm run build
```

Expected: the complete Vitest suite and Vite production build PASS. The existing Vite chunk-size advisory is non-blocking; new warnings are not accepted.

- [ ] **Step 4: Run cross-screen layout regression checks**

```bash
npm run test:e2e -- \
  tests/e2e/home-runtime.spec.js \
  tests/e2e/weather-detail-modal.spec.js \
  tests/e2e/weather-earthship-layout.spec.js
```

Expected: all selected Playwright checks PASS at 1340x800 and 1280x720. Weather, Earthship, and modals retain their existing structure.

- [ ] **Step 5: Verify repository scope and cleanliness**

```bash
git diff --check 28b0ed9..HEAD
git status --short --branch
```

Expected: no whitespace errors and no uncommitted product changes. Only the planned compass helper/tests, CompassRose, Home, and focused tests differ from design commit `28b0ed9`.

Do not push, merge, restart services, or deploy without a separate operator instruction after review.
