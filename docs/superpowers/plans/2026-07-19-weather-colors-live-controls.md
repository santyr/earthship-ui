# Weather Condition Colors + Live Controls Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Color every forecast/condition weather icon on Home and Weather by condition, and make every Controls-page switch live through correlated OpenHAB owner rules.

**Architecture:** Workstream A adds a condition→color map to the existing `wmo.js` single source of truth and threads colors through the existing `OhIcon color` prop at five render sites. Workstream B finishes Tasks 3–6 of `docs/superpowers/plans/2026-07-18-live-control-activation.md`: canonical greywater and night-load owner rules (following the deployed `openhab/rules/feeder-owner.js` patterns), a correlated UI request client, proxy allowlisting of exactly four request items, then attended receipt-bound deployment and live sign-off.

**Tech Stack:** Svelte 5, Vitest/jsdom, Playwright, Vite same-origin proxy, OpenHAB 5.2 REST + ECMAScript rules, JDBC persistence.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-19-weather-colors-live-controls-design.md`. Parent-plan global constraints apply verbatim (`docs/superpowers/plans/2026-07-18-live-control-activation.md:11`).
- The browser never receives or stores the OpenHAB token; never command actuator items (`Goat_Plugs_Outlet2_Switch`, `SouthOutlet_Outlet2_Switch`, `OverrideSwitch`, `Dish_Washer_Power`, `ShurefloPump_Power`, `Goat_Plugs_Outlet1_Switch`) from the UI.
- HTTP 2xx = transport acceptance, not equipment success. No automatic retry after transport break, timeout, or outcome-unknown.
- Greywater: 5-minute cycles, 230-minute start-to-start gap, `SkyCondition == CLEAR` → SoC ≥90 else SoC ≥98, aerobic fallback never bypasses SoC thresholds, **after-dark curfew preserved** (`Sun_Position_Elevation > 0` to start, force-OFF past sunset, fail closed on missing astro data). Curfew gates manual requests too.
- Feeder owner rule never branches on requesting client/source.
- Home outdoor card icon/sparkline keep the temperature-band color (HOME-SPARK-COLOR). Do not change them.
- Only Lenovo Tab M9 1340x800 landscape and ≥1280x720 laptops; no document/card scrolling.
- Agents do not actuate protected production controls; live switch tests are performed by Sat.
- Leave `test-results/` untracked.

---

### Task 1: Condition color map in wmo.js

**Files:**
- Modify: `src/lib/ui/wmo.js`
- Test: `tests/ui/wmo-colors.test.js` (create)

**Interfaces:**
- Consumes: existing `BANDS`/`findBand` structure in `src/lib/ui/wmo.js`.
- Produces: `wmoColor(code): string|null`; `skyIconColor(iconName): string|null`; exported `CONDITION_COLORS` object (keys: `sunny, clearNight, partly, cloudy, fog, rain, pouring, snow, thunder`).

- [ ] **Step 1: Write the failing test**

Create `tests/ui/wmo-colors.test.js`:

```js
import { describe, expect, it } from 'vitest';
import { wmoColor, skyIconColor, CONDITION_COLORS } from '../../src/lib/ui/wmo.js';

describe('wmoColor', () => {
  it('maps band edges to condition colors', () => {
    expect(wmoColor(0)).toBe(CONDITION_COLORS.sunny);      // clear
    expect(wmoColor(2)).toBe(CONDITION_COLORS.partly);
    expect(wmoColor(3)).toBe(CONDITION_COLORS.cloudy);
    expect(wmoColor(45)).toBe(CONDITION_COLORS.fog);
    expect(wmoColor(51)).toBe(CONDITION_COLORS.rain);      // drizzle
    expect(wmoColor(61)).toBe(CONDITION_COLORS.pouring);   // rain band renders pouring icon
    expect(wmoColor(63)).toBe(CONDITION_COLORS.pouring);   // heavy split
    expect(wmoColor(71)).toBe(CONDITION_COLORS.snow);
    expect(wmoColor(80)).toBe(CONDITION_COLORS.pouring);   // showers
    expect(wmoColor(85)).toBe(CONDITION_COLORS.snow);
    expect(wmoColor(95)).toBe(CONDITION_COLORS.thunder);
  });

  it('returns null for unknown or invalid codes', () => {
    for (const code of [null, undefined, '', 'NULL', 'UNDEF', 'abc', 44]) {
      expect(wmoColor(code)).toBeNull();
    }
  });
});

