# Change-only UI Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Base essential temperature freshness on upstream updates and battery freshness on its heartbeat value, preserving honest unavailable states and existing critical alerts.

**Architecture:** Keep value rendering on the existing statechanged stream. A separate targeted stateupdated callback maintains monotonic temperature evidence; the existing snapshot readiness store gates warnings. One parser serves REST update evidence, SSE update evidence, and heartbeat values.

**Tech Stack:** Svelte stores, JavaScript ES modules, Vitest, Playwright, existing Vite fixture server.

## Global Constraints

- Worktree: `/home/sat/earthship-ui/.worktrees/change-only-alerts`, branch `fix/change-only-alerts`, reviewed base `4818d754e4394f98660901d6f8ed40e2f0feed5b`.
- The September 5 operator approval of all pending work (Hexmem event 8668) supersedes the specification's pending-review wording. This document covers UI only. Deployment still requires the exact reviewed deployment target and rollback to be presented; do not restart services while implementing or testing.
- Keep JDBC everyChange and restoreOnStartup unchanged. Do not alter estimator gates, advisory thresholds, household controls, the forecast schedule, or counters.
- Task 82 remains on hold. Never send test DMs or save decrypted DM archives.
- No external-checker implementation in this task. Its separate plan and the specification's remaining historical algorithm families remain required; this task does not close the all-algorithm audit.
- No new dependencies, control writes, server configuration changes, or persistence changes.
- Temperature threshold remains 15 minutes; heartbeat threshold is 12 minutes. Equality with a threshold remains healthy, matching the existing strictly-greater-than convention.
- Source timestamps are distinct from local receipt. Never infer health from row age, value changes, reconnect receipt, or density.

---

### Task 1: Integrate upstream freshness from REST and SSE through header alerts

**Files:**

- Create `src/lib/openhab/timestamp.js`: strict shared timestamp parser.
- Create `src/lib/alerts/batteryHealth.js`: shared existing comms/device normalization.
- Modify `src/lib/openhab/client.js`, `sse.js`, `store.js`, `index.js`: request and transport independent source evidence.
- Replace `src/lib/alerts/staleness.js`; modify `alertStore.js` and `consoleAlerts.js`: compute and display unavailable/stale evidence without duplicate battery warnings.
- Replace `tests/alert-staleness.test.js`; create `tests/timestamp.test.js`.
- Modify `tests/store.test.js`, `tests/client.test.js`, `tests/openhab-proxy-policy.test.js`, `tests/ui/HeaderAlerts.test.js`, and `tests/e2e/home-runtime.spec.js` for the exact changed contracts and browser regression below.
- Existing `tests/sse.test.js`, `tests/openhab-init.test.js`, and `tests/console-alerts.test.js` remain in the focused regression command; their existing parser, reconnect, boot-retry, and critical-alert contracts remain supported.

**Interfaces:**

- `parseSourceTimestamp(value, nowMs = Date.now()) -> number | null`: finite positive epoch milliseconds (number) or offset-qualified ISO string; no numeric-string coercion.
- `itemUpdateEvidence`: writable `{ [temperatureName]: { lastKnown: number | null, available: boolean } }`. Only the two curated temperatures are stored here.
- `applyUpdateEvidence(name, rawTimestamp) -> void`: never writes the items store. Invalid/missing input retains lastKnown and marks unavailable. Older valid input leaves the entire prior record untouched. Equal valid input restores availability.
- `createSSE({ onUpdateEvidence(name, rawTimestamp), ...existingOptions })`: invokes only for targeted stateupdated events; does not call onState for them.
- `computeStaleEssentials(evidence, nowMs, { values, ready }) -> staleEssentials[]`: existing alert entry shape plus `unavailable: true` when evidence cannot establish freshness.
- Reuse `clientReady` for boot gating; do not add a second snapshot-ready flag or local receipt clock.

- [ ] **Step 1: Add strict parser tests before implementation.** Create `tests/timestamp.test.js`:

