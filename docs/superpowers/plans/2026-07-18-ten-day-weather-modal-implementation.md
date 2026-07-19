# Ten-Day Weather Detail Modals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show ten forecast days on Home and Weather and open one accessible ten-hour detail modal for every selected day.

**Architecture:** OpenHAB continues to own external forecast retrieval and publishes one additive, versioned `Forecast_10Day_JSON` item. Earthship UI validates that payload through a pure adapter, renders shared day buttons in route-specific layouts, and mounts one application-level modal and controller. The two legacy forecast JSON items and retained MainUI layouts remain unchanged.

**Tech Stack:** Python 3 standard library, Open-Meteo Forecast API, OpenHAB REST, Svelte 5, Svelte stores, ECharts 6, Vitest 4, Testing Library, Playwright.

## Global Constraints

- `Forecast_Hourly_JSON` remains a 14-entry array with fields `{h,t,p,r,w}`.
- `Forecast_Daily_JSON` remains a seven-entry array with fields `{d,hi,lo,p,w,pv}`.
- The new `Forecast_10Day_JSON` payload is version `1`, below 64 KiB, and contains at most ten unique ascending days.
- `generatedAt` and every hourly `at` timestamp include a UTC offset or `Z`.
- Today selects the first ten forecast records at or after the current local hour and may cross midnight.
- Future days select 08:00 through 17:00 local time and never borrow another date.
- Home and Weather must remain bounded at 1340×800 and 1280×720 with no page, card, or modal scrolling.
- The first modal version shows temperature, precipitation probability, solar radiation, wind, and weather condition.
- Existing MainUI weather arrays and layouts are not modified.
- No browser request goes directly to Open-Meteo.
- No household actuator, command endpoint, or control is involved.
- Live edits under `/home/sat/openhab`, item provisioning, timer-triggered refresh, and UI service restart require a separate contemporaneous deployment approval.
- Preserve the user-owned untracked `test-results/` directory.

---

### Task 1: Validate and Select Ten-Day Forecast Data

**Files:**
- Create: `src/lib/weather/forecastDetail.js`
- Test: `tests/forecast-detail.test.js`

**Interfaces:**
- Produces: `parseForecast10Day(raw, options?) -> ForecastResult`
- Produces: `parseLegacyDailyForecast(raw) -> ForecastDay[]`
- Produces: `selectForecastWindow(result, selectedDate, options?) -> ForecastWindow`
- Produces: constants `FORECAST_DETAIL_ITEM`, `FORECAST_DETAIL_MAX_BYTES`, and `FORECAST_DETAIL_STALE_MS`
- `ForecastResult`: `{ status, reason, generatedAtMs, timezone, days }`
- `ForecastWindow`: `{ mode, hours, expectedHours, missingHours }`

- [ ] **Step 1: Write failing parser and window-selection tests**

Create `tests/forecast-detail.test.js` with deterministic helpers and assertions:

