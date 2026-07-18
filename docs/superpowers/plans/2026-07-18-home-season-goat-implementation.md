# Home Seasonal Countdown and Goat Feeding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a truthful local seasonal countdown and a read-only Goat Feedings card with transition-only visual/audio feedback while preserving the two exact bounded Home layouts.

**Architecture:** Keep deterministic formatting, seasonal math, and feeder transition semantics in `homeCardState.js`. Encapsulate browser lifecycle, feedback timing, and best-effort Web Audio in a focused `GoatFeedingsCard.svelte`; `Home.svelte` only supplies item states and places the card. Extend the existing exact-size Playwright fixture with live statechanged events so runtime transition behavior is verified through the real store and SSE path.

**Tech Stack:** Svelte 5 runes, JavaScript ES modules, Vitest, Testing Library Svelte, Playwright, bundled Iconify MDI icons, the exact Unicode goat glyph, browser Web Audio API.

## Global Constraints

- Supported layouts are exactly 1340×800 CSS pixels and 1280×720 CSS pixels.
- Neither viewport may gain page, card, tile-body, or card-content overflow.
- `GoatFeedingsToday` and `Goat_Plugs_Outlet2_Switch` are read-only inputs.
- Never import a command client, call `sendCommand`, or expose a feeder control.
- Initial `ON`, duplicate `ON`, unknown states, and `ON` after unknown never activate feedback.
- Only an observed `OFF` to `ON` transition activates feedback.
- Visual feedback always works; audio is quiet, short, best-effort, and available only after a pointer/key interaction.
- Respect `prefers-reduced-motion: reduce`.
- Seasonal calculation has no network or runtime package dependency and uses browser-local calendar dates.
- Outdoor icon and sparkline use one live temperature-band color with at least 3:1 contrast against `#11151c`.
- AC Metrics remains excluded from Battery.

---

### Task 1: Pure Goat and Seasonal State

**Files:**
- Modify: `src/lib/ui/homeCardState.js`
- Modify: `tests/home-card-state.test.js`

**Interfaces:**
- Produces: `formatGoatFeedings(raw): string`
- Produces: `createGoatFeederTracker(): { initialized: boolean, previous: 'ON' | 'OFF' | null }`
- Produces: `advanceGoatFeederTracker(tracker, raw): { tracker, activated: boolean }`
- Produces: `nextSeasonEvent(now?: Date): { name: string, days: number, label: string, instant: Date } | null`

- [ ] **Step 1: Write failing Goat helper tests**

```js
it.each([
  ['0', '0 feedings today'],
  ['1', '1 feeding today'],
  ['2.4', '2 feedings today'],
  ['UNDEF', 'Feedings unavailable'],
  [-1, 'Feedings unavailable'],
])('formats Goat feedings %s truthfully', (raw, expected) => {
  expect(formatGoatFeedings(raw)).toBe(expected);
});

it('activates only after a known OFF to ON transition', () => {
  let state = createGoatFeederTracker();
  ({ tracker: state } = advanceGoatFeederTracker(state, 'ON'));
  expect(advanceGoatFeederTracker(state, 'ON').activated).toBe(false);
  ({ tracker: state } = advanceGoatFeederTracker(state, 'OFF'));
  expect(advanceGoatFeederTracker(state, 'ON').activated).toBe(true);
});

it('breaks the OFF to ON chain when an unknown state intervenes', () => {
  let state = advanceGoatFeederTracker(createGoatFeederTracker(), 'OFF').tracker;
  state = advanceGoatFeederTracker(state, 'UNDEF').tracker;
  expect(advanceGoatFeederTracker(state, 'ON').activated).toBe(false);
});
```

- [ ] **Step 2: Run Goat helper tests to verify RED**

Run: `npm test -- --run tests/home-card-state.test.js`

Expected: FAIL because the three exports do not exist.

- [ ] **Step 3: Implement minimal Goat helpers**

```js
export function formatGoatFeedings(raw) {
  const count = finiteNumber(raw);
  if (count === null || count < 0) return 'Feedings unavailable';
  const rounded = Math.round(count);
  return `${rounded} ${rounded === 1 ? 'feeding' : 'feedings'} today`;
}

export function createGoatFeederTracker() {
  return { initialized: false, previous: null };
}

export function advanceGoatFeederTracker(tracker, raw) {
  const normalized = String(raw ?? '').trim().toUpperCase();
  const known = normalized === 'ON' || normalized === 'OFF' ? normalized : null;
  if (!known) {
    return {
      tracker: { initialized: Boolean(tracker?.initialized), previous: null },
      activated: false,
    };
  }
  if (!tracker?.initialized) {
    return { tracker: { initialized: true, previous: known }, activated: false };
  }
  return {
    tracker: { initialized: true, previous: known },
    activated: tracker.previous === 'OFF' && known === 'ON',
  };
}
```

