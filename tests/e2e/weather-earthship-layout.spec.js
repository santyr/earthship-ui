import { expect, test } from '@playwright/test';
import { createServer } from 'vite';

const TARGETS = [
  { name: 'm9-1340x800', width: 1340, height: 800 },
  { name: 'laptop-1280x720', width: 1280, height: 720 },
];

const ITEMS = [
  { name: 'Current_US_AQI', state: 'NULL', type: 'Number' },
  { name: 'Forecast_AQI', state: 'REFRESH', type: 'String' },
  {
    name: 'Forecast_Hourly_JSON',
    state: JSON.stringify(Array.from({ length: 14 }, (_, index) => ({
      h: `${index + 8}:00`,
      t: 62 + index,
      p: index * 3,
      r: index * 20,
      w: 1,
    }))),
    type: 'String',
  },
  {
    name: 'Forecast_Daily_JSON',
    state: JSON.stringify(Array.from({ length: 7 }, (_, index) => ({
      d: index === 0 ? 'Today' : `Day ${index + 1}`,
      hi: 72 + index,
      lo: 42 + index,
      p: index * 8,
      pv: 4.5 + index,
      w: 1,
    }))),
    type: 'String',
  },
  { name: 'SkyConditionIcon', state: 'sunny', type: 'String' },
  { name: 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', state: '68.2', type: 'Number' },
  { name: 'AmbientWeatherWS2902A_ApparentTemperature', state: '67.1', type: 'Number' },
  { name: 'OutdoorTemp_24h_High', state: '74', type: 'Number' },
  { name: 'OutdoorTemp_24h_Low', state: '41', type: 'Number' },
  { name: 'AmbientWeatherWS2902A_WeatherDataWs2902a_RelativeHumidity', state: '31', type: 'Number' },
  { name: 'AmbientWeatherWS2902A_WindSpeed', state: '12', type: 'Number' },
  { name: 'AmbientWeatherWS2902A_WindGust', state: '27', type: 'Number' },
  { name: 'AmbientWeatherWS2902A_RainFallDay', state: '0.12', type: 'Number' },
  { name: 'AmbientWeatherWS2902A_RainFallEvent', state: '0.18', type: 'Number' },
  { name: 'AmbientWeatherWS2902A_RainFallWeek', state: '1.72', type: 'Number' },
  { name: 'AmbientWeatherWS2902A_RainFallMonth', state: '3.41', type: 'Number' },
  { name: 'AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative', state: '30.12', type: 'Number' },
  { name: 'AmbientWeatherWS2902A_PressureTrend', state: 'Steady', type: 'String' },
  { name: 'Shelly_HT1_Indoor_Temperature', state: '71.5', type: 'Number' },
  { name: 'AmbientWeatherWS2902A_IndoorSensor_Temperature', state: '69.1', type: 'Number' },
  { name: 'AmbientWeatherWS2902A_WH31E_193_Temperature', state: '66.8', type: 'Number' },
  { name: 'Shelly_HT1_Atmospheric_Humidity', state: '28', type: 'Number' },
  { name: 'AmbientWeatherWS2902A_IndoorSensor_RelativeHumidity', state: '33', type: 'Number' },
  { name: 'AmbientWeatherWS2902A_WH31E_193_RelativeHumidity', state: '38', type: 'Number' },
  { name: 'OutdoorTemp_24h_High', state: '74', type: 'Number' },
  { name: 'OutdoorTemp_24h_Low', state: '41', type: 'Number' },
  { name: 'IndoorTemp_24h_High', state: '71', type: 'Number' },
  { name: 'IndoorTemp_24h_Low', state: '68', type: 'Number' },
  { name: 'Thermal_Advisory', state: 'vent|Open south windows before the afternoon peak', type: 'String' },
  { name: 'Forecast_Tomorrow_High', state: '76', type: 'Number' },
  { name: 'Forecast_Tomorrow_Low', state: '45', type: 'Number' },
  { name: 'SouthOutlet_Outlet2_Switch', state: 'OFF', type: 'Switch' },
  {
    name: 'SouthOutlet_AutoStatus',
    state: 'reason=soil moisture recovery cycle delayed,fallbackInMin=127',
    type: 'String',
  },
  { name: 'SouthOutlet_LastAutoRun', state: '2026-07-18T12:00:00Z', type: 'DateTime' },
];

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
  await page.setViewportSize({ width: target.width, height: target.height });
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
  await page.route('**/fixture-openhab/rest/events?*', (request) => request.fulfill({
    status: 200,
    contentType: 'text/event-stream',
    body: '',
  }));

  await page.goto(`${baseURL}#/${route}`, { waitUntil: 'domcontentloaded' });
  await page.locator(`.${route}-grid`).waitFor();
}