```js
import { describe, expect, it } from 'vitest';
import {
  FORECAST_DETAIL_MAX_BYTES,
  parseForecast10Day,
  parseLegacyDailyForecast,
  selectForecastWindow,
} from '../src/lib/weather/forecastDetail.js';

function hour(date, hourValue, offset = '-06:00') {
  return {
    at: `${date}T${String(hourValue).padStart(2, '0')}:00:00${offset}`,
    tempF: 60 + hourValue,
    precipPct: hourValue,
    radiationWm2: hourValue * 20,
    windMph: 5 + hourValue / 2,
    weatherCode: 1,
  };
}

function day(date, label, start = 0, end = 23) {
  return {
    date,
    label,
    summary: {
      highF: 80,
      lowF: 50,
      precipPct: 20,
      weatherCode: 1,
      pvKwh: 6.4,
    },
    hours: Array.from({ length: end - start + 1 }, (_, index) => (
      hour(date, start + index)
    )),
  };
}

function payload(days, generatedAt = '2026-07-18T12:00:00-06:00') {
  return JSON.stringify({
    version: 1,
    generatedAt,
    timezone: 'America/Denver',
    days,
  });
}

describe('ten-day forecast contract', () => {
  it('normalizes ten ordered days and preserves provider nulls', () => {
    const days = Array.from({ length: 10 }, (_, index) => {
      const date = `2026-07-${String(18 + index).padStart(2, '0')}`;
      return day(date, index === 0 ? 'Today' : `Day ${index + 1}`);
    });
    days[0].hours[0].windMph = null;

    const result = parseForecast10Day(payload(days), {
      nowMs: Date.parse('2026-07-18T13:00:00-06:00'),
    });

    expect(result.status).toBe('ready');
    expect(result.days).toHaveLength(10);
    expect(result.days[0].hours[0].windMph).toBeNull();
  });

  it('rejects unsupported, duplicate, unordered, oversize, and offset-free payloads', () => {
    const validDay = day('2026-07-18', 'Today');
    expect(parseForecast10Day(JSON.stringify({
      version: 2,
      generatedAt: '2026-07-18T12:00:00-06:00',
      timezone: 'America/Denver',
      days: [validDay],
    })).status).toBe('unavailable');
    expect(parseForecast10Day(payload([validDay, validDay])).reason).toMatch(/duplicate/i);
    expect(parseForecast10Day(payload([
      day('2026-07-19', 'Tomorrow'),
      validDay,
    ])).reason).toMatch(/ascending/i);
    expect(parseForecast10Day(payload([{
      ...validDay,
      hours: [{ ...validDay.hours[0], at: '2026-07-18T00:00:00' }],
    }])).reason).toMatch(/offset/i);
    expect(parseForecast10Day('x'.repeat(FORECAST_DETAIL_MAX_BYTES + 1)).reason)
      .toMatch(/size/i);
  });

  it('marks forecasts older than four hours stale without dropping data', () => {
    const result = parseForecast10Day(
      payload([day('2026-07-18', 'Today')], '2026-07-18T08:00:00-06:00'),
      { nowMs: Date.parse('2026-07-18T12:00:01-06:00') },
    );
    expect(result.status).toBe('stale');
    expect(result.days).toHaveLength(1);
  });

  it('selects today from the current hour across midnight', () => {
    const result = parseForecast10Day(payload([
      day('2026-07-18', 'Today'),
      day('2026-07-19', 'Tomorrow'),
    ]), { nowMs: Date.parse('2026-07-18T20:32:00-06:00') });
    const selected = selectForecastWindow(result, '2026-07-18', {
      nowMs: Date.parse('2026-07-18T20:32:00-06:00'),
    });
    expect(selected.mode).toBe('rolling');
    expect(selected.hours).toHaveLength(10);
    expect(selected.hours[0].at).toContain('T21:00:00');
    expect(selected.hours.at(-1).at).toContain('2026-07-19T06:00:00');
  });

  it('selects exactly 08:00 through 17:00 for a future day', () => {
    const result = parseForecast10Day(payload([
      day('2026-07-18', 'Today'),
      day('2026-07-19', 'Tomorrow'),
    ]), { nowMs: Date.parse('2026-07-18T12:00:00-06:00') });
    const selected = selectForecastWindow(result, '2026-07-19', {
      nowMs: Date.parse('2026-07-18T12:00:00-06:00'),
    });
    expect(selected.mode).toBe('daytime');
    expect(selected.hours.map(({ at }) => at.slice(11, 13))).toEqual([
      '08', '09', '10', '11', '12', '13', '14', '15', '16', '17',
    ]);
  });

  it('retains exact partial coverage and maps the legacy seven-day fallback', () => {
    const result = parseForecast10Day(payload([
      day('2026-07-19', 'Tomorrow', 8, 14),
    ]), { nowMs: Date.parse('2026-07-18T12:00:00-06:00') });
    const selected = selectForecastWindow(result, '2026-07-19', {
      nowMs: Date.parse('2026-07-18T12:00:00-06:00'),
    });
    expect(selected.hours).toHaveLength(7);
    expect(selected.missingHours).toBe(3);

    expect(parseLegacyDailyForecast(JSON.stringify([
      { d: 'Today', hi: 80, lo: 50, p: 20, w: 1, pv: 6.4 },
    ]))).toEqual([expect.objectContaining({
      date: null,
      label: 'Today',
      summary: expect.objectContaining({ highF: 80, pvKwh: 6.4 }),
    })]);
  });
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
npm test -- tests/forecast-detail.test.js
```

Expected: FAIL because `src/lib/weather/forecastDetail.js` does not exist.

- [ ] **Step 3: Implement strict parsing and selection**

Create `src/lib/weather/forecastDetail.js` with:

```js
export const FORECAST_DETAIL_ITEM = 'Forecast_10Day_JSON';
export const FORECAST_DETAIL_MAX_BYTES = 64 * 1024;
export const FORECAST_DETAIL_STALE_MS = 4 * 60 * 60 * 1_000;

const SENTINELS = new Set(['', 'NULL', 'UNDEF']);
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const OFFSET_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

function unavailable(reason) {
  return {
    status: 'unavailable',
    reason,
    generatedAtMs: null,
    timezone: 'America/Denver',
    days: [],
  };
}

function nullableNumber(value, field) {
  if (value === null) return null;
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new TypeError(`${field} must be a finite number or null`);
  }
  return value;
}

function normalizeHour(raw, date) {
  if (!raw || typeof raw !== 'object' || !OFFSET_TIMESTAMP.test(raw.at ?? '')) {
    throw new TypeError('hour timestamp must include an offset');
  }
  const atMs = Date.parse(raw.at);
  if (!Number.isFinite(atMs) || raw.at.slice(0, 10) !== date) {
    throw new TypeError('hour timestamp must belong to its day');
  }
  return Object.freeze({
    at: raw.at,
    atMs,
    tempF: nullableNumber(raw.tempF, 'tempF'),
    precipPct: nullableNumber(raw.precipPct, 'precipPct'),
    radiationWm2: nullableNumber(raw.radiationWm2, 'radiationWm2'),
    windMph: nullableNumber(raw.windMph, 'windMph'),
    weatherCode: nullableNumber(raw.weatherCode, 'weatherCode'),
  });
}

function normalizeDay(raw) {
  if (!raw || typeof raw !== 'object' || !DATE.test(raw.date ?? '')) {
    throw new TypeError('day date must be ISO');
  }
  if (!Array.isArray(raw.hours)) throw new TypeError('day hours are required');
  const summary = raw.summary ?? {};
  const hours = raw.hours.map((value) => normalizeHour(value, raw.date));
  for (let index = 1; index < hours.length; index += 1) {
    if (hours[index - 1].atMs >= hours[index].atMs) {
      throw new TypeError('hours must be strictly ascending');
    }
  }
  return Object.freeze({
    date: raw.date,
    label: typeof raw.label === 'string' && raw.label.trim() ? raw.label.trim() : raw.date,
    summary: Object.freeze({
      highF: nullableNumber(summary.highF, 'highF'),
      lowF: nullableNumber(summary.lowF, 'lowF'),
      precipPct: nullableNumber(summary.precipPct, 'summary.precipPct'),
      weatherCode: nullableNumber(summary.weatherCode, 'summary.weatherCode'),
      pvKwh: nullableNumber(summary.pvKwh, 'pvKwh'),
    }),
    hours: Object.freeze(hours),
  });
}

export function parseForecast10Day(raw, { nowMs = Date.now() } = {}) {
  if (typeof raw !== 'string' || SENTINELS.has(raw.trim())) return unavailable('forecast detail missing');
  if (new TextEncoder().encode(raw).length > FORECAST_DETAIL_MAX_BYTES) {
    return unavailable('forecast detail exceeds size limit');
  }
  try {
    const parsed = JSON.parse(raw);
    if (parsed?.version !== 1) throw new TypeError('unsupported forecast detail version');
    if (parsed.timezone !== 'America/Denver') throw new TypeError('unexpected forecast timezone');
    if (!OFFSET_TIMESTAMP.test(parsed.generatedAt ?? '')) {
      throw new TypeError('generatedAt must include an offset');
    }
    const generatedAtMs = Date.parse(parsed.generatedAt);
    if (!Number.isFinite(generatedAtMs)) throw new TypeError('generatedAt is invalid');
    if (!Array.isArray(parsed.days) || parsed.days.length > 10) {
      throw new TypeError('forecast days must contain at most ten entries');
    }
    const days = parsed.days.map(normalizeDay);
    const seen = new Set();
    for (let index = 0; index < days.length; index += 1) {
      if (seen.has(days[index].date)) throw new TypeError('duplicate forecast day');
      seen.add(days[index].date);
      if (index > 0 && days[index - 1].date >= days[index].date) {
        throw new TypeError('forecast days must be strictly ascending');
      }
    }
    return Object.freeze({
      status: nowMs - generatedAtMs > FORECAST_DETAIL_STALE_MS ? 'stale' : 'ready',
      reason: '',
      generatedAtMs,
      timezone: parsed.timezone,
      days: Object.freeze(days),
    });
  } catch (error) {
    return unavailable(error?.message || 'forecast detail invalid');
  }
}

export function parseLegacyDailyForecast(raw) {
  if (typeof raw !== 'string' || SENTINELS.has(raw.trim())) return [];
  try {
    const rows = JSON.parse(raw);
    if (!Array.isArray(rows)) return [];
    const legacyNumber = (value) => {
      if (value === null || value === undefined || SENTINELS.has(String(value).trim())) return null;
      const number = Number(value);
      return Number.isFinite(number) ? number : null;
    };
    return rows.slice(0, 7).map((row, index) => Object.freeze({
      date: null,
      label: index === 1 ? 'Tomorrow' : String(row?.d ?? (index === 0 ? 'Today' : `D${index + 1}`)),
      summary: Object.freeze({
        highF: legacyNumber(row?.hi),
        lowF: legacyNumber(row?.lo),
        precipPct: legacyNumber(row?.p),
        weatherCode: legacyNumber(row?.w),
        pvKwh: legacyNumber(row?.pv),
      }),
      hours: Object.freeze([]),
    }));
  } catch {
    return [];
  }
}

function localDateAt(nowMs, timezone) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(nowMs);
  const value = Object.fromEntries(parts.map(({ type, value: part }) => [type, part]));
  return `${value.year}-${value.month}-${value.day}`;
}

export function selectForecastWindow(result, selectedDate, { nowMs = Date.now() } = {}) {
  const allHours = result.days.flatMap(({ hours }) => hours).sort((a, b) => a.atMs - b.atMs);
  const today = localDateAt(nowMs, result.timezone);
  let hours;
  let mode;
  if (selectedDate === today) {
    mode = 'rolling';
    const nextHourMs = Math.ceil(nowMs / 3_600_000) * 3_600_000;
    hours = allHours.filter(({ atMs }) => atMs >= nextHourMs).slice(0, 10);
  } else {
    mode = 'daytime';
    hours = allHours.filter(({ at }) => (
      at.slice(0, 10) === selectedDate
      && Number(at.slice(11, 13)) >= 8
      && Number(at.slice(11, 13)) <= 17
    ));
  }
  return Object.freeze({
    mode,
    hours: Object.freeze(hours),
    expectedHours: 10,
    missingHours: Math.max(0, 10 - hours.length),
  });
}
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
npm test -- tests/forecast-detail.test.js
```

