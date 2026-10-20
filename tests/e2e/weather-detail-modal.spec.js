import { expect, test } from './fixture-test.js';
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
        hours: Array.from({ length: 12 }, (_, index) => {
          const hour = index + 7;
          return ({
            at: `${date}T${String(hour).padStart(2, '0')}:00:00-06:00`,
            tempF: 50 + hour + dayIndex,
            precipPct: (hour * 5) % 100,
            radiationWm2: hour >= 6 && hour <= 19 ? (hour - 5) * 65 : 0,
            windMph: 4 + (hour % 9),
            weatherCode: (hour + dayIndex) % 4,
          });
        }),
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

async function openFixture(page, route, target, detail = null) {
  const consoleErrors = [];
  const pageErrors = [];
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    // The common fixture deliberately returns 503 for these optional reports.
    // Keep unexpected asset failures and JavaScript console errors observable.
    const pathname = new URL(message.location().url || '/', baseURL).pathname;
    const unavailableReport = ['/api/daily-pv-potential', '/api/household-energy-observation'].includes(pathname);
    if (unavailableReport && message.text() === 'Failed to load resource: the server responded with a status of 503 (Service Unavailable)') return;
    consoleErrors.push({ message: message.text(), url: message.location().url });
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
    json: detail ? ITEMS.map(item => item.name === 'Forecast_10Day_JSON' ? {...item,state:detail} : item) : ITEMS,
  }));
  await page.route('**/fixture-openhab/rest/things', route => route.fulfill({ json: [] }));
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
    test(`${route} opens bounded twelve-hour weather detail at ${target.name}`, async ({ page }) => {
      await page.clock.install({ time: new Date('2026-07-18T13:00:00-06:00') });
      const errors = await openFixture(page, route, target);
      const buttons = page.locator('[data-forecast-day]');
      await expect(buttons).toHaveCount(10);
      const opener = buttons.nth(1);
      await opener.click();

      const dialog = page.getByRole('dialog', { name: /forecast/i });
      await expect(dialog).toBeVisible();
      await expect(dialog.locator('[data-testid="weather-detail-hour"]')).toHaveCount(12);
      expect(await dialog.locator('[data-testid="weather-detail-hour"] .hour-time').allTextContents()).toEqual([
        '7 AM', '8 AM', '9 AM', '10 AM', '11 AM', '12 PM',
        '1 PM', '2 PM', '3 PM', '4 PM', '5 PM', '6 PM',
      ]);
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

for (const target of TARGETS) {
  for (const route of ['home', 'weather']) {
    test(`${route} summarizes predominant daily sky instead of any daily rain at ${target.name}`, async ({page}) => {
      await page.clock.install({time:new Date('2026-07-18T13:00:00-06:00')});
      const mutations=[];page.on('request',request=>{if(!['GET','HEAD'].includes(request.method()))mutations.push(request.url());});
      const detail=JSON.parse(forecastDetail());
      for(const [index,day] of detail.days.entries()) {
        day.summary={...day.summary,weatherCode:null,cloudPct:90,precipPct:null,precipSumIn:0.12};
        day.hours=Array.from({length:24},(_,h)=>({at:`${day.date}T${String(h).padStart(2,'0')}:00:00-06:00`,isDay:h>=8&&h<18,tempF:65,precipPct:null,precipIn:0,radiationWm2:300,windMph:3,weatherCode:null,cloudPct:100}));
        for(let h=8;h<18;h++) {
          day.hours[h].cloudPct=index===1?(h<14?5:95):index===2?45:95;
          if(index===1&&h===16)day.hours[h].precipIn=0.05;
          if(index===2&&h>=15)day.hours[h].precipIn=0.4/25.4;
          if(index===3&&h<14)day.hours[h].precipIn=0.3/25.4;
        }
      }
      const errors=await openFixture(page,route,target,JSON.stringify(detail));
      const days=page.locator('[data-forecast-day]');await expect(days).toHaveCount(10);
      await expect(days.nth(1).locator('.day-icon')).toHaveAttribute('title',/^Mostly sunny/);
      await expect(days.nth(2).locator('.day-icon')).toHaveAttribute('title',/^Partly cloudy/);
      await expect(days.nth(3).locator('.day-icon')).toHaveAttribute('title',/^Precipitation through most daylight/);
      for(const index of [1,2,3]) {await expect(days.nth(index).locator('.day-icon svg')).toBeVisible();await expect(days.nth(index)).toContainText('0.12″');}
      await days.nth(2).click();
      const dialog=page.getByRole('dialog',{name:/forecast/i});await expect(dialog).toBeVisible();
      await expect(dialog.locator('.weather-detail-summary')).toContainText('Partly cloudy');
      await page.keyboard.press('Escape');await expect(dialog).toBeHidden();
      expect(errors.pageErrors).toEqual([]);expect(errors.consoleErrors).toEqual([]);expect(mutations).toEqual([]);
      expect(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+2&&document.documentElement.scrollWidth<=innerWidth+2)).toBe(true);
    });
  }
}