async function expectRouteBounded(page, route) {
  const result = await page.evaluate((routeName) => {
    const grid = document.querySelector(`.${routeName}-grid`);
    const screen = document.querySelector('main.screen');
    const bounds = (element) => {
      const rect = element.getBoundingClientRect();
      return {
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
      };
    };
    return {
      document: {
        clientWidth: document.documentElement.clientWidth,
        clientHeight: document.documentElement.clientHeight,
        scrollWidth: document.documentElement.scrollWidth,
        scrollHeight: document.documentElement.scrollHeight,
      },
      screen: {
        ...bounds(screen),
        clientWidth: screen.clientWidth,
        clientHeight: screen.clientHeight,
        scrollWidth: screen.scrollWidth,
        scrollHeight: screen.scrollHeight,
      },
      grid: {
        ...bounds(grid),
        clientWidth: grid.clientWidth,
        clientHeight: grid.clientHeight,
        scrollWidth: grid.scrollWidth,
        scrollHeight: grid.scrollHeight,
        overflowX: getComputedStyle(grid).overflowX,
        overflowY: getComputedStyle(grid).overflowY,
      },
      cells: [...grid.querySelectorAll(':scope > .cell')].map((cell) => ({
        classes: cell.className,
        ...bounds(cell),
        clientWidth: cell.clientWidth,
        clientHeight: cell.clientHeight,
        scrollWidth: cell.scrollWidth,
        scrollHeight: cell.scrollHeight,
      })),
    };
  }, route);

  expect(result.document.scrollWidth).toBeLessThanOrEqual(result.document.clientWidth);
  expect(result.document.scrollHeight).toBeLessThanOrEqual(result.document.clientHeight);
  expect(result.screen.scrollWidth).toBeLessThanOrEqual(result.screen.clientWidth);
  expect(result.screen.scrollHeight).toBeLessThanOrEqual(result.screen.clientHeight);
  expect(result.grid.overflowX).toBe('hidden');
  expect(result.grid.overflowY).toBe('hidden');
  expect(result.grid.scrollWidth).toBeLessThanOrEqual(result.grid.clientWidth);
  expect(result.grid.scrollHeight).toBeLessThanOrEqual(result.grid.clientHeight);

  for (const cell of result.cells) {
    expect(cell.left).toBeGreaterThanOrEqual(result.grid.left - 0.5);
    expect(cell.top).toBeGreaterThanOrEqual(result.grid.top - 0.5);
    expect(cell.right).toBeLessThanOrEqual(result.grid.right + 0.5);
    expect(cell.bottom).toBeLessThanOrEqual(result.grid.bottom + 0.5);
    expect(cell.scrollWidth, cell.classes).toBeLessThanOrEqual(cell.clientWidth);
    expect(cell.scrollHeight, cell.classes).toBeLessThanOrEqual(cell.clientHeight);
  }
}