Expected: one test file passes with six tests.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/lib/weather/forecastDetail.js tests/forecast-detail.test.js
git commit -m "feat: validate ten-day forecast detail"
```

---

### Task 2: Share Ten-Day Buttons Across Home and Weather

**Files:**
- Create: `src/lib/ui/DailyForecast.svelte`
- Create: `src/lib/weather/detailStore.js`
- Modify: `src/screens/Home.svelte`
- Modify: `src/screens/Weather.svelte`
- Test: `tests/ui/DailyForecast.test.js`
- Modify: `tests/ui/Weather.test.js`
- Modify: `tests/home-tablet-contract.test.js`

**Interfaces:**
- Consumes: normalized `ForecastDay[]` from Task 1
- Produces: `DailyForecast` props `{ days, variant, onselect }`
- Produces: `weatherDetailStore`, `openWeatherDetail({ date, label })`, and `closeWeatherDetail()`

- [ ] **Step 1: Write failing shared-component and route-contract tests**

Create `tests/ui/DailyForecast.test.js`:

```js
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import DailyForecast from '../../src/lib/ui/DailyForecast.svelte';

const days = Array.from({ length: 10 }, (_, index) => ({
  date: `2026-07-${String(18 + index).padStart(2, '0')}`,
  label: index === 0 ? 'Today' : `Day ${index + 1}`,
  summary: {
    highF: 80 + index,
    lowF: 50 + index,
    precipPct: index * 5,
    weatherCode: 1,
    pvKwh: 6.4,
  },
  hours: [],
}));

afterEach(cleanup);

describe('DailyForecast', () => {
  it('renders ten native day buttons and emits the selected day', async () => {
    const onselect = vi.fn();
    const { container } = render(DailyForecast, {
      props: { days, variant: 'home', onselect },
    });
    expect(screen.getAllByRole('button')).toHaveLength(10);
    expect(container.querySelector('[data-forecast-variant="home"]')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: /Day 2/i }));
    expect(onselect).toHaveBeenCalledWith(days[1]);
  });

  it('renders the weather two-column variant and keeps legacy rows activatable', async () => {
    const onselect = vi.fn();
    const legacy = [{ ...days[0], date: null, label: 'Today' }];
    const { container } = render(DailyForecast, {
      props: { days: legacy, variant: 'weather', onselect },
    });
    expect(container.querySelector('[data-forecast-variant="weather"]')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: /Today/i }));
    expect(onselect).toHaveBeenCalledWith(legacy[0]);
  });
});
```

Extend route tests to require:

```js
expect(home).toContain('<DailyForecast');
expect(home).toContain('Forecast_10Day_JSON');
expect(home).not.toMatch(/forecastDaily\.slice\(0,\s*7\)/);
```

and render `Weather` with a valid `Forecast_10Day_JSON`, then assert ten day
buttons are present.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
npm test -- tests/ui/DailyForecast.test.js tests/ui/Weather.test.js tests/home-tablet-contract.test.js
```

Expected: FAIL because the component/store do not exist and both routes still
render legacy markup.

- [ ] **Step 3: Implement the modal store**

Create `src/lib/weather/detailStore.js`:

```js
import { writable } from 'svelte/store';

let nextOpenId = 0;

export const weatherDetailStore = writable({
  open: false,
  openId: 0,
  date: null,
  label: '',
  openedAtMs: 0,
  opener: null,
});

export function openWeatherDetail({ date = null, label = 'Forecast' } = {}) {
  weatherDetailStore.set({
    open: true,
    openId: ++nextOpenId,
    date,
    label,
    openedAtMs: Date.now(),
    opener: typeof document !== 'undefined' && document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null,
  });
}

export function closeWeatherDetail() {
  weatherDetailStore.update((state) => ({ ...state, open: false }));
}
```

- [ ] **Step 4: Implement `DailyForecast.svelte`**

Use native buttons and the existing `OhIcon`, `wmoIcon`, and token colors:

