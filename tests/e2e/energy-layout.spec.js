import { expect, test } from '@playwright/test';
import { createServer } from 'vite';

import { energyAnalyticsFixture, energyAnalyticsV2Fixture, energyAnalyticsCurrentV3Fixture } from '../fixtures/energyAnalytics.js';

const TARGETS = [
  { name: 'm9-1340x800', width: 1340, height: 800 },
  { name: 'laptop-1280x720', width: 1280, height: 720 },
];

const STATES = {
  BMS_SOC: '89',
  Predicted_SoC_Trough_Tomorrow: '51',
  BMS_Runtime_Basis: 'now',
  BMS_TimeToDischarge_Smoothed: '770',
  MPPT60_EnergyFromPV_Today: '3.2',
  Predicted_PV_Today_kWh: '6.6',
  Forecast_PV_Error_7d: '13',
  Predicted_Curtailment_Hours: '2',
  Forecast_Daily_JSON: JSON.stringify(Array.from({ length: 7 }, (_, index) => ({
    d: index === 0 ? 'Today' : index === 1 ? 'Tomorrow' : `Day ${index + 1}`,
    pv: 6.4 + index / 10,
  }))),
  BMS_Temperature: '77',
  BMS_Charge_Cycles: '2',
  BMS_Capacity_Remaining_Ah: '89',
  BMS_Comms_Status: 'OK',
  BMS_DevicePresent: '1',
  Energy_Analytics_JSON: JSON.stringify(energyAnalyticsFixture()),
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

async function openEnergyFixture(page, target, analytics = energyAnalyticsFixture(), states = {}) {
  const historyRequests = [];
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
  await page.route('**/config.json', (route) => route.fulfill({
    json: { openhabUrl: '/fixture-openhab', apiToken: 'fixture-only', staleBannerSeconds: 90 },
  }));
  await page.route('**/fixture-openhab/rest/items?*', (route) => route.fulfill({
    json: Object.entries({ ...STATES, ...states, Energy_Analytics_JSON: JSON.stringify(analytics) })
      .map(([name, state]) => ({ name, state, type: 'String' })),
  }));
  await page.route('**/fixture-openhab/rest/persistence/items/**', (route) => {
    const url = new URL(route.request().url());
    historyRequests.push(url);
    const now = Date.now();
    return route.fulfill({
      json: {
        data: Array.from({ length: 48 }, (_, index) => ({
          time: now - (47 - index) * 30 * 60_000,
          state: String(50 + index / 2),
        })),
      },
    });
  });

  await page.goto(`${baseURL}#/energy`, { waitUntil: 'domcontentloaded' });
  await page.locator('.energy-grid').waitFor();
  await page.locator('.hero-chart svg').waitFor({ timeout: 20_000 });
  await page.locator('.pv-chart svg').waitFor({ timeout: 20_000 });
  return historyRequests;
}

test('Energy PV comparison and outlook use the current dated forecast', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-24T04:46:00-06:00') });
  const summary = (pvKwh) => ({ highF: null, lowF: null, precipPct: null, weatherCode: null, pvKwh });
  await openEnergyFixture(page, TARGETS[0], energyAnalyticsFixture(), {
    Predicted_PV_Today_kWh: '3.42',
    Forecast_10Day_JSON: JSON.stringify({
      version: 1,
      generatedAt: '2026-09-24T03:20:00-06:00',
      timezone: 'America/Denver',
      days: [
        { date: '2026-09-24', label: 'Today', summary: summary(3.3), hours: [] },
        { date: '2026-09-25', label: 'Tomorrow', summary: summary(5.5), hours: [] },
      ],
    }),
  });
  await expect(page.locator('.pv-sub')).toHaveText('of 3.3 kWh predicted');
  await expect(page.locator('.outlook-value')).toHaveText(['3.3', '5.5']);
});

for (const target of TARGETS) {
  test(`Energy keeps both history plots readable at ${target.name}`, async ({ page }) => {
    await openEnergyFixture(page, target);

    const geometry = await page.evaluate(() => {
      const box = (element) => {
        const rect = element.getBoundingClientRect();
        return { top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left, height: rect.height };
      };
      return {
        grid: box(document.querySelector('.energy-grid')),
        heroPlot: box(document.querySelector('.hero-chart svg')),
        pvPlot: box(document.querySelector('.pv-chart svg')),
        overflowingCells: [...document.querySelectorAll('.energy-grid > .cell')]
          .filter((cell) => (
            cell.scrollWidth > cell.clientWidth || cell.scrollHeight > cell.clientHeight
          ))
          .map((cell) => cell.className),
      };
    });

    expect(geometry.heroPlot.height).toBeGreaterThanOrEqual(64);
    expect(geometry.pvPlot.height).toBeGreaterThanOrEqual(64);
    expect(geometry.overflowingCells).toEqual([]);
    for (const plot of [geometry.heroPlot, geometry.pvPlot]) {
      expect(plot.left).toBeGreaterThanOrEqual(geometry.grid.left);
      expect(plot.top).toBeGreaterThanOrEqual(geometry.grid.top);
      expect(plot.right).toBeLessThanOrEqual(geometry.grid.right);
      expect(plot.bottom).toBeLessThanOrEqual(geometry.grid.bottom);
    }
  });
}

