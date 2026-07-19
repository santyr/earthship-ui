import { expect, test } from '@playwright/test';
import { createServer } from 'vite';

const TARGETS = [
  { name: 'm9-1340x800', width: 1340, height: 800 },
  { name: 'laptop-1280x720', width: 1280, height: 720 },
];

const ITEMS = [
  ['living_room_1_Switch', 'OFF'],
  ['living_room_2_Switch', 'OFF'],
  ['LED_living_room_1_Switch', 'ON'],
  ['LivingRoomCircadian_Enable', 'ON'],
  ['LivingRoomCircadian_LastResult', 'ok'],
  ['Dish_Washer_Power', 'ON'],
  ['ShurefloPump_Power', 'OFF'],
  ['Goat_Plugs_Outlet1_Switch', 'OFF'],
  ['Goat_Plugs_Outlet2_Switch', 'OFF'],
  ['SouthOutlet_Outlet2_Switch', 'OFF'],
  ['OverrideSwitch', 'ON'],
  ['FeederOverride', 'ON'],
].map(([name, state]) => ({ name, state, type: 'Switch' }));

const THINGS = [
  ['tplinksmarthome:kl125:E7FA31', 'ONLINE', 'NONE', ''],
  ['tplinksmarthome:kl125:E62B6D', 'OFFLINE', 'COMMUNICATION_ERROR', 'No route to host'],
  ['tplinksmarthome:kl125:E7CAD9', 'ONLINE', 'NONE', ''],
  ['tplinksmarthome:hs103:a34b4957dc', 'ONLINE', 'NONE', ''],
  ['tplinksmarthome:hs103:08482dd378', 'ONLINE', 'NONE', ''],
  ['tplinksmarthome:ep40:3cb500a208', 'ONLINE', 'NONE', ''],
  ['tplinksmarthome:kp200:7BD449', 'ONLINE', 'NONE', ''],
].map(([UID, status, statusDetail, description]) => ({
  UID,
  statusInfo: { status, statusDetail, description },
}));

let server;
let baseURL;
let previousReleaseMode;

test.beforeAll(async () => {
  previousReleaseMode = process.env.RELEASE_MODE;
  process.env.RELEASE_MODE = 'safe-compat';
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
  if (previousReleaseMode === undefined) delete process.env.RELEASE_MODE;
  else process.env.RELEASE_MODE = previousReleaseMode;
});

async function openControls(page, target) {
  const pageErrors = [];
  const commandRequests = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('request', (request) => {
    if (request.method() !== 'GET') commandRequests.push({
      method: request.method(), url: request.url(),
    });
  });

  await page.setViewportSize({ width: target.width, height: target.height });
  await page.addInitScript(() => {
    class FixtureEventSource {
      constructor() { setTimeout(() => this.onopen?.({ type: 'open' }), 0); }
      close() {}
    }
    Object.defineProperty(window, 'EventSource', {
      configurable: true, writable: true, value: FixtureEventSource,
    });
  });
  await page.route('**/config.json', (route) => route.fulfill({
    json: { openhabUrl: '/fixture-openhab', apiToken: 'fixture-only', staleBannerSeconds: 90 },
  }));
  await page.route('**/fixture-openhab/rest/items?*', (route) => route.fulfill({ json: ITEMS }));
  await page.route('**/fixture-openhab/rest/things', (route) => route.fulfill({ json: THINGS }));

  await page.goto(`${baseURL}#/controls`, { waitUntil: 'domcontentloaded' });
  await page.locator('.controls-grid').waitFor();
  await expect(page.getByRole('button', { name: /Living Room 1/i })).toBeEnabled();

  return { commandRequests, pageErrors };
}

