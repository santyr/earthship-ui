import { expect, test } from '@playwright/test';
import { createServer } from 'vite';

const TARGETS = [
  { name: 'm9-1340x800', width: 1340, height: 800 },
  { name: 'laptop-1280x720', width: 1280, height: 720 },
];

const BASE_STATES = {
  AmbientWeatherWS2902A_ApparentTemperature: '71.8',
  AmbientWeatherWS2902A_UVIndex: '0',
  AmbientWeatherWS2902A_IndoorSensor_RelativeHumidity: '35',
  AmbientWeatherWS2902A_IndoorSensor_Temperature: '70.2',
  AmbientWeatherWS2902A_PressureTrend: 'steady',
  AmbientWeatherWS2902A_RainFallDay: '9.99',
  AmbientWeatherWS2902A_RainFallEvent: '0.42',
  AmbientWeatherWS2902A_RainFallHourlyRate: '0',
  AmbientWeatherWS2902A_RainFallMonth: '4.90',
  AmbientWeatherWS2902A_RainFallWeek: '1.72',
  AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative: '30.12',
  AmbientWeatherWS2902A_WeatherDataWs2902a_RelativeHumidity: '37',
  AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature: '73.4',
  AmbientWeatherWS2902A_WindDirection: '0',
  AmbientWeatherWS2902A_WindGust: '18',
  AmbientWeatherWS2902A_WindSpeed: '11',
  BatteryChargingStatus: 'OFF',
  BatteryIcon: 'iconify:mdi:battery-60',
  BMS_Comms_Status: 'OK',
  BMS_DevicePresent: '1',
  BMS_SOC: '62',
  BMS_TimeToDischarge_Smoothed: '640',
  BMS_TimeToFull_Smoothed: '1040',
  BTC_Price_24h_PercentChange: '-1.25',
  BTC_USD_Price: '118532',
  ConextGateway_ACPowerValue: '576',
  Current_US_AQI: '42',
  DCData_Current: '-4.2',
  DCData_Native_Power: '150',
  DCData_Voltage: '52',
  Forecast_AQI: '501',
  Forecast_Daily_JSON: JSON.stringify(Array.from({ length: 7 }, (_, index) => ({
    d: index === 0 ? 'Today' : `Day ${index + 1}`,
    hi: 79 + index,
    lo: 49 + index,
    pv: 5.2 + index / 2,
    w: index % 3,
  }))),
  GoatFeedingsToday: '2',
  Goat_Plugs_Outlet2_Switch: 'ON',
  IndoorTemp_24h_High: '72',
  IndoorTemp_24h_Low: '67',
  MoonPhaseicon: 'iconify:mdi:moon-waxing-crescent',
  Moon_MoonPhaseName: 'Waxing crescent',
  MPPT60_EnergyFromPV_Today: '5.2',
  MPPT60_PV_Power: '410',
  OutdoorTemp_24h_High: '79',
  OutdoorTemp_24h_Low: '51',
  Predicted_Curtailment_Hours: '0',
  Predicted_PV_Today_kWh: '7.1',
  Predicted_SoC_Trough_Tomorrow: '58',
  SkyConditionIcon: 'iconify:bi:sun-fill',
  SouthOutlet_LastAutoRun: '2026-07-18T12:00:00Z',
  SouthOutlet_Outlet2_Switch: 'OFF',
  SunPhaseIcon: 'iconify:mdi:white-balance-sunny',
  Sun_Rise_Start: '2026-07-18T05:58:00-06:00',
  Sun_Set_End: '2026-07-18T20:18:00-06:00',
  Thermal_Advisory: 'none',
};

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

function itemSnapshot(overrides = {}) {
  return Object.entries({ ...BASE_STATES, ...overrides }).map(([name, state]) => ({
    name,
    state,
    type: 'String',
  }));
}