- [ ] **Step 4: Write failing seasonal helper tests**

```js
it('counts browser-local calendar days to the 2026 autumn equinox', () => {
  expect(nextSeasonEvent(new Date(2026, 6, 18, 23, 30))).toMatchObject({
    name: 'autumn equinox',
    days: 66,
    label: '66 days to autumn equinox',
  });
});

it('uses singular and event-day wording', () => {
  expect(nextSeasonEvent(new Date(2026, 8, 21, 12))).toMatchObject({
    days: 1,
    label: '1 day to autumn equinox',
  });
  expect(nextSeasonEvent(new Date(2026, 8, 22, 23))).toMatchObject({
    days: 0,
    label: 'autumn equinox today',
  });
});

it('rolls from the December solstice to the next spring equinox', () => {
  expect(nextSeasonEvent(new Date(2026, 11, 22, 12))).toMatchObject({
    name: 'spring equinox',
  });
});
```

- [ ] **Step 5: Run seasonal tests to verify RED**

Run: `npm test -- --run tests/home-card-state.test.js`

Expected: FAIL because `nextSeasonEvent` does not exist.

- [ ] **Step 6: Implement polynomial event instants and DST-safe local-day subtraction**

```js
const DAY_MS = 86_400_000;
const JULIAN_UNIX_EPOCH = 2_440_587.5;
const SEASON_EVENTS = Object.freeze([
  ['spring equinox', [2451623.80984, 365242.37404, 0.05169, -0.00411, -0.00057]],
  ['summer solstice', [2451716.56767, 365241.62603, 0.00325, 0.00888, -0.00030]],
  ['autumn equinox', [2451810.21715, 365242.01767, -0.11575, 0.00337, 0.00078]],
  ['winter solstice', [2451900.05952, 365242.74049, -0.06223, -0.00823, 0.00032]],
]);

function seasonInstant(year, coefficients) {
  const y = (year - 2000) / 1000;
  const jde = coefficients.reduce((sum, coefficient, power) => sum + coefficient * y ** power, 0);
  return new Date((jde - JULIAN_UNIX_EPOCH) * DAY_MS);
}

function localDayStamp(date) {
  return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate());
}

export function nextSeasonEvent(now = new Date()) {
  if (!(now instanceof Date) || Number.isNaN(now.getTime())) return null;
  const today = localDayStamp(now);
  const candidates = [now.getFullYear(), now.getFullYear() + 1]
    .flatMap((year) => SEASON_EVENTS.map(([name, coefficients]) => ({
      name,
      instant: seasonInstant(year, coefficients),
    })))
    .map((event) => ({ ...event, day: localDayStamp(event.instant) }))
    .filter((event) => event.day >= today)
    .sort((a, b) => a.day - b.day);
  const next = candidates[0];
  if (!next) return null;
  const days = Math.round((next.day - today) / DAY_MS);
  return {
    name: next.name,
    days,
    label: days === 0
      ? `${next.name} today`
      : `${days} ${days === 1 ? 'day' : 'days'} to ${next.name}`,
    instant: next.instant,
  };
}
```

- [ ] **Step 7: Run the pure helper suite to verify GREEN**

Run: `npm test -- --run tests/home-card-state.test.js`

Expected: all Home card-state tests pass.

### Task 2: Read-only Goat Feedings Component

**Files:**
- Create: `src/lib/ui/GoatFeedingsCard.svelte`
- Create: `tests/ui/GoatFeedingsCard.test.js`

**Interfaces:**
- Consumes: `feedings`, `motorState`, optional `feedbackMs`
- Consumes: Task 1 Goat helper exports
- Produces: a centered `Tile` group named from the truthful feeding text
- Produces: `.goat-feed-icon` in steady state and `.goat-activation-icon` during feedback

- [ ] **Step 1: Write failing component tests**

