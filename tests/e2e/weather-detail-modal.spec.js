import { expect, test } from '@playwright/test';
import { createServer } from 'vite';

const TARGETS = [
  { name: 'm9-1340x800', width: 1340, height: 800 },
  { name: 'laptop-1280x720', width: 1280, height: 720 },
];

function forecastDetail() {
  return JSON.stringify({
    version: 1,
    generatedAt: '2026-07-18T12:00:00-06:00',
    timezone: 'America/Denver',
    days: Array.from({ length: 10 }, (_, dayIndex) => {
      const date = `2026-07-${String(18 + dayIndex).padStart(2, '0')}`;
      return {
        date,
        label: dayIndex === 0 ? 'Today' : `Day ${dayIndex + 1}`,
        summary: {
          highF: 78 + dayIndex,
          lowF: 48 + dayIndex,
          precipPct: dayIndex * 7,
          weatherCode: dayIndex % 4,
          pvKwh: 5.2 + dayIndex / 2,
        },
        hours: Array.from({ length: 24 }, (_, hour) => ({
          at: `${date}T${String(hour).padStart(2, '0')}:00:00-06:00`,
          tempF: 50 + hour + dayIndex,
          precipPct: (hour * 5) % 100,
          radiationWm2: hour >= 6 && hour <= 19 ? (hour - 5) * 65 : 0,
          windMph: 4 + (hour % 9),
          weatherCode: (hour + dayIndex) % 4,
        })),
      };
    }),
  });
}

const STATES = {
  AmbientWeatherWS2902A_ApparentTemperature: '67.1',
  AmbientWeatherWS2902A_IndoorSensor_RelativeHumidity: '33',
  AmbientWeatherWS2902A_IndoorSensor_Temperature: '69.1',
  AmbientWeatherWS2902A_PressureTrend: 'Steady',
  AmbientWeatherWS2902A_RainFallDay: '0.12',
  AmbientWeatherWS2902A_RainFallHourlyRate: '0',
  AmbientWeatherWS2902A_RainFallWeek: '1.72',
  AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative: '30.12',
  AmbientWeatherWS2902A_WeatherDataWs2902a_RelativeHumidity: '31',
  AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature: '68.2',
  AmbientWeatherWS2902A_UVIndex: '2',
  AmbientWeatherWS2902A_WH31E_193_Temperature: '66.8',
  AmbientWeatherWS2902A_WindDirection: '180',
  AmbientWeatherWS2902A_WindGust: '27',
  AmbientWeatherWS2902A_WindSpeed: '12',
  BMS_SOC: '62',
  ConextGateway_ACPowerValue: '576',
  Current_US_AQI: '42',
  DCData_Current: '-4.2',
  DCData_Voltage: '52',
  Forecast_10Day_JSON: forecastDetail(),
  Forecast_AQI: 'REFRESH',
  Forecast_Daily_JSON: JSON.stringify(Array.from({ length: 7 }, (_, index) => ({
    d: index === 0 ? 'Today' : `Day ${index + 1}`,
    hi: 72 + index,
    lo: 42 + index,
    p: index * 8,
    pv: 4.5 + index,
    w: 1,
  }))),
  Forecast_Hourly_JSON: JSON.stringify(Array.from({ length: 14 }, (_, index) => ({
    h: `${index + 8}:00`,
    t: 62 + index,
    p: index * 3,
    r: index * 20,
    w: 1,
  }))),
  MPPT60_EnergyFromPV_Today: '5.2',
  MPPT60_PV_Power: '410',
  SkyConditionIcon: 'iconify:bi:sun-fill',
};

const ITEMS = Object.entries(STATES).map(([name, state]) => ({
  name,
  state,
  type: 'String',
}));

let server;
let baseURL;

test.beforeAll(async () => {
  server = await createServer({
    root: process.cwd(),
    logLevel: 'error',
    server: { port: 0, strictPort: false },
  });
  await server.listen();
  baseURL = server.resolvedUrls.local[0];
});

test.afterAll(async () => {
  await server?.close();
});

async function openFixture(page, route, target) {
  const consoleErrors = [];
  const pageErrors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await page.setViewportSize({ width: target.width, height: target.height });
  await page.addInitScript(() => {
    class FixtureEventSource {
      constructor() {
        setTimeout(() => this.onopen?.({ type: 'open' }), 0);
      }
      close() {}
    }
    Object.defineProperty(window, 'EventSource', {
      configurable: true,
      writable: true,
      value: FixtureEventSource,
    });
  });
  await page.route('**/config.json', (request) => request.fulfill({
    json: {
      openhabUrl: '/fixture-openhab',
      apiToken: 'fixture-only',
      staleBannerSeconds: 90,
    },
  }));
  await page.route('**/fixture-openhab/rest/items?*', (request) => request.fulfill({
    json: ITEMS,
  }));
  await page.route('**/fixture-openhab/rest/persistence/items/**', (request) => {
    const now = Date.now();
    return request.fulfill({
      json: {
        data: Array.from({ length: 24 }, (_, index) => ({
          time: now - (23 - index) * 15 * 60_000,
          state: String(50 + index / 2),
        })),
      },
    });
  });

  await page.goto(`${baseURL}#/${route}`, { waitUntil: 'domcontentloaded' });
  await page.locator(`.${route}-grid`).waitFor();
  return { consoleErrors, pageErrors };
}

for (const target of TARGETS) {
  for (const route of ['home', 'weather']) {
    test(`${route} opens bounded ten-hour weather detail at ${target.name}`, async ({ page }) => {
      const errors = await openFixture(page, route, target);
      const buttons = page.locator('[data-forecast-day]');
      await expect(buttons).toHaveCount(10);
      const opener = buttons.nth(1);
      await opener.click();

      const dialog = page.getByRole('dialog', { name: /forecast/i });
      await expect(dialog).toBeVisible();
      await expect(dialog.locator('[data-testid="weather-detail-hour"]')).toHaveCount(10);
      await expect(dialog.locator('.weather-detail-chart svg')).toBeVisible();

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
      expect(errors.consoleErrors).toEqual([]);
      expect(errors.pageErrors).toEqual([]);
    });
  }
}
