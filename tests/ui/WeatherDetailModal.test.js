// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  '../../node_modules/svelte/src/index-client.js'
));

const mocks = vi.hoisted(() => {
  const chart = {
    dispose: vi.fn(),
    resize: vi.fn(),
    setOption: vi.fn(),
  };
  return {
    chart,
    init: vi.fn(() => chart),
  };
});

vi.mock('../../src/lib/charts/loadEcharts.js', () => ({
  getEcharts: async () => ({ init: mocks.init }),
}));
vi.mock('../../src/lib/weather/capabilityState.js', async () => {
  const { writable } = await import('svelte/store');
  return { weatherCapabilityRaw: writable(null), weatherCapabilityClock: writable(Date.now()) };
});

import WeatherDetailModal from '../../src/lib/ui/WeatherDetailModal.svelte';
import { applyState, items } from '../../src/lib/openhab/store.js';
import {
  closeWeatherDetail,
  openWeatherDetail,
} from '../../src/lib/weather/detailStore.js';
import { currentRoute } from '../../src/routes.js';
import { weatherCapabilityRaw, weatherCapabilityClock } from '../../src/lib/weather/capabilityState.js';
import atmosphericOriginals from '../fixtures/weather-atmosphere.json';
import { capabilityFixture, CAPABILITY_NOW } from '../fixtures/weather-capabilities.js';

function payload({ count = 12, stale = false, precipSumIn, hourPrecipIn, version = 1, firstTempF = 60 } = {}) {
  return JSON.stringify({
    version,
    ...(version === 2 ? {
      temperatureAdjustment: {
        highCorrectionF: 2.5,
        lowCorrectionF: -9,
        hourlyMethod: 'hourly-blend',
        hourBuckets: Array.from({ length: 24 }, (_, hour) => ({
          hour,
          count: hour === 7 ? 7 : 0,
          weight: hour === 7 ? 0.5 : 0,
        })),
      },
    } : {}),
    generatedAt: new Date(Date.now() - (stale ? 5 * 60 * 60 * 1_000 : 0)).toISOString(),
    timezone: 'America/Denver',
    days: [{
      date: '2026-07-19',
      label: 'Tomorrow',
      summary: {
        highF: 78,
        lowF: 52,
        precipPct: 20,
        ...(precipSumIn !== undefined ? { precipSumIn } : {}),
        weatherCode: 1,
        pvKwh: 6.4,
      },
      hours: Array.from({ length: count }, (_, index) => ({
        at: `2026-07-19T${String(index + 7).padStart(2, '0')}:00:00-06:00`,
        tempF: firstTempF + index,
        precipPct: index * 5,
        ...(hourPrecipIn !== undefined ? { precipIn: hourPrecipIn(index) } : {}),
        radiationWm2: index * 80,
        windMph: 5 + index,
        weatherCode: 1,
      })),
    }],
  });
}

function addOpener(label = 'Open forecast') {
  const opener = document.createElement('button');
  opener.textContent = label;
  document.body.append(opener);
  opener.focus();
  return opener;
}

async function openTomorrow() {
  openWeatherDetail({ date: '2026-07-19', label: 'Tomorrow' });
  return screen.findByRole('dialog', { name: /Tomorrow forecast/i });
}