```js
import { expect, it } from 'vitest';
import { parseSourceTimestamp } from '../src/lib/openhab/timestamp.js';

const NOW = Date.parse('2026-09-05T18:00:00Z');
it.each([
  [NOW, NOW],
  ['2026-09-05T11:59:59.123456789-06:00[America/Denver]', NOW - 877],
  ['2026-09-05T17:59:59Z', NOW - 1000],
  ['2024-02-29T00:00:00+00:00', Date.parse('2024-02-29T00:00:00Z')],
])('parses %s without changing its instant', (value, expected) => {
  expect(parseSourceTimestamp(value, NOW)).toBe(expected);
});
it.each([
  undefined, null, '', 'NULL', 'UNDEF', true, {}, [], NaN, Infinity,
  0, -1, NOW + 1, String(NOW), '2026-09-05T18:00:01Z',
  '2026-09-05T17:00:00', '2026-02-29T01:00:00Z',
  '2026-04-31T01:00:00Z', '2026-13-01T01:00:00Z',
  '2026-01-00T01:00:00Z', '2026-01-01T24:00:00Z',
  '2026-01-01T12:60:00Z', '2026-01-01T12:00:60Z',
  '2026-01-01T12:00:00+24:00', '2026-01-01T12:00:00+01:60',
  '2026-01-01T12:00:00Z[]', '2026-01-01T12:00:00Z[broken',
  '2026-01-01T12:00:00Z trailing',
])('rejects unusable evidence %s', (value) => {
  expect(parseSourceTimestamp(value, NOW)).toBeNull();
});
```

- [ ] **Step 2: Replace the obsolete receipt-clock tests with real stream integration tests.** Replace `tests/alert-staleness.test.js` in full:

```js
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { createSSE } from '../src/lib/openhab/sse.js';
import {
  initOpenhab, items, clientReady, itemUpdateEvidence, applySnapshot,
} from '../src/lib/openhab/store.js';
import { alertContext, consoleAlerts, startStalenessMonitor } from '../src/lib/alerts/alertStore.js';
import { ESSENTIAL_ITEMS, computeStaleEssentials } from '../src/lib/alerts/staleness.js';

const OUT = ESSENTIAL_ITEMS[0].name;
const IN = ESSENTIAL_ITEMS[1].name;
const NOW = Date.parse('2026-09-05T18:00:00Z');
let stream, stop, snapshot;
class FakeES {
  static all = [];
  constructor(url) { this.url = url; FakeES.all.push(this); }
  close() {}
}
function emit(name, suffix, payload) {
  FakeES.all.at(-1).onmessage({ data: JSON.stringify({
    topic: `openhab/items/${name}/${suffix}`, payload: JSON.stringify(payload),
  }) });
}
function healthy(at = Date.now()) {
  return [
    { name: OUT, state: '70', lastStateUpdate: at },
    { name: IN, state: '69', lastStateUpdate: at },
    { name: 'BMS_SOC', state: '100', lastStateUpdate: at - 6 * 3600000 },
    { name: 'BMS_SOC_LastUpdate', state: new Date(at).toISOString() },
    { name: 'BMS_Comms_Status', state: 'OK' },
    { name: 'BMS_DevicePresent', state: '1' },
  ];
}
async function boot(rows = healthy()) {
  snapshot = rows;
  const client = { getAllItems: vi.fn(async () => snapshot), getAllThings: async () => [] };
  await initOpenhab({ openhabUrl: '', staleBannerSeconds: 90 }, {
    clientFactory: () => client,
    sseFactory: (options) => { stream = createSSE(options); return stream; },
  });
  FakeES.all.at(-1).onopen();
  return client;
}
const warnings = () => get(consoleAlerts).alerts.filter(a => a.priorityKey === 'telemetry-stale');
beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(NOW); vi.stubGlobal('EventSource', FakeES);
  FakeES.all = []; items.set({}); clientReady.set(false); itemUpdateEvidence.set({});
  alertContext.set({ staleEssentials: [], batteryAlarms: [] });
  stop = startStalenessMonitor();
});
afterEach(() => { stop(); stream?.stop(); stream = null; vi.unstubAllGlobals(); vi.useRealTimers(); });

it('does not manufacture boot alarms; an empty successful snapshot warns', async () => {
  expect(warnings()).toEqual([]);
  await boot([]);
  expect(warnings()).toHaveLength(3);
  expect(warnings().every(a => a.severity === 'warning' && a.shortText.includes('unavailable'))).toBe(true);
  expect(get(consoleAlerts).alerts.some(a => a.priorityKey === 'battery-critical')).toBe(false);
});
it('keeps hours of constant SoC healthy using the heartbeat value', async () => {
  await boot();
  for (let i = 0; i < 48; i++) {
    vi.advanceTimersByTime(5 * 60000);
    emit('BMS_SOC_LastUpdate', 'statechanged', { value: new Date(Date.now()).toISOString() });
    for (const name of [OUT, IN]) emit(name, 'stateupdated', { value: '70', lastStateUpdate: Date.now() });
    expect(warnings()).toEqual([]);
  }
  expect(get(items).BMS_SOC).toBe('100');
});
it('subscribes only to two update topics and never renders their duplicate values', async () => {
  await boot();
  const topics = new URL(FakeES.all[0].url, 'http://fixture').searchParams.get('topics').split(',');
  expect(topics).toEqual(['openhab/items/*/statechanged', 'openhab/things/*/status',
    `openhab/items/${OUT}/stateupdated`, `openhab/items/${IN}/stateupdated`]);
  const seen = vi.fn(); const unsubscribe = items.subscribe(seen); seen.mockClear();
  emit(OUT, 'statechanged', { value: '71' });
  emit(OUT, 'stateupdated', { value: '71', lastStateUpdate: '2026-09-05T11:59:59.123456789-06:00[America/Denver]' });
  emit('Other', 'stateupdated', { value: '2', lastStateUpdate: NOW });
  expect(seen).toHaveBeenCalledTimes(1); expect(get(items)[OUT]).toBe('71');
  expect(get(itemUpdateEvidence).Other).toBeUndefined(); unsubscribe();
});
it('statechanged cannot cure stale temperatures but equal-value updates can', async () => {
  await boot(healthy(NOW - 16 * 60000));
  expect(warnings().map(a => a.id)).toContain(`telemetry-stale:${OUT}`);
  emit(OUT, 'statechanged', { value: '70' });
  expect(warnings().map(a => a.id)).toContain(`telemetry-stale:${OUT}`);
  emit(OUT, 'stateupdated', { value: '70', lastStateUpdate: '2026-09-05T11:59:59.123456789-06:00[America/Denver]' });
  expect(get(itemUpdateEvidence)[OUT]).toEqual({ lastKnown: NOW - 877, available: true });
  expect(warnings().map(a => a.id)).not.toContain(`telemetry-stale:${OUT}`);
});
it('retains diagnostic time on invalid evidence and ignores older valid evidence', async () => {
  await boot();
  emit(OUT, 'stateupdated', { lastStateUpdate: 'bad' });
  expect(get(itemUpdateEvidence)[OUT]).toEqual({ lastKnown: NOW, available: false });
  emit(OUT, 'stateupdated', { lastStateUpdate: NOW - 1 });
  expect(get(itemUpdateEvidence)[OUT]).toEqual({ lastKnown: NOW, available: false });
  emit(OUT, 'stateupdated', { lastStateUpdate: NOW });
  expect(get(itemUpdateEvidence)[OUT]).toEqual({ lastKnown: NOW, available: true });
  emit(OUT, 'stateupdated', {});
  expect(get(itemUpdateEvidence)[OUT].available).toBe(false);
  emit(OUT, 'stateupdated', { lastStateUpdate: NOW + 1 });
  expect(get(itemUpdateEvidence)[OUT]).toEqual({ lastKnown: NOW, available: false });
});
it('reconnect requests another snapshot without rejuvenating stale evidence', async () => {
  const client = await boot(healthy(NOW - 16 * 60000));
  snapshot = healthy(NOW - 30 * 60000);
  FakeES.all[0].onerror(); await vi.advanceTimersByTimeAsync(1000);
  FakeES.all.at(-1).onopen(); await Promise.resolve(); await Promise.resolve();
  expect(client.getAllItems).toHaveBeenCalledTimes(2);
  expect(get(itemUpdateEvidence)[OUT].lastKnown).toBe(NOW - 16 * 60000);
  expect(warnings().map(a => a.id)).toContain(`telemetry-stale:${OUT}`);
  applySnapshot([]);
  expect(get(itemUpdateEvidence)[OUT]).toEqual({ lastKnown: NOW - 16 * 60000, available: false });
  expect(get(items).BMS_SOC_LastUpdate).toBeUndefined();
});
it.each([undefined, 'NULL', 'UNDEF', 'bad', '2026-09-05T18:00:01Z', '2026-09-05T17:47:59Z'])(
  'warns on unusable or expired heartbeat %s', async (value) => {
    await boot();
    if (value === undefined) applySnapshot(healthy().filter(row => row.name !== 'BMS_SOC_LastUpdate'));
    else emit('BMS_SOC_LastUpdate', 'statechanged', { value });
    expect(warnings().map(a => a.id)).toContain('telemetry-stale:BMS_SOC');
  });
it.each([undefined, 'NULL', 'UNDEF', ''])(
  'missing comms %s warns without becoming a critical fault', async (value) => {
    await boot(); emit('BMS_Comms_Status', 'statechanged', { value: value ?? 'UNDEF' });
    expect(warnings().map(a => a.id)).toContain('telemetry-stale:BMS_SOC');
    expect(get(consoleAlerts).alerts.some(a => a.priorityKey === 'battery-critical')).toBe(false);
  });
it.each([['BMS_Comms_Status', 'FAULT'], ['BMS_DevicePresent', 'OFF']])(
  'explicit %s failure suppresses only redundant battery freshness', async (name, value) => {
    await boot(healthy(NOW - 16 * 60000)); emit(name, 'statechanged', { value });
    expect(get(consoleAlerts).alerts.some(a => a.priorityKey === 'battery-critical')).toBe(true);
    expect(warnings().map(a => a.id)).not.toContain('telemetry-stale:BMS_SOC');
    expect(warnings().map(a => a.id)).toContain(`telemetry-stale:${OUT}`);
  });
it('checks exact thresholds and stops both reactive and timer updates', async () => {
  await boot();
  const evaluate = (elapsed) => computeStaleEssentials(get(itemUpdateEvidence), NOW + elapsed, {
    values: get(items), ready: true,
  }).map(a => a.name);
  expect(evaluate(12 * 60000)).not.toContain('BMS_SOC');
  expect(evaluate(12 * 60000 + 1)).toContain('BMS_SOC');
  expect(evaluate(15 * 60000)).not.toContain(OUT);
  expect(evaluate(15 * 60000 + 1)).toContain(OUT);
  stop(); const before = get(alertContext);
  emit('BMS_Comms_Status', 'statechanged', { value: 'UNDEF' });
  vi.advanceTimersByTime(20 * 60000); expect(get(alertContext)).toBe(before);
});
```

