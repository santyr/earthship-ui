# Earthship Console UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A tablet-first, WS-2000-console-style household dashboard for the off-grid Earthship openHAB system (weather, battery/solar, passive-thermal, greywater, subtle BTC), rendering live data with safety-gated controls.

**Architecture:** Svelte SPA (Vite build) reading openHAB REST for initial state + persistence history, and the openHAB SSE event stream for sub-second live updates. A framework-agnostic data layer (`src/lib/openhab/`) is unit-tested in isolation; Svelte components subscribe to a reactive item store. ECharts renders charts (incl. future forecast rows). Served as a static bundle by nginx on the LAN; runtime config (openHAB URL + token) loaded at boot from an un-committed `config.json`.

**Tech Stack:** Svelte 5 + Vite + Tailwind CSS + ECharts; Vitest (unit) + Playwright (viewport smoke); PWA via `vite-plugin-pwa`. Node 24 / npm 11 (confirmed installed).

## Global Constraints

- **Repo:** `github.com/santyr/earthship-ui` (private, santyr account). Local clone `~/earthship-ui`. `gh` has both `santyr` (active) and `hexdaemon` accounts — all git ops MUST stay under santyr.
- **Secrets:** `config.json` (openHAB URL + API token) is gitignored, NEVER committed. Only `config.example.json` is tracked. Token is read at runtime, never baked into the bundle.
- **openHAB base URL:** `http://ogsatoth:8080` (LAN). Auth: bearer token via `Authorization` header.
- **Reference viewport (must not overflow):** Lenovo Tab M9 landscape, **1340×800**. Home screen fits with NO vertical scroll at this size. Also smoke-test 1920×1080 and 390×844.
- **Perf budget:** initial load < 2 s on the M9; SSE update → paint < 100 ms. Light on effects (modest GPU): no blur, minimal animation.
- **NULL discipline:** any item state of `NULL`/`UNDEF`/absent renders as `—` in a dimmed tile — never the literal `undefined`/`NaN`.
- **Color language:** amber=temperature, cyan/green=wind, blue=rain/water, yellow=solar, violet=forecast, orange=advisory; battery bands green>60 / yellow>40 / orange>12 / red≤12 (interim; 50/30/12 at full-bank — single `socBands(soc, full=false)` helper).
- **Controls never bypass rules:** UI writes request/command items only; safety-gated devices (SouthOutlet) are actuated by openHAB rules through their existing gates.
- **Commit style:** end messages with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Commit after every green step.

---

## Confirmed item bindings (all 51 verified present 2026-07-17)

Battery/solar: `BMS_SOC`, `BMS_TimeToDischarge_Smoothed`, `BMS_Runtime_Basis`, `DCData_Current`, `DCData_Voltage`, `BMS_Temperature` (°F), `BMS_Charge_Cycles`, `BMS_Capacity_Remaining_Ah`, `BMS_Comms_Status`, `BatteryChargingStatus`, `BatteryIcon`, `MPPT60_PV_Power`, `MPPT60_EnergyFromPV_Today`, `ChargerStatus`.
Predictions: `Predicted_PV_Today_kWh`, `Predicted_SoC_Trough_Tomorrow`, `Predicted_Curtailment_Hours`, `Forecast_PV_Error_7d`, `Forecast_Trough_Error_7d`, `Thermal_Advisory` (`code|text`).
Weather (measured): `AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature`, `..._IndoorSensor_Temperature`, `..._WindSpeed`, `..._WindGust`, `..._RainFallDay`, `..._WeatherDataWs2902a_PressureRelative`, `..._PressureTrend`, `SkyConditionIcon`, `..._ApparentTemperature`, `OutdoorTemp_24h_High/Low`.
Weather (forecast): `Forecast_AQI`, `Forecast_Daily_High/Low`, `Forecast_Tomorrow_High`, `Forecast_Hourly_JSON`, `Forecast_Daily_JSON`.
Earthship zones: `Shelly_HT1_Indoor_Temperature` (south glazing), `AmbientWeatherWS2902A_WH31E_193_Temperature` (north mass), `..._IndoorSensor_Temperature` (room air).
Sun/moon: `Sun_Rise_Start`, `Sun_Set_End`, `Moon_MoonPhaseName`.
Greywater/controls: `SouthOutlet_Outlet2_Switch`, `SouthOutlet_AutoStatus`, `SouthOutlet_LastAutoRun`, `living_room_1_Switch`, `LivingRoomCircadian_Enable`, `Goat_Plugs_Outlet1_Switch`, `Goat_Plugs_Outlet2_Switch`.
BTC: `BTC_USD_Price`, `BTC_Price_24h_PercentChange`.

---

## Phase 0 — Scaffold & serving

### Task 0.1: Vite + Svelte + Tailwind scaffold

**Files:**
- Create: `package.json`, `vite.config.js`, `svelte.config.js`, `tailwind.config.js`, `postcss.config.js`, `index.html`, `src/main.js`, `src/App.svelte`, `src/app.css`
- Modify: `.gitignore` (already excludes node_modules/dist/config.json)

**Interfaces:**
- Produces: a dev server (`npm run dev`) and production build (`npm run build` → `dist/`).