describe('WeatherDetailModal', () => {
  beforeEach(() => {
    global.ResizeObserver = class {
      observe() {}
      disconnect() {}
    };
    currentRoute.set('home');
    weatherCapabilityRaw.set(null);
    weatherCapabilityClock.set(CAPABILITY_NOW);
    items.set({ Forecast_10Day_JSON: payload() });
    mocks.init.mockClear();
    mocks.chart.setOption.mockClear();
    mocks.chart.resize.mockClear();
    mocks.chart.dispose.mockClear();
    document.body.style.overflow = '';
  });

  afterEach(() => {
    vi.useRealTimers();
    closeWeatherDetail();
    currentRoute.set('home');
    items.set({});
    cleanup();
    document.body.innerHTML = '';
    document.body.style.overflow = '';
  });

  it('keeps the selected day and chart when a later production issue arrives while open', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-18T12:00:00-06:00'));
    const issue = JSON.parse(payload({ firstTempF: 65 }));
    Object.assign(issue, { version: 3, provider: 'weathernext3', providerStatus: 'AVAILABLE',
      productionModel: { issueSha256: 'a'.repeat(64), status: 'ACTIVE', localCoverageQualified: false,
        probabilityClaim: false, temperatureStatistic: 'model_point_with_declared_raw_fallback',
        windStatistic: 'native_instantaneous_with_separate_local_hour_mean' } });
    Object.assign(issue.days[0].summary, { temperatureScope: 'full_day', temperatureStatistic: 'extrema_of_hourly_point_forecasts' });
    items.set({ Forecast_10Day_JSON: JSON.stringify(issue) });
    render(WeatherDetailModal);
    await openTomorrow();
    await vi.advanceTimersByTimeAsync(0);
    expect(screen.getAllByTestId('weather-detail-hour')).toHaveLength(12);

    // A publication can arrive between clock ticks; its real generation time
    // is later than opening, but not later than the current wall clock.
    vi.setSystemTime(new Date('2026-07-18T12:00:00.050-06:00'));
    issue.generatedAt = new Date().toISOString();
    issue.productionModel.issueSha256 = 'b'.repeat(64);
    issue.days[0].hours[0].tempF = 66;
    applyState('Forecast_10Day_JSON', JSON.stringify(issue));
    flushSync();
    await vi.advanceTimersByTimeAsync(0);

    expect(screen.getByRole('dialog', { name: /Tomorrow forecast/i })).toBeTruthy();
    expect(screen.queryByText('Hourly detail unavailable')).toBeNull();
    expect(screen.getAllByTestId('weather-detail-hour')).toHaveLength(12);
    expect(screen.getAllByTestId('weather-detail-hour')[0].querySelector('.hour-temp').textContent).toBe('66°');
    expect(mocks.chart.setOption.mock.calls.at(-1)[0].series.find(series => series.name === 'Temperature').data[0]).toBe(66);
  });

  it('ages the forecast stale without an item update', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-18T12:00:00-06:00'));
    items.set({ Forecast_10Day_JSON: payload() });
    render(WeatherDetailModal);
    await openTomorrow();
    expect(screen.queryByText('Forecast data may be stale')).toBeNull();

    vi.setSystemTime(new Date('2026-07-18T16:00:01-06:00'));
    await vi.advanceTimersByTimeAsync(1000);
    flushSync();

    expect(screen.getByText('Forecast data may be stale')).toBeTruthy();
  });

  it('advances the rolling hours and remaining temperature range without an item update', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-19T06:30:00-06:00'));
    const issue = JSON.parse(payload());
    issue.days[0].summary.highF = null;
    issue.days[0].summary.lowF = null;
    items.set({ Forecast_10Day_JSON: JSON.stringify(issue) });
    render(WeatherDetailModal);
    openWeatherDetail({ date: '2026-07-19', label: 'Today' });
    await screen.findByRole('dialog');
    expect(screen.getAllByTestId('weather-detail-hour')[0].querySelector('.hour-time').textContent).toBe('7 AM');
    expect(screen.getByText('71° / 60° · remaining hours')).toBeTruthy();

    vi.setSystemTime(new Date('2026-07-19T07:30:00-06:00'));
    await vi.advanceTimersByTimeAsync(1000);
    flushSync();

    expect(screen.getAllByTestId('weather-detail-hour')).toHaveLength(11);
    expect(screen.getAllByTestId('weather-detail-hour')[0].querySelector('.hour-time').textContent).toBe('8 AM');
    expect(screen.getByText('71° / 61° · remaining hours')).toBeTruthy();
  });

  it('rejects a future issue until the current clock reaches its generation time', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-18T12:00:00-06:00'));
    const issue = JSON.parse(payload());
    issue.generatedAt = '2026-07-18T12:01:00-06:00';
    items.set({ Forecast_10Day_JSON: JSON.stringify(issue) });
    render(WeatherDetailModal);
    await openTomorrow();
    expect(screen.getByText('Hourly detail unavailable')).toBeTruthy();
    expect(screen.queryAllByTestId('weather-detail-hour')).toHaveLength(0);

    vi.setSystemTime(new Date('2026-07-18T12:01:00-06:00'));
    await vi.advanceTimersByTimeAsync(1000);
    flushSync();

    expect(screen.queryByText('Hourly detail unavailable')).toBeNull();
    expect(screen.getAllByTestId('weather-detail-hour')).toHaveLength(12);
  });

  it('shows active production points and wind scope without explanatory labels', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-07-18T12:00:00-06:00'));
    const raw = JSON.parse(payload({ firstTempF: 65 }));
    Object.assign(raw, { version: 3, provider: 'weathernext3', providerStatus: 'AVAILABLE',
      productionModel: { issueSha256: 'a'.repeat(64), status: 'MIXED_WITH_RAW_FALLBACK', localCoverageQualified: false,
        probabilityClaim: false, temperatureStatistic: 'model_point_with_declared_raw_fallback',
        windStatistic: 'native_instantaneous_with_separate_local_hour_mean' } });
    Object.assign(raw.days[0].summary, { temperatureScope: 'full_day', temperatureStatistic: 'extrema_of_hourly_point_forecasts' });
    raw.days[0].hours[0].windMeanMph = 2;
    items.set({ Forecast_10Day_JSON: JSON.stringify(raw) });
    addOpener();render(WeatherDetailModal);await openTomorrow();
    expect(screen.queryByText('Production temperature model · experimental')).toBeNull();
    expect(screen.queryByText('Shaded band and dashed raw mean use original WeatherNext statistics. The orange displayed forecast is separate.')).toBeNull();
    expect(screen.getByText('65°')).toBeTruthy();
    expect(screen.getByText('2 mph').title).toContain('Local station hourly mean');
    expect(screen.getByText('6 mph').title).toContain('Native instantaneous wind');
    expect(screen.queryByText(/Daily highs and lows are extrema of hourly point forecasts/)).toBeNull();
    expect(screen.queryByText(/Available local models supply forecast points/)).toBeNull();
  });

  it('renders a complete twelve-hour icon/value strip and SVG chart', async () => {
    // The fixture's 2026-07-19 hours are "Tomorrow" relative to a pinned
    // 07-18 clock; unpinned, these tests fail whenever the wall-clock date
    // catches up to the fixture. shouldAdvanceTime keeps waitFor polling.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-07-18T12:00:00-06:00'));
    items.set({ Forecast_10Day_JSON: payload() });
    addOpener();
    render(WeatherDetailModal);
    await openTomorrow();

    expect(screen.getAllByTestId('weather-detail-hour')).toHaveLength(12);
    expect(document.getElementById('weather-detail-modal-description')?.textContent)
      .toContain('12 of 12 hourly periods shown.');
    expect(screen.getByText('60°')).toBeTruthy();
    expect(screen.getByText('0 W/m²')).toBeTruthy();
    await waitFor(() => expect(mocks.init).toHaveBeenCalledWith(
      expect.any(HTMLElement),
      null,
      { renderer: 'svg' },
    ));
    expect(mocks.chart.setOption).toHaveBeenCalled();
  });

  it('shows original raw ranges separately from displayed temperature and withdraws expired ranges', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(CAPABILITY_NOW);
    items.set({ Forecast_10Day_JSON: payload().replaceAll('2026-07-19', '2026-10-21') });
    weatherCapabilityRaw.set(JSON.stringify(capabilityFixture()));
    addOpener();
    render(WeatherDetailModal);
    openWeatherDetail({ date: '2026-10-21', label: 'Today' });
    await screen.findByRole('dialog', { name: /Today forecast/i });
    expect(screen.queryByText('WeatherNext p10–p90; local coverage not yet verified')).toBeNull();
    expect(screen.getAllByText('32°–50°').length).toBeGreaterThan(0);
    expect(screen.queryByText(/Raw median/)).toBeNull();
    expect(screen.queryByText(/Source initialized 6h ago/)).toBeNull();
    await waitFor(() => expect(mocks.chart.setOption.mock.calls.at(-1)?.[0].series.some(s => s.name === 'WeatherNext p10–p90')).toBe(true));
    const option = mocks.chart.setOption.mock.calls.at(-1)[0];
    expect(option.series.find(s => s.name === 'Temperature').data.some(v => v > 50)).toBe(true);
    expect(option.series.find(s => s.name === 'WeatherNext raw mean').data.filter(v => v !== null).every(v => v === 68)).toBe(true);
    weatherCapabilityClock.set(CAPABILITY_NOW + 3600000);
    await waitFor(() => expect(screen.queryAllByText('32°–50°')).toHaveLength(0));
    await waitFor(() => expect(mocks.chart.setOption.mock.calls.at(-1)[0].series.some(s => s.name === 'WeatherNext p10–p90')).toBe(false));
    expect(screen.getAllByTestId('weather-detail-hour').length).toBeGreaterThan(0);
  });

  it('renders producer-corrected v2 temperatures without applying correction items again', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-07-18T12:00:00-06:00'));
    items.set({
      Forecast_10Day_JSON: payload({ version: 2, firstTempF: 66.8 }),
      Forecast_HighCorrection_F: -12,
      Forecast_LowCorrection_F: -12,
    });
    addOpener();
    render(WeatherDetailModal);
    await openTomorrow();

    expect(screen.getByText('67°')).toBeTruthy();
    expect(screen.queryByText('55°')).toBeNull();
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalled());
    expect(JSON.stringify(mocks.chart.setOption.mock.calls.at(-1)[0])).toContain('66.8');
  });

  it('announces stale and partial forecast coverage', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-07-18T12:00:00-06:00'));
    items.set({ Forecast_10Day_JSON: payload({ count: 7, stale: true }) });
    addOpener();
    render(WeatherDetailModal);
    await openTomorrow();

    expect(screen.getByRole('status').textContent).toContain('Forecast data may be stale');
    expect(screen.getByRole('status').textContent).toContain('7 of 12 hours available');
    expect(screen.getAllByTestId('weather-detail-hour')).toHaveLength(7);
  });

  it('renders a clear unavailable state for a legacy-only selection', async () => {
    items.set({
      Forecast_10Day_JSON: 'UNDEF',
      Forecast_Daily_JSON: '[{"d":"Today","hi":80,"lo":50}]',
    });
    addOpener();
    render(WeatherDetailModal);
    openWeatherDetail({ date: null, label: 'Today' });

    expect(await screen.findByRole('dialog', { name: /Today forecast/i })).toBeTruthy();
    expect(screen.getByText('Hourly detail unavailable')).toBeTruthy();
    expect(mocks.init).not.toHaveBeenCalled();
  });

  it('focuses close, traps Tab, closes on Escape, and restores the opener', async () => {
    const opener = addOpener();
    render(WeatherDetailModal);
    const dialog = await openTomorrow();
    const close = screen.getByRole('button', { name: 'Close weather detail' });

    await waitFor(() => expect(document.activeElement).toBe(close));
    await fireEvent.keyDown(dialog, { key: 'Tab' });
    expect(document.activeElement).toBe(close);
    // The collapsed experimental disclosure is now the last keyboard target.
    const disclosure = dialog.querySelector('summary');
    await fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(disclosure);
    await fireEvent.keyDown(dialog, { key: 'Tab' });
    expect(document.activeElement).toBe(close);
    await fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(opener);
  });

  it('closes from the backdrop but not from panel activation', async () => {
    addOpener();
    const { container } = render(WeatherDetailModal);
    const dialog = await openTomorrow();

    await fireEvent.click(dialog);
    expect(screen.getByRole('dialog')).toBeTruthy();
    await fireEvent.click(container.querySelector('.weather-detail-backdrop'));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('closes on route change and restores the prior body overflow', async () => {
    document.body.style.overflow = 'clip';
    addOpener();
    render(WeatherDetailModal);
    await openTomorrow();

    expect(document.body.style.overflow).toBe('hidden');
    currentRoute.set('weather');
    flushSync();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.body.style.overflow).toBe('clip');
  });

  it('restores body overflow and disposes the chart when destroyed while open', async () => {
    document.body.style.overflow = 'scroll';
    addOpener();
    const view = render(WeatherDetailModal);
    await openTomorrow();
    await waitFor(() => expect(mocks.init).toHaveBeenCalled());

    expect(document.body.style.overflow).toBe('hidden');
    view.unmount();
    expect(document.body.style.overflow).toBe('scroll');
    expect(mocks.chart.dispose).toHaveBeenCalled();
  });

  // These two use fake timers pinned well before the fixture's forecast date
  // so selectForecastWindow always resolves 'daytime' mode (all 12 hours from
  // index 0) regardless of the real wall-clock date the suite runs on — the
  // same real-time coupling that makes the two pre-existing tests above
  // flaky depending on time of day/date.
  it('shows the day summary rain amount and per-hour amounts when positive', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-18T12:00:00-06:00'));
    try {
      items.set({
        Forecast_10Day_JSON: payload({
          precipSumIn: 0.24,
          hourPrecipIn: (index) => (index === 0 ? 0.05 : 0),
        }),
      });
      addOpener();
      const { container } = render(WeatherDetailModal);
      await openTomorrow();

      const summaryAmount = screen.getByTestId('modal-day-rain-amount');
      expect(summaryAmount.textContent).toBe('0.24″');
      expect(summaryAmount.getAttribute('style')).toContain('rgb(59, 130, 246)');

      const hourAmounts = container.querySelectorAll('[data-testid="modal-hour-rain-amount"]');
      expect(hourAmounts).toHaveLength(1);
      expect(hourAmounts[0].textContent).toBe('0.05″');
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows no rain amounts when precip amounts are zero, null, or missing', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-18T12:00:00-06:00'));
    try {
      items.set({ Forecast_10Day_JSON: payload() });
      addOpener();
      const { container } = render(WeatherDetailModal);
      await openTomorrow();

      expect(container.querySelectorAll('[data-testid="modal-day-rain-amount"]')).toHaveLength(0);
      expect(container.querySelectorAll('[data-testid="modal-hour-rain-amount"]')).toHaveLength(0);
      expect(container.textContent).not.toContain('″');
    } finally {
      vi.useRealTimers();
    }
  });


