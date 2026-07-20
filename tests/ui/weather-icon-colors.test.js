// @vitest-environment jsdom
//
// Task 2: verify condition colors (Task 1's wmoColor/skyIconColor) are
// actually threaded through OhIcon's `color` prop at each render site.
//
// @iconify/svelte/offline copies the `color` prop into the rendered <svg>'s
// `style` attribute (`style="color: <value>;"`), not a `color` attribute —
// confirmed by probing OhIcon's rendered output directly. jsdom normalizes
// both the hex value (to `rgb(r, g, b)`) and the `currentColor` fallback (to
// lowercase `currentcolor`) when read back via `svg.style.color`, so
// assertions compare against that normalized form rather than raw hex.
import { cleanup, render, screen } from '@testing-library/svelte';
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

import DailyForecast from '../../src/lib/ui/DailyForecast.svelte';
import HourlyStrip from '../../src/lib/ui/HourlyStrip.svelte';
import WeatherDetailModal from '../../src/lib/ui/WeatherDetailModal.svelte';
import { CONDITION_COLORS } from '../../src/lib/ui/wmo.js';
import { items } from '../../src/lib/openhab/store.js';
import {
  closeWeatherDetail,
  openWeatherDetail,
} from '../../src/lib/weather/detailStore.js';
import { currentRoute } from '../../src/routes.js';

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
}

const POURING_RGB = hexToRgb(CONDITION_COLORS.pouring);

const day = {
  date: '2026-07-19',
  label: 'Sat',
  summary: { weatherCode: 61, highF: 86, lowF: 59, precipPct: 60, pvKwh: 2 },
  hours: [],
};

// 44 falls in the documented "unknown" gap between the cloudy (max 3) and
// fog (min 45) bands — wmoColor(44) is asserted null by wmo-colors.test.js.
const unmappedDay = {
  date: '2026-07-20',
  label: 'Sun',
  summary: { weatherCode: 44, highF: 80, lowF: 55, precipPct: 10, pvKwh: 3 },
  hours: [],
};

afterEach(cleanup);

describe('condition icon colors', () => {
  it('DailyForecast colors day icons by condition', () => {
    const { container } = render(DailyForecast, { days: [day], variant: 'home' });
    const svg = container.querySelector('.day-icon svg');
    expect(svg?.style.color).toBe(POURING_RGB);
  });

  it('DailyForecast falls back to currentColor for an unmapped code', () => {
    const { container } = render(DailyForecast, { days: [unmappedDay], variant: 'home' });
    const svg = container.querySelector('.day-icon svg');
    expect(svg?.style.color).toBe('currentcolor');
  });

  it('HourlyStrip colors hour icons by condition', () => {
    const { container } = render(HourlyStrip, {
      hours: [{ h: '2p', t: 70, p: 10, r: 100, w: 61 }],
    });
    const svg = container.querySelector('.hs-icon-col svg');
    expect(svg?.style.color).toBe(POURING_RGB);
  });

  it('HourlyStrip falls back to currentColor for an unmapped code', () => {
    const { container } = render(HourlyStrip, {
      hours: [{ h: '2p', t: 70, p: 10, r: 100, w: 44 }],
    });
    const svg = container.querySelector('.hs-icon-col svg');
    expect(svg?.style.color).toBe('currentcolor');
  });

  describe('WeatherDetailModal', () => {
    // Deliberately NOT "today" (real system clock): selecting today's date
    // routes selectForecastWindow into its 'rolling' mode, which filters
    // hours by the real current time-of-day and would make this test flaky
    // depending on when it runs (WeatherDetailModal.test.js already
    // exhibits this pre-existing issue, out of scope for this task). A
    // future date takes the 'daytime' branch (hour-of-day 8-17 only),
    // which is stable regardless of wall-clock time.
    const SELECTED_DATE = '2026-07-20';

    function payload({ weatherCode = 61 } = {}) {
      return JSON.stringify({
        version: 1,
        generatedAt: new Date().toISOString(),
        timezone: 'America/Denver',
        days: [{
          date: SELECTED_DATE,
          label: 'Tomorrow',
          summary: { highF: 86, lowF: 59, precipPct: 60, weatherCode, pvKwh: 2 },
          hours: [{
            at: `${SELECTED_DATE}T08:00:00-06:00`,
            tempF: 70,
            precipPct: 60,
            radiationWm2: 100,
            windMph: 5,
            weatherCode,
          }],
        }],
      });
    }

    function addOpener() {
      const opener = document.createElement('button');
      opener.textContent = 'Open forecast';
      document.body.append(opener);
      opener.focus();
      return opener;
    }

    async function openTomorrow() {
      openWeatherDetail({ date: SELECTED_DATE, label: 'Tomorrow' });
      return screen.findByRole('dialog', { name: /Tomorrow forecast/i });
    }

    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2026-07-19T12:00:00-06:00'));
      global.ResizeObserver = class {
        observe() {}
        disconnect() {}
      };
      currentRoute.set('home');
      mocks.init.mockClear();
      mocks.chart.setOption.mockClear();
    });

    afterEach(() => {
      closeWeatherDetail();
      currentRoute.set('home');
      items.set({});
      document.body.innerHTML = '';
      document.body.style.overflow = '';
      vi.useRealTimers();
    });

    it('colors the selected-day summary icon and an hourly icon by condition', async () => {
      items.set({ Forecast_10Day_JSON: payload({ weatherCode: 61 }) });
      addOpener();
      const { container } = render(WeatherDetailModal);
      await openTomorrow();

      const summarySvg = container.querySelector('.weather-detail-summary svg');
      expect(summarySvg?.style.color).toBe(POURING_RGB);

      const hourSvg = container.querySelector('.weather-detail-hour svg');
      expect(hourSvg?.style.color).toBe(POURING_RGB);
    });

    it('falls back to currentColor for an unmapped weather code', async () => {
      items.set({ Forecast_10Day_JSON: payload({ weatherCode: 44 }) });
      addOpener();
      const { container } = render(WeatherDetailModal);
      await openTomorrow();

      const summarySvg = container.querySelector('.weather-detail-summary svg');
      expect(summarySvg?.style.color).toBe('currentcolor');

      const hourSvg = container.querySelector('.weather-detail-hour svg');
      expect(hourSvg?.style.color).toBe('currentcolor');
    });
  });
});