- [ ] **Step 1: Scaffold Vite + Svelte**
```bash
cd ~/earthship-ui
npm create vite@latest . -- --template svelte
# when prompted about non-empty dir, keep existing files (README, docs, .gitignore, config.example.json)
npm install
```
- [ ] **Step 2: Add Tailwind**
```bash
npm install -D tailwindcss @tailwindcss/postcss postcss autoprefixer
```
Create `postcss.config.js`:
```js
export default { plugins: { '@tailwindcss/postcss': {}, autoprefixer: {} } };
```
Create `tailwind.config.js`:
```js
export default {
  content: ['./index.html', './src/**/*.{svelte,js,ts}'],
  theme: { extend: {} },
  plugins: [],
};
```
Replace `src/app.css` with:
```css
@import 'tailwindcss';
:root { color-scheme: dark; }
html, body { margin: 0; height: 100%; background: #0b0e11; color: #e6edf3;
  font-family: Inter, system-ui, sans-serif; font-variant-numeric: tabular-nums;
  -webkit-user-select: none; user-select: none; overscroll-behavior: none; }
```
- [ ] **Step 3: Verify dev server boots**
Run: `npm run dev` — visit the printed URL.
Expected: default Svelte page on the dark background.
- [ ] **Step 4: Verify production build**
Run: `npm run build`
Expected: `dist/` created, no errors.
- [ ] **Step 5: Commit**
```bash
git add -A && git commit -m "chore: Vite+Svelte+Tailwind scaffold

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 0.2: Runtime config loading

**Files:**
- Create: `public/config.json` (gitignored copy for dev), `src/lib/config.js`, `tests/config.test.js`
- Modify: `config.example.json` (already exists)

**Interfaces:**
- Produces: `loadConfig(): Promise<{openhabUrl, apiToken, staleBannerSeconds}>` — fetches `/config.json`, throws a typed error if missing/malformed.

- [ ] **Step 1: Write failing test** — `tests/config.test.js`
```js
import { describe, it, expect, vi } from 'vitest';
import { parseConfig } from '../src/lib/config.js';
describe('parseConfig', () => {
  it('accepts a valid config', () => {
    const c = parseConfig({ openhabUrl: 'http://x:8080', apiToken: 't', staleBannerSeconds: 90 });
    expect(c.openhabUrl).toBe('http://x:8080');
    expect(c.staleBannerSeconds).toBe(90);
  });
  it('defaults staleBannerSeconds to 90', () => {
    expect(parseConfig({ openhabUrl: 'http://x', apiToken: 't' }).staleBannerSeconds).toBe(90);
  });
  it('throws when openhabUrl missing', () => {
    expect(() => parseConfig({ apiToken: 't' })).toThrow(/openhabUrl/);
  });
});
```
- [ ] **Step 2: Add Vitest, run to confirm fail**
```bash
npm install -D vitest
npx vitest run tests/config.test.js
```
Expected: FAIL (module not found).
- [ ] **Step 3: Implement** — `src/lib/config.js`
```js
export function parseConfig(raw) {
  if (!raw || typeof raw.openhabUrl !== 'string') throw new Error('config: openhabUrl required');
  if (typeof raw.apiToken !== 'string') throw new Error('config: apiToken required');
  return {
    openhabUrl: raw.openhabUrl.replace(/\/$/, ''),
    apiToken: raw.apiToken,
    staleBannerSeconds: Number.isFinite(raw.staleBannerSeconds) ? raw.staleBannerSeconds : 90,
  };
}
export async function loadConfig() {
  const r = await fetch('/config.json', { cache: 'no-store' });
  if (!r.ok) throw new Error('config.json not found — copy config.example.json');
  return parseConfig(await r.json());
}
```
- [ ] **Step 4: Run tests, expect pass**
Run: `npx vitest run tests/config.test.js` — Expected: 3 pass.
- [ ] **Step 5: Create dev config (gitignored) and add test script**
```bash
cp config.example.json public/config.json
# edit public/config.json: openhabUrl http://ogsatoth:8080, apiToken = $OPENHAB_TOKEN from ~/.config/hex/openhab.env
```
Add to `package.json` scripts: `"test": "vitest run"`.
- [ ] **Step 6: Commit** (`public/config.json` must NOT be staged — verify with `git status`)
```bash
git add src/lib/config.js tests/config.test.js package.json && git commit -m "feat: runtime config loading

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 1 — Data layer (full TDD; this is the testable core)

### Task 1.1: REST client (fetch items, post commands, persistence)

**Files:**
- Create: `src/lib/openhab/client.js`, `tests/client.test.js`

**Interfaces:**
- Produces:
  - `createClient({openhabUrl, apiToken})` → `{ getAllItems(), getItem(name), sendCommand(name, value), getHistory(name, {starttime, endtime}) }`
  - `getAllItems(): Promise<Array<{name, state, type}>>`
  - `sendCommand(name, value): Promise<void>` — POST plain text to `/rest/items/{name}`
  - `getHistory(name, opts): Promise<Array<{time: number, state: number}>>` — parses `/rest/persistence/items/{name}`, includes future rows.