describe('skyIconColor', () => {
  it('maps openHAB condition icon names by category', () => {
    expect(skyIconColor('iconify:mdi:weather-sunny')).toBe(CONDITION_COLORS.sunny);
    expect(skyIconColor('mdi:weather-night')).toBe(CONDITION_COLORS.clearNight);
    expect(skyIconColor('iconify:mdi:weather-night-partly-cloudy')).toBe(CONDITION_COLORS.partly);
    expect(skyIconColor('iconify:mdi:weather-partly-cloudy')).toBe(CONDITION_COLORS.partly);
    expect(skyIconColor('iconify:bi:cloud-sun-fill')).toBe(CONDITION_COLORS.partly);
    expect(skyIconColor('mdi:weather-cloudy')).toBe(CONDITION_COLORS.cloudy);
    expect(skyIconColor('mdi:weather-fog')).toBe(CONDITION_COLORS.fog);
    expect(skyIconColor('mdi:weather-rainy')).toBe(CONDITION_COLORS.rain);
    expect(skyIconColor('mdi:weather-pouring')).toBe(CONDITION_COLORS.pouring);
    expect(skyIconColor('mdi:weather-snowy')).toBe(CONDITION_COLORS.snow);
    expect(skyIconColor('mdi:weather-snowy-heavy')).toBe(CONDITION_COLORS.snow);
    expect(skyIconColor('mdi:weather-lightning')).toBe(CONDITION_COLORS.thunder);
  });

  it('returns null for unknown, empty, or non-weather names', () => {
    for (const name of [null, undefined, '', 'NULL', 'UNDEF', 'mdi:home-thermometer']) {
      expect(skyIconColor(name)).toBeNull();
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- tests/ui/wmo-colors.test.js`
Expected: FAIL — `wmoColor` is not exported.

- [ ] **Step 3: Implement the color map**

In `src/lib/ui/wmo.js`, add colors (per spec palette) and attach a `colorKey` to each band; `findBand`'s heavy-rain split gets `colorKey: 'pouring'`:

```js
// Condition colors (spec 2026-07-19). Anchored to tokens.js accents where
// one exists; all ≥3:1 contrast on the #11151c tile background.
export const CONDITION_COLORS = Object.freeze({
  sunny: '#eab308',
  clearNight: '#cbd5e1',
  partly: '#cbd5e1',
  cloudy: '#94a3b8',
  fog: '#8b93a1',
  rain: '#3b82f6',
  pouring: '#2563eb',
  snow: '#bfdbfe',
  thunder: '#8b5cf6',
});
```

Band → colorKey: sunny(≤1) `sunny`, partly(2) `partly`, cloudy(3) `cloudy`, fog `fog`, drizzle `rain`, rain 61–67 `pouring` (matches its pouring icon), snow bands `snow`, showers `pouring`, thunder `thunder`.

```js
export function wmoColor(code) {
  const key = findBand(code)?.colorKey;
  return key ? CONDITION_COLORS[key] : null;
}

const SKY_ICON_RULES = [
  [/night-partly|cloud-sun|partly/, 'partly'],
  [/weather-night|moon/, 'clearNight'],
  [/sunny|weather-sunset/, 'sunny'],
  [/fog|hazy/, 'fog'],
  [/pouring/, 'pouring'],
  [/rainy|drizzle|showers/, 'rain'],
  [/snowy|snow/, 'snow'],
  [/lightning|thunder/, 'thunder'],
  [/cloudy|cloud/, 'cloudy'],
];

export function skyIconColor(iconName) {
  if (!iconName || iconName === 'NULL' || iconName === 'UNDEF') return null;
  const name = String(iconName).replace(/^iconify:/, '');
  if (!/^(mdi|bi):/.test(name) || !/weather|cloud|moon|sun/.test(name)) return null;
  const rule = SKY_ICON_RULES.find(([re]) => re.test(name));
  return rule ? CONDITION_COLORS[rule[1]] : null;
}
```

Order matters: `partly` before `clearNight`/`sunny`/`cloudy` so composite names match their composite category.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- tests/ui/wmo-colors.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib/ui/wmo.js tests/ui/wmo-colors.test.js
git commit -m "feat: add condition color map for weather icons"
```

---

### Task 2: Apply condition colors at all render sites

**Files:**
- Modify: `src/lib/ui/DailyForecast.svelte:31`
- Modify: `src/lib/ui/HourlyStrip.svelte:153`
- Modify: `src/lib/ui/WeatherDetailModal.svelte:245,283`
- Modify: `src/screens/Weather.svelte:136`
- Test: `tests/ui/weather-icon-colors.test.js` (create)
- Test: existing `tests/e2e/weather-earthship-layout.spec.js`, `tests/e2e/home-runtime.spec.js` (no modification expected)

**Interfaces:**
- Consumes: `wmoColor(code)`, `skyIconColor(iconName)` from Task 1; `OhIcon` prop `color` (defaults `currentColor`).
- Produces: colored condition icons at the five spec render sites; Home outdoor card untouched.

- [ ] **Step 1: Write the failing component test**

Create `tests/ui/weather-icon-colors.test.js` (follow the render/query style of `tests/ui/typed-controls.test.js` — `@testing-library/svelte` render, query SVG by container). Assert, for a fixture forecast day/hour with `weatherCode: 61`:

```js
import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/svelte';
import DailyForecast from '../../src/lib/ui/DailyForecast.svelte';
import { CONDITION_COLORS } from '../../src/lib/ui/wmo.js';

const day = {
  key: '2026-07-19',
  label: 'Sat',
  summary: { weatherCode: 61, tMax: 30, tMin: 15, precipProb: 60, precipSum: 2 },
};

describe('condition icon colors', () => {
  it('DailyForecast colors day icons by condition', () => {
    const { container } = render(DailyForecast, { days: [day], variant: 'home' });
    const svg = container.querySelector('.day-icon svg');
    expect(svg?.getAttribute('color')).toBe(CONDITION_COLORS.pouring);
  });
});
```

Match the actual `days` fixture shape used by existing `DailyForecast`/modal tests (check `tests/ui/` or `src/lib/weather/forecastDetail.js` for the real field names and reuse their fixture builder if one exists). Add equivalent assertions for `HourlyStrip` (row with `w: 61`), `WeatherDetailModal` (selected day summary icon + one hourly icon), and a `Weather.svelte`-level check is covered by `skyIconColor` unit tests from Task 1 (screen renders `color={skyIconColor($items.SkyConditionIcon)}`; jsdom-rendering the whole screen is not required). Also assert unknown code renders without a color attribute override (falls back to `currentColor`).

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- tests/ui/weather-icon-colors.test.js`
Expected: FAIL — icons render with default `currentColor`.

- [ ] **Step 3: Wire colors through the components**

In each site pass the mapped color, falling back to `currentColor` when null:

- `DailyForecast.svelte`: `<OhIcon icon={wmoIcon(day.summary.weatherCode)} size="1.2rem" color={wmoColor(day.summary.weatherCode) ?? 'currentColor'} />` (import `wmoColor`).
- `HourlyStrip.svelte`: same pattern with `row.w`.
- `WeatherDetailModal.svelte`: both icon sites, using the day/hour `weatherCode`.
- `Weather.svelte` current icon: `<OhIcon icon={$items.SkyConditionIcon} size="2.4rem" color={skyIconColor($items.SkyConditionIcon) ?? 'currentColor'} />` (import `skyIconColor`).
- Do NOT touch `src/screens/Home.svelte:472` (outdoor card) or its sparkline.

- [ ] **Step 4: Run focused tests, e2e, and build**

```bash
npm test -- tests/ui/weather-icon-colors.test.js tests/ui/wmo-colors.test.js
npm test
npm run test:e2e -- tests/e2e/home-runtime.spec.js tests/e2e/weather-earthship-layout.spec.js --workers=1
npm run build
```

Expected: all PASS; no layout/geometry changes.

- [ ] **Step 5: Commit**

```bash
git add src/lib/ui/DailyForecast.svelte src/lib/ui/HourlyStrip.svelte \
  src/lib/ui/WeatherDetailModal.svelte src/screens/Weather.svelte \
  tests/ui/weather-icon-colors.test.js
git commit -m "feat: color weather icons by condition"
```

---

### Task 3: Canonical greywater rule with manual requests (source + simulations only)

**Files:**
- Create: `openhab/rules/southoutlet-cycle.js`
- Create: `tests/openhab/greywater-rule.test.js`
- Create: `tests/openhab/greywater-recovery.test.js`
- Modify: `openhab/managed-resources.json`
- Test: existing `tests/openhab/request-ledger.test.js`, `tests/openhab/rest-safety.test.js`

**Interfaces:**
- Consumes: canonical Task 15 contract at `docs/superpowers/plans/2026-07-17-earthship-ui-tablet-audit-implementation.md:3346`; ledger/readback/result patterns from `openhab/rules/feeder-owner.js`; simulation harness `tests/openhab/rule-harness.js`; the live `hex_southoutlet_cycle` script (fetch via GET `/rest/rules/hex_southoutlet_cycle` for the current curfew/fail-closed chain).
- Produces: rule source posting `SouthOutlet_ManualResult` JSON `{requestId, status: 'accepted'|'completed'|'denied'|'failed', reason, at}`; request item `SouthOutlet_ManualRequest` accepting the ledger contract used by `feeder-owner.js` (`{"requestId": /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/, "requestedAt": ISO}`); items `SouthOutlet_LastCycleStart`, `SouthOutlet_LastCycle`; capability id `greywater-request-v1`.

- [ ] **Step 1: Inventory live state (read-only)**

Fetch and record into the task notes: `GET /rest/rules/hex_southoutlet_cycle` (current script — the deployed version includes the after-dark curfew), `GET /rest/items?fields=name,type` filtered to `SouthOutlet_*`, `SkyCondition`, `Sun_Position_Elevation`, persistence config for `SouthOutlet_LastAutoRun`. Reuse existing items; create only `SouthOutlet_ManualRequest` (String), `SouthOutlet_ManualResult` (String), `SouthOutlet_LastCycleStart` (DateTime), `SouthOutlet_LastCycle` (String) via the managed-resources manifest.

- [ ] **Step 2: Write failing sentinel simulations (RED)**

Following the harness style of `tests/openhab/feeder-rule.test.js` + `rule-harness.js`, write `tests/openhab/greywater-rule.test.js` covering, at minimum:

- clear-sky eligibility: `SkyCondition == 'CLEAR'` + SoC 91 → auto cycle starts; SoC 89 → denied `low_soc`.
- non-clear eligibility: `SkyCondition == 'CLOUDY'` (and `NULL`) + SoC 97 → no start; SoC 98.5 → start.
- 5-minute cycle: outlet ON exactly `5 * 60 * 1000` ms then OFF.
- 230-minute gap: second start before gap → `cooldown_wait`; manual request during gap → result `denied` reason `cooldown`.
- curfew: `Sun_Position_Elevation = -1` → no start, running cycle forced OFF with status reason `after_dark`; elevation `NULL`/`UNDEF` → fail closed; manual request at night → `denied` reason `after_dark`.
- aerobic fallback: >24 h since last run + non-clear + SoC 97 → still NO start (never bypasses SoC threshold); >24 h + SoC 98.5 + daylight → start.
- BMS chain preserved: comms stale > 1800 s → force OFF `bms_comms_stale`; invalid SoC/voltage → force OFF.
- manual request happy path: valid request JSON in daylight, SoC eligible, gap elapsed → `accepted` then `completed`, `SouthOutlet_LastCycleStart`/`SouthOutlet_LastCycle` updated, ledger newest-32 persisted with readback gate (reuse `request-ledger.test.js` expectations against the new item).
- duplicate requestId → single cycle, second request `denied` `duplicate`; malformed JSON → `failed` `request_invalid`; reload with outlet ON and no timer → OFF (`orphan_outlet_off`).

`tests/openhab/greywater-recovery.test.js`: restart with pending accepted request → terminal `unknown`-safe recovery per canonical Task 15 (no re-actuation), ledger recovery mirrors `feeder-owner.js` recovery branches.

- [ ] **Step 3: Run RED**

Run: `npm test -- tests/openhab/greywater-rule.test.js tests/openhab/greywater-recovery.test.js`
Expected: FAIL only because `openhab/rules/southoutlet-cycle.js` does not exist.

- [ ] **Step 4: Implement `openhab/rules/southoutlet-cycle.js`**

Start from the live `hex_southoutlet_cycle` script (Step 1 capture) and apply the spec amendments. Core eligibility (replaces `INTERIM_CURTAILMENT_ONLY` block entirely):

```js
const CFG = {
  // ...existing items plus:
  skyConditionItem: 'SkyCondition',
  sunElevationItem: 'Sun_Position_Elevation',
  requestItem: 'SouthOutlet_ManualRequest',
  resultItem: 'SouthOutlet_ManualResult',
  lastCycleStartItem: 'SouthOutlet_LastCycleStart',
  lastCycleItem: 'SouthOutlet_LastCycle',
  clearSocMin: 90,
  defaultSocMin: 98,
  requiredGapMs: 230 * 60 * 1000,
  fallbackMaxGapMs: 24 * 60 * 60 * 1000,
  cycleMs: 5 * 60 * 1000,
};

function socEligible(soc) {
  const sky = state(CFG.skyConditionItem, 'NULL');
  const threshold = sky === 'CLEAR' ? CFG.clearSocMin : CFG.defaultSocMin;
  return { eligible: soc >= threshold, threshold, sky };
}

// After-dark curfew (operator 2026-07-19, re-approved with this spec):
// fail closed on missing astro data; gates auto AND manual paths; a cycle
// caught running past sunset is forced OFF by the cron evaluation.
function daylight() {
  const elev = num(CFG.sunElevationItem, NaN);
  return Number.isFinite(elev) && elev > 0;
}
```

Evaluation order: validity/fail-closed chain (voltage → comms → SoC parse → absurd voltage) → curfew force-OFF → orphan-outlet cleanup → SoC eligibility (`socEligible`) → gap check → start. The aerobic fallback only widens *why* a start is considered (gap > 24 h), never the SoC/curfew gates. Manual requests: triggered by `SouthOutlet_ManualRequest` item update; parse/ledger/readback/result functions copied from the proven `feeder-owner.js` implementations (same regex, same newest-32 ledger, same persist/readback gate, same finally-cleanup); an eligible manual request runs the same `startCycle` and posts `accepted` → `completed`; every denial posts the gate's reason. Rule triggers: existing `DCData_Voltage`/`BMS_SOC` change + 5-min cron + the request item.

- [ ] **Step 5: Run GREEN**

```bash
npm test -- tests/openhab/greywater-rule.test.js tests/openhab/greywater-recovery.test.js \
  tests/openhab/request-ledger.test.js tests/openhab/rest-safety.test.js
```
Expected: PASS without contacting the physical pump.

- [ ] **Step 6: Add managed-resources entries**

Extend `openhab/managed-resources.json` with the four new items, persistence requirements (`SouthOutlet_ManualRequest`, `SouthOutlet_LastCycleStart` persisted/restoreOnStartup like the feeder ledger), the rule UID `hex_southoutlet_cycle` (replace-in-place), and protected dependency `SouthOutlet_Outlet2_Switch`. Follow the existing manifest schema exactly.

- [ ] **Step 7: Commit**

```bash
git add openhab/rules/southoutlet-cycle.js tests/openhab/greywater-rule.test.js \
  tests/openhab/greywater-recovery.test.js openhab/managed-resources.json
git commit -m "feat: add safety-gated greywater requests"
```

---

### Task 4: Serialized night-load owner (source + simulations only)

**Files:**
- Create: `openhab/rules/night-load-owner.js`
- Create: `tests/openhab/night-load-override-rule.test.js`
- Create: `tests/openhab/night-load-recovery.test.js`
- Create: `tests/openhab/override-graph.test.js`
- Modify: `openhab/managed-resources.json`

**Interfaces:**
- Consumes: canonical Task 16 contract at `docs/superpowers/plans/2026-07-17-earthship-ui-tablet-audit-implementation.md:3544`; ledger/readback/result patterns from `openhab/rules/feeder-owner.js`; harness `tests/openhab/rule-harness.js`.
- Produces: request/result String item pairs `NightLoadOverride_Request`/`NightLoadOverride_Result` and `NightLoadDevice_Request`/`NightLoadDevice_Result` (device requests carry `{"requestId", "requestedAt", "device": "dishwasher"|"shureflo"|"goat-cam", "command": "ON"|"OFF"}`); capability id `night-load-owner-v1`; one serialized owner rule commanding `OverrideSwitch`, `Dish_Washer_Power`, `ShurefloPump_Power`, `Goat_Plugs_Outlet1_Switch`.

- [ ] **Step 1: Inventory live state (read-only)**

Record all live rules referencing `OverrideSwitch`, `Dish_Washer_Power`, `ShurefloPump_Power`, `Goat_Plugs_Outlet1_Switch`, `FeederOverride` (GET `/rest/rules?summary=false` filtered), existing schedules, item metadata/persistence, and the Goat Cam ↔ FeederOverride coupling direction. Consolidate by UID per the canonical contract; do not create a duplicate owner.

- [ ] **Step 2: Write failing sentinel simulations (RED)**

Per the canonical Task 16 contract: exact ON/OFF matrices (override ON forces the owned set to the night-load policy states; override OFF restores requested device states), serialized request handling (one in-flight request; concurrent second request `denied` `busy`), persisted ledgers with readback gates, commit-before-command ordering, provider-generation matching (a device request is `completed` only when the provider item reflects the commanded state; mismatch → `failed`), restart-uncertain recovery (no re-actuation, pending → terminal), Goat Cam coupling preserved in its existing direction, schedule interactions, malformed/duplicate request handling identical to the feeder contract, and `override-graph.test.js` proving the retirement of duplicate child rules happens only inside the reversible graph transaction. Static rest-safety scan: no direct browser write path to any of the four actuator items.

- [ ] **Step 3: Run RED**

Run: `npm test -- tests/openhab/night-load-override-rule.test.js tests/openhab/night-load-recovery.test.js tests/openhab/override-graph.test.js`
Expected: FAIL only because `openhab/rules/night-load-owner.js` does not exist.

- [ ] **Step 4: Implement the serialized reducer**

One rule source, triggers on both request items plus a periodic reconciliation cron. Reuse `feeder-owner.js` helpers verbatim for parse/ledger/readback/result. Reducer core: a single persisted owner state machine (`idle` → `transitioning`) stored in a String item ledger; device matrix applied atomically; every command followed by provider readback verification before posting the terminal result. No branching on request source.

- [ ] **Step 5: Run GREEN**

```bash
npm test -- tests/openhab/night-load-override-rule.test.js \
  tests/openhab/night-load-recovery.test.js tests/openhab/override-graph.test.js \
  tests/openhab/request-ledger.test.js tests/openhab/rest-safety.test.js
```
Expected: PASS.

- [ ] **Step 6: Manifest + commit**

Add the four request/result items, owner rule, persistence, and protected dependencies to `openhab/managed-resources.json`.

```bash
git add openhab/rules/night-load-owner.js tests/openhab/night-load-*.test.js \
  tests/openhab/override-graph.test.js openhab/managed-resources.json
git commit -m "feat: serialize night load controls"
```

---

### Task 5: UI request client and live wiring

**Files:**
- Create: `src/lib/controls/requestClient.js`
- Create: `tests/control-state.test.js` additions + `tests/outcome-store.test.js` additions
- Create: `tests/request-client.test.js`
- Modify: `src/lib/controls/controlState.js`
- Modify: `src/lib/ui/Toggle.svelte`
- Modify: `src/screens/Controls.svelte`
- Modify: `src/lib/openhab/proxyPolicy.js`
- Test: `tests/openhab-proxy-policy.test.js`, `tests/ui/typed-controls.test.js`

**Interfaces:**
- Consumes: request/result contracts from Tasks 3–4 and the live feeder contract (`openhab/rules/feeder-owner.js`): request JSON `{"requestId","requestedAt"}` (+ `device`/`command` for `NightLoadDevice_Request`); result JSON `{"requestId","status","reason","at"}`; `getClientOnce()` / `items` store from `src/lib/openhab/index.js`; `deriveControlState` context flags (`capabilities`, `ownerTransitioning`, `ownerBusy`); `recordControlOutcome` from `outcomeStore.js`; phases from `CONTROL_PHASES`.
- Produces: `submitControlRequest(control, payloadExtras, deps): Promise<{phase, reason}>` where terminal `phase ∈ {'accepted','confirmed','error','unknown'}` fed to `Toggle`'s `onPhaseChange`; `REQUEST_POST_ITEMS` export consumed by `proxyPolicy.js`.

- [ ] **Step 1: Write failing tests (RED)**

`tests/request-client.test.js`:

```js
import { describe, expect, it, vi } from 'vitest';
import { submitControlRequest, buildRequestPayload } from '../src/lib/controls/requestClient.js';
```

Prove: `buildRequestPayload()` generates unique `requestId`s matching `/^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/` and ISO `requestedAt`; a result update with a *different* requestId does not resolve the pending promise; matching `completed` → `{phase:'confirmed'}`; `denied` → `{phase:'error', reason}`; `failed` → `{phase:'error'}`; no result before the timeout (use fake timers, bound = 30 s) → `{phase:'unknown'}` and **no second POST ever occurs** (assert `sendCommand`/`postUpdate` spy called exactly once); transport error on POST → `{phase:'unknown'}` without retry.

`tests/openhab-proxy-policy.test.js` additions: POST allowed for exactly `GoatFeeder_ManualRequest`, `SouthOutlet_ManualRequest`, `NightLoadDevice_Request`, `NightLoadOverride_Request` plus the four existing direct items (`living_room_1_Switch`, `living_room_2_Switch`, `LED_living_room_1_Switch`, `LivingRoomCircadian_Enable`); POST denied for every actuator item and for `*_Result` items.

`tests/ui/typed-controls.test.js` additions: with `capabilities: {'greywater-request-v1': true}` etc. and provider ONLINE, the circulation/feeder/owned/override controls render enabled with hold interaction; a hold submits one correlated request; `denied` shows the failed tone with the rule reason; owned devices disable during `ownerTransitioning`/`ownerBusy`; feeder submits like any other (no special-casing).

`tests/control-state.test.js` additions: `deriveControlState` returns `enabled: true` for kinds `owned-binary`/`action`/`safety-request`/`policy-status` when the capability is verified true, provider ONLINE, and owner idle (replacing today's hardcoded "submission unavailable" reasons).

- [ ] **Step 2: Run RED**

```bash
npm test -- tests/request-client.test.js tests/openhab-proxy-policy.test.js \
  tests/ui/typed-controls.test.js tests/control-state.test.js
```
Expected: FAIL — module missing, states still status-only, proxy denies request items.

- [ ] **Step 3: Implement**

`requestClient.js`: `buildRequestPayload(extras)` via `crypto.randomUUID()` (`ui-<uuid>` satisfies the regex); `submitControlRequest` POSTs the JSON string to `control.requestItem` through the same-origin proxy client, subscribes to `items` for `control.resultItem` updates, resolves on the matching `requestId` terminal status, times out at 30 s → `unknown`, never retries. `controlState.js`: enable the four correlated kinds when `capabilities[control.capability] === true`, provider (when present) ONLINE, and not owner-busy/transitioning; keep every existing disable reason for the negative cases. `Toggle.svelte`: in `submit()`, branch — direct kinds keep `sendCommand`; correlated kinds call `submitControlRequest`, feeding phases through the existing `onPhaseChange`/`outcomeStore` machinery. `Controls.svelte`: pass a `capabilities` prop sourced from a new exported `VERIFIED_CAPABILITIES` constant in `controlState.js` (all false until Task 7 flips the verified ones in one reviewed commit) plus owner busy/transition state derived from the `NightLoadOverride_Result`/ledger items. `proxyPolicy.js`: add `REQUEST_POST_PATHS` from the four request items; allow POST when path ∈ direct ∪ request sets under `safe-compat`/`full`.

- [ ] **Step 4: Run GREEN + full gates**

```bash
npm test -- tests/request-client.test.js tests/openhab-proxy-policy.test.js \
  tests/ui/typed-controls.test.js tests/control-state.test.js tests/outcome-store.test.js
npm test
npm run test:e2e -- --workers=1
npm run build
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib/controls/requestClient.js src/lib/controls/controlState.js \
  src/lib/ui/Toggle.svelte src/screens/Controls.svelte src/lib/openhab/proxyPolicy.js \
  tests/request-client.test.js tests/openhab-proxy-policy.test.js \
  tests/ui/typed-controls.test.js tests/control-state.test.js tests/outcome-store.test.js
git commit -m "feat: activate correlated household controls"
```

---

### Task 6: Attended openHAB deployment (OPERATOR-GATED)

**Files:**
- Modify: `scripts/openhab-config.mjs` (add greywater + night-load transaction subjects if not generic)
- Verify: live openHAB via REST only

**Interfaces:**
- Consumes: committed rule sources and manifest from Tasks 3–4; `scripts/openhab-config.mjs` snapshot/apply/rehearse/verify/rollback/close operations and receipt format (read the script first; reuse its existing subcommands).
- Produces: live items, persistence, and rules for greywater and night-load; closed receipts; capabilities ready for verification.

**STOP: This task requires Sat's contemporaneous approval before any live write, and (for greywater) Sat able to see the pump. Request approval in-conversation and wait.**

- [ ] **Step 1: Greywater transaction** — with approval: snapshot the exact SouthOutlet subset (rule, items, persistence, links), verify provider `SouthOutlet_Outlet2_Switch` OFF, disable `hex_southoutlet_cycle`, apply the new script + items via REST, rehearse rollback/reapply while disabled, verify hashes/persistence/no-ERROR logs, re-enable, then `runnow` and confirm a safe status (e.g. `cooldown_wait`/`after_dark`/denial — NOT a surprise start; if SoC/sky/gap all permit a start, that is an expected observable cycle Sat watches). Close the receipt.
- [ ] **Step 2: Night-load transaction** — with approval, outside both schedules: snapshot owner graph (rules, schedules, items, metadata, persistence, provider states, coupling-rule hashes), keep schedules disabled until the owner verifies healthy, apply, rehearse rollback/reapply, activate owner first and schedules last, close the receipt only when provider states, policy state, rule status, and logs agree.
- [ ] **Step 3: Record** — save receipt summaries to hexmem (`event_type: config_change`, category `operations`) and commit any script changes:

```bash
git add scripts/openhab-config.mjs
git commit -m "feat: deploy greywater and night-load owners"
```

---

### Task 7: Live verification, capability activation, and sign-off (OPERATOR-GATED)

**Files:**
- Modify: `src/lib/controls/controlState.js` (flip `VERIFIED_CAPABILITIES`)
- Modify: `docs/qa/ui-audit-matrix.csv`

**Interfaces:**
- Consumes: deployed owners (Task 6), live UI service `earthship-ui.service` on port 5190.
- Produces: live controls in production UI; audit matrix rows `verified-live`; operator sign-off.

- [ ] **Step 1: Flip verified capabilities** — set `feeder-request-v1`, `greywater-request-v1`, `night-load-owner-v1` true in `VERIFIED_CAPABILITIES` only after Task 6 receipts closed. Run `npm test && npm run build`, commit `feat: enable verified control capabilities`, then `systemctl --user restart earthship-ui.service` and verify active/enabled/listening on 5190.
- [ ] **Step 2: Read-only live verification** — request/result items exist and persist, rules IDLE/RUNNING, provider Things ONLINE, proxy denies actuator POSTs (curl through the UI origin), no browser token, no new openHAB ERROR/Exception entries.
- [ ] **Step 3: Sat operates every control live** while the agent observes evidence: tap toggles each living-room light and restores; hold toggles Circadian; each owned load produces matching owner + provider receipts; feeder produces one pulse, one count increment, confirmed OFF; circulation produces an explicit safety denial or one approved 5-minute cycle with matching result and final OFF; Night Load Override follows the exact matrix. **Stop immediately on mismatch or outcome-unknown.**
- [ ] **Step 4: Record sign-off** — update `docs/qa/ui-audit-matrix.csv` to `verified-live` only for behavior actually observed; run `npm test -- tests/audit-matrix.test.js`, `git diff --check`; commit `docs: record live control sign-off`; save the receipt summary to hexmem.