The undefined heartbeat case uses a missing snapshot field because the existing ordinary SSE parser intentionally ignores payloads without a value. Preserve that parser contract.

- [ ] **Step 3: Run the red tests.**

```bash
npx vitest run tests/timestamp.test.js tests/alert-staleness.test.js
```

Expected: failure importing the new parser and new evidence export. Do not update assertions to receipt-time semantics.

- [ ] **Step 4: Implement the parser.** Create `src/lib/openhab/timestamp.js`:

```js
export function parseSourceTimestamp(value, nowMs = Date.now()) {
  let timestamp = null;
  if (typeof value === 'number') timestamp = value;
  else if (typeof value === 'string') {
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})(?:\[[A-Za-z0-9_+./-]+\])?$/.exec(value);
    if (!match) return null;
    const [, y, mo, d, h, mi, s, fraction = '', zone] = match;
    const year = Number(y), month = Number(mo), day = Number(d);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (month < 1 || month > 12 || day < 1 || day > days[month - 1]
      || Number(h) > 23 || Number(mi) > 59 || Number(s) > 59) return null;
    if (zone !== 'Z' && (Number(zone.slice(1, 3)) > 23 || Number(zone.slice(4)) > 59)) return null;
    timestamp = Date.parse(`${y}-${mo}-${d}T${h}:${mi}:${s}.${fraction.padEnd(3, '0').slice(0, 3)}${zone}`);
  }
  return Number.isFinite(nowMs) && Number.isFinite(timestamp) && timestamp > 0 && timestamp <= nowMs
    ? timestamp : null;
}
```