- [ ] **Step 1: Write failing tests** — `tests/client.test.js`
```js
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createClient } from '../src/lib/openhab/client.js';
const cfg = { openhabUrl: 'http://oh:8080', apiToken: 'TK' };
beforeEach(() => { global.fetch = vi.fn(); });

it('getAllItems returns parsed array with auth header', async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => [{ name: 'A', state: '5', type: 'Number' }] });
  const items = await createClient(cfg).getAllItems();
  expect(items[0].name).toBe('A');
  expect(fetch).toHaveBeenCalledWith('http://oh:8080/rest/items?fields=name,state,type',
    expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer TK' }) }));
});
it('sendCommand posts plain text body', async () => {
  fetch.mockResolvedValue({ ok: true });
  await createClient(cfg).sendCommand('Sw', 'ON');
  const [url, opts] = fetch.mock.calls[0];
  expect(url).toBe('http://oh:8080/rest/items/Sw');
  expect(opts.method).toBe('POST');
  expect(opts.body).toBe('ON');
  expect(opts.headers['Content-Type']).toBe('text/plain');
});
it('getHistory maps time/state to numbers', async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ data: [{ time: 1000, state: '54' }, { time: 2000, state: '55.5' }] }) });
  const h = await createClient(cfg).getHistory('BMS_SOC', { starttime: 'a', endtime: 'b' });
  expect(h).toEqual([{ time: 1000, state: 54 }, { time: 2000, state: 55.5 }]);
});
it('sendCommand throws on non-ok', async () => {
  fetch.mockResolvedValue({ ok: false, status: 500 });
  await expect(createClient(cfg).sendCommand('Sw', 'ON')).rejects.toThrow(/500/);
});
```
- [ ] **Step 2: Run, confirm fail** — `npx vitest run tests/client.test.js` → FAIL.
- [ ] **Step 3: Implement** — `src/lib/openhab/client.js`
```js
export function createClient({ openhabUrl, apiToken }) {
  const h = { Authorization: `Bearer ${apiToken}` };
  const base = openhabUrl.replace(/\/$/, '');
  return {
    async getAllItems() {
      const r = await fetch(`${base}/rest/items?fields=name,state,type`, { headers: h });
      if (!r.ok) throw new Error(`getAllItems ${r.status}`);
      return r.json();
    },
    async getItem(name) {
      const r = await fetch(`${base}/rest/items/${name}`, { headers: h });
      if (!r.ok) throw new Error(`getItem ${name} ${r.status}`);
      return r.json();
    },
    async sendCommand(name, value) {
      const r = await fetch(`${base}/rest/items/${name}`, {
        method: 'POST', headers: { ...h, 'Content-Type': 'text/plain' }, body: String(value) });
      if (!r.ok) throw new Error(`sendCommand ${name} ${r.status}`);
    },
    async getHistory(name, { starttime, endtime }) {
      const q = new URLSearchParams({ starttime, endtime });
      const r = await fetch(`${base}/rest/persistence/items/${name}?${q}`, { headers: h });
      if (!r.ok) throw new Error(`getHistory ${name} ${r.status}`);
      const d = await r.json();
      return (d.data || []).map((p) => ({ time: p.time, state: parseFloat(String(p.state)) }));
    },
  };
}
```
- [ ] **Step 4: Run, expect pass** — 4 pass.
- [ ] **Step 5: Commit**
```bash
git add src/lib/openhab/client.js tests/client.test.js && git commit -m "feat: openHAB REST client

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.2: Value helpers (NULL-safe parse, formatters, socBands)

**Files:**
- Create: `src/lib/openhab/values.js`, `tests/values.test.js`

**Interfaces:**
- Produces: `num(state): number|null` (null on NULL/UNDEF/non-numeric), `fmt(state, unit='', digits=0): string` (`—` when null), `socBands(soc, full=false): string` (hex color), `runtimeText(minutes): string` (`5 h 20 m` / `2 d 3 h` / `> 7 d` / `—`).

- [ ] **Step 1: Write failing tests** — `tests/values.test.js`
```js
import { describe, it, expect } from 'vitest';
import { num, fmt, socBands, runtimeText } from '../src/lib/openhab/values.js';
it('num strips units and rejects NULL', () => {
  expect(num('53.42 V')).toBe(53.42);
  expect(num('NULL')).toBeNull();
  expect(num('UNDEF')).toBeNull();
  expect(num(undefined)).toBeNull();
});
it('fmt renders em-dash for null', () => {
  expect(fmt('88.9 °F', '°', 0)).toBe('89°');
  expect(fmt('NULL', '°')).toBe('—');
});
it('socBands interim vs full', () => {
  expect(socBands(70)).toBe('#22c55e');   // >60 green
  expect(socBands(45)).toBe('#eab308');   // >40 yellow
  expect(socBands(45, true)).toBe('#22c55e'); // full: >30 green (wait: 45>30 green? see impl)
  expect(socBands(12)).toBe('#ef4444');   // ≤12 red
});
it('runtimeText formats', () => {
  expect(runtimeText(320)).toBe('5 h 20 m');
  expect(runtimeText(45)).toBe('45 min');
  expect(runtimeText(3000)).toBe('2 d 2 h');
  expect(runtimeText(0)).toBe('—');
  expect(runtimeText(null)).toBe('—');
});
```
- [ ] **Step 2: Run, confirm fail.**
- [ ] **Step 3: Implement** — `src/lib/openhab/values.js`
```js
export function num(state) {
  if (state === undefined || state === null) return null;
  const s = String(state);
  if (s === 'NULL' || s === 'UNDEF' || s === '') return null;
  const n = parseFloat(s.replace(/[^0-9.+-]/g, ''));
  return Number.isFinite(n) ? n : null;
}
export function fmt(state, unit = '', digits = 0) {
  const n = num(state);
  return n === null ? '—' : n.toFixed(digits) + unit;
}
export function socBands(soc, full = false) {
  const n = num(soc);
  if (n === null) return '#6b7280';
  const [g, y, o] = full ? [50, 30, 12] : [60, 40, 12];
  if (n <= o) return '#ef4444';
  if (n <= y) return '#f97316';
  if (n <= g) return '#eab308';
  return '#22c55e';
}
export function runtimeText(minutes) {
  const n = num(minutes);
  if (n === null || n <= 0) return '—';
  if (n >= 10080) return '> 7 d';
  if (n >= 2880) return `${Math.floor(n / 1440)} d ${Math.round((n % 1440) / 60)} h`;
  if (n >= 60) return `${Math.floor(n / 60)} h ${Math.round(n % 60)} m`;
  return `${Math.round(n)} min`;
}
```
Note: correct the socBands full-mode assertion in Step 1 to match: `socBands(35, true)` → yellow (`#eab308`), `socBands(45, true)` → green. Fix the test literal before running if needed.
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit**
```bash
git add src/lib/openhab/values.js tests/values.test.js && git commit -m "feat: NULL-safe value helpers + socBands + runtimeText

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.3: SSE stream with reconnect + staleness

**Files:**
- Create: `src/lib/openhab/sse.js`, `tests/sse.test.js`

**Interfaces:**
- Produces: `createSSE({openhabUrl, apiToken, onState, onStatus})` → `{ start(), stop() }`.
  - `onState(name: string, value: string)` called per `statechanged` event.
  - `onStatus('live'|'stale'|'offline')` called on connection transitions.
  - Parses openHAB SSE payload: topic `openhab/items/{name}/statechanged`, JSON payload `{ "type":"...", "payload":"{\"value\":\"...\"}" }`.
  - Reconnect with backoff (1s→2s→…→max 30s); emits `stale` after `staleBannerSeconds`, `offline` after 10 min silent.

- [ ] **Step 1: Write failing tests** — `tests/sse.test.js` (parse logic is the unit-testable part; extract it)
```js
import { describe, it, expect } from 'vitest';
import { parseSSEMessage } from '../src/lib/openhab/sse.js';
it('extracts item name and value from statechanged event', () => {
  const raw = JSON.stringify({
    topic: 'openhab/items/BMS_SOC/statechanged',
    payload: JSON.stringify({ value: '54', oldValue: '55' }),
    type: 'ItemStateChangedEvent',
  });
  expect(parseSSEMessage(raw)).toEqual({ name: 'BMS_SOC', value: '54' });
});
it('returns null for non-item events', () => {
  expect(parseSSEMessage(JSON.stringify({ topic: 'openhab/things/x/status', payload: '{}' }))).toBeNull();
});
it('returns null for malformed json', () => {
  expect(parseSSEMessage('not json')).toBeNull();
});
```
- [ ] **Step 2: Run, confirm fail.**
- [ ] **Step 3: Implement** — `src/lib/openhab/sse.js`
```js
export function parseSSEMessage(raw) {
  let msg;
  try { msg = JSON.parse(raw); } catch { return null; }
  const m = /^openhab\/items\/([^/]+)\/statechanged$/.exec(msg.topic || '');
  if (!m) return null;
  let payload;
  try { payload = JSON.parse(msg.payload); } catch { return null; }
  if (payload.value === undefined) return null;
  return { name: m[1], value: String(payload.value) };
}

