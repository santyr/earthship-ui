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

test('Bedroom never borrows the relocated Office Hallway sensor or held Item', async ({ page }) => {
  const now = Date.now();
  await page.clock.install({ time: new Date(now) });
  const epoch = '831b737c-ab25-48d7-9a90-889746e56410';
  const snapshot = JSON.stringify({ version: 1, streamEpoch: epoch, records: { bedroom: {
    version: 1, streamEpoch: epoch, model: 'AmbientWeather-WH31E', sensorId: 223,
    field: 'tempinf', status: 'valid', reason: 'accepted', temperatureF: 71.4,
    receivedAt: new Date(now).toISOString(), recordedAt: new Date(now).toISOString(),
    validUntil: new Date(now + 120_000).toISOString(),
  } } });
  await page.setViewportSize({ width: 1340, height: 800 });
  await page.route('**/config.json', route => route.fulfill({ json: { openhabUrl: '/fixture-openhab', apiToken: 'fixture' } }));
  await page.route('**/fixture-openhab/rest/items?*', route => route.fulfill({ json: [
    { name: 'Weather_Temperature_Evidence_JSON', type: 'String', state: snapshot },
    { name: 'AmbientWeatherWS2902A_IndoorSensor_Temperature', type: 'Number', state: '69' },
    { name: 'Bedroom_Temperature', type: 'Number:Temperature', state: '71.4 °F' },
  ] }));
  await page.route('**/fixture-openhab/rest/things', route => route.fulfill({ json: [] }));
  await page.route('**/fixture-openhab/rest/events?*', route => route.fulfill({
    contentType: 'text/event-stream', body: ': fixture\n\n',
  }));
  await page.goto(`${baseURL}#/shades`);
  await page.getByRole('button', { name: 'Bathroom + Bedroom', exact: true }).click();
  const label = page.locator('[aria-label="Bedroom shades"] .sensor-evidence');
  await expect(label).toHaveText('Zone temperature pending');
  await page.clock.fastForward(120_001);
  await expect(label).toHaveText('Zone temperature pending');
});

test('shared preview accepts all 26 slots but rejects the removed 27th shade', async ({ request }) => {
  const headers = { Origin: new URL(baseURL).origin };
  const valid = await request.post(`${baseURL}api/shades-preview`, {
    headers, data: { slots: Array.from({ length: 26 }, (_, i) => i + 1), openPercent: 50 },
  });
  expect(valid.status()).toBe(200);
  const snapshot = await valid.json();
  expect(snapshot.positions).toEqual(Array(26).fill(50));
  const invalid = await request.post(`${baseURL}api/shades-preview`, {
    headers, data: { slots: [27], openPercent: 0 },
  });
  expect(invalid.status()).toBe(400);
  const next = await request.post(`${baseURL}api/shades-preview`, {
    headers, data: { slots: [26], openPercent: 50 },
  });
  const unchanged = await next.json();
  expect(unchanged.positions).toEqual(Array(26).fill(50));
  expect(unchanged.revision).toBe(snapshot.revision + 1);
});

