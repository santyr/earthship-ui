// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `${process.cwd()}/node_modules/svelte/src/index-client.js`
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

import WeatherDetailModal from '../../src/lib/ui/WeatherDetailModal.svelte';
import { items } from '../../src/lib/openhab/store.js';
import {
  closeWeatherDetail,
  openWeatherDetail,
} from '../../src/lib/weather/detailStore.js';
import { currentRoute } from '../../src/routes.js';

function payload({ count = 10, stale = false, precipSumIn, hourPrecipIn } = {}) {
  return JSON.stringify({
    version: 1,
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
        at: `2026-07-19T${String(index + 8).padStart(2, '0')}:00:00-06:00`,
        tempF: 60 + index,
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
    items.set({ Forecast_10Day_JSON: payload() });
    mocks.init.mockClear();
    mocks.chart.setOption.mockClear();
    mocks.chart.resize.mockClear();
    mocks.chart.dispose.mockClear();
    document.body.style.overflow = '';
  });

  afterEach(() => {
    closeWeatherDetail();
    currentRoute.set('home');
    items.set({});
    cleanup();
    document.body.innerHTML = '';
    document.body.style.overflow = '';
  });

  it('renders a complete ten-hour icon/value strip and SVG chart', async () => {
    addOpener();
    render(WeatherDetailModal);
    await openTomorrow();

    expect(screen.getAllByTestId('weather-detail-hour')).toHaveLength(10);
    expect(screen.getByText('60°')).toBeTruthy();
    expect(screen.getByText('0 W/m²')).toBeTruthy();
    await waitFor(() => expect(mocks.init).toHaveBeenCalledWith(
      expect.any(HTMLElement),
      null,
      { renderer: 'svg' },
    ));
    expect(mocks.chart.setOption).toHaveBeenCalled();
  });

  it('announces stale and partial forecast coverage', async () => {
    items.set({ Forecast_10Day_JSON: payload({ count: 7, stale: true }) });
    addOpener();
    render(WeatherDetailModal);
    await openTomorrow();

    expect(screen.getByRole('status').textContent).toContain('Forecast data may be stale');
    expect(screen.getByRole('status').textContent).toContain('7 of 10 hours available');
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
    await fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
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
  // so selectForecastWindow always resolves 'daytime' mode (all 10 hours from
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
});