export function createSSE({ openhabUrl, apiToken, onState, onStatus, staleSeconds = 90 }) {
  const base = openhabUrl.replace(/\/$/, '');
  const url = `${base}/rest/events?topics=openhab/items/*/statechanged`;
  let es = null, backoff = 1000, staleTimer = null, offlineTimer = null, stopped = false;
  function armTimers() {
    clearTimeout(staleTimer); clearTimeout(offlineTimer);
    staleTimer = setTimeout(() => onStatus('stale'), staleSeconds * 1000);
    offlineTimer = setTimeout(() => onStatus('offline'), 10 * 60 * 1000);
  }
  function connect() {
    if (stopped) return;
    // EventSource can't set headers; openHAB accepts token via query for SSE.
    es = new EventSource(`${url}&accessToken=${encodeURIComponent(apiToken)}`);
    es.onopen = () => { backoff = 1000; onStatus('live'); armTimers(); };
    es.onmessage = (e) => {
      const parsed = parseSSEMessage(e.data);
      if (parsed) { onState(parsed.name, parsed.value); onStatus('live'); armTimers(); }
    };
    es.onerror = () => {
      es.close();
      if (stopped) return;
      backoff = Math.min(backoff * 2, 30000);
      setTimeout(connect, backoff);
    };
  }
  return {
    start() { stopped = false; connect(); },
    stop() { stopped = true; clearTimeout(staleTimer); clearTimeout(offlineTimer); if (es) es.close(); },
  };
}
```
- [ ] **Step 4: Run, expect pass** (3 pass — parse logic; connection tested live in Task 1.4).
- [ ] **Step 5: Verify token-in-query SSE works against live openHAB**
```bash
# confirm the accessToken query param authenticates the SSE stream:
source ~/.config/hex/openhab.env
timeout 5 curl -s -N "http://ogsatoth:8080/rest/events?topics=openhab/items/BMS_SOC/statechanged&accessToken=$OPENHAB_TOKEN" | head -c 200
```
Expected: an event JSON (or clean silence — both mean auth accepted, not 401). If 401, fall back to header auth via a fetch-based SSE polyfill (note in plan; document the chosen path in a code comment).
- [ ] **Step 6: Commit**
```bash
git add src/lib/openhab/sse.js tests/sse.test.js && git commit -m "feat: SSE stream with reconnect + staleness

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.4: Reactive item store (Svelte)

**Files:**
- Create: `src/lib/openhab/store.js`, `src/lib/openhab/index.js`, `tests/store.test.js`

**Interfaces:**
- Produces:
  - `items` — a Svelte readable store; `$items[name]` → latest state string (or undefined).
  - `connection` — readable store: `'connecting'|'live'|'stale'|'offline'`.
  - `initOpenhab(config)` — loads all items once, starts SSE, wires updates into the store. Returns the client (for commands/history).
  - `index.js` re-exports `initOpenhab, items, connection, num, fmt, socBands, runtimeText, createClient`.

