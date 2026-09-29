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
  test(`${target.name}: 27 local-preview shades fit and never submit movement`, async ({ page }) => {
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
    await expect(page.getByText(/preview only · no shade commands/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Open all' })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Close all' })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Open all' })).toHaveCSS('background-color', 'rgb(45, 69, 84)');
    await expect(page.getByRole('button', { name: 'Open all' })).toHaveCSS('opacity', '1');
    await expect(page.getByRole('button', { name: 'Kitchen + Living Room' })).toHaveCSS('background-color', 'rgb(55, 85, 104)');
    const master = page.getByRole('article', { name: 'All 27 shades: Local preview' });
    await expect(master).toBeVisible();
    await expect(master.locator('.position-value')).toHaveText(/^(?:\d{1,2}|100)%$/);
    await expect(page.getByRole('slider', { name: 'All 27 shades local preview percent open' })).toBeEnabled();
    const tones = await page.locator('.zone:first-child .shade-card').evaluateAll((cards) => cards.slice(0, 3)
      .map((card) => getComputedStyle(card).backgroundImage));
    expect(tones[1]).not.toBe(tones[2]);
    expect(await master.evaluate((card) => getComputedStyle(card).backgroundColor)).not.toBe('rgba(0, 0, 0, 0)');
    for (const [view, zones, count, last] of [
      ['Kitchen + Living Room', ['Kitchen', 'Living Room'], 17, 'Living Room Shade 17'],
      ['Bathroom + Bedroom', ['Bathroom', 'Bedroom'], 10, 'Bedroom Shade 27'],
    ]) {
      await page.getByRole('button', { name: view }).click();
      await expect(page.locator('.shade-grid .shade-card')).toHaveCount(count + zones.length);
      await expect(page.locator('.master-card')).toHaveCount(1);
      await expect(page.getByRole('article', { name: `${last}: Local preview` })).toBeVisible();
      for (const zone of zones) {
        await expect(page.getByRole('heading', { name: zone, exact: true })).toBeVisible();
        await expect(page.getByRole('button', { name: `Open ${zone}` })).toBeEnabled();
        await expect(page.getByRole('button', { name: `Close ${zone}` })).toBeEnabled();
        await expect(page.getByRole('slider', { name: `${zone} group local preview percent open` })).toBeEnabled();
      }
      await expect(page.locator('input[type="range"]')).toHaveCount(count + zones.length + 1);
      await expect(page.locator('input[type="range"]:not(:disabled)')).toHaveCount(count + zones.length + 1);

      const geometry = await page.evaluate(() => {
        const viewport = { width: document.documentElement.clientWidth, height: document.documentElement.clientHeight };
        const pageLayout = document.querySelector('.shades-page');
        const cards = [...document.querySelectorAll('.shade-grid .shade-card')].map((card) => {
          const box = card.getBoundingClientRect();
          return { left: box.left, top: box.top, right: box.right, bottom: box.bottom,
            width: box.width, scrollWidth: card.scrollWidth, clientWidth: card.clientWidth };
        });
        const window = document.querySelector('.shade-grid .window-glass').getBoundingClientRect();
        const control = document.querySelector('.shade-grid .window-control').getBoundingClientRect();
        const slider = document.querySelector('.shade-grid input[type="range"]').getBoundingClientRect();
        const master = document.querySelector('.master-card').getBoundingClientRect();
        const masterControl = document.querySelector('.master-card .window-control').getBoundingClientRect();
        const masterSlider = document.querySelector('.master-card input[type="range"]').getBoundingClientRect();
        return { viewport, documentWidth: document.documentElement.scrollWidth, documentHeight: document.documentElement.scrollHeight,
          pageHeight: pageLayout.clientHeight, pageScrollHeight: pageLayout.scrollHeight,
          cards, window: { width: window.width, height: window.height }, controlWidth: control.width,
          sliderHeight: slider.height, sliderWidth: slider.width,
          master: { left: master.left, right: master.right, top: master.top, bottom: master.bottom },
          masterControlWidth: masterControl.width, masterSliderHeight: masterSlider.height, masterSliderWidth: masterSlider.width,
          allSlidersFillControls: [...document.querySelectorAll('.window-control input[type="range"]')]
            .every((input) => Math.abs(input.getBoundingClientRect().width - input.parentElement.getBoundingClientRect().width) < 1),
          vertical: getComputedStyle(document.querySelector('.shade-grid input[type="range"]')).writingMode,
          truncatedCardLabels: [...document.querySelectorAll('.card-name')]
            .filter((label) => label.scrollWidth > label.clientWidth).map((label) => label.textContent) };
      });
      expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewport.width);
      expect(geometry.documentHeight).toBeLessThanOrEqual(geometry.viewport.height);
      expect(geometry.cards.every((card) => card.left >= 0 && card.right <= geometry.viewport.width)).toBe(true);
      expect(geometry.cards.every((card) => card.scrollWidth <= card.clientWidth)).toBe(true);
      expect(geometry.cards.every((card) => card.width <= (target.width < 900 ? 49 : 57))).toBe(true);
      expect(geometry.window.width).toBe(target.width < 900 ? 16 : 18);
      expect(Math.abs(geometry.sliderWidth - geometry.controlWidth)).toBeLessThan(1);
      expect(Math.abs(geometry.masterSliderWidth - geometry.masterControlWidth)).toBeLessThan(1);
      expect(geometry.allSlidersFillControls).toBe(true);
      expect(geometry.window.height).toBeGreaterThanOrEqual(75);
      expect(geometry.sliderHeight).toBeGreaterThanOrEqual(75);
      if (target.name === 'lenovo-m9') expect(geometry.sliderHeight).toBeGreaterThanOrEqual(180);
      if (target.name === 'laptop-floor') expect(geometry.sliderHeight).toBeGreaterThanOrEqual(95);
      if (target.width < 900) {
        expect(geometry.sliderHeight).toBeGreaterThanOrEqual(125);
        expect(geometry.pageScrollHeight).toBeGreaterThan(geometry.pageHeight);
        await page.locator('.shades-page').evaluate((element) => { element.scrollTop = element.scrollHeight; });
        const last = await page.locator('.zone:last-child .shade-card:last-child').boundingBox();
        const screenBottom = await page.locator('.screen').evaluate((element) => element.getBoundingClientRect().bottom);
        expect(last.y + last.height).toBeLessThanOrEqual(screenBottom + 1);
      } else {
        expect(geometry.pageScrollHeight).toBeLessThanOrEqual(geometry.pageHeight);
        expect(geometry.cards.every((card) => card.top >= 0 && card.bottom <= geometry.viewport.height)).toBe(true);
        expect(geometry.master.bottom).toBeLessThanOrEqual(geometry.viewport.height);
      }
      expect(geometry.masterSliderHeight).toBeGreaterThan(geometry.sliderHeight);
      expect(geometry.master.left).toBeGreaterThanOrEqual(0);
      expect(geometry.master.right).toBeLessThanOrEqual(geometry.viewport.width);
      expect(geometry.master.top).toBeGreaterThanOrEqual(0);
      expect(geometry.vertical).toBe('vertical-lr');
      expect(geometry.truncatedCardLabels).toEqual([]);
    }
    expect(writes).toEqual([]);
    expect(errors).toEqual([]);
  });
}