```svelte
<script>
  import OhIcon from './OhIcon.svelte';
  import { wmoIcon, wmoLabel } from './wmo.js';

  let { days = [], variant = 'home', onselect = () => {} } = $props();

  const value = (raw, suffix = '') => (
    typeof raw === 'number' && Number.isFinite(raw) ? `${Math.round(raw)}${suffix}` : '—'
  );

  const accessibleName = (day) => [
    day.label,
    wmoLabel(day.summary.weatherCode),
    `high ${value(day.summary.highF, ' degrees')}`,
    `low ${value(day.summary.lowF, ' degrees')}`,
    `precipitation ${value(day.summary.precipPct, ' percent')}`,
  ].join(', ');
</script>

<div class="daily-forecast" data-forecast-variant={variant}>
  {#each days as day, index (`${day.date ?? 'legacy'}-${day.label}-${index}`)}
    <button
      type="button"
      class="forecast-day"
      class:emphasized={index < 2}
      data-forecast-day={day.date ?? ''}
      aria-label={accessibleName(day)}
      onclick={() => onselect(day)}
    >
      <span class="day-label">{day.label}</span>
      <OhIcon icon={wmoIcon(day.summary.weatherCode)} size="1.2rem" />
      <span class="day-hilo">{value(day.summary.highF, '°')} / {value(day.summary.lowF, '°')}</span>
      <span class="day-precip">{value(day.summary.precipPct, '%')}</span>
      <span class="day-pv">PV {value(day.summary.pvKwh, ' kWh')}</span>
    </button>
  {/each}
</div>
```

Add bounded CSS:

```css
.daily-forecast {
  display: grid;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
}
.daily-forecast[data-forecast-variant='home'] {
  grid-template-columns: repeat(10, minmax(0, 1fr));
  gap: 0.3rem;
}
.daily-forecast[data-forecast-variant='weather'] {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-template-rows: repeat(5, minmax(0, 1fr));
  grid-auto-flow: column;
  gap: 0.14rem 0.55rem;
}
.forecast-day {
  min-width: 0;
  min-height: 0;
  border: 1px solid transparent;
  border-radius: 0.45rem;
  background: transparent;
  color: #e6edf3;
  display: grid;
  grid-template-columns: 1fr;
  place-items: center;
  padding: 0.1rem;
  font: inherit;
  cursor: pointer;
}
.daily-forecast[data-forecast-variant='home'] .forecast-day {
  grid-template-rows: repeat(4, minmax(0, auto));
}
.daily-forecast[data-forecast-variant='home'] .day-precip,
.daily-forecast[data-forecast-variant='home'] .day-pv {
  display: inline;
  font-size: 0.6rem;
}
.daily-forecast[data-forecast-variant='weather'] .forecast-day {
  grid-template-columns: minmax(3.5rem, 0.8fr) 1.2rem minmax(4.8rem, 1fr)
    minmax(2.6rem, 0.55fr) minmax(4.6rem, 0.85fr);
  column-gap: 0.25rem;
  text-align: left;
}
.forecast-day:hover,
.forecast-day:focus-visible {
  border-color: #8b5cf6;
  background: rgba(139, 92, 246, 0.1);
  outline: none;
}
```

- [ ] **Step 5: Integrate both routes with additive fallback**

In both `Home.svelte` and `Weather.svelte`:

```js
import DailyForecast from '../lib/ui/DailyForecast.svelte';
import {
  parseForecast10Day,
  parseLegacyDailyForecast,
} from '../lib/weather/forecastDetail.js';
import { openWeatherDetail } from '../lib/weather/detailStore.js';

const detailedForecast = $derived(parseForecast10Day($items.Forecast_10Day_JSON));
const legacyForecast = $derived(parseLegacyDailyForecast($items.Forecast_Daily_JSON));
const forecastDays = $derived(
  detailedForecast.days.length > 0 ? detailedForecast.days : legacyForecast,
);

function selectForecastDay(day) {
  openWeatherDetail({ date: day.date, label: day.label });
}
```

Replace route-local forecast loops with:

```svelte
<DailyForecast days={forecastDays} variant="home" onselect={selectForecastDay} />
```

and:

```svelte
<DailyForecast days={forecastDays} variant="weather" onselect={selectForecastDay} />
```

Remove only superseded route-local forecast row styles and helpers. Preserve
all non-forecast layout, current 14-hour strip, AQI, and measured tiles.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```bash
npm test -- tests/forecast-detail.test.js tests/ui/DailyForecast.test.js tests/ui/Weather.test.js tests/home-tablet-contract.test.js
```

Expected: all four files pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/lib/ui/DailyForecast.svelte src/lib/weather/detailStore.js \
  src/screens/Home.svelte src/screens/Weather.svelte \
  tests/ui/DailyForecast.test.js tests/ui/Weather.test.js \
  tests/home-tablet-contract.test.js
git commit -m "feat: share ten-day weather controls"
```

---

### Task 3: Build the Accessible Weather Detail Modal

**Files:**
- Create: `src/lib/weather/detailChart.js`
- Create: `src/lib/ui/WeatherDetailModal.svelte`
- Modify: `src/App.svelte`
- Test: `tests/weather-detail-chart.test.js`
- Test: `tests/ui/WeatherDetailModal.test.js`

**Interfaces:**
- Consumes: Task 1 parser/window and Task 2 store
- Produces: `buildWeatherDetailOption({ hours, widthPx }) -> EChartsOption`
- Produces: one app-level `<WeatherDetailModal />`

- [ ] **Step 1: Write failing chart-option and modal-behavior tests**

Create `tests/weather-detail-chart.test.js`:

```js
import { describe, expect, it } from 'vitest';
import { buildWeatherDetailOption } from '../src/lib/weather/detailChart.js';