it('shows source-labeled atmospheric diagnostics without claiming model use or condensation safety', async () => {
  vi.useFakeTimers({ toFake: ['Date'] });vi.setSystemTime(CAPABILITY_NOW);
  items.set({ Forecast_10Day_JSON: payload().replaceAll('2026-07-19','2026-10-21') });
  weatherCapabilityRaw.set(JSON.stringify(atmosphericOriginals.outdoor));weatherCapabilityClock.set(CAPABILITY_NOW);
  render(WeatherDetailModal);openWeatherDetail({date:'2026-10-21',label:'Today'});
  await screen.findByRole('dialog');
  expect(screen.getByText('Forecast atmosphere · raw diagnostic')).toBeTruthy();
  expect(screen.getByText('Dew point: 41.0°F')).toBeTruthy();
  expect(screen.getByText('Sea-level pressure: 900.0 hPa')).toBeTruthy();
  expect(screen.getByText('Scalar mean wind: 4.5 mph')).toBeTruthy();
  expect(screen.getByText('Mean vector: 3.2 mph from 135°')).toBeTruthy();
  expect(screen.getByText(/Cloud total 40% · high 40% · mid 40% · low 40%/)).toBeTruthy();
  expect(screen.getByText(/Diagnostic RH from forecast mean temperature and dew point/)).toBeTruthy();
  expect(screen.getByText(/Current temperature model does not use these added fields/)).toBeTruthy();
  expect(screen.getByText(/Surface condensation not assessed/)).toBeTruthy();
  expect(screen.getByText(/Qualified indoor temperature and humidity required/)).toBeTruthy();
  expect(screen.getAllByText(/initialized 1h ago; available 0m ago/).length).toBeGreaterThan(0);
  weatherCapabilityRaw.set(null);flushSync();expect(screen.queryByText('Forecast atmosphere · raw diagnostic')).toBeNull();
  expect(screen.getAllByTestId('weather-detail-hour').length).toBeGreaterThan(0);
});

it('withdraws only the indoor comparison when its original evidence expires', async () => {
  vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(CAPABILITY_NOW);
  items.set({Forecast_10Day_JSON:payload().replaceAll('2026-07-19','2026-10-21')});
  weatherCapabilityRaw.set(JSON.stringify(atmosphericOriginals.qualified));weatherCapabilityClock.set(CAPABILITY_NOW);
  render(WeatherDetailModal);openWeatherDetail({date:'2026-10-21',label:'Today'});await screen.findByRole('dialog');
  expect(screen.getByText(/Forecast outdoor air is drier than current qualified indoor air/)).toBeTruthy();
  const deadline=Date.parse(atmosphericOriginals.qualified.groups.atmosphere.moisture.valid_until);
  weatherCapabilityClock.set(deadline);flushSync();
  expect(screen.queryByText(/Forecast outdoor air is drier than current qualified indoor air/)).toBeNull();
  expect(screen.getByText(/Indoor evidence expired/)).toBeTruthy();expect(screen.getByText('Dew point: 41.0°F')).toBeTruthy();
});

});