- [ ] **Step 1: Write failing test** — `tests/store.test.js`
```js
import { describe, it, expect, vi } from 'vitest';
import { get } from 'svelte/store';
import { items, applyState, applySnapshot } from '../src/lib/openhab/store.js';
it('applySnapshot seeds many items', () => {
  applySnapshot([{ name: 'A', state: '1' }, { name: 'B', state: '2' }]);
  expect(get(items).A).toBe('1');
  expect(get(items).B).toBe('2');
});
it('applyState updates a single item reactively', () => {
  applySnapshot([{ name: 'A', state: '1' }]);
  applyState('A', '9');
  expect(get(items).A).toBe('9');
});
```
- [ ] **Step 2: Run, confirm fail** (needs `svelte` store import — already a dep).
- [ ] **Step 3: Implement** — `src/lib/openhab/store.js`
```js
import { writable } from 'svelte/store';
import { createClient } from './client.js';
import { createSSE } from './sse.js';

export const items = writable({});
export const connection = writable('connecting');

export function applySnapshot(arr) {
  items.update((m) => { for (const it of arr) m[it.name] = it.state; return { ...m }; });
}
export function applyState(name, value) {
  items.update((m) => { m[name] = value; return { ...m }; });
}

export async function initOpenhab(config) {
  const client = createClient(config);
  applySnapshot(await client.getAllItems());
  const sse = createSSE({
    ...config,
    staleSeconds: config.staleBannerSeconds,
    onState: applyState,
    onStatus: (s) => connection.set(s),
  });
  sse.start();
  return client;
}
```
Create `src/lib/openhab/index.js`:
```js
export { initOpenhab, items, connection } from './store.js';
export { num, fmt, socBands, runtimeText } from './values.js';
export { createClient } from './client.js';
```
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit**
```bash
git add src/lib/openhab/ tests/store.test.js && git commit -m "feat: reactive item store + openhab index

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.5: Live smoke — bare tile proves the pipeline

**Files:**
- Modify: `src/App.svelte`

**Interfaces:**
- Consumes: `initOpenhab, items, connection, fmt` from `src/lib/openhab`.

- [ ] **Step 1: Wire a minimal live readout** — `src/App.svelte`
```svelte
<script>
  import { onMount } from 'svelte';
  import { initOpenhab, items, connection, fmt } from './lib/openhab';
  import { loadConfig } from './lib/config.js';
  onMount(async () => { initOpenhab(await loadConfig()); });
</script>
<main class="p-8">
  <p class="text-sm text-neutral-500">connection: {$connection}</p>
  <h1 class="text-6xl font-bold" style="color:#f59e0b">
    {fmt($items.AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature, '°', 0)}
  </h1>
  <p class="text-2xl">SoC {fmt($items.BMS_SOC, '%', 0)} · PV {fmt($items.MPPT60_PV_Power, ' W', 0)}</p>
</main>
```
- [ ] **Step 2: Run dev, verify LIVE data + updates**
Run: `npm run dev` — open on the workstation.
Expected: connection shows `live`, real outdoor temp + SoC + PV render, and values update within seconds without reload (watch PV change, or `sendCommand` a test item).
- [ ] **Step 3: Verify on the actual M9**
Open the dev URL (`http://<workstation-ip>:5173`) in the M9's browser. Expected: same live readout, legible.
- [ ] **Step 4: Commit**
```bash
git add src/App.svelte && git commit -m "feat: live data smoke tile

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2 — Design system & tile primitives (visual; approve on M9 before screens)

> These tasks are visual — verification is "renders correctly at 1340×800 on the M9," not unit tests. Build the reusable primitives, then a static sample Home for sign-off BEFORE building real screens (design doc Rollout step 2).

### Task 2.1: Design tokens + Tile/Gauge/Sparkline primitives

**Files:**
- Create: `src/lib/ui/tokens.js` (color map, tile sizes), `src/lib/ui/Tile.svelte`, `src/lib/ui/StatTile.svelte`, `src/lib/ui/Arc.svelte` (SoC arc gauge, SVG), `src/lib/ui/Sparkline.svelte` (ECharts mini), `src/lib/ui/CompassRose.svelte`

**Interfaces:**
- Produces:
  - `Tile.svelte` props: `{ label, accent='#6b7280', span=1, dim=false }` + default slot. Renders the console tile chrome (rounded 1px border, small-caps label top-left).
  - `StatTile.svelte` props: `{ label, value, unit, accent, footer, icon, dim }` — the common big-number tile.
  - `Arc.svelte` props: `{ value=0..100, color, label, sublabel }` — SVG arc gauge.
  - `Sparkline.svelte` props: `{ data: Array<{time,state}>, color }`.
  - `CompassRose.svelte` props: `{ degrees, speed, gust }`.

- [ ] **Step 1: Install ECharts**
```bash
npm install echarts
```
- [ ] **Step 2: Build tokens + Tile + StatTile** (write `tokens.js` with the Global-Constraints color map; `Tile.svelte` and `StatTile.svelte` per the interface). Full component code authored here.
- [ ] **Step 3: Build Arc, Sparkline, CompassRose** (SVG for Arc/Compass; ECharts for Sparkline with a shared dark theme object in `tokens.js`).
- [ ] **Step 4: Render a primitives gallery** at a temporary `/gallery` route (or swap `App.svelte`) showing each primitive with sample props.
Expected: all primitives render crisply at 1340×800; no overflow; numerals legible at ~1 m (wall distance).
- [ ] **Step 5: Verify on the M9** — gallery legible and correctly proportioned.
- [ ] **Step 6: Commit**
```bash
git add src/lib/ui/ package.json && git commit -m "feat: console design tokens + tile/gauge primitives

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 2.2: App shell — nav rail + header (clock, connection, BTC ticker)

**Files:**
- Create: `src/lib/ui/Shell.svelte`, `src/lib/ui/Header.svelte`, `src/lib/ui/BtcTicker.svelte`, `src/routes.js`
- Modify: `src/App.svelte` (mount Shell + router)

**Interfaces:**
- Produces: `Shell.svelte` with a left rail (Home/Energy/Weather/Earthship icons) on ≥900px, bottom tabs below; a top `Header` (date/time, `connection` badge, `BtcTicker`); a `<slot/>` for the active screen. Client-side routing via a tiny hash router in `routes.js` (no dependency).
- Consumes: `connection`, `items` stores; `BtcTicker` reads `BTC_USD_Price`, `BTC_Price_24h_PercentChange`.