- [ ] **Step 5: Share existing battery normalization without changing critical semantics.** Create `src/lib/alerts/batteryHealth.js`:

```js
export function normalizedComms(value) {
  const text = value == null ? '' : String(value).trim();
  return ['', 'NULL', 'UNDEF'].includes(text.toUpperCase()) ? '' : text;
}
export function normalizedDevicePresent(value) {
  const normalized = normalizedComms(value).toUpperCase();
  if (!normalized) return null;
  if (['1', 'ON', 'TRUE', 'PRESENT', 'ONLINE', 'OK'].includes(normalized)) return true;
  if (['0', 'OFF', 'FALSE', 'ABSENT', 'OFFLINE', 'ERROR', 'FAULT'].includes(normalized)) return false;
  return null;
}
```

In `consoleAlerts.js`, add this import, remove the old local `normalizedDevicePresent` function, and replace the comms declaration and stale short text with the exact lines shown:

```js
import { normalizedComms, normalizedDevicePresent } from './batteryHealth.js';
```

```js
const comms = normalizedComms(items.BMS_Comms_Status);
```

```js
shortText: `${label} ${stale.unavailable ? 'freshness unavailable' : 'stale'}`,
fullText: clean(stale.fullText) || `${label} telemetry is stale.`,
```

- [ ] **Step 6: Replace freshness computation.** Replace `src/lib/alerts/staleness.js` in full:

```js
import { parseSourceTimestamp } from '../openhab/timestamp.js';
import { normalizedComms, normalizedDevicePresent } from './batteryHealth.js';

export const ESSENTIAL_STALE_THRESHOLD_MS = 15 * 60000;
export const STALENESS_CHECK_INTERVAL_MS = 60000;
export const ESSENTIAL_ITEMS = Object.freeze([
  Object.freeze({ name: 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', label: 'Outdoor temperature', route: 'home' }),
  Object.freeze({ name: 'AmbientWeatherWS2902A_IndoorSensor_Temperature', label: 'Indoor temperature', route: 'home' }),
  Object.freeze({ name: 'BMS_SOC', label: 'Battery SoC', route: 'energy', thresholdMs: 12 * 60000 }),
]);
export const TEMPERATURE_ITEMS = Object.freeze(ESSENTIAL_ITEMS.filter(item => item.name !== 'BMS_SOC'));

export function computeStaleEssentials(evidence = {}, nowMs = Date.now(), {
  values = {}, ready = false,
} = {}) {
  if (!ready) return [];
  const stale = [];
  for (const item of ESSENTIAL_ITEMS) {
    const limit = item.thresholdMs ?? ESSENTIAL_STALE_THRESHOLD_MS;
    let timestamp;
    if (item.name === 'BMS_SOC') {
      const comms = normalizedComms(values.BMS_Comms_Status);
      if ((comms && comms.toUpperCase() !== 'OK') || normalizedDevicePresent(values.BMS_DevicePresent) === false) continue;
      timestamp = comms ? parseSourceTimestamp(values.BMS_SOC_LastUpdate, nowMs) : null;
    } else {
      const source = evidence[item.name];
      timestamp = source?.available ? parseSourceTimestamp(source.lastKnown, nowMs) : null;
    }
    const unavailable = timestamp === null;
    if (!unavailable && nowMs - timestamp <= limit) continue;
    stale.push({
      name: item.name, label: item.label, route: item.route, severity: 'warning',
      ...(unavailable ? { unavailable: true } : { transitionAt: timestamp + limit }),
      fullText: unavailable ? `${item.label} freshness is unavailable.`
        : `${item.label} has not updated in over ${Math.round(limit / 60000)} minutes.`,
    });
  }
  return stale;
}
```

- [ ] **Step 7: Replace the source-clock store implementation.** In `store.js`, import `get` alongside `writable`, add the two imports below, then replace the entire old `itemLastUpdated` declaration/getter and `applySnapshot`/`applyState` region with the following code. Preserve client creation, readiness, retries, Thing status, and reconnect logic.