```js
function installFakeAudioContext() {
  const context = {
    currentTime: 1,
    destination: {},
    resume: vi.fn(() => Promise.resolve()),
    close: vi.fn(() => Promise.resolve()),
    createOscillator: vi.fn(() => ({
      type: '',
      frequency: {
        setValueAtTime: vi.fn(),
        exponentialRampToValueAtTime: vi.fn(),
      },
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
    })),
    createGain: vi.fn(() => ({
      gain: {
        setValueAtTime: vi.fn(),
        exponentialRampToValueAtTime: vi.fn(),
      },
      connect: vi.fn(),
    })),
  };
  Object.defineProperty(window, 'AudioContext', {
    configurable: true,
    value: class {
      constructor() { return context; }
    },
  });
  return context;
}

it('renders a read-only feeding summary with the normal feed icon', () => {
  const { container } = render(GoatFeedingsCard, {
    props: { feedings: '2', motorState: 'OFF' },
  });
  expect(screen.getByRole('group', { name: 'Goat feedings: 2 feedings today' })).toBeInTheDocument();
  expect(container.querySelector('.goat-feed-icon svg')).toBeInTheDocument();
  expect(container.querySelector('button')).toBeNull();
});

it('ignores initial ON and shows the goat only for a later OFF to ON', async () => {
  const view = render(GoatFeedingsCard, {
    props: { feedings: '1', motorState: 'ON', feedbackMs: 1800 },
  });
  expect(view.container.querySelector('.goat-activation-icon')).toBeNull();
  await view.rerender({ feedings: '1', motorState: 'OFF', feedbackMs: 1800 });
  await view.rerender({ feedings: '2', motorState: 'ON', feedbackMs: 1800 });
  expect(view.container.querySelector('.goat-activation-icon svg')).toBeInTheDocument();
  vi.advanceTimersByTime(1800);
  await tick();
  expect(view.container.querySelector('.goat-activation-icon')).toBeNull();
});

it('does not attempt audio before a browser interaction', async () => {
  const context = installFakeAudioContext();
  const view = render(GoatFeedingsCard, { props: { feedings: '0', motorState: 'OFF' } });
  await view.rerender({ feedings: '1', motorState: 'ON' });
  expect(context.createOscillator).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run component tests to verify RED**

Run: `npm test -- --run tests/ui/GoatFeedingsCard.test.js`

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement the component**

Implement:

```svelte
<script>
  import { onMount, onDestroy } from 'svelte';
  import Tile from './Tile.svelte';
  import OhIcon from './OhIcon.svelte';
  import {
    advanceGoatFeederTracker,
    createGoatFeederTracker,
    formatGoatFeedings,
  } from './homeCardState.js';

  let { feedings, motorState, feedbackMs = 1800 } = $props();
  let active = $state(false);
  let tracker = createGoatFeederTracker();
  let timer;
  let audioContext;
  let audioArmed = false;
  const feedingText = $derived(formatGoatFeedings(feedings));

  function armAudio() {
    if (audioArmed || typeof window === 'undefined') return;
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    try {
      audioContext = new AudioContext();
      audioContext.resume?.().catch(() => {});
      audioArmed = true;
    } catch {
      audioContext = undefined;
    }
  }

  function playChime() {
    if (!audioArmed || !audioContext) return;
    try {
      const now = audioContext.currentTime;
      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();
      oscillator.type = 'sine';
      oscillator.frequency.setValueAtTime(659.25, now);
      oscillator.frequency.exponentialRampToValueAtTime(880, now + 0.12);
      gain.gain.setValueAtTime(0.025, now);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.25);
      oscillator.connect(gain);
      gain.connect(audioContext.destination);
      oscillator.start(now);
      oscillator.stop(now + 0.25);
    } catch {
      // Visual feedback is authoritative; audio is best-effort.
    }
  }

  function activate() {
    active = true;
    clearTimeout(timer);
    timer = setTimeout(() => { active = false; }, feedbackMs);
    playChime();
  }

  $effect(() => {
    const result = advanceGoatFeederTracker(tracker, motorState);
    tracker = result.tracker;
    if (result.activated) activate();
  });

  onMount(() => {
    window.addEventListener('pointerdown', armAudio, { passive: true });
    window.addEventListener('keydown', armAudio);
  });

  onDestroy(() => {
    clearTimeout(timer);
    window.removeEventListener('pointerdown', armAudio);
    window.removeEventListener('keydown', armAudio);
    audioContext?.close?.().catch(() => {});
  });
</script>
```

Render the exact bounded card:

```svelte
<Tile
  label="Goat Feedings"
  accessibleLabel={`Goat feedings: ${feedingText}`}
  accent="#8b5cf6"
  hideLabel fill clip centerBody
  padding="0.55rem 0.65rem"