test('preview sliders update individual, zone and all positions without shade commands', async ({ page }) => {
  const writes = [];
  page.on('request', (request) => {
    if (request.method() !== 'GET' && !request.url().includes('/api/shades-preview')) writes.push(request.url());
  });
  await page.setViewportSize({ width: 1340, height: 800 });
  await page.route('**/config.json', (route) => route.fulfill({ json: { openhabUrl: '/fixture-openhab', apiToken: 'fixture', staleBannerSeconds: 90 } }));
  await page.route('**/fixture-openhab/rest/items?*', (route) => route.fulfill({ json: [] }));
  await page.route('**/fixture-openhab/rest/things', (route) => route.fulfill({ json: [] }));
  await page.goto(`${baseURL}#/shades`, { waitUntil: 'domcontentloaded' });

  const setRange = async (name, value) => page.getByRole('slider', { name }).evaluate((slider, percent) => {
    slider.value = String(percent);
    slider.dispatchEvent(new Event('input', { bubbles: true }));
    slider.dispatchEvent(new Event('change', { bubbles: true }));
  }, value);
  const master = page.getByRole('article', { name: 'All 27 shades: Local preview' });
  const kitchen = page.getByRole('article', { name: 'Kitchen Shade 01: Local preview' });
  const living = page.getByRole('article', { name: 'Living Room Shade 09: Local preview' });

  await setRange('All 27 shades local preview percent open', 76);
  await expect(master.locator('.position-value')).toHaveText('76%');
  await expect(kitchen.locator('.position-value')).toHaveText('76%');
  await expect(living.locator('.position-value')).toHaveText('76%');

  await setRange('Kitchen Shade 01 local preview percent open', 45);
  await expect(kitchen.locator('.position-value')).toHaveText('45%');
  await expect(master.locator('.position-caption')).toHaveText('mixed');
  await expect(page.getByRole('article', { name: 'Kitchen group: Local preview' }).locator('.position-caption')).toHaveText('mixed');
  await expect(living.locator('.position-value')).toHaveText('76%');

  await setRange('Kitchen group local preview percent open', 25);
  await expect(kitchen.locator('.position-value')).toHaveText('25%');
  await expect(page.getByRole('article', { name: 'Kitchen Shade 08: Local preview' }).locator('.position-value')).toHaveText('25%');
  await expect(living.locator('.position-value')).toHaveText('76%');

  await setRange('All 27 shades local preview percent open', 100);
  await expect(master.locator('.position-value')).toHaveText('100%');
  await expect(kitchen.locator('.position-value')).toHaveText('100%');
  await expect(living.locator('.position-value')).toHaveText('100%');

  const closeKitchen = page.getByRole('button', { name: 'Close Kitchen' });
  await closeKitchen.click();
  await expect(closeKitchen).toHaveClass(/pressed/);
  await expect(kitchen.locator('.position-value')).toHaveText('0%');
  await expect(living.locator('.position-value')).toHaveText('100%');
  await expect(master.locator('.position-caption')).toHaveText('mixed');
  await page.getByRole('button', { name: 'Open Kitchen' }).click();
  await expect(kitchen.locator('.position-value')).toHaveText('100%');
  await page.getByRole('button', { name: 'Close all' }).click();
  await expect(master.locator('.position-value')).toHaveText('0%');
  const openAll = page.getByRole('button', { name: 'Open all' });
  await openAll.click();
  await expect(openAll).toHaveClass(/pressed/);
  await expect(master.locator('.position-value')).toHaveText('100%');
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('article', { name: 'All 27 shades: Local preview' }).locator('.position-value')).toHaveText('100%');
  expect(writes).toEqual([]);
});