async function openHomeFixture(page, target, { states = {}, staleSeconds = 90 } = {}) {
  let activeStates = { ...states };
  const historyRequests = [];
  const unexpectedExternalRequests = [];
  const pageErrors = [];

  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) unexpectedExternalRequests.push(request.url());
  });

  await page.setViewportSize({ width: target.width, height: target.height });
  await page.addInitScript(() => {
    class FixtureEventSource {
      constructor() {
        window.__fixtureEventSources ??= [];
        window.__fixtureEventSources.push(this);
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
  await page.route('**/config.json', (route) => route.fulfill({
    json: {
      openhabUrl: '/fixture-openhab',
      apiToken: 'fixture-only',
      staleBannerSeconds: staleSeconds,
    },
  }));
  await page.route('**/fixture-openhab/rest/items?*', (route) => route.fulfill({
    json: itemSnapshot(activeStates),
  }));
  await page.route('**/fixture-openhab/rest/persistence/items/**', (route) => {
    const url = new URL(route.request().url());
    const name = decodeURIComponent(url.pathname.split('/').at(-1));
    historyRequests.push(name);
    const now = Date.now();
    return route.fulfill({
      json: {
        data: Array.from({ length: 24 }, (_, index) => ({
          time: now - (23 - index) * 15 * 60_000,
          state: String(50 + index / 2),
        })),
      },
    });
  });

  await page.goto(`${baseURL}#/home`, { waitUntil: 'domcontentloaded' });
  await page.locator('.home-grid').waitFor();
  await page.locator('.outdoor-spark svg').waitFor({ timeout: 20_000 });
  return {
    historyRequests,
    pageErrors,
    unexpectedExternalRequests,
    setStates: (overrides) => { activeStates = { ...activeStates, ...overrides }; },
    emitState: async (name, value) => {
      activeStates = { ...activeStates, [name]: value };
      await page.evaluate(({ itemName, itemValue }) => {
        const source = window.__fixtureEventSources?.at(-1);
        if (!source) throw new Error('Fixture EventSource is unavailable');
        source.onmessage?.({
          data: JSON.stringify({
            topic: `openhab/items/${itemName}/statechanged`,
            payload: JSON.stringify({ value: itemValue }),
            type: 'ItemStateChangedEvent',
          }),
        });
      }, { itemName: name, itemValue: value });
    },
  };
}

async function homeGeometry(page) {
  return page.evaluate(() => {
    const box = (element) => {
      const rect = element.getBoundingClientRect();
      return {
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        width: rect.width,
        height: rect.height,
      };
    };
    const extent = (element) => ({
      ...box(element),
      clientWidth: element.clientWidth,
      clientHeight: element.clientHeight,
      scrollWidth: element.scrollWidth,
      scrollHeight: element.scrollHeight,
    });
    const grid = document.querySelector('.home-grid');
    const screen = document.querySelector('main.screen');
    const shell = document.querySelector('[data-bounded-shell]');
    const outdoorSvg = document.querySelector('.outdoor-spark svg');
    const compass = document.querySelector('.compass-square');
    const windMeta = document.querySelector('.wind-meta');
    const rainValue = document.querySelector('.rain-cell .value');
    const rainFooter = document.querySelector('.rain-cell .footer');
    const indoor = document.querySelector('.indoor-temp');
    const indoorMeta = document.querySelector('.indoor-meta');
    const northCardinal = [...document.querySelectorAll('.dir-label')].find((label) => label.textContent === 'N');
    const windNeedle = document.querySelector('.compass-needle');
    const sunMoon = document.querySelector('.sm-row');
    const powerFlowLine = document.querySelector('.pf-line1');
    const goatIcon = document.querySelector('.goat-feed-icon, .goat-activation-icon');
    const goatText = document.querySelector('.goat-feeding-text');
    return {
      document: {
        clientWidth: document.documentElement.clientWidth,
        clientHeight: document.documentElement.clientHeight,
        scrollWidth: document.documentElement.scrollWidth,
        scrollHeight: document.documentElement.scrollHeight,
      },
      body: {
        clientWidth: document.body.clientWidth,
        clientHeight: document.body.clientHeight,
        scrollWidth: document.body.scrollWidth,
        scrollHeight: document.body.scrollHeight,
      },
      shell: box(shell),
      screen: {
        ...box(screen),
        clientWidth: screen.clientWidth,
        clientHeight: screen.clientHeight,
        scrollWidth: screen.scrollWidth,
        scrollHeight: screen.scrollHeight,
      },
      grid: {
        ...box(grid),
        clientWidth: grid.clientWidth,
        clientHeight: grid.clientHeight,
        scrollWidth: grid.scrollWidth,
        scrollHeight: grid.scrollHeight,
      },
      cells: [...grid.querySelectorAll(':scope > .cell')].map((cell) => ({
        classes: cell.className,
        ...box(cell),
        clientWidth: cell.clientWidth,
        clientHeight: cell.clientHeight,
        scrollWidth: cell.scrollWidth,
        scrollHeight: cell.scrollHeight,
        tile: extent(cell.querySelector('.tile')),
        tileBody: extent(cell.querySelector('.tile-body')),
      })),
      outdoorSvg: box(outdoorSvg),
      outdoorHost: box(document.querySelector('.outdoor-spark')),
      outdoor: {
        icon: box(document.querySelector('.cond-icon')),
        temp: box(document.querySelector('.big-temp')),
        chips: box(document.querySelector('.outdoor-chips')),
        chipItems: [...document.querySelectorAll('.outdoor-chips > span')].map(box),
        sub: box(document.querySelector('.outdoor-sub')),
        hilo: box(document.querySelector('.outdoor-hilo')),
        spark: box(document.querySelector('.outdoor-spark')),
      },
      indoor: {
        icon: box(document.querySelector('.indoor-icon')),
        temp: box(document.querySelector('.indoor-temp')),
        meta: box(document.querySelector('.indoor-meta')),
        humidity: box(document.querySelector('.indoor-hum')),
        hilo: box(document.querySelector('.indoor-hilo')),
      },
      rain: {
        stat: box(document.querySelector('.rain-cell .stat')),
        icon: box(document.querySelector('.rain-cell .state-icon')),
        value: box(rainValue),
        footer: box(rainFooter),
        layout: {
          statDisplay: getComputedStyle(document.querySelector('.rain-cell .stat')).display,
          statAlign: getComputedStyle(document.querySelector('.rain-cell .stat')).alignItems,
          statDirection: getComputedStyle(document.querySelector('.rain-cell .stat')).flexDirection,
          iconDisplay: getComputedStyle(document.querySelector('.rain-cell .state-icon')).display,
          valueWhiteSpace: getComputedStyle(rainValue).whiteSpace,
        },
      },
      battery: {
        top: box(document.querySelector('.battery-top')),
        arc: box(document.querySelector('.battery-arc')),
        meta: box(document.querySelector('.battery-meta')),
        status: box(document.querySelector('.batt-status')),
        icon: box(document.querySelector('.batt-icon')),
        indicator: box(document.querySelector('.batt-indicator')),
        empty: box(document.querySelector('.batt-runtime-empty')),
        full: box(document.querySelector('.batt-runtime-full')),
        spark: box(document.querySelector('.battery-spark')),
      },
      baro: {
        head: box(document.querySelector('.baro-head')),
        icon: box(document.querySelector('.baro-status-icon')),
        value: box(document.querySelector('.baro-value')),
        spark: box(document.querySelector('.baro-spark')),
        trend: box(document.querySelector('.baro-trend')),
      },
      solar: {
        head: box(document.querySelector('.solar-head')),
        icon: box(document.querySelector('.solar-icon')),
        main: box(document.querySelector('.solar-main')),
        sub: box(document.querySelector('.solar-sub')),
        current: box(document.querySelector('.solar-current')),
        curtail: box(document.querySelector('.curtail-lamp')),
      },
      greywater: {
        icon: box(document.querySelector('.gw-icon')),
        text: box(document.querySelector('.gw-text')),
      },
      windNeedleCount: document.querySelectorAll('.compass-needle').length,
      powerFlow: {
        line: extent(powerFlowLine),
      },
      goat: {
        icon: box(goatIcon),
        text: box(goatText),
      },
      windHubCount: document.querySelectorAll('.compass-hub').length,
      windCardinalCount: document.querySelectorAll('.dir-label').length,
      windCardinals: [...document.querySelectorAll('.dir-label')].map((label) => ({ label: label.textContent, ...box(label) })),
      northCardinal: box(northCardinal),
      windNeedle: windNeedle ? box(windNeedle) : null,
      compass: box(compass),
      compassHost: box(document.querySelector('.compass-cap')),
      windMeta: box(windMeta),
      colors: {
        outdoor: getComputedStyle(document.querySelector('.big-temp')).color,
        indoor: getComputedStyle(indoor).color,
      },
      fonts: {
        outdoor: parseFloat(getComputedStyle(document.querySelector('.big-temp')).fontSize),
        indoor: parseFloat(getComputedStyle(indoor).fontSize),
        indoorHumidity: parseFloat(getComputedStyle(document.querySelector('.indoor-hum')).fontSize),
        indoorHilo: parseFloat(getComputedStyle(document.querySelector('.indoor-hilo')).fontSize),
        compassCardinal: parseFloat(getComputedStyle(document.querySelector('.dir-label')).fontSize),
        compassCardinalWeight: getComputedStyle(document.querySelector('.dir-label')).fontWeight,
        rainValue: parseFloat(getComputedStyle(rainValue).fontSize),
        rainFooter: parseFloat(getComputedStyle(rainFooter).fontSize),
        sunMoon: parseFloat(getComputedStyle(sunMoon).fontSize),
      },
      visibleLabels: grid.querySelectorAll('.tile-label').length,
      headerHeight: document.querySelector('header.header').getBoundingClientRect().height,
      centeredBodies: grid.querySelectorAll('[data-tile-center-body]').length,
    };
  });
}

function expectBounded(geometry, target) {
  expect(geometry.document.scrollWidth).toBeLessThanOrEqual(geometry.document.clientWidth);
  expect(geometry.document.scrollHeight).toBeLessThanOrEqual(geometry.document.clientHeight);
  expect(geometry.body.scrollWidth).toBeLessThanOrEqual(geometry.body.clientWidth);
  expect(geometry.body.scrollHeight).toBeLessThanOrEqual(geometry.body.clientHeight);
  expect(geometry.shell.width).toBe(target.width);
  expect(geometry.shell.height).toBe(target.height);
  expect(geometry.screen.scrollWidth).toBeLessThanOrEqual(geometry.screen.clientWidth);
  expect(geometry.screen.scrollHeight).toBeLessThanOrEqual(geometry.screen.clientHeight);
  expect(geometry.grid.scrollWidth).toBeLessThanOrEqual(geometry.grid.clientWidth);
  expect(geometry.grid.scrollHeight).toBeLessThanOrEqual(geometry.grid.clientHeight);
  for (const cell of geometry.cells) {
    expect(cell.left, cell.classes).toBeGreaterThanOrEqual(geometry.grid.left - 0.5);
    expect(cell.top, cell.classes).toBeGreaterThanOrEqual(geometry.grid.top - 0.5);
    expect(cell.right, cell.classes).toBeLessThanOrEqual(geometry.grid.right + 0.5);
    expect(cell.bottom, cell.classes).toBeLessThanOrEqual(geometry.grid.bottom + 0.5);
    expect(cell.scrollWidth, cell.classes).toBeLessThanOrEqual(cell.clientWidth);
    expect(cell.scrollHeight, cell.classes).toBeLessThanOrEqual(cell.clientHeight);
    expect(cell.tile.scrollWidth, `${cell.classes} tile`).toBeLessThanOrEqual(cell.tile.clientWidth);
    expect(cell.tile.scrollHeight, `${cell.classes} tile`).toBeLessThanOrEqual(cell.tile.clientHeight);
    expect(cell.tileBody.scrollWidth, `${cell.classes} body`).toBeLessThanOrEqual(cell.tileBody.clientWidth);
    expect(cell.tileBody.scrollHeight, `${cell.classes} body`).toBeLessThanOrEqual(cell.tileBody.clientHeight);
  }
}


function expectHomeCardSeparation(geometry) {
  const { outdoor, indoor, rain, battery, baro, solar, greywater, goat, powerFlow } = geometry;
  expect(powerFlow.line.width).toBeGreaterThan(0);
  expect(powerFlow.line.scrollWidth).toBeLessThanOrEqual(powerFlow.line.clientWidth);
  expect(goat.icon.right).toBeLessThanOrEqual(goat.text.left + 0.5);
  expect(outdoor.icon.right).toBeLessThanOrEqual(outdoor.temp.left + 0.5);
  expect(outdoor.temp.right).toBeLessThanOrEqual(outdoor.chips.left + 0.5);
  expect(outdoor.temp.bottom).toBeLessThanOrEqual(outdoor.sub.top + 0.5);
  expect(outdoor.chips.bottom).toBeLessThanOrEqual(outdoor.sub.top + 0.5);
  expect(outdoor.sub.bottom).toBeLessThanOrEqual(outdoor.hilo.top + 0.5);
  expect(outdoor.hilo.bottom).toBeLessThanOrEqual(outdoor.spark.top + 0.5);
  expect(indoor.icon.right).toBeLessThanOrEqual(indoor.temp.left + 0.5);
  expect(indoor.temp.right).toBeLessThanOrEqual(indoor.meta.left + 0.5);
  expect(indoor.humidity.bottom).toBeLessThanOrEqual(indoor.hilo.top + 0.5);
  for (let index = 1; index < outdoor.chipItems.length; index += 1) {
    expect(outdoor.chipItems[index - 1].bottom).toBeLessThanOrEqual(outdoor.chipItems[index].top + 0.5);
  }
  expect(rain.icon.bottom).toBeLessThanOrEqual(rain.value.top + 0.5);
  expect(rain.stat.bottom).toBeLessThanOrEqual(rain.footer.top + 0.5);
  expect(rain.layout).toEqual({
    statDisplay: 'flex',
    statAlign: 'center',
    statDirection: 'column',
    iconDisplay: 'flex',
    valueWhiteSpace: 'nowrap',
  });
  expect(battery.arc.right).toBeLessThanOrEqual(battery.meta.left + 0.5);
  expect(battery.icon.right).toBeLessThanOrEqual(battery.indicator.left + 0.5);
  expect(battery.status.bottom).toBeLessThanOrEqual(battery.empty.top + 0.5);
  expect(battery.empty.bottom).toBeLessThanOrEqual(battery.full.top + 0.5);
  expect(battery.top.bottom).toBeLessThanOrEqual(battery.spark.top + 0.5);
  expect(baro.icon.right).toBeLessThanOrEqual(baro.value.left + 0.5);
  expect(baro.head.bottom).toBeLessThanOrEqual(baro.spark.top + 0.5);
  expect(baro.spark.bottom).toBeLessThanOrEqual(baro.trend.top + 0.5);
  expect(solar.icon.right).toBeLessThanOrEqual(solar.main.left + 0.5);
  expect(solar.head.bottom).toBeLessThanOrEqual(solar.sub.top + 0.5);
  expect(solar.sub.bottom).toBeLessThanOrEqual(solar.current.top + 0.5);
  expect(solar.current.bottom).toBeLessThanOrEqual(solar.curtail.top + 0.5);
  expect(greywater.icon.right).toBeLessThanOrEqual(greywater.text.left + 0.5);
}

async function expectExtremaMarkerGeometry(dialog) {
  const tolerance = 1;
  const chartBox = await dialog.locator('.chart-canvas').boundingBox();
  const highBox = await dialog.locator('text').filter({ hasText: 'High' }).boundingBox();
  const lowBox = await dialog.locator('text').filter({ hasText: 'Low' }).boundingBox();

  expect(chartBox).not.toBeNull();
  expect(highBox).not.toBeNull();
  expect(lowBox).not.toBeNull();

  for (const [name, markerBox] of [['High', highBox], ['Low', lowBox]]) {
    expect(markerBox.x, `${name} left edge`).toBeGreaterThanOrEqual(chartBox.x - tolerance);
    expect(markerBox.y, `${name} top edge`).toBeGreaterThanOrEqual(chartBox.y - tolerance);
    expect(markerBox.x + markerBox.width, `${name} right edge`)
      .toBeLessThanOrEqual(chartBox.x + chartBox.width + tolerance);
    expect(markerBox.y + markerBox.height, `${name} bottom edge`)
      .toBeLessThanOrEqual(chartBox.y + chartBox.height + tolerance);
  }

  const overlapWidth = Math.min(
    highBox.x + highBox.width,
    lowBox.x + lowBox.width,
  ) - Math.max(highBox.x, lowBox.x);
  const overlapHeight = Math.min(
    highBox.y + highBox.height,
    lowBox.y + lowBox.height,
  ) - Math.max(highBox.y, lowBox.y);
  expect(
    overlapWidth > tolerance && overlapHeight > tolerance,
    `High/Low labels overlap by ${overlapWidth} x ${overlapHeight}px`,
  ).toBe(false);
}

for (const target of TARGETS) {
  test(`Home settled layout is bounded and usable at ${target.name}`, async ({ page }, testInfo) => {
    const runtime = await openHomeFixture(page, target);
    const geometry = await homeGeometry(page);

    expectBounded(geometry, target);
    expectHomeCardSeparation(geometry);
    expect(geometry.visibleLabels).toBe(0);
    expect(geometry.centeredBodies).toBe(14);
    expect(geometry.headerHeight).toBe(44);
    expect(geometry.colors.outdoor).toBe('rgb(255, 255, 255)');
    expect(geometry.colors.indoor).toBe('rgb(255, 255, 255)');
    expect(geometry.fonts.outdoor).toBeCloseTo(70.4, 1);
    expect(geometry.fonts.indoor).toBeCloseTo(70.4, 1);
    expect(geometry.fonts.indoorHumidity).toBeCloseTo(16.8, 1);
    expect(geometry.fonts.indoorHilo).toBeCloseTo(15.2, 1);
    expect(geometry.fonts.rainValue).toBeCloseTo(16, 1);
    expect(geometry.fonts.rainFooter).toBeCloseTo(11.52, 1);
    expect(geometry.fonts.sunMoon).toBeGreaterThanOrEqual(13.5);
    expect(geometry.compass.width).toBeGreaterThanOrEqual(80);
    expect(geometry.compass.height).toBe(geometry.compass.width);
    expect(geometry.compass.right).toBeLessThanOrEqual(geometry.compassHost.right + 0.5);
    expect(geometry.compass.bottom).toBeLessThanOrEqual(geometry.compassHost.bottom + 0.5);
    expect(geometry.compass.bottom).toBeLessThanOrEqual(geometry.windMeta.top + 0.5);
    expect(geometry.outdoorSvg.width).toBeGreaterThanOrEqual(160);
    expect(geometry.outdoorSvg.height).toBeGreaterThanOrEqual(35);
    expect(geometry.windCardinalCount).toBe(4);
    expect(geometry.fonts.compassCardinal).toBeCloseTo(12, 1);
    expect(geometry.fonts.compassCardinalWeight).toBe('800');
    expect(geometry.outdoorSvg.right).toBeLessThanOrEqual(geometry.outdoorHost.right + 0.5);
    expect(geometry.outdoorSvg.bottom).toBeLessThanOrEqual(geometry.outdoorHost.bottom + 0.5);

    expect(geometry.outdoor.chipItems).toHaveLength(2);
    expect(geometry.windNeedleCount).toBe(1);
    expect(geometry.windHubCount).toBe(1);
    for (const cardinal of geometry.windCardinals) {
      expect(cardinal.left, cardinal.label).toBeGreaterThanOrEqual(geometry.compass.left - 0.5);
      expect(cardinal.top, cardinal.label).toBeGreaterThanOrEqual(geometry.compass.top - 0.5);
      expect(cardinal.right, cardinal.label).toBeLessThanOrEqual(geometry.compass.right + 0.5);
      expect(cardinal.bottom, cardinal.label).toBeLessThanOrEqual(geometry.compass.bottom + 0.5);
    }
    expect(geometry.windNeedle.top - geometry.northCardinal.bottom).toBeGreaterThanOrEqual(1);
    await expect(page.getByRole('group', { name: 'Power Flow', exact: true })).toBeAttached();
    await expect(page.getByRole('group', { name: 'Goat feedings: 2 feedings today', exact: true })).toBeVisible();
    await expect(page.locator('.goat-activation-icon')).toHaveCount(0);
    await expect(page.locator('.sm-season')).toContainText(/(?:equinox|solstice)/);
    await expect(page.locator('.outdoor-spark svg path[stroke="#4caf50"]').first()).toBeVisible();

    await runtime.emitState('Goat_Plugs_Outlet2_Switch', 'OFF');
    await runtime.emitState('Goat_Plugs_Outlet2_Switch', 'ON');
    await expect(page.locator('.goat-activation-icon')).toHaveText('🐐');
    await runtime.emitState('GoatFeedingsToday', '3');
    await expect(page.getByRole('group', { name: 'Goat feedings: 3 feedings today', exact: true })).toBeVisible();

    await runtime.emitState('AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', '86');
    await expect(page.locator('.cond-icon svg')).toHaveCSS('color', 'rgb(244, 67, 54)');
    await expect(page.locator('.outdoor-spark svg path[stroke="#f44336"]').first()).toBeVisible();
    await expect(page.getByRole('group', { name: 'Indoor', exact: true })).toBeAttached();
    await expect(page.getByRole('group', { name: 'Rain', exact: true })).toBeAttached();
    await expect(page.getByText('AQI 42', { exact: true })).toBeVisible();
    await expect(page.getByRole('img', { name: 'Wind direction 0 degrees, speed 11 mph', exact: true })).toBeVisible();
    await expect(page.getByText('AQI 501', { exact: true })).toHaveCount(0);
    await expect(page.locator('.aqi-chip')).toHaveCSS('color', 'rgb(248, 250, 252)');
    await expect(page.locator('.aqi-chip')).toHaveCSS('border-top-color', 'rgb(34, 197, 94)');
    await expect(page.getByText('UV 0', { exact: true })).toHaveCSS('color', 'rgb(76, 175, 80)');
    await expect(page.locator('.rain-rate-chip')).toHaveCount(0);
    await expect(page.getByRole('group', { name: 'Greywater status idle', exact: true })).toBeAttached();
    await expect(page.locator('.gw-icon')).toHaveCSS('color', 'rgb(139, 147, 161)');
    await expect(page.locator('.compass-needle')).toHaveAttribute('fill', '#4caf50');
    await expect(page.locator('.compass-hub')).toHaveAttribute('fill', '#4caf50');
    await expect(page.locator('.wind-gust')).toHaveCSS('color', 'rgb(255, 152, 0)');
    await expect(page.locator('.wind-max')).toHaveCSS('color', 'rgb(244, 67, 54)');
    await expect(page.locator('.battery-arc .arc-value')).toHaveText('62%');
    await expect(page.locator('.batt-icon')).toHaveCSS('color', 'rgb(34, 197, 94)');
    await expect(page.locator('.batt-indicator')).toHaveCSS('color', 'rgb(245, 158, 11)');
    await expect(page.locator('.batt-runtime-empty')).toHaveText('Empty 10 h 40 m');
    await expect(page.locator('.batt-runtime-full')).toHaveText('Full 17 h 20 m');
    await expect(page.locator('.rain-cell .state-icon')).toHaveCSS('color', 'rgb(59, 130, 246)');
    await expect(page.locator('.rain-cell .value')).toHaveText('9.99″ / 17,427 gal');
    await expect(page.locator('.rain-cell .footer')).toHaveText('Week 1.72″ / 3,000 gal');
    await expect(page.locator('.baro-status-icon')).toHaveCSS('color', 'rgb(139, 147, 161)');
    await expect(page.locator('.baro-trend')).toHaveCSS('color', 'rgb(139, 147, 161)');
    await expect(page.locator('.solar-icon')).toHaveCSS('color', 'rgb(255, 193, 7)');
    await expect(page.locator('.solar-current')).toHaveCSS('color', 'rgb(255, 193, 7)');
    await expect(page.locator('.curtail-lamp')).toHaveCSS('color', 'rgb(139, 147, 161)');
    const liveConditionMarkup = await page.locator('.cond-icon').innerHTML();
    expect(liveConditionMarkup).not.toBe('');
    await expect(page.locator('.btc-icon svg')).toBeVisible();
    await expect(page.locator('.btc-icon')).toHaveCSS('color', 'rgb(239, 68, 68)');
    await expect(page.locator('.btc-pct')).toHaveCSS('color', 'rgb(239, 68, 68)');

    await page.waitForTimeout(100);
    expect(runtime.historyRequests).not.toContain('BTC_USD_Price');
    const bitcoin = page.getByRole('button', { name: 'Open Bitcoin history chart' });
    await bitcoin.focus();
    await bitcoin.press('Enter');
    await expect(page.getByRole('dialog').getByRole('heading', { name: 'Bitcoin (USD)' })).toBeVisible();
    await expect.poll(() => runtime.historyRequests).toContain('BTC_USD_Price');
    await page.getByRole('button', { name: 'Close chart' }).click();
    await bitcoin.click();
    await expect(page.getByRole('dialog').getByRole('heading', { name: 'Bitcoin (USD)' })).toBeVisible();
    await page.getByRole('button', { name: 'Close chart' }).click();

    await page.getByRole('button', { name: 'Open Outdoor temperature chart' }).click();
    let dialog = page.getByRole('dialog', { name: 'Outdoor Temp' });
    await expect(dialog.locator('svg')).toBeVisible();
    await expect(dialog.locator('text').filter({ hasText: 'High' })).toHaveCount(1);
    await expect(dialog.locator('text').filter({ hasText: 'Low' })).toHaveCount(1);
    await expectExtremaMarkerGeometry(dialog);
    await page.screenshot({ path: testInfo.outputPath('outdoor-extrema.png') });
    await page.getByRole('button', { name: 'Close chart' }).click();

    await page.getByRole('button', { name: /Open Battery chart/ }).click();
    dialog = page.getByRole('dialog', { name: 'Battery SoC' });
    await expect(dialog.locator('svg')).toBeVisible();
    await expect(dialog.locator('text').filter({ hasText: 'High' })).toHaveCount(1);
    await expect(dialog.locator('text').filter({ hasText: 'Low' })).toHaveCount(1);
    await expectExtremaMarkerGeometry(dialog);
    await page.screenshot({ path: testInfo.outputPath('battery-extrema.png') });
    await page.getByRole('button', { name: 'Close chart' }).click();

    expect(runtime.pageErrors).toEqual([]);
    expect(runtime.unexpectedExternalRequests).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath('home-settled.png') });
    runtime.setStates({ SkyConditionIcon: 'UNDEF' });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.locator('.home-grid').waitFor();
    await expect(page.locator('.cond-icon svg')).toBeVisible();
    const fallbackConditionMarkup = await page.locator('.cond-icon').innerHTML();
    expect(fallbackConditionMarkup).not.toBe(liveConditionMarkup);
    expect(runtime.pageErrors).toEqual([]);
    expect(runtime.unexpectedExternalRequests).toEqual([]);
  });

  test(`Home contains long, unavailable, and stale states at ${target.name}`, async ({ page }, testInfo) => {
    const runtime = await openHomeFixture(page, target, {
      staleSeconds: 0.02,
      states: {
        AmbientWeatherWS2902A_RainFallDay: 'UNDEF',
        AmbientWeatherWS2902A_RainFallHourlyRate: '0.126',
        AmbientWeatherWS2902A_RainFallWeek: 'NULL',
        AmbientWeatherWS2902A_UVIndex: 'UNDEF',
        AmbientWeatherWS2902A_PressureTrend: 'falling',
        AmbientWeatherWS2902A_WindDirection: 'UNDEF',
        BatteryChargingStatus: 'NULL',
        BatteryIcon: 'NULL',
        BMS_SOC: 'UNDEF',
        BMS_TimeToDischarge_Smoothed: 'UNDEF',
        BMS_TimeToFull_Smoothed: 'UNDEF',
        BTC_Price_24h_PercentChange: 'NULL',
        Current_US_AQI: 'NULL',
        DCData_Current: 'UNDEF',
        MPPT60_PV_Power: '650',
        Predicted_Curtailment_Hours: '2',
        SkyConditionIcon: 'UNDEF',
        SouthOutlet_Outlet2_Switch: 'NULL',
        Moon_MoonPhaseName: 'Waxing gibbous approaching the full moon',
        Thermal_Advisory: 'close_up_tomorrow|Close every south opening before tomorrow morning to retain thermal mass',
      },
    });

    await expect(page.getByRole('img', { name: 'openHAB connection: stale' })).toBeVisible();
    await expect(page.locator('[data-header-alert-winner]')).toContainText('Close every south opening');
    await expect(page.getByRole('group', { name: 'Power Flow', exact: true })).toBeAttached();
    await expect(page.getByRole('group', { name: 'Advisory', exact: true })).toHaveCount(0);
    await expect(page.locator('.btc-icon')).toHaveCSS('color', 'rgb(247, 147, 26)');
    await expect(page.locator('.btc-pct')).toHaveCSS('color', 'rgb(247, 147, 26)');
    await expect(page.getByRole('img', { name: 'Wind direction unavailable, speed 11 mph', exact: true })).toBeVisible();
    await expect(page.getByRole('group', { name: 'Greywater status unavailable', exact: true })).toBeAttached();
    await expect(page.locator('.gw-icon')).toHaveCSS('color', 'rgb(139, 147, 161)');
    await expect(page.locator('.aqi-chip')).toHaveCSS('color', 'rgb(248, 250, 252)');
    await expect(page.locator('.aqi-chip')).toHaveCSS('border-top-color', 'rgb(139, 147, 161)');
    await expect(page.getByText('UV —', { exact: true })).toHaveCSS('color', 'rgb(139, 147, 161)');
    await expect(page.locator('.rain-rate-chip')).toHaveText('RAIN 0.13 in/h');
    await expect(page.locator('.rain-rate-chip')).toHaveCSS('color', 'rgb(59, 130, 246)');
    await expect(page.locator('.rain-rate-chip')).toHaveCSS('border-top-color', 'rgb(59, 130, 246)');
    await expect(page.locator('.cond-icon svg')).toBeVisible();
    await expect(page.locator('.compass-needle')).toHaveCount(0);
    await expect(page.locator('.compass-hub')).toHaveCount(0);
    await expect(page.locator('.battery-arc .arc-value')).toHaveText('—');
    await expect(page.locator('.battery-arc [data-arc-value]')).toHaveCount(0);
    await expect(page.locator('.batt-indicator')).toHaveText('— unavailable');
    await expect(page.locator('.batt-indicator')).toHaveCSS('color', 'rgb(139, 147, 161)');
    await expect(page.locator('.batt-icon')).toHaveCSS('color', 'rgb(107, 114, 128)');
    await expect(page.locator('.batt-icon')).not.toHaveClass(/charging/);
    await expect(page.locator('.batt-runtime-empty')).toHaveText('Empty —');
    await expect(page.locator('.batt-runtime-full')).toHaveText('Full —');
    await expect(page.locator('.rain-cell .value')).toHaveText('—');
    await expect(page.locator('.rain-cell .footer')).toHaveText('Week —');
    await expect(page.locator('.rain-cell .state-icon')).toHaveCSS('color', 'rgb(139, 147, 161)');
    await expect(page.locator('.baro-status-icon')).toHaveCSS('color', 'rgb(255, 87, 34)');
    await expect(page.locator('.baro-trend')).toHaveCSS('color', 'rgb(255, 87, 34)');
    await expect(page.locator('.solar-icon')).toHaveCSS('color', 'rgb(255, 152, 0)');
    await expect(page.locator('.solar-current')).toHaveCSS('color', 'rgb(255, 152, 0)');
    await expect(page.locator('.curtail-lamp')).toHaveCSS('color', 'rgb(234, 179, 8)');

    await expect(page.locator('.sm-moon')).toHaveAttribute(
      'title',
      'Waxing Gibbous Approaching The Full Moon'
    );
    await expect(page.locator('.sm-moon')).toHaveCSS('text-overflow', 'ellipsis');
    const geometry = await homeGeometry(page);
    expectBounded(geometry, target);
    expectHomeCardSeparation(geometry);
    expect(geometry.centeredBodies).toBe(14);
    expect(geometry.outdoor.chipItems).toHaveLength(3);
    expect(geometry.windNeedleCount).toBe(0);
    expect(geometry.windHubCount).toBe(0);
    expect(geometry.fonts.outdoor).toBeCloseTo(70.4, 1);
    expect(geometry.fonts.indoor).toBeCloseTo(70.4, 1);
    expect(geometry.windCardinalCount).toBe(4);
    expect(geometry.fonts.compassCardinal).toBeCloseTo(12, 1);
    expect(geometry.fonts.compassCardinalWeight).toBe('800');
    expect(geometry.headerHeight).toBe(44);
    expect(runtime.pageErrors).toEqual([]);
    expect(runtime.unexpectedExternalRequests).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath('home-long-unavailable-stale.png') });
  });
}