```js
import { parseSourceTimestamp } from './timestamp.js';
import { TEMPERATURE_ITEMS } from '../alerts/staleness.js';
```

```js
export const itemUpdateEvidence = writable({});

export function applyUpdateEvidence(name, rawTimestamp) {
  if (!TEMPERATURE_ITEMS.some(item => item.name === name)) return;
  const timestamp = parseSourceTimestamp(rawTimestamp);
  const prior = get(itemUpdateEvidence)[name];
  if (timestamp !== null && prior?.lastKnown != null && timestamp < prior.lastKnown) return;
  itemUpdateEvidence.update(current => ({
    ...current,
    [name]: { lastKnown: timestamp ?? prior?.lastKnown ?? null, available: timestamp !== null },
  }));
}

export function applySnapshot(arr) {
  const rows = new Map(arr.map(item => [item.name, item]));
  for (const item of TEMPERATURE_ITEMS) applyUpdateEvidence(item.name, rows.get(item.name)?.lastStateUpdate);
  items.update(current => {
    const next = { ...current };
    // A bulk snapshot is authoritative about absence for these health values.
    // Preserve the existing merge behavior for ordinary display items.
    for (const name of ['BMS_SOC_LastUpdate', 'BMS_Comms_Status', 'BMS_DevicePresent']) {
      if (!rows.has(name)) delete next[name];
    }
    for (const item of arr) next[item.name] = item.state;
    return next;
  });
}
export function applyState(name, value) {
  items.update(current => ({ ...current, [name]: value }));
}
```

In the existing `sseFactory` options add `onUpdateEvidence: applyUpdateEvidence,` immediately after `onState: applyState,`. In `index.js` replace its `getItemLastUpdated,` export with `itemUpdateEvidence,`. No receipt timestamp API remains.

- [ ] **Step 8: Transport targeted update evidence and request REST source timestamps.** In `client.js`, replace the one query string `fields=name,state,type` with `fields=name,state,type,lastStateUpdate`. In `sse.js`, add this import and parser before the existing parsers:

```js
import { TEMPERATURE_ITEMS } from '../alerts/staleness.js';

export function parseUpdateEvidenceSSEMessage(raw) {
  let message;
  try { message = JSON.parse(raw); } catch { return null; }
  const match = /^openhab\/items\/([^/]+)\/stateupdated$/.exec(message?.topic || '');
  if (!match || !TEMPERATURE_ITEMS.some(item => item.name === match[1])) return null;
  let payload;
  try { payload = JSON.parse(message.payload); } catch { payload = null; }
  return { name: match[1], lastStateUpdate: payload?.lastStateUpdate };
}
```

Add `onUpdateEvidence = () => {},` to `createSSE`'s destructured options. Replace the `topics` declaration:

```js
const topics = ['openhab/items/*/statechanged', 'openhab/things/*/status',
  ...TEMPERATURE_ITEMS.map(item => `openhab/items/${item.name}/stateupdated`)].join(',');
```

Insert this block first inside `es.onmessage`, before ordinary item parsing. Matching update messages with malformed payloads explicitly mark their source unavailable; malformed envelopes that cannot identify a target remain ignored.

```js
const update = parseUpdateEvidenceSSEMessage(e.data);
if (update) {
  onUpdateEvidence(update.name, update.lastStateUpdate);
  setStatus('live');
  armTimers();
  return;
}
```

- [ ] **Step 9: Reactively project source changes as well as clock expiry.** In `alertStore.js`, import `get` alongside `derived, writable` and replace the openhab import with:

```js
import { connection, items, itemUpdateEvidence, clientReady } from '../openhab/index.js';
```

Replace `startStalenessMonitor` in full (the derived `consoleAlerts` remains unchanged):

```js
export function startStalenessMonitor({ intervalMs = STALENESS_CHECK_INTERVAL_MS, now = Date.now } = {}) {
  const check = () => {
    const staleEssentials = computeStaleEssentials(get(itemUpdateEvidence), now(), {
      values: get(items), ready: get(clientReady),
    });
    alertContext.update(context => ({ ...context, staleEssentials }));
  };
  const unsubscribe = [items, itemUpdateEvidence, clientReady].map(store => store.subscribe(check));
  const timer = setInterval(check, intervalMs);
  return () => { clearInterval(timer); unsubscribe.forEach(stop => stop()); };
}
```