test('preview positions synchronize between separate tablet and laptop clients', async ({ browser }) => {
  const laptop = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const tablet = await browser.newContext({ viewport: { width: 1340, height: 800 } });
  const a = await laptop.newPage();
  const b = await tablet.newPage();
  const actualCommands = [];
  for (const page of [a, b]) {
    page.on('request', (request) => {
      if (request.method() !== 'GET' && !request.url().includes('/api/shades-preview')) actualCommands.push(request.url());
    });
    await page.route('**/config.json', (route) => route.fulfill({ json: { openhabUrl: '/fixture-openhab', apiToken: 'fixture', staleBannerSeconds: 90 } }));
    await page.route('**/fixture-openhab/rest/items?*', (route) => route.fulfill({ json: [] }));
    await page.route('**/fixture-openhab/rest/things', (route) => route.fulfill({ json: [] }));
    await page.goto(`${baseURL}#/shades`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByText('Shared preview only · no shade commands')).toBeVisible();
  }
  const kitchenA = a.getByRole('article', { name: 'Kitchen Shade 01: Local preview' });
  const kitchenB = b.getByRole('article', { name: 'Kitchen Shade 01: Local preview' });
  await a.getByRole('button', { name: 'Close Kitchen' }).click();
  await expect(kitchenB.locator('.position-value')).toHaveText('0%');
  await b.getByRole('slider', { name: 'Kitchen Shade 01 local preview percent open' }).evaluate((slider) => {
    slider.value = '64';
    slider.dispatchEvent(new Event('input', { bubbles: true }));
    slider.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await expect(kitchenA.locator('.position-value')).toHaveText('64%');
  await expect(a.getByRole('article', { name: 'Kitchen group: Local preview' }).locator('.position-caption')).toHaveText('mixed');
  const invalidStatus = await a.evaluate(async () => (await fetch('/api/shades-preview', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slots: [1, 28], openPercent: 70 }),
  })).status);
  expect(invalidStatus).toBe(400);
  await expect(kitchenB.locator('.position-value')).toHaveText('64%');
  await b.getByRole('button', { name: 'Open all' }).click();
  await expect(a.getByRole('article', { name: 'All 27 shades: Local preview' }).locator('.position-value')).toHaveText('100%');
  await expect(kitchenA.locator('.position-value')).toHaveText('100%');
  await expect(a.getByRole('article', { name: 'Living Room Shade 09: Local preview' }).locator('.position-value')).toHaveText('100%');
  expect(actualCommands).toEqual([]);
  await laptop.close();
  await tablet.close();
});