test('Energy period selection issues a fresh 4-hour history range', async ({ page }) => {
  const historyRequests = await openEnergyFixture(page, TARGETS[0]);
  const hero = page.locator('.hero-chart');
  const requestCount = historyRequests.length;

  await hero.getByRole('button', { name: '4h', exact: true }).click();
  await expect.poll(() => historyRequests.length).toBeGreaterThan(requestCount);
  await expect(hero.getByRole('button', { name: '4h', exact: true })).toHaveAttribute('aria-pressed', 'true');

  const latest = historyRequests.at(-1);
  const start = Date.parse(latest.searchParams.get('starttime'));
  const end = Date.parse(latest.searchParams.get('endtime'));
  expect(end - start).toBe(4 * 60 * 60 * 1000);
});

test('Lenovo Energy shows dated observed and earlier estimated EFC without horizontal overflow', async ({ page }) => {
  const analytics = energyAnalyticsCurrentV3Fixture();
  analytics.lifecycle.highSocHoursAbove90 = 49.6;
  analytics.lifecycle.highSocHoursAbove95 = 32.5;
  await openEnergyFixture(page, TARGETS[0], analytics);
  await expect(page.locator('.analytics-value')).toHaveText('0.43 observed EFC');
  await expect(page.locator('.analytics-through')).toHaveText('since Sep 20 · through Sep 22');
  await expect(page.getByText('Charge cycles', { exact: true })).toBeVisible();
  await expect(page.locator('.vital-value[title*="Not equivalent full cycles"]')).toHaveText('2');
  await expect(page.getByText('BMS remaining', { exact: true })).toBeVisible();
  await expect(page.getByText('Predicted Curtailment (today)', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Open energy analytics details' }).click();
  await expect(page.getByText('Earlier estimated EFC (Jul 19–Sep 19)')).toBeVisible();
  await expect(page.getByText('9.81')).toBeVisible();
  await expect(page.getByText('Observed above 90% SoC')).toBeVisible();
  await expect(page.getByText('Observed above 95% SoC')).toBeVisible();
  const layout = await page.evaluate(() => {
    const panel = document.querySelector('.analytics-panel');
    const compact = document.querySelector('.analytics-compact');
    return { bodyOverflow: document.body.scrollWidth > document.body.clientWidth,
      panelOverflow: panel.scrollWidth > panel.clientWidth,
      compactOverflow: compact.scrollWidth > compact.clientWidth };
  });
  expect(layout).toEqual({ bodyOverflow: false, panelOverflow: false, compactOverflow: false });
});


test("Energy exposes observational analytics detail without adding controls", async ({ page }) => {
  const analytics = energyAnalyticsV2Fixture();
  analytics.battery.status = 'degraded';
  await openEnergyFixture(page, TARGETS[0], analytics);
  await page.getByRole("button", { name: "Open energy analytics details" }).click();
  const dialog = page.getByRole("dialog", { name: "Energy analytics details" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "Winter" })).toBeVisible();
  await expect(dialog.getByText('Daily SoC range (DoD)')).toBeVisible();
  await expect(dialog.getByText('16.0 pp')).toBeVisible();
  const dailyRangeValue = dialog.getByText('Daily SoC range (DoD)').locator('..').locator('dd');
  await expect.poll(() => dailyRangeValue.evaluate((element) => element.innerText))
    .toBe('16.0 pp');
  await expect(dialog.getByText('Daily estimated EFC')).toBeVisible();
  await expect(dialog.getByText('0.160', { exact: true })).toBeVisible();
  await expect(dialog.getByText('The latest day is incomplete; daily battery values may change.'))
    .toBeVisible();
  await expect(dialog.locator("form, input, select, textarea")).toHaveCount(0);
  await page.getByRole('button', { name: 'Close energy analytics details' }).click();
  await expect(dialog).toBeHidden();
});

test('Energy renders legacy battery cycle evidence as unavailable', async ({ page }) => {
  await openEnergyFixture(page, TARGETS[0]);
  await page.getByRole('button', { name: 'Open energy analytics details' }).click();
  const dialog = page.getByRole('dialog', { name: 'Energy analytics details' });
  await expect(dialog.getByText('Daily SoC range (DoD)').locator('..').locator('dd'))
    .toHaveText('Unavailable');
  await expect(dialog.getByText('Daily estimated EFC').locator('..').locator('dd'))
    .toHaveText('Unavailable');
});