for (const target of TARGETS) {
  test(`${target.name}: 26 local-preview shades fit and never submit movement`, async ({ page }) => {
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
    await expect(page.getByText(/preview only · no shade commands/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Open all' })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Close all' })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Open all' })).toHaveCSS('background-color', 'rgb(76, 113, 132)');
    await expect(page.getByRole('button', { name: 'Open all' })).toHaveCSS('opacity', '1');
    await expect(page.getByRole('button', { name: 'Kitchen + Living Room' })).toHaveCSS('background-color', 'rgb(76, 113, 132)');
    const master = page.getByRole('article', { name: 'All 26 shades: Local preview' });
    await expect(master).toBeVisible();
    await expect(master.locator('.position-value')).toHaveText(/^(?:\d{1,2}|100)%$/);
    await expect(page.getByRole('slider', { name: 'All 26 shades local preview percent open' })).toBeEnabled();
    const tones = await page.locator('.zone:first-child .shade-card').evaluateAll((cards) => cards.slice(0, 3)
      .map((card) => getComputedStyle(card).backgroundImage));
    expect(tones[1]).not.toBe(tones[2]);
    expect(await master.evaluate((card) => getComputedStyle(card).backgroundColor)).not.toBe('rgba(0, 0, 0, 0)');
    for (const [view, zones, count, last] of [
      ['Kitchen + Living Room', ['Kitchen', 'Living Room'], 17, 'Living Room Shade 17'],
      ['Bathroom + Bedroom', ['Bathroom', 'Bedroom'], 9, 'Bedroom Shade 26'],
    ]) {
      await page.getByRole('button', { name: view }).click();
      await expect(page.locator('.shade-grid .shade-card')).toHaveCount(count + zones.length);
      await expect(page.locator('.master-card')).toHaveCount(1);
      await expect(page.getByRole('article', { name: `${last}: Local preview` })).toBeVisible();
      for (const zone of zones) {
        await expect(page.getByRole('heading', { name: zone, exact: true })).toBeVisible();
        await expect(page.getByRole('button', { name: `Open ${zone}` })).toBeEnabled();
        await expect(page.getByRole('button', { name: `Close ${zone}` })).toBeEnabled();
        await expect(page.getByRole('button', { name: `Open ${zone}` })).toHaveCSS('background-color', 'rgb(76, 113, 132)');
        await expect(page.getByRole('button', { name: `Open ${zone}` })).toHaveCSS('opacity', '1');
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
    await page.getByRole('button', { name: 'Set shade percentage' }).click();
    const editor = page.getByRole('dialog', { name: 'Set shade percentage' });
    await expect(editor).toBeVisible();
    await expect(editor.locator('option')).toHaveCount(31);
    await expect(editor.getByRole('option', { name: 'Bathroom (all 4)', exact: true })).toHaveCount(1);
    await expect(editor.getByRole('option', { name: 'Bedroom Shade 22', exact: true })).toHaveCount(1);
    await expect(editor.getByRole('option', { name: 'Bedroom Shade 27', exact: true })).toHaveCount(0);
    const editorGeometry = await editor.evaluate((element) => {
      const box = element.getBoundingClientRect();
      return { right: box.right, bottom: box.bottom, left: box.left, top: box.top,
        fits: element.scrollWidth <= element.clientWidth,
        touchHeights: [...element.querySelectorAll('button,input,select')].map((control) => control.getBoundingClientRect().height) };
    });
    expect(editorGeometry.left).toBeGreaterThanOrEqual(0);
    expect(editorGeometry.top).toBeGreaterThanOrEqual(0);
    expect(editorGeometry.right).toBeLessThanOrEqual(target.width);
    expect(editorGeometry.bottom).toBeLessThanOrEqual(target.height);
    expect(editorGeometry.fits).toBe(true);
    expect(editorGeometry.touchHeights.every((height) => height >= 44)).toBe(true);
    await editor.getByRole('button', { name: 'Cancel' }).click();
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
  const master = page.getByRole('article', { name: 'All 26 shades: Local preview' });
  const kitchen = page.getByRole('article', { name: 'Kitchen Shade 01: Local preview' });
  const living = page.getByRole('article', { name: 'Living Room Shade 09: Local preview' });

  await setRange('All 26 shades local preview percent open', 76);
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

  await setRange('All 26 shades local preview percent open', 100);
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
  await expect(page.getByRole('article', { name: 'All 26 shades: Local preview' }).locator('.position-value')).toHaveText('100%');
  expect(writes).toEqual([]);
});

test('precise preview editor scopes percentages and steps without motor commands', async ({ page }) => {
  const commands = [];
  page.on('request', (request) => {
    if (request.method() !== 'GET' && !request.url().includes('/api/shades-preview')) commands.push(request.url());
  });
  await page.setViewportSize({ width: 1340, height: 800 });
  await page.route('**/config.json', (route) => route.fulfill({ json: { openhabUrl: '/fixture-openhab', apiToken: 'fixture', staleBannerSeconds: 90 } }));
  await page.route('**/fixture-openhab/rest/items?*', (route) => route.fulfill({ json: [] }));
  await page.route('**/fixture-openhab/rest/things', (route) => route.fulfill({ json: [] }));
  await page.goto(`${baseURL}#/shades`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Shared preview only · no shade commands')).toBeVisible();
  await page.getByRole('button', { name: 'Close all', exact: true }).click();
  const kitchen = page.getByRole('article', { name: 'Kitchen Shade 01: Local preview' });
  const living = page.getByRole('article', { name: 'Living Room Shade 09: Local preview' });
  const launch = page.getByRole('button', { name: 'Set shade percentage' });
  await launch.click();
  const editor = page.getByRole('dialog', { name: 'Set shade percentage' });
  const percent = editor.getByRole('spinbutton', { name: 'Percent open' });
  const target = editor.getByRole('combobox', { name: 'Shades to adjust' });
  const apply = editor.getByRole('button', { name: 'Apply preview' });
  await expect(percent).toHaveValue('0');
  await target.selectOption({ label: 'Living Room Shade 09' });
  await percent.fill('47');
  await editor.getByRole('button', { name: 'Open 5% more' }).click();
  await expect(percent).toHaveValue('52');
  await editor.getByRole('button', { name: 'Close 5% more' }).click();
  await expect(percent).toHaveValue('47');
  await expect(living.locator('.position-value')).toHaveText('0%');
  await percent.fill('47.5');
  await expect(apply).toBeDisabled();
  await percent.fill('101');
  await expect(apply).toBeDisabled();
  await percent.fill('');
  await expect(apply).toBeDisabled();
  await percent.fill('47');
  await apply.click();
  await expect(editor).not.toBeVisible();
  await expect(living.locator('.position-value')).toHaveText('47%');
  await expect(kitchen.locator('.position-value')).toHaveText('0%');
  await expect(launch).toBeFocused();

  await launch.click();
  await expect(editor.getByText('Mixed positions — choose a percentage.')).toBeVisible();
  await expect(percent).toHaveValue('');
  await expect(editor.getByRole('button', { name: 'Open 5% more' })).toBeDisabled();
  await target.selectOption({ label: 'Kitchen (all 8)' });
  await percent.fill('99');
  await editor.getByRole('button', { name: 'Open 5% more' }).click();
  await expect(percent).toHaveValue('100');
  await apply.click();
  await expect(kitchen.locator('.position-value')).toHaveText('100%');
  await expect(page.getByRole('article', { name: 'Kitchen Shade 08: Local preview' }).locator('.position-value')).toHaveText('100%');
  await expect(living.locator('.position-value')).toHaveText('47%');

  await launch.click();
  await editor.getByRole('button', { name: 'Open fully' }).click();
  await editor.getByRole('button', { name: 'Cancel' }).click();
  await expect(living.locator('.position-value')).toHaveText('47%');
  await launch.click();
  await editor.getByRole('button', { name: 'Close fully' }).click();
  await page.keyboard.press('Escape');
  await expect(editor).not.toBeVisible();
  await expect(living.locator('.position-value')).toHaveText('47%');
  await launch.click();
  await editor.getByRole('button', { name: 'Close fully' }).click();
  await editor.getByRole('button', { name: 'Close 5% more' }).click();
  await expect(percent).toHaveValue('0');
  await apply.click();
  await expect(kitchen.locator('.position-value')).toHaveText('0%');
  await expect(living.locator('.position-value')).toHaveText('0%');
  expect(commands).toEqual([]);
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
  await b.getByRole('button', { name: 'Set shade percentage' }).click();
  const editor = b.getByRole('dialog', { name: 'Set shade percentage' });
  await editor.getByRole('combobox', { name: 'Shades to adjust' }).selectOption({ label: 'Kitchen Shade 01' });
  await editor.getByRole('spinbutton', { name: 'Percent open' }).fill('61');
  await editor.getByRole('button', { name: 'Apply preview' }).click();
  await expect(kitchenA.locator('.position-value')).toHaveText('61%');
  await expect(a.getByRole('article', { name: 'Kitchen group: Local preview' }).locator('.position-caption')).toHaveText('mixed');
  const invalidStatus = await a.evaluate(async () => (await fetch('/api/shades-preview', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slots: [1, 28], openPercent: 70 }),
  })).status);
  expect(invalidStatus).toBe(400);
  await expect(kitchenB.locator('.position-value')).toHaveText('61%');
  await b.getByRole('button', { name: 'Open all' }).click();
  await expect(a.getByRole('article', { name: 'All 26 shades: Local preview' }).locator('.position-value')).toHaveText('100%');
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