async function controlsGeometry(page) {
  return page.evaluate(() => {
    const box = (element) => {
      const rect = element.getBoundingClientRect();
      return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom };
    };
    const grid = document.querySelector('.controls-grid');
    const screen = document.querySelector('main.screen');
    return {
      document: {
        clientWidth: document.documentElement.clientWidth,
        clientHeight: document.documentElement.clientHeight,
        scrollWidth: document.documentElement.scrollWidth,
        scrollHeight: document.documentElement.scrollHeight,
      },
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
        ...box(cell),
        clientWidth: cell.clientWidth,
        clientHeight: cell.clientHeight,
        scrollWidth: cell.scrollWidth,
        scrollHeight: cell.scrollHeight,
      })),
      buttons: [...grid.querySelectorAll('button.control')].map((button) => ({
        ...box(button),
        clientWidth: button.clientWidth,
        clientHeight: button.clientHeight,
        scrollWidth: button.scrollWidth,
        scrollHeight: button.scrollHeight,
      })),
    };
  });
}

for (const target of TARGETS) {
  test(`Controls stays bounded and truthful at ${target.name}`, async ({ page }) => {
    const runtime = await openControls(page, target);

    await expect(page.getByRole('button', { name: /Living Room 2/i })).toBeDisabled();
    await expect(page.getByRole('button', { name: /Living Room 2/i })).toContainText('Provider OFFLINE');
    await expect(page.getByRole('button', { name: /Living Room 1/i })).toContainText('Tap to toggle');
    await expect(page.getByRole('button', { name: /Circadian/i })).toBeEnabled();
    await expect(page.getByRole('button', { name: /Circadian/i })).toContainText('Hold 600 ms');
    const dishwasher = page.getByRole('button', { name: /Dishwasher/i });
    await expect(dishwasher).toHaveClass(/on/);
    await expect(dishwasher.locator('.pill')).toHaveCSS('background-color', 'rgb(34, 197, 94)');
    // Override is ON in the fixture, so the three owned loads stay disabled
    // ("Owned by Night Load Override"); the verified correlated controls
    // (capabilities flipped 2026-07-19) are live with hold interaction.
    for (const label of [/Dishwasher/i, /Shureflo Pump/i, /Goat Cam/i]) {
      await expect(page.getByRole('button', { name: label })).toBeDisabled();
    }
    for (const label of [/Feed once/i, /Request circulation/i, /^Night Load Override/i]) {
      const control = page.getByRole('button', { name: label });
      await expect(control).toBeEnabled();
      await expect(control).toContainText('Hold 600 ms');
    }

    const geometry = await controlsGeometry(page);
    expect(geometry.document.scrollWidth).toBeLessThanOrEqual(geometry.document.clientWidth);
    expect(geometry.document.scrollHeight).toBeLessThanOrEqual(geometry.document.clientHeight);
    expect(geometry.screen.scrollWidth).toBeLessThanOrEqual(geometry.screen.clientWidth);
    expect(geometry.screen.scrollHeight).toBeLessThanOrEqual(geometry.screen.clientHeight);
    expect(geometry.grid.scrollWidth).toBeLessThanOrEqual(geometry.grid.clientWidth);
    expect(geometry.grid.scrollHeight).toBeLessThanOrEqual(geometry.grid.clientHeight);
    expect(geometry.buttons).toHaveLength(10);

    for (const cell of geometry.cells) {
      expect(cell.left).toBeGreaterThanOrEqual(geometry.grid.left - 0.5);
      expect(cell.top).toBeGreaterThanOrEqual(geometry.grid.top - 0.5);
      expect(cell.right).toBeLessThanOrEqual(geometry.grid.right + 0.5);
      expect(cell.bottom).toBeLessThanOrEqual(geometry.grid.bottom + 0.5);
      expect(cell.scrollWidth).toBeLessThanOrEqual(cell.clientWidth);
      expect(cell.scrollHeight).toBeLessThanOrEqual(cell.clientHeight);
    }
    for (const button of geometry.buttons) {
      expect(button.clientWidth).toBeGreaterThanOrEqual(44);
      expect(button.clientHeight).toBeGreaterThanOrEqual(44);
      expect(button.scrollWidth).toBeLessThanOrEqual(button.clientWidth);
      expect(button.scrollHeight).toBeLessThanOrEqual(button.clientHeight);
    }

    expect(runtime.commandRequests).toEqual([]);
    expect(runtime.pageErrors).toEqual([]);
  });
}