- [ ] **Step 10: Update affected existing tests and fixtures explicitly.**

In `tests/client.test.js`, change both exact expected URLs from `fields=name,state,type` to `fields=name,state,type,lastStateUpdate`. Add `'/rest/items?fields=name,state,type,lastStateUpdate',` beside the existing accepted read URL in `tests/openhab-proxy-policy.test.js`; retain the old accepted URL as backwards-compatible read coverage.

In `tests/store.test.js`, replace `getItemLastUpdated,` with `itemUpdateEvidence,` in the imports, and replace only the test named `records a lastUpdated timestamp per item on snapshot and statechanged` with:

```js
it('retains upstream temperature evidence without using ordinary value receipt', () => {
  const name = 'AmbientWeatherWS2902A_IndoorSensor_Temperature';
  const sourceAt = Date.now() - 60000;
  applySnapshot([{ name, state: '70', lastStateUpdate: sourceAt }]);
  applyState(name, '71');
  applyState('TS_B', '2');
  expect(get(itemUpdateEvidence)[name]).toEqual({ lastKnown: sourceAt, available: true });
  expect(get(itemUpdateEvidence).TS_B).toBeUndefined();
});
```

In the `openhab/index.js` mock factory in `tests/ui/HeaderAlerts.test.js`, add these two exports beside `connection`. The component test does not start a monitor; these stores model the new module contract without creating artificial healthy evidence:

```js
itemUpdateEvidence: writable({}),
clientReady: writable(false),
```

In `tests/e2e/home-runtime.spec.js`, replace only `itemSnapshot` with:

```js
function itemSnapshot(overrides = {}) {
  const sourceAt = Date.now() - 1000;
  return Object.entries({
    ...BASE_STATES, BMS_SOC_LastUpdate: new Date(sourceAt).toISOString(), ...overrides,
  }).map(([name, state]) => ({ name, state, type: 'String', lastStateUpdate: sourceAt }));
}
```

These explicit healthy source values preserve the existing long/unavailable layout test's intended thermal winner. Do not make production parsing accept missing evidence to preserve an old fixture.

- [ ] **Step 11: Add a real browser freshness regression to the existing fixture file.** Append this test outside the existing target loop. It uses the existing isolated fixture server, mocked EventSource and REST routes. It does not call an action endpoint. The request listener makes attempted action writes fail acceptance even if intercepted.

```js
test('upstream freshness reaches the tablet header without value changes', async ({ page }, testInfo) => {
  const writes = [];
  page.on('request', request => {
    if (!['GET', 'HEAD'].includes(request.method())) writes.push(request.url());
  });
  // Install the clock before app startup, then advance all timers deterministically.
  await page.clock.install({ time: new Date() });
  const runtime = await openHomeFixture(page, { width: 1340, height: 800 });
  await expect(page.locator('[data-header-alert-winner]')).toHaveCount(0);
  await page.clock.fastForward(16 * 60000);
  // Re-establish transport liveness without renewing any sensor evidence.
  await runtime.emitState('BMS_SOC', '62');
  await expect(page.locator('[data-header-alert-winner]')).toContainText('stale');
  await runtime.emitState('BMS_SOC_LastUpdate', await page.evaluate(() => new Date(Date.now()).toISOString()));
  await page.evaluate(() => {
    const source = window.__fixtureEventSources.at(-1);
    for (const name of ['AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', 'AmbientWeatherWS2902A_IndoorSensor_Temperature']) {
      source.onmessage({ data: JSON.stringify({ topic: `openhab/items/${name}/stateupdated`,
        payload: JSON.stringify({ value: 'unchanged', lastStateUpdate: Date.now() }) }) });
    }
  });
  await expect(page.locator('[data-header-alert-winner]')).toHaveCount(0);
  await expect(page.locator('.battery-arc .arc-value')).toHaveText('62%');
  await runtime.emitState('BMS_SOC_LastUpdate', 'UNDEF');
  await expect(page.locator('[data-header-alert-winner]')).toContainText('Battery SoC freshness unavailable');
  await runtime.emitState('BMS_Comms_Status', 'FAULT');
  await expect(page.locator('[data-header-alert-winner]')).toContainText('BMS communication fault');
  await runtime.emitState('BMS_Comms_Status', 'NULL');
  await expect(page.locator('[data-header-alert-winner]')).toContainText('freshness unavailable');
  const geometry = await homeGeometry(page);
  expectBounded(geometry, { width: 1340, height: 800 });
  expect(geometry.headerHeight).toBe(44);
  expect(runtime.pageErrors).toEqual([]);
  expect(runtime.unexpectedExternalRequests).toEqual([]);
  expect(writes).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath('upstream-freshness-1340x800.png') });
});
```