describe('weather detail chart', () => {
  it('renders ten aligned condition, temperature, precipitation, radiation, and wind values', () => {
    const hours = Array.from({ length: 10 }, (_, index) => ({
      at: `2026-07-19T${String(index + 8).padStart(2, '0')}:00:00-06:00`,
      tempF: 60 + index,
      precipPct: index * 5,
      radiationWm2: index * 80,
      windMph: 5 + index,
      weatherCode: 1,
    }));
    const option = buildWeatherDetailOption({ hours, widthPx: 900 });
    expect(option.xAxis.data).toHaveLength(10);
    expect(option.series.map(({ name }) => name)).toEqual([
      'Radiation', 'Precipitation', 'Temperature', 'Wind',
    ]);
    expect(option.series.every(({ data }) => data.length === 10)).toBe(true);
    expect(option.animation).toBe(false);
  });
});
```

Create `tests/ui/WeatherDetailModal.test.js` with mocked ECharts and OpenHAB
items. Cover:

- complete ten-hour rendering;
- stale warning;
- `7 of 10 hours available`;
- legacy selection with `Hourly detail unavailable`;
- close-button focus on open;
- Tab trap, Escape close, and opener focus restoration;
- backdrop closes while panel activation does not.
- route change closes the dialog and restores background/body state;
- body scroll locking is restored exactly after close and destroy.

The central assertion setup is:

```js
items.set({
  Forecast_10Day_JSON: validPayload,
});
const opener = document.createElement('button');
document.body.append(opener);
opener.focus();
render(WeatherDetailModal);
openWeatherDetail({ date: '2026-07-19', label: 'Tomorrow' });
expect(await screen.findByRole('dialog', { name: /Tomorrow forecast/i })).toBeTruthy();
expect(screen.getAllByTestId('weather-detail-hour')).toHaveLength(10);
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
npm test -- tests/weather-detail-chart.test.js tests/ui/WeatherDetailModal.test.js
```

Expected: FAIL because the option builder and modal do not exist.

- [ ] **Step 3: Implement the pure chart option**

Create `src/lib/weather/detailChart.js`. Use four series in this order:

```js
[
  {
    name: 'Radiation',
    type: 'bar',
    yAxisIndex: 2,
    data: hours.map(({ radiationWm2 }) => radiationWm2),
    itemStyle: { color: '#fbbf24', opacity: 0.14 },
    silent: true,
  },
  {
    name: 'Precipitation',
    type: 'bar',
    yAxisIndex: 1,
    data: hours.map(({ precipPct }) => precipPct),
    itemStyle: { color: '#38bdf8', opacity: 0.55 },
  },
  {
    name: 'Temperature',
    type: 'line',
    yAxisIndex: 0,
    data: hours.map(({ tempF }) => tempF),
    showSymbol: true,
    lineStyle: { width: 2, color: '#f59e0b' },
  },
  {
    name: 'Wind',
    type: 'line',
    yAxisIndex: 3,
    data: hours.map(({ windMph }) => windMph),
    showSymbol: true,
    lineStyle: { width: 2, color: '#22d3ee' },
  },
]
```

The complete option uses:

- category labels formatted from each offset-bearing `at`;
- left temperature axis;
- right 0–100 precipitation axis;
- hidden radiation axis;
- offset right wind axis;
- unsmoothed lines;
- HTML tooltip with all four numeric metrics;
- measured grid margins based on `widthPx`;
- `animation: false`.

- [ ] **Step 4: Implement `WeatherDetailModal.svelte`**

Follow `ChartModal.svelte` for focus and measured resize behavior. The modal:

- subscribes to `weatherDetailStore` and `$items.Forecast_10Day_JSON`;
- parses with `openedAtMs`;
- finds the selected day;
- calls `selectForecastWindow`;
- renders ten icon/hour/value columns with `data-testid="weather-detail-hour"`;
- announces stale and partial coverage;
- renders `Hourly detail unavailable` when the new payload/date is absent;
- initializes ECharts as SVG only when at least one hour exists;
- observes the chart container with `observeElementSize`;
- disposes ECharts and restores opener focus on close;
- traps focus and handles Escape/backdrop identically to `ChartModal`;
- closes when `$currentRoute` changes.

Use fixed IDs:

```js
const TITLE_ID = 'weather-detail-modal-title';
const DESCRIPTION_ID = 'weather-detail-modal-description';
```

Use these bounded outer dimensions:

```css
.weather-detail-backdrop {
  position: fixed;
  inset: 0;
  z-index: 210;
  padding: 1.25rem;
  display: grid;
  place-items: center;
  background: rgba(4, 6, 10, 0.86);
}
.weather-detail-panel {
  width: min(1160px, 100%);
  height: min(680px, 100%);
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
}
.weather-detail-hours {
  display: grid;
  grid-template-columns: repeat(10, minmax(0, 1fr));
}
```

- [ ] **Step 5: Mount the modal once**

In `src/App.svelte`:

```svelte
import WeatherDetailModal from './lib/ui/WeatherDetailModal.svelte';
```

and after `<ChartModal />`:

```svelte
<WeatherDetailModal />
```

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```bash
npm test -- tests/forecast-detail.test.js tests/weather-detail-chart.test.js \
  tests/ui/DailyForecast.test.js tests/ui/WeatherDetailModal.test.js \
  tests/ui/Weather.test.js tests/home-tablet-contract.test.js
