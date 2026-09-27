import { expect, test } from '@playwright/test';
import { createServer } from 'vite';

const TARGETS = [
  { name: 'lenovo-m9', width: 1340, height: 800 },
  { name: 'laptop-floor', width: 1280, height: 720 },
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
  test(`${target.name}: 26 uncommissioned shades fit and never submit movement`, async ({ page }) => {
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
    await expect(page.getByText('26 planned · 0 mapped · 0 reporting')).toBeVisible();
    await expect(page.locator('.shade-card')).toHaveCount(13);
    await expect(page.getByRole('article', { name: /Shade 01: Awaiting Item mapping/ })).toBeVisible();
    await page.getByRole('button', { name: '14–26' }).click();
    await expect(page.locator('.shade-card')).toHaveCount(13);
    await expect(page.getByRole('article', { name: /Shade 26: Awaiting Item mapping/ })).toBeVisible();

    const geometry = await page.evaluate(() => {
      const viewport = { width: document.documentElement.clientWidth, height: document.documentElement.clientHeight };
      const cards = [...document.querySelectorAll('.shade-card')].map((card) => {
        const box = card.getBoundingClientRect();
        return { left: box.left, top: box.top, right: box.right, bottom: box.bottom, scrollWidth: card.scrollWidth, clientWidth: card.clientWidth };
      });
      return { viewport, documentWidth: document.documentElement.scrollWidth, documentHeight: document.documentElement.scrollHeight, cards };
    });
    expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewport.width);
    expect(geometry.documentHeight).toBeLessThanOrEqual(geometry.viewport.height);
    expect(geometry.cards.every((card) => card.left >= 0 && card.top >= 0 && card.right <= geometry.viewport.width && card.bottom <= geometry.viewport.height)).toBe(true);
    expect(geometry.cards.every((card) => card.scrollWidth <= card.clientWidth)).toBe(true);
    expect(writes).toEqual([]);
    expect(errors).toEqual([]);
  });
}