test('Lenovo touch input moves a preview shade without sending a command', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1340, height: 800 }, hasTouch: true });
  const page = await context.newPage();
  const writes = [];
  page.on('request', (request) => {
    if (request.method() !== 'GET' && !request.url().includes('/api/shades-preview')) writes.push(request.url());
  });
  await page.route('**/config.json', (route) => route.fulfill({ json: { openhabUrl: '/fixture-openhab', apiToken: 'fixture', staleBannerSeconds: 90 } }));
  await page.route('**/fixture-openhab/rest/items?*', (route) => route.fulfill({ json: [] }));
  await page.route('**/fixture-openhab/rest/things', (route) => route.fulfill({ json: [] }));
  await page.goto(`${baseURL}#/shades`, { waitUntil: 'domcontentloaded' });

  const kitchen = page.getByRole('article', { name: 'Kitchen Shade 01: Local preview' });
  const slider = kitchen.getByRole('slider', { name: 'Kitchen Shade 01 local preview percent open' });
  const box = await slider.boundingBox();
  expect(box.height).toBeGreaterThanOrEqual(180);
  await page.touchscreen.tap(box.x + 2, box.y + box.height * 0.15);
  const high = Number(await slider.inputValue());
  expect(high).toBeGreaterThan(75);
  await expect(kitchen.locator('.position-value')).toHaveText(`${high}%`);
  await page.touchscreen.tap(box.x + box.width - 2, box.y + box.height * 0.85);
  const low = Number(await slider.inputValue());
  expect(low).toBeLessThan(25);
  await expect(kitchen.locator('.position-value')).toHaveText(`${low}%`);
  await page.setViewportSize({ width: 800, height: 600 });
  const dragBox = await slider.boundingBox();
  const dragX = dragBox.x + 2;
  const dragY = dragBox.y + dragBox.height * 0.8;
  const initialScroll = await page.locator('.shades-page').evaluate((element) => element.scrollTop);
  const cdp = await context.newCDPSession(page);
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: dragX, y: dragY, id: 1 }] });
  await page.evaluate(() => new Promise(requestAnimationFrame));
  const dragValues = [Number(await slider.inputValue())];
  for (const offset of [-25, -50, -75, -100]) {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: dragX, y: dragY + offset, id: 1 }] });
    await page.evaluate(() => new Promise(requestAnimationFrame));
    dragValues.push(Number(await slider.inputValue()));
    await expect(kitchen.locator('.position-value')).toHaveText(`${dragValues.at(-1)}%`);
  }
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await page.evaluate(() => new Promise(requestAnimationFrame));
  expect(dragValues[0]).toBeLessThan(35);
  expect(dragValues.at(-1)).toBeGreaterThan(65);
  expect(dragValues.every((value, index) => index === 0 || value >= dragValues[index - 1])).toBe(true);
  await expect(kitchen.locator('.position-value')).toHaveText(`${dragValues.at(-1)}%`);
  const rightX = dragBox.x + dragBox.width - 2;
  const rightStartY = dragBox.y + dragBox.height * 0.2;
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: rightX, y: rightStartY, id: 2 }] });
  await page.evaluate(() => new Promise(requestAnimationFrame));
  const rightDragValues = [Number(await slider.inputValue())];
  for (const offset of [25, 50, 75, 100]) {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: rightX, y: rightStartY + offset, id: 2 }] });
    await page.evaluate(() => new Promise(requestAnimationFrame));
    rightDragValues.push(Number(await slider.inputValue()));
    await expect(kitchen.locator('.position-value')).toHaveText(`${rightDragValues.at(-1)}%`);
  }
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await page.evaluate(() => new Promise(requestAnimationFrame));
  expect(rightDragValues[0]).toBeGreaterThan(65);
  expect(rightDragValues.at(-1)).toBeLessThan(35);
  expect(rightDragValues.every((value, index) => index === 0 || value <= rightDragValues[index - 1])).toBe(true);
  expect(await page.locator('.shades-page').evaluate((element) => element.scrollTop)).toBe(initialScroll);
  expect(writes).toEqual([]);
  await context.close();
});

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