```

Expected: all six files pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/lib/weather/detailChart.js src/lib/ui/WeatherDetailModal.svelte \
  src/App.svelte tests/weather-detail-chart.test.js \
  tests/ui/WeatherDetailModal.test.js
git commit -m "feat: add ten-hour weather modal"
```

---

### Task 4: Prove Both Routes and Supported Viewports

**Files:**
- Create: `tests/e2e/weather-detail-modal.spec.js`
- Modify: `docs/qa/ui-audit-matrix.csv`

**Interfaces:**
- Consumes: the complete UI feature from Tasks 1–3
- Produces: browser evidence for both routes and both supported viewports

- [ ] **Step 1: Write the failing browser contract**

Create a fixture with ten days, 24 hours per day, and an additive
`Forecast_10Day_JSON` item. For each viewport and each route:

```js
for (const target of TARGETS) {
  for (const route of ['home', 'weather']) {
    test(`${route} opens bounded ten-hour weather detail at ${target.name}`, async ({ page }) => {
      await openFixture(page, route, target);
      const buttons = page.locator('[data-forecast-day]');
      await expect(buttons).toHaveCount(10);
      const opener = buttons.nth(1);
      await opener.click();
      const dialog = page.getByRole('dialog', { name: /forecast/i });
      await expect(dialog).toBeVisible();
      await expect(dialog.locator('[data-testid="weather-detail-hour"]')).toHaveCount(10);
      await expect(dialog.locator('svg')).toBeVisible();

      const bounds = await dialog.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        return {
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          scrollWidth: element.scrollWidth,
          clientWidth: element.clientWidth,
          scrollHeight: element.scrollHeight,
          clientHeight: element.clientHeight,
        };
      });
      expect(bounds.left).toBeGreaterThanOrEqual(0);
      expect(bounds.top).toBeGreaterThanOrEqual(0);
      expect(bounds.right).toBeLessThanOrEqual(target.width);
      expect(bounds.bottom).toBeLessThanOrEqual(target.height);
      expect(bounds.scrollWidth).toBeLessThanOrEqual(bounds.clientWidth);
      expect(bounds.scrollHeight).toBeLessThanOrEqual(bounds.clientHeight);

      await page.keyboard.press('Escape');
      await expect(dialog).toBeHidden();
      await expect(opener).toBeFocused();
    });
  }
}
```

Also capture console and page errors and require both arrays to remain empty.

- [ ] **Step 2: Run browser test and verify RED**

Run:

```bash
npx playwright test tests/e2e/weather-detail-modal.spec.js --workers=1
```

Expected: FAIL before integration is complete or if either route/modal
overflows.

- [ ] **Step 3: Make only bounded layout corrections**

Adjust `DailyForecast.svelte`, `WeatherDetailModal.svelte`, and the two
forecast-card callers only where measured browser evidence fails. Do not
modify Shell, Tile, unrelated routes, the existing 14-hour chart, or phone
styles.

- [ ] **Step 4: Update the audit matrix**

Replace `FUTURE-FORECAST-MODAL` with a verified automated contract:

```csv
WEATHER-DETAIL-MODAL,home and weather,ten-day forecast controls and shared modal,future forecast,both targets,complete stale partial and unavailable,Ten day buttons open the selected ten-hour weather window with temperature precipitation radiation wind and conditions,tests/forecast-detail.test.js; tests/ui/WeatherDetailModal.test.js; tests/e2e/weather-detail-modal.spec.js,verified-automated
```

- [ ] **Step 5: Run the complete UI verification gate**

Run:

```bash
npm test
npx playwright test tests/e2e/weather-detail-modal.spec.js \
  tests/e2e/weather-earthship-layout.spec.js tests/e2e/home-runtime.spec.js \
  --workers=1
npm run build
git diff --check
```

Expected:

- all Vitest files pass;
- all selected Playwright tests pass at both supported targets;
- production build exits zero with only the existing chunk-size advisory;
- diff check prints nothing.

- [ ] **Step 6: Commit Task 4**

```bash
git add tests/e2e/weather-detail-modal.spec.js docs/qa/ui-audit-matrix.csv \
  src/lib/ui/DailyForecast.svelte src/lib/ui/WeatherDetailModal.svelte \
  src/screens/Home.svelte src/screens/Weather.svelte
git commit -m "test: verify ten-day weather modals"
```

---

### Task 5: Deploy the OpenHAB Forecast Producer After Separate Approval

**Files:**
- Modify live: `/home/sat/openhab/scripts/forecast_intel.py`
- Create live test: `/home/sat/openhab/tests/test_forecast_intel.py`
- Create live backup: `/home/sat/openhab/backups/forecast-10day-v1-predeploy/`
- Create OpenHAB item: `Forecast_10Day_JSON`