>
  <div class="goat-feeding-body" class:active>
    {#if active}
      <span class="goat-activation-icon" aria-hidden="true">🐐</span>
    {:else}
      <span class="goat-feed-icon" aria-hidden="true">
        <OhIcon icon="iconify:mdi:food-apple-outline" size="1.35rem" />
      </span>
    {/if}
    <span class="goat-feeding-text" title={feedingText}>{feedingText}</span>
  </div>
</Tile>

<style>
  .goat-feeding-body {
    width: 100%;
    min-width: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.45rem;
    overflow: hidden;
    color: #c7cfd9;
  }
  .goat-feed-icon,
  .goat-activation-icon {
    display: inline-flex;
    flex: 0 0 auto;
    color: #8b5cf6;
    line-height: 1;
  }
  .goat-activation-icon {
    color: #f59e0b;
    animation: goat-pulse 600ms ease-in-out infinite alternate;
  }
  .goat-feeding-text {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.78rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  @keyframes goat-pulse {
    from { transform: scale(1); opacity: 0.75; }
    to { transform: scale(1.12); opacity: 1; }
  }
  @media (prefers-reduced-motion: reduce) {
    .goat-activation-icon { animation: none; }
  }
</style>
```

- [ ] **Step 4: Run component and helper tests to verify GREEN**

Run: `npm test -- --run tests/ui/GoatFeedingsCard.test.js tests/home-card-state.test.js`

Expected: both test files pass with no warnings.

### Task 3: Home Integration and Seasonal Row

**Files:**
- Modify: `src/screens/Home.svelte`
- Modify: `tests/home-tablet-contract.test.js`

**Interfaces:**
- Consumes: `GoatFeedingsCard`
- Consumes: `SeasonCountdown`, which owns the live clock and `nextSeasonEvent` call
- Supplies: `$items.GoatFeedingsToday`, `$items.Goat_Plugs_Outlet2_Switch`

- [ ] **Step 1: Write failing source-contract tests**

```js
expect(home).toContain('feedings={$items.GoatFeedingsToday}');
expect(home).toContain('motorState={$items.Goat_Plugs_Outlet2_Switch}');
expect(home).toContain("'topbar topbar topbar topbar goat greywater'");
expect(home).toContain('class="cell goat-cell"');
expect(home).toMatch(/<SeasonCountdown\s*\/>/);
expect(seasonCountdown).toContain('class="sm-row sm-season"');
expect(home).toMatch(/<Sparkline\s+data=\{outdoorSpark\}\s+color=\{outdoorIconColor\}/);
expect(home).not.toContain('sendCommand');
```

- [ ] **Step 2: Run source-contract tests to verify RED**

Run: `npm test -- --run tests/home-tablet-contract.test.js`

Expected: FAIL on missing Goat and seasonal integration.

- [ ] **Step 3: Wire the Goat and live seasonal components**

Import `GoatFeedingsCard` and `SeasonCountdown`; the latter refreshes its own browser-local clock hourly and clears that timer on teardown.

Place after Power Flow:

```svelte
<div class="cell goat-cell">
  <GoatFeedingsCard
    feedings={$items.GoatFeedingsToday}
    motorState={$items.Goat_Plugs_Outlet2_Switch}
  />
</div>
```

Add `<SeasonCountdown />` after daylight. Change the top area string to `'topbar topbar topbar topbar goat greywater'` and assign `.goat-cell { grid-area: goat; }`; the component supplies the bounded muted seasonal row.

Change the Outdoor sparkline from `color={colors.temperature}` to `color={outdoorIconColor}`. In the pure state test, assert every output of `outdoorTemperatureIconColor` has at least 3:1 contrast against `#11151c`; change the sub-freezing purple from `#9c27b0` to `#ab47bc` so the shared icon/line color clears that floor.

- [ ] **Step 4: Run source-contract and focused UI tests to verify GREEN**

Run: `npm test -- --run tests/home-tablet-contract.test.js tests/ui/GoatFeedingsCard.test.js tests/home-card-state.test.js`

Expected: all focused tests pass.

### Task 4: Exact Runtime and Geometry Verification

**Files:**
- Modify: `tests/e2e/home-runtime.spec.js`

**Interfaces:**
- Extends `openHomeFixture` with `emitState(name, value)` that sends a real openHAB `statechanged` payload through the fixture EventSource.
- Verifies Task 3 through the application store, not by directly rerendering a component.

- [ ] **Step 1: Add failing fixture, runtime, and geometry assertions**

Add `GoatFeedingsToday: '2'` and `Goat_Plugs_Outlet2_Switch: 'ON'` to the initial fixture. Track EventSource instances in the init script and return:

```js
emitState: async (name, value) => page.evaluate(({ name, value }) => {
  const source = window.__fixtureEventSources.at(-1);
  source.onmessage?.({
    data: JSON.stringify({
      topic: `openhab/items/${name}/statechanged`,
      payload: JSON.stringify({ value }),
      type: 'ItemStateChangedEvent',
    }),
  });
}, { name, value }),
```

At both target viewports assert:

```js
await expect(page.getByRole('group', { name: 'Goat feedings: 2 feedings today' })).toBeVisible();
await expect(page.locator('.goat-activation-icon')).toHaveCount(0);
await runtime.emitState('Goat_Plugs_Outlet2_Switch', 'OFF');
await runtime.emitState('Goat_Plugs_Outlet2_Switch', 'ON');
await expect(page.locator('.goat-activation-icon svg')).toBeVisible();
await expect(page.locator('.sm-season')).toContainText(/(?:equinox|solstice)/);
```
await expect(page.locator('.outdoor-spark svg path[stroke="#4caf50"]').first()).toBeVisible();
await runtime.emitState('AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', '86');
await expect(page.locator('.cond-icon svg')).toHaveCSS('color', 'rgb(244, 67, 54)');
await expect(page.locator('.outdoor-spark svg path[stroke="#f44336"]').first()).toBeVisible();

Extend geometry with Power Flow line and Goat body boxes. Assert the Power Flow first line has positive width, `scrollWidth <= clientWidth`, the Goat icon is left of its text, centered body count is `14`, and all existing bounded-cell checks include the new card.

- [ ] **Step 2: Run Playwright to verify RED**

Run: `npx playwright test tests/e2e/home-runtime.spec.js`

Expected: FAIL because the items, component, EventSource emitter, or geometry fields are not yet fully wired.

- [ ] **Step 3: Complete only the fixture/geometry plumbing required by the assertions**

In the init script, expose each source without bypassing SSE:

```js
class FixtureEventSource {
  constructor() {
    window.__fixtureEventSources ??= [];
    window.__fixtureEventSources.push(this);
    setTimeout(() => this.onopen?.({ type: 'open' }), 0);
  }
  close() {}
}
```

Return this fixture API alongside `setStates`:

```js
emitState: async (name, value) => page.evaluate(({ name, value }) => {
  const source = window.__fixtureEventSources.at(-1);
  source.onmessage?.({
    data: JSON.stringify({
      topic: `openhab/items/${name}/statechanged`,
      payload: JSON.stringify({ value }),
      type: 'ItemStateChangedEvent',
    }),
  });
}, { name, value }),
```

Add these measurements:

```js
const powerFlowLine = document.querySelector('.pf-line1');
const goatIcon = document.querySelector('.goat-feed-icon, .goat-activation-icon');
const goatText = document.querySelector('.goat-feeding-text');

powerFlow: {
  line: extent(powerFlowLine),
},
goat: {
  icon: box(goatIcon),
  text: box(goatText),
},
```

Add these separation/bounds assertions and update both centered-card expectations:

```js
expect(geometry.powerFlow.line.width).toBeGreaterThan(0);
expect(geometry.powerFlow.line.scrollWidth).toBeLessThanOrEqual(geometry.powerFlow.line.clientWidth);
expect(geometry.goat.icon.right).toBeLessThanOrEqual(geometry.goat.text.left + 0.5);
expect(geometry.centeredBodies).toBe(14);
```

Do not bypass the real SSE parser or Svelte item store.

- [ ] **Step 4: Run exact-size Playwright to verify GREEN**

Run: `npx playwright test tests/e2e/home-runtime.spec.js`

Expected: four tests pass at Lenovo Tab M9 1340×800 and laptop 1280×720 with no overflow or page errors.

### Task 5: Final Verification and Scoped Handoff

**Files:**
- Create: `.superpowers/sdd/home-review-fixes-report.md`
- Verify: all scoped Home files and tests

**Interfaces:**
- Produces: fresh unit, build, and exact-size browser evidence.

- [ ] **Step 1: Run focused verification**

Run:

```bash
npm test -- --run tests/home-card-state.test.js tests/ui/GoatFeedingsCard.test.js tests/home-tablet-contract.test.js
npx playwright test tests/e2e/home-runtime.spec.js
```

Expected: all focused unit/component/contract and four exact-size browser tests pass.

- [ ] **Step 2: Run full verification**

Run:

```bash
npm test
npm run build
git diff --check
```

Expected: full unit suite passes, production build exits 0, and diff check emits no errors.

- [ ] **Step 3: Write the SDD report**

Record requirements, red/green commands and outcomes, exact viewport geometry evidence, changed files, read-only proof, and any unresolved live OpenHAB dependency in `.superpowers/sdd/home-review-fixes-report.md`.

- [ ] **Step 4: Commit only scoped Home changes**

Stage the exact Home/helper/component/test/report paths, inspect `git diff --cached`, and commit with:

```bash
git commit -m "feat: complete tablet Home status console"
```

Do not stage unrelated OpenHAB, deployment, or other-agent files.
