import { expect, test } from '@playwright/test';
import { createServer } from 'vite';

const TARGETS = [
  { name: 'lenovo-m9', width: 1340, height: 800 },
  { name: 'laptop-floor', width: 1280, height: 720 },
  { name: 'compact-tablet', width: 900, height: 800 },
  { name: 'scaled-lenovo-landscape', width: 800, height: 600 },
  { name: 'narrow-landscape', width: 700, height: 600 },
];

let server;
let baseURL;

test.beforeAll(async () => {
  server = await createServer({ root: process.cwd(), logLevel: 'error', server: { port: 0, strictPort: false } });
  await server.listen();
  baseURL = server.resolvedUrls.local[0];
});

test.afterAll(async () => { await server?.close(); });

for (const target of TARGETS) {
  test(`${target.name}: 27 room-grouped uncommissioned shades fit and never submit movement`, async ({ page }) => {
    const writes = [];
    const errors = [];
    page.on('request', (request) => { if (request.method() !== 'GET') writes.push(request.url()); });
    page.on('pageerror', (error) => errors.push(error.message));
    await page.setViewportSize({ width: target.width, height: target.height });
    await page.route('**/config.json', (route) => route.fulfill({ json: { openhabUrl: '/fixture-openhab', apiToken: 'fixture', staleBannerSeconds: 90 } }));
    await page.route('**/fixture-openhab/rest/items?*', (route) => route.fulfill({ json: [] }));
    await page.route('**/fixture-openhab/rest/things', (route) => route.fulfill({ json: [] }));
    await page.goto(`${baseURL}#/shades`, { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('heading', { name: 'Window shades' })).toBeVisible();
    await expect(page.getByText('27 planned · 0 mapped · 0 reporting')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Open all' })).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Close all' })).toBeDisabled();
    const master = page.getByRole('article', { name: 'All 27 shades: Position unavailable' });
    await expect(master).toBeVisible();
    await expect(master.locator('.position-value')).toHaveText('—');
    await expect(page.getByRole('slider', { name: 'All 27 shades percent open; movement disabled until commissioning' })).toBeDisabled();
    for (const [view, zones, count, last] of [
      ['Kitchen + Living Room', ['Kitchen', 'Living Room'], 17, 'Living Room Shade 17'],
      ['Bathroom + Bedroom', ['Bathroom', 'Bedroom'], 10, 'Bedroom Shade 27'],
    ]) {
      await page.getByRole('button', { name: view }).click();
      await expect(page.locator('.shade-grid .shade-card')).toHaveCount(count + zones.length);
      await expect(page.locator('.master-card')).toHaveCount(1);
      await expect(page.getByRole('article', { name: `${last}: Awaiting Item mapping` })).toBeVisible();
      for (const zone of zones) {
        await expect(page.getByRole('heading', { name: zone, exact: true })).toBeVisible();
        await expect(page.getByRole('button', { name: `Open ${zone}` })).toBeDisabled();
        await expect(page.getByRole('button', { name: `Close ${zone}` })).toBeDisabled();
        await expect(page.getByRole('slider', { name: `${zone} group percent open; movement disabled until commissioning` })).toBeDisabled();
      }
      await expect(page.locator('input[type="range"]')).toHaveCount(count + zones.length + 1);
      await expect(page.locator('input[type="range"]:not(:disabled)')).toHaveCount(0);

      const geometry = await page.evaluate(() => {
        const viewport = { width: document.documentElement.clientWidth, height: document.documentElement.clientHeight };
        const cards = [...document.querySelectorAll('.shade-grid .shade-card')].map((card) => {
          const box = card.getBoundingClientRect();
          return { left: box.left, top: box.top, right: box.right, bottom: box.bottom,
            width: box.width, scrollWidth: card.scrollWidth, clientWidth: card.clientWidth };
        });
        const window = document.querySelector('.shade-grid .window-glass').getBoundingClientRect();
        const slider = document.querySelector('.shade-grid input[type="range"]').getBoundingClientRect();
        const master = document.querySelector('.master-card').getBoundingClientRect();
        const masterSlider = document.querySelector('.master-card input[type="range"]').getBoundingClientRect();
        return { viewport, documentWidth: document.documentElement.scrollWidth, documentHeight: document.documentElement.scrollHeight,
          cards, window: { width: window.width, height: window.height }, sliderHeight: slider.height,
          master: { left: master.left, right: master.right, top: master.top, bottom: master.bottom },
          masterSliderHeight: masterSlider.height,
          vertical: getComputedStyle(document.querySelector('.shade-grid input[type="range"]')).writingMode,
          truncatedCardLabels: [...document.querySelectorAll('.card-name')]
            .filter((label) => label.scrollWidth > label.clientWidth).map((label) => label.textContent) };
      });
      expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewport.width);
      expect(geometry.documentHeight).toBeLessThanOrEqual(geometry.viewport.height);
      expect(geometry.cards.every((card) => card.left >= 0 && card.top >= 0 && card.right <= geometry.viewport.width && card.bottom <= geometry.viewport.height)).toBe(true);
      expect(geometry.cards.every((card) => card.scrollWidth <= card.clientWidth)).toBe(true);
      expect(geometry.cards.every((card) => card.width <= (target.width < 900 ? 47 : 53))).toBe(true);
      expect(geometry.window.width).toBe(target.width < 900 ? 18 : 20);
      expect(geometry.window.height).toBeGreaterThanOrEqual(75);
      expect(geometry.sliderHeight).toBeGreaterThanOrEqual(75);
      if (target.name === 'lenovo-m9') expect(geometry.sliderHeight).toBeGreaterThanOrEqual(120);
      if (target.name === 'laptop-floor') expect(geometry.sliderHeight).toBeGreaterThanOrEqual(95);
      expect(geometry.masterSliderHeight).toBeGreaterThan(geometry.sliderHeight);
      expect(geometry.master.left).toBeGreaterThanOrEqual(0);
      expect(geometry.master.right).toBeLessThanOrEqual(geometry.viewport.width);
      expect(geometry.master.top).toBeGreaterThanOrEqual(0);
      expect(geometry.master.bottom).toBeLessThanOrEqual(geometry.viewport.height);
      expect(geometry.vertical).toBe('vertical-lr');
      expect(geometry.truncatedCardLabels).toEqual([]);
    }
    expect(writes).toEqual([]);
    expect(errors).toEqual([]);
  });
}

test('short landscape tablets can scroll to the last vertical control', async ({ page }) => {
  await page.setViewportSize({ width: 800, height: 480 });
  await page.goto(`${baseURL}#/shades`, { waitUntil: 'domcontentloaded' });
  const pageLayout = page.locator('.shades-page');
  await expect(pageLayout).toBeVisible();
  const scroll = await pageLayout.evaluate((element) => ({ height: element.clientHeight, content: element.scrollHeight }));
  expect(scroll.content).toBeGreaterThan(scroll.height);
  await pageLayout.evaluate((element) => { element.scrollTop = element.scrollHeight; });
  const lastWindow = page.locator('.zone').last().locator('.window-glass').last();
  const windowBox = await lastWindow.boundingBox();
  const screenBottom = await page.locator('.screen').evaluate((element) => element.getBoundingClientRect().bottom);
  expect(windowBox.y + windowBox.height).toBeLessThanOrEqual(screenBottom);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(800);
});