**Interfaces:**
- Produces legacy `Forecast_Hourly_JSON` and `Forecast_Daily_JSON` unchanged
- Produces versioned `Forecast_10Day_JSON`
- Consumes Open-Meteo ten-day daily/hourly snapshot

- [ ] **Step 1: Stop at the live deployment approval gate**

Request contemporaneous approval to:

- back up the active producer and item state;
- edit the timer-referenced live producer;
- provision one unlinked display-only String item;
- run one display-only JSON refresh;
- read-verify all three item shapes.

This approval does not authorize timer changes, service restarts, item
commands, or household actuation.

- [ ] **Step 2: Snapshot live state after approval**

Create a timestamped backup containing:

- `forecast_intel.py`;
- `forecast-json.service` and `.timer`;
- `forecast-intel.service` and `.timer`;
- item-definition GET result or explicit absent marker for
  `Forecast_10Day_JSON`;
- current state and byte length for both legacy JSON items.

Record SHA-256 hashes and refuse to overwrite an existing backup.

- [ ] **Step 3: Write the failing producer tests**

Use Python `unittest` and load the script without allowing its token lookup or
network calls at import. Tests must inject a synthetic single provider
snapshot and a recording `oh_put_state`.

Cover:

- ten detail days and offset-bearing timestamps;
- detail fields including wind and null preservation;
- exact 14-entry legacy hourly contract;
- exact seven-entry legacy daily contract;
- detail payload below 64 KiB;
- legacy publication before additive detail;
- legacy publication continuing after injected detail failure.

Run:

```bash
python3 -m unittest -v /home/sat/openhab/tests/test_forecast_intel.py
```

Expected: FAIL because the active producer has no ten-day payload builder.

- [ ] **Step 4: Implement a single ten-day provider snapshot**

Change the query to include hourly
`temperature_2m,precipitation_probability,shortwave_radiation,wind_speed_10m,weather_code`,
the existing daily variables, `wind_speed_unit=mph`,
`timezone=America/Denver`, and `forecast_days=10`.

Add pure functions:

```python
def build_forecast_payloads(snapshot, pv_per_day, now):
    """Return (legacy_hourly, legacy_daily, detail_v1)."""

def serialize_detail(detail):
    """Compact JSON, reject encoded size >= 64 KiB."""

def publish_forecast_payloads(payloads, put_state=oh_put_state):
    """Publish hourly legacy, daily legacy, then additive detail."""
```

Use `zoneinfo.ZoneInfo("America/Denver")` to attach the correct offset to every
provider-local timestamp. Preserve provider `None` values. Never coerce them to
zero in the detail payload.

`build_json_items()` fetches once, builds once, publishes the two legacy items,
then attempts the additive item. An additive failure is logged and re-raised
only after both legacy updates complete.

- [ ] **Step 5: Run producer tests and verify GREEN**

Run:

```bash
python3 -m unittest -v /home/sat/openhab/tests/test_forecast_intel.py
python3 -m py_compile /home/sat/openhab/scripts/forecast_intel.py
```

Expected: all producer tests pass and compilation exits zero.

- [ ] **Step 6: Provision the display-only item**

Create only:

```json
{
  "type": "String",
  "name": "Forecast_10Day_JSON",
  "label": "10-Day Forecast Detail",
  "category": "weather",
  "tags": []
}
```

Read it back and require exact type/name plus no links and no command-producing
metadata.

- [ ] **Step 7: Run one display-only refresh and verify compatibility**

Run the existing JSON-only service entrypoint once. Verify:

- `Forecast_10Day_JSON` parses, is version 1, has ten days, and is below 64 KiB;
- each detail day is ascending and contains offset-bearing hourly records;
- `Forecast_Hourly_JSON` remains an array of exactly 14 legacy rows;
- `Forecast_Daily_JSON` remains an array of exactly seven legacy rows;
- both timers retain their exact schedules and enabled state;
- no OpenHAB item command or actuator event occurred.

- [ ] **Step 8: Deploy the UI and perform live read-only verification**

Because the household runtime is the versioned user-level
`earthship-ui.service` on port 5190, restart only that service after the
committed UI code is present. Verify Home and Weather each show ten buttons,
open the shared modal, and show ten hours from live data. Do not change nginx
or add a second release server.

- [ ] **Step 9: Record the live outcome**

Update `docs/qa/ui-audit-matrix.csv` from automated evidence to include the
live producer/item readback evidence. Record the verified outcome and rollback
backup path in private Hexmem. If any live gate fails, restore the exact
producer and item definition/state from the backup and verify both legacy
items refresh again before reporting failure.

---

## Final Verification

Before claiming implementation complete:

```bash
npm test
npx playwright test tests/e2e/weather-detail-modal.spec.js \
  tests/e2e/weather-earthship-layout.spec.js tests/e2e/home-runtime.spec.js \
  --workers=1
npm run build
git diff --check
git status --short
```

Expected: all automated checks pass; the only untracked path is the pre-existing
user-owned `test-results/`. Live completion additionally requires every Task 5
readback check after separate approval.