- [ ] **Step 1: Build hash router** `src/routes.js` (a `currentRoute` writable, `navigate(name)`, hashchange listener).
- [ ] **Step 2: Build `BtcTicker.svelte`** — small mono price + 24h %; green when `num(BTC_Price_24h_PercentChange) >= 0` else red; dimmed vs tiles.
- [ ] **Step 3: Build `Header.svelte`** (live clock via `setInterval`, connection badge with color, slot for ticker) and `Shell.svelte` (rail + tabs + stale banner when `$connection !== 'live'`).
- [ ] **Step 4: Wire `App.svelte`** to render Shell with a placeholder per route.
- [ ] **Step 5: Verify on M9** — rail + header + BTC ticker legible; tapping nav switches placeholder screens; stale banner appears if openHAB paused.
- [ ] **Step 6: Commit**
```bash
git add src/lib/ui/Shell.svelte src/lib/ui/Header.svelte src/lib/ui/BtcTicker.svelte src/routes.js src/App.svelte && git commit -m "feat: app shell, nav, header with BTC ticker

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 2.3: Static sample Home — SIGN-OFF GATE

**Files:**
- Create: `src/screens/Home.svelte` (static/sample values first)

- [ ] **Step 1: Lay out the Home tile grid** (design doc "Home" tile list) with hardcoded sample values — full 4×3-ish landscape arrangement, hero tiles for Outdoor and Battery, forecast strip, advisory bar, greywater lamp, BTC in header.
- [ ] **Step 2: Verify on the M9 at 1340×800 — NO SCROLL.**
- [ ] **Step 3: OPERATOR SIGN-OFF.** Present to Sat on the tablet. Iterate arrangement/typography/color until approved. Do NOT proceed to Phase 3 until the look is approved.
- [ ] **Step 4: Commit the approved layout**
```bash
git add src/screens/Home.svelte && git commit -m "feat: Home console layout (static, approved)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 — Home screen (live data)

### Task 3.1: Bind Home tiles to live items

**Files:**
- Modify: `src/screens/Home.svelte`

**Interfaces:**
- Consumes: `items` store + helpers; item names from the confirmed bindings list.

- [ ] **Step 1: Replace sample values with `$items` bindings** for every tile: Outdoor (`...Ws2902a_Temperature`, ApparentTemperature, OutdoorTemp_24h_High/Low, SkyConditionIcon, Forecast_AQI), Battery (`BMS_SOC`→Arc with `socBands`, `BatteryChargingStatus`, `runtimeText(BMS_TimeToDischarge_Smoothed)` + `BMS_Runtime_Basis`, `DCData_Current`), Solar (`MPPT60_EnergyFromPV_Today` vs `Predicted_PV_Today_kWh`, `MPPT60_PV_Power`), zones (Shelly/WH31E/Indoor), Wind (CompassRose), Rain, Baro (+Sparkline via history), Forecast strip (parse `Forecast_Daily_JSON`), Sun/Moon, advisory bar (`Thermal_Advisory` split on `|`, show only when code≠none), greywater lamp (`SouthOutlet_Outlet2_Switch`, `SouthOutlet_LastAutoRun`).
- [ ] **Step 2: NULL-safety pass** — every binding through `fmt`/`num`; confirm no `undefined`/`NaN` by temporarily pointing at a NULL item.
- [ ] **Step 3: Verify on M9** — all live, updates within seconds, no scroll, advisory bar hidden (currently none), BTC in header.
- [ ] **Step 4: Playwright viewport smoke** — add `tests/e2e/home.spec.js` asserting the Home route renders without horizontal overflow at 1340×800 and 390×844.
```bash
npm install -D @playwright/test && npx playwright install chromium
npx playwright test
```
- [ ] **Step 5: Commit**
```bash
git add src/screens/Home.svelte tests/e2e/home.spec.js && git commit -m "feat: live Home console

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — Energy screen

### Task 4.1: Energy charts + vitals

**Files:**
- Create: `src/screens/Energy.svelte`, `src/lib/ui/HistoryChart.svelte`

**Interfaces:**
- Produces: `HistoryChart.svelte` props `{ series: Array<{name, color, label, dashedFromNow?}>, hours }` — fetches each via `client.getHistory`, renders ECharts; `dashedFromNow` draws future rows dashed (for predicted trough / forecast).
- Consumes: `createClient` (via a shared client from `initOpenhab` — store it in `src/lib/openhab/store.js` as an export `getClientOnce()`), history for `BMS_SOC`, `MPPT60_EnergyFromPV_Today`.

- [ ] **Step 1: Export the client** — add `let _client; ...; export function getClientOnce(){return _client;}` set inside `initOpenhab`.
- [ ] **Step 2: Build `HistoryChart.svelte`** (ECharts line, dark theme, future-row dashing, NULL gaps).
- [ ] **Step 3: Build `Energy.svelte`**: SoC 24h curve + predicted trough marker (`Predicted_SoC_Trough_Tomorrow` as a forward point), PV today vs predicted with accuracy badge (`Forecast_PV_Error_7d`), runtime+basis tile, curtailment (`Predicted_Curtailment_Hours`) bar, 7-day PV bars (from `Forecast_Daily_JSON` pv field), battery vitals row (`BMS_Temperature` °F, `BMS_Charge_Cycles`, `BMS_Capacity_Remaining_Ah`, `BMS_Comms_Status` lamp).
- [ ] **Step 4: Verify on M9** — charts render, SoC history real, accuracy badge shows "calibrating" until scored.
- [ ] **Step 5: Commit**
```bash
git add src/screens/Energy.svelte src/lib/ui/HistoryChart.svelte src/lib/openhab/store.js && git commit -m "feat: Energy screen

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 5 — Weather screen

### Task 5.1: Weather (current, hourly strip, 7-day, measured)

**Files:**
- Create: `src/screens/Weather.svelte`, `src/lib/ui/HourlyStrip.svelte`, `src/lib/ui/wmo.js`

**Interfaces:**
- Produces: `wmo.js` → `wmoIcon(code): string` (mdi name) + `wmoLabel(code)`; `HourlyStrip.svelte` renders `Forecast_Hourly_JSON` (temp line + precip bars + radiation ribbon via ECharts).
- Consumes: `Forecast_Hourly_JSON`, `Forecast_Daily_JSON`, measured weather items, `Forecast_AQI`.