for (const target of TARGETS) {
  test(`Weather is fully bounded at ${target.name}`, async ({ page }, testInfo) => {
    await openFixture(page, 'weather', target);
    await expect(page.getByText('Modeled US AQI')).toBeVisible();
    await expect(page.getByText('Unavailable')).toBeVisible();
    await expectRouteBounded(page, 'weather');
    await expect(page.locator('.hs-chart svg, .hs-chart canvas')).toBeVisible();

    const hourlyBounds = await page.evaluate(() => {
      const bounds = (element) => {
        const rect = element.getBoundingClientRect();
        return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height };
      };
      const chart = document.querySelector('.hs-chart');
      const rendered = chart.querySelector('svg');
      const visibleCount = (selector) => [...rendered.querySelectorAll(selector)].filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      }).length;
      return {
        cell: bounds(document.querySelector('.hourly-cell')),
        chart: bounds(chart),
        rendered: bounds(rendered),
        inlineFallbackHeight: Number.parseFloat(chart.style.height),
        iconColumns: document.querySelectorAll('.hs-icons .hs-icon-col').length,
        visibleLabels: visibleCount('text'),
        visiblePaths: visibleCount('path'),
      };
    });
    expect(hourlyBounds.inlineFallbackHeight).toBeGreaterThan(0);
    expect(hourlyBounds.iconColumns).toBe(14);
    expect(hourlyBounds.visibleLabels).toBeGreaterThanOrEqual(14);
    expect(hourlyBounds.visiblePaths).toBeGreaterThanOrEqual(14);
    expect(hourlyBounds.chart.height).toBeGreaterThan(64);
    expect(hourlyBounds.rendered.width).toBeGreaterThan(100);
    expect(hourlyBounds.rendered.height).toBeGreaterThan(64);
    expect(hourlyBounds.chart.left).toBeGreaterThanOrEqual(hourlyBounds.cell.left);
    expect(hourlyBounds.chart.top).toBeGreaterThanOrEqual(hourlyBounds.cell.top);
    expect(hourlyBounds.chart.right).toBeLessThanOrEqual(hourlyBounds.cell.right);
    expect(hourlyBounds.chart.bottom).toBeLessThanOrEqual(hourlyBounds.cell.bottom);

    const currentBounds = await page.evaluate(() => {
      const cell = document.querySelector('.current-cell').getBoundingClientRect();
      const content = document.querySelector('.cur-main').getBoundingClientRect();
      return { cellBottom: cell.bottom, contentBottom: content.bottom };
    });
    expect(currentBounds.contentBottom).toBeLessThanOrEqual(currentBounds.cellBottom);
    await page.screenshot({ path: testInfo.outputPath('weather.png') });
  });

  test(`Earthship is bounded and ordered north-to-south at ${target.name}`, async ({ page }, testInfo) => {
    await openFixture(page, 'earthship', target);
    await expectRouteBounded(page, 'earthship');
    await expect(page.locator('.loop-svg .zone-label')).toHaveText([
      'North Mass',
      'Room Air',
      'South Wall',
      'Outdoor',
    ]);
    await expect(page.locator('.loop-svg .zone-temp')).toHaveText([
      '67°',
      '69°',
      '72°',
      '68°',
    ]);
    const loopBounds = await page.evaluate(() => {
      const bounds = (element) => {
        const rect = element.getBoundingClientRect();
        return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom };
      };
      return {
        cell: bounds(document.querySelector('.loop-cell')),
        svg: bounds(document.querySelector('.loop-svg')),
        zones: [...document.querySelectorAll('.loop-svg .zone-group')].map(bounds),
      };
    });
    expect(loopBounds.svg.left).toBeGreaterThanOrEqual(loopBounds.cell.left);
    expect(loopBounds.svg.top).toBeGreaterThanOrEqual(loopBounds.cell.top);
    expect(loopBounds.svg.right).toBeLessThanOrEqual(loopBounds.cell.right);
    expect(loopBounds.svg.bottom).toBeLessThanOrEqual(loopBounds.cell.bottom);
    for (const zone of loopBounds.zones) {
      expect(zone.left).toBeGreaterThanOrEqual(loopBounds.svg.left);
      expect(zone.top).toBeGreaterThanOrEqual(loopBounds.svg.top);
      expect(zone.right).toBeLessThanOrEqual(loopBounds.svg.right);
      expect(zone.bottom).toBeLessThanOrEqual(loopBounds.svg.bottom);
    }
    await expect(page.locator('.humidity-label')).toHaveText([
      'North Mass',
      'Room Air',
      'South Wall',
    ]);
    await page.screenshot({ path: testInfo.outputPath('earthship.png') });
  });
}