- [ ] **Step 12: Run focused tests, then full UI regression and build.**

```bash
npx vitest run tests/timestamp.test.js tests/alert-staleness.test.js tests/store.test.js tests/sse.test.js tests/client.test.js tests/openhab-init.test.js tests/console-alerts.test.js tests/openhab-proxy-policy.test.js tests/ui/HeaderAlerts.test.js
npm test
npm run build
npx playwright test tests/e2e/home-runtime.spec.js
```

Expected: all focused assertions pass, full UI suite passes with no skipped old freshness tests, production build exits zero, all existing Home tests plus the new 1340×800 test pass. Record actual counts; the parent reported 1103 baseline UI tests, not a count to hard-code as the new result. If browser binaries are unavailable, report that exact blocker rather than claiming browser verification.

- [ ] **Step 13: Inspect and independently review the complete diff.**

```bash
git diff --check
git diff --stat
rg -n 'getItemLastUpdated|itemLastUpdated|60-minute threshold|60.min.*BMS' src tests
git diff -- src/lib/openhab src/lib/alerts tests
```

Expected: whitespace clean; obsolete receipt-time API and obsolete battery threshold absent. Review source provenance, timestamp calendar checks, targeted-only subscription topics, ignored older evidence, missing-field snapshot behavior, critical/unavailable separation, boot gating, teardown, and absence of action writes. This planning task itself does not implement, commit, or deploy. During execution, commit the tested implementation for independent task and whole-branch review before any merge or deployment.

- [ ] **Step 14: Commit the reviewed UI implementation only.**

```bash
git add src/lib/openhab/timestamp.js src/lib/alerts/batteryHealth.js src/lib/openhab/client.js src/lib/openhab/sse.js src/lib/openhab/store.js src/lib/openhab/index.js src/lib/alerts/staleness.js src/lib/alerts/alertStore.js src/lib/alerts/consoleAlerts.js tests/timestamp.test.js tests/alert-staleness.test.js tests/store.test.js tests/client.test.js tests/openhab-proxy-policy.test.js tests/ui/HeaderAlerts.test.js tests/e2e/home-runtime.spec.js
git commit -m "fix: use upstream evidence for essential telemetry freshness"
```

Report the exact commit and validation evidence. Do not include separately planned checker files or unrelated working-tree changes. Do not claim historical change-only algorithm compatibility from this UI result.

## Self-review and residual boundaries

The code uses one list of essential temperatures, one parser, one evidence store, and the existing clientReady gate. Normal device/comms semantics are extracted once and shared. Invalid evidence is unavailable, known timestamps are retained, and older valid evidence never clears an unavailable state. Snapshot absence clears only the three battery health inputs so old cached comms/heartbeat cannot masquerade as current evidence.

SSE value ordering for ordinary items is intentionally unchanged: timestamps govern temperature freshness evidence, not a redesign of all rendering. The BMS heartbeat is interpreted from its value every time; its own REST lastStateUpdate and BMS_SOC row age do not grant health. Missing battery snapshot values cannot be recovered until a subsequent valid snapshot or value event arrives.

The separately planned external checker and every historical family listed in the approved specification remain outstanding after this independently testable UI task. No historical interpolation, estimator, advisory, household action, OpenHAB persistence, notifier, or live deployment change is included.