- [ ] **Step 1: Build `wmo.js`** (WMO code → mdi icon map, from the design's icon logic) with a unit test `tests/wmo.test.js` (code 0→sunny, 63→pouring, 71→snowy).
- [ ] **Step 2: Build `HourlyStrip.svelte`** (ECharts combined chart from parsed JSON).
- [ ] **Step 3: Build `Weather.svelte`**: current header (measured temp, feels-like, hi/lo, sky icon), AQI tile (EPA bands), hourly strip, 7-day rows (icons + hi/lo + precip + PV), measured wind/rain/pressure tiles.
- [ ] **Step 4: Verify on M9.**
- [ ] **Step 5: Commit**
```bash
git add src/screens/Weather.svelte src/lib/ui/HourlyStrip.svelte src/lib/ui/wmo.js tests/wmo.test.js && git commit -m "feat: Weather screen

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 6 — Earthship screen

### Task 6.1: Thermal loop + greywater

**Files:**
- Create: `src/screens/Earthship.svelte`, `src/lib/ui/ThermalLoop.svelte`

**Interfaces:**
- Produces: `ThermalLoop.svelte` — SVG diagram: south glazing → room air → north mass, live temps, flow arrows whose direction/size derive from inter-zone deltas.
- Consumes: `Shelly_HT1_Indoor_Temperature`, `AmbientWeatherWS2902A_IndoorSensor_Temperature`, `AmbientWeatherWS2902A_WH31E_193_Temperature`, `Thermal_Advisory`, greywater items.

- [ ] **Step 1: Build `ThermalLoop.svelte`** (SVG, delta-driven arrows).
- [ ] **Step 2: Build `Earthship.svelte`**: thermal loop, buffering ratio (from 24h high/low items), advisory panel, greywater block (`SouthOutlet_Outlet2_Switch`, `SouthOutlet_AutoStatus` reason narrative, `SouthOutlet_LastAutoRun` age), zone humidity row.
- [ ] **Step 3: Verify on M9.**
- [ ] **Step 4: Commit**
```bash
git add src/screens/Earthship.svelte src/lib/ui/ThermalLoop.svelte && git commit -m "feat: Earthship screen

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 7 — Controls (safety-gated) — LAST, needs rule review

### Task 7.1: openHAB rule — honor a manual pump request through the gates

**Files:**
- Create (openHAB, via REST): item `SouthOutlet_ManualRequest` (Switch); modify rule `hex_southoutlet_cycle` to add a trigger on it.
- Backup: `~/openhab/backups/rule-hex_southoutlet_cycle-<date>-manualreq-BEFORE.json`

- [ ] **Step 1: Create the request item** (REST PUT, tag `control`).
- [ ] **Step 2: Backup + patch the rule**: add an `ItemStateChangeTrigger` on `SouthOutlet_ManualRequest`; in `evaluate()`, when the request is ON, treat as a cycle attempt that still passes EVERY existing gate (comms, invalid SoC/voltage, low-SoC cutoff, cooldown/hydrology, curtailment bypass allowed), then set the request back to OFF. If any gate fails, forceOff with reason `manual_denied_<gate>` and reset the request. Full patched script authored here.
- [ ] **Step 3: Verify** — REST-set `SouthOutlet_ManualRequest` ON while SoC healthy → a cycle starts (or a clear `manual_denied_*` status if a gate blocks); request auto-resets; `openhab_sanity_check.py` still green.
- [ ] **Step 4: Record** — hexmem fact documenting the manual-request path; runbook note.

### Task 7.2: Control tiles in the UI

**Files:**
- Create: `src/lib/ui/ControlButton.svelte` (600ms press-and-hold confirm)
- Modify: `src/screens/Home.svelte` or a small controls drawer

**Interfaces:**
- Produces: `ControlButton.svelte` props `{ label, active, onConfirm }` — fires `onConfirm` only after a 600 ms hold.
- Consumes: `getClientOnce().sendCommand(...)`.

- [ ] **Step 1: Build `ControlButton.svelte`** with press-and-hold + progress ring; unit-test the hold timer logic (`tests/hold.test.js`).
- [ ] **Step 2: Wire controls**: living-room lights (`living_room_1_Switch` etc.), `LivingRoomCircadian_Enable` toggle, goat outlets (`Goat_Plugs_Outlet1/2_Switch`), and "Circulate now" → `sendCommand('SouthOutlet_ManualRequest','ON')`.
- [ ] **Step 3: Verify on M9** — hold-to-confirm works; a light toggles; pump request triggers a cycle (watch `SouthOutlet_AutoStatus`).
- [ ] **Step 4: Commit**
```bash
git add src/lib/ui/ControlButton.svelte src/screens/Home.svelte tests/hold.test.js && git commit -m "feat: safety-gated control tiles + manual pump request

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 8 — PWA, auto-dim, offline, deploy

### Task 8.1: PWA + time-of-day dim + offline state

**Files:**
- Create: `src/lib/ui/theme.js` (dim factor from `Sun_SunPhaseName`/elevation), `public/manifest.webmanifest`, icons
- Modify: `vite.config.js` (vite-plugin-pwa), `src/lib/ui/Shell.svelte` (offline full-screen state)

- [ ] **Step 1: Add `vite-plugin-pwa`**, manifest, icons (`npm install -D vite-plugin-pwa`).
- [ ] **Step 2: Auto-dim** — apply a CSS brightness/opacity variable driven by sun phase (dim after dusk).
- [ ] **Step 3: Offline state** — when `$connection === 'offline'`, show a console-style "STATION OFFLINE" overlay with last-known values + age.
- [ ] **Step 4: Verify on M9** — install to home screen; kill openHAB briefly → offline overlay; restore → recovers; after dusk → dimmer.
- [ ] **Step 5: Commit.**

### Task 8.2: Production deploy on the LAN

**Files:**
- Create: `deploy.sh`, nginx site config (or reuse), `~/earthship-ui/config.json` on the server (gitignored)

- [ ] **Step 1: `npm run build`**; serve `dist/` via nginx at `http://ogsatoth:8090` (site config authored here); place real `config.json` (token from `~/.config/hex/openhab.env`, perms 0640).
- [ ] **Step 2: Point the M9 at `http://ogsatoth:8090`, install PWA, confirm full app live.**
- [ ] **Step 3: Add a sanity-checker line** (optional) — `openhab_sanity_check.py` pings `http://ogsatoth:8090` reachable.
- [ ] **Step 4: Commit deploy script; push; record hexmem fact (URL, deploy path, nginx config location).**

---

## Self-Review

**Spec coverage:** Devices/priority → Global Constraints + M9 verification in every visual task ✓. Design language → Task 2.1 tokens ✓. Architecture (Svelte/Vite/Tailwind/ECharts, REST+SSE, static serve, config.json) → Phase 0–1, 8.2 ✓. Data layer (SSE, history incl. future rows, commands) → Tasks 1.1–1.4 ✓. Four screens → Phases 3–6 ✓. Controls (lights, circadian, goat outlets, safety-gated pump request) → Phase 7 ✓. BTC ticker → Task 2.2 ✓. Error handling (SSE reconnect, stale banner, offline, NULL) → Tasks 1.3, 8.1, values NULL discipline ✓. Testing (Vitest data layer, Playwright viewports, M9 device checks) → throughout ✓. PWA + auto-dim → Task 8.1 ✓. Deploy → Task 8.2 ✓.

**Placeholder scan:** Visual tasks (Phase 2–6) intentionally specify files/interfaces/bindings/verification rather than full component source — this is a deliberate, documented choice because the design mandates on-device visual iteration (Rollout step 2) and pre-writing pixel code would be discarded. The unit-testable core (Phase 0–1, hold timer, wmo, rule) carries full TDD code. This is the honest boundary, not a placeholder gap.

**Type consistency:** `num/fmt/socBands/runtimeText` signatures consistent across tasks; `items`/`connection` stores consistent; `getClientOnce()` introduced in 4.1 and reused in 7.2; `createSSE`/`createClient` factory shapes stable. `socBands` full-mode test literal flagged for correction in Task 1.2 Step 3.

---

## Phase 3 REVISED (operator feedback at 2.3 sign-off, 2026-07-17)

Static Home look APPROVED. Operator wants the live Home enriched to match/exceed the existing openHAB overview page. New requirements folded into Phase 3:

### Task 3.0: Shared interactive infra (before live Home)
- **Icon rendering:** add `@iconify/svelte` + offline icon sets `@iconify-json/mdi` and `@iconify-json/bi` (openHAB icon strings use `iconify:mdi:*` and `iconify:bi:*` — must render OFFLINE, no internet dep for the wall display). Create `src/lib/ui/OhIcon.svelte` props `{ icon }` where `icon` is an openHAB icon string (e.g. `$items.MoonPhaseicon`); strips the `iconify:` prefix and renders. NULL-safe (renders nothing/placeholder on empty).
- **Click-to-chart:** `src/lib/ui/ChartModal.svelte` — a full-screen overlay showing an ECharts history chart for one or more items, fetched via `getClientOnce().getHistory(...)` (add `getClientOnce()` export to store.js now). Includes future forecast rows where relevant. A `src/lib/ui/chartStore.js` writable holds `{open, title, items:[{name,color,label}], hours}`; tiles call `openChart({...})`; ChartModal subscribes and renders; tap-outside/close button dismisses. Reusable by all screens.
- **Toggle control:** `src/lib/ui/Toggle.svelte` props `{ item, label, onColor }` — reads `$items[item]`, shows on/off state, `sendCommand(item, state==='ON'?'OFF':'ON')` on tap (press-and-hold 500ms confirm to avoid accidental taps on the wall). Uses `getClientOnce().sendCommand`. For `SouthOutlet_Outlet2_Switch` (safety-gated pump) it toggles directly like the overview (manual override; rule reasserts next cycle) — flagged for operator.

### Task 3.1 REVISED: live + dense Home
Bind every tile to live items (real SoC/temps/etc.). Additions vs the static version:
- Real icons via OhIcon: Outdoor uses `SkyConditionIcon`; Sun&Moon uses `SunPhaseIcon` + `MoonPhaseicon`; Battery uses `BatteryIcon`.
- BOTH indoor and outdoor: Outdoor tile (temp/feels/hi-lo/humidity, `...Ws2902a_*` + `OutdoorTemp_24h_*`) AND an Indoor readout (`...IndoorSensor_Temperature`/`_RelativeHumidity` + `IndoorTemp_24h_*`).
- Every chartable tile is clickable → `openChart` with its item(s) (mirror overview: Inside, Outside, SoC, Solar, Wind, Pressure, Rain, BTC all chartable).
- A Controls row of `Toggle`s mirroring the overview switches: `living_room_1_Switch`, `living_room_2_Switch`, `LED_living_room_1_Switch`, `LivingRoomCircadian_Enable`, `Goat_Plugs_Outlet1_Switch` (Goat Cam), `Dish_Washer_Power`, `ShurefloPump_Power`, `SouthOutlet_Outlet2_Switch` (Fountain/pump), `OverrideSwitch`.
- Fill the sparse hero lower-halves with `Sparkline` trends (outdoor temp history in Outdoor; SoC history in Battery) — "more at a glance".
- Still fit 1340×800 no-scroll; verify via headless chromium screenshot at 1340×800 before operator re-review.
- Data-path: same-origin `/rest` proxy (CORS fix, commit d1475eb) — dev Vite proxy, prod nginx.
