import { test as base, expect } from '@playwright/test';
import { createServer } from 'vite';

// This suite's policy writes are fulfilled in-browser. No household proxy or
// motor request may escape the fixture, including in secondary clients.
process.env.OPENHAB_PROXY_TARGET = 'http://127.0.0.1:9';
delete process.env.OPENHAB_TOKEN;
const test = base.extend({
  isolatedPolicyNetwork: [async ({ context }, use) => {
    const violations = [];
    const errors = [];
    context.on('page', page => page.on('pageerror', error => errors.push(error.message)));
    await context.route('**/*', async route => {
      const request = route.request();
      const url = new URL(request.url());
      if (!baseURL || url.origin !== new URL(baseURL).origin || !['GET', 'HEAD'].includes(request.method())) {
        violations.push(`${request.method()} ${url.pathname}`);
        return route.abort('blockedbyclient');
      }
      if (url.pathname === '/config.json') return route.fulfill({ json: { openhabUrl: '/fixture-openhab', apiToken: 'fixture' } });
      if (url.pathname.startsWith('/api/')) return route.fulfill({ status: 503, json: { error: 'fixture unavailable' } });
      if (url.pathname.startsWith('/fixture-openhab/')) return route.fulfill({ json: [] });
      return route.continue();
    });
    await use();
    expect(violations, 'unexpected real request or mutation').toEqual([]);
    expect(errors, 'browser runtime errors').toEqual([]);
  }, { auto: true }],
});
test.use({ hasTouch: true });
let server;
let baseURL;
test.beforeAll(async () => {
  server = await createServer({ root: process.cwd(), logLevel: 'error', server: { port: 0, strictPort: false } });
  await server.listen();
  baseURL = server.resolvedUrls.local[0];
});
test.afterAll(async () => { await server?.close(); });

const labels = { automation_off: 'Manual only — automation off', nightly_override: 'Paused — nightly override',
  policy_unavailable: 'Paused — policy unavailable', override_unavailable: 'Paused — override unavailable',
  awaiting_commissioning: 'Enabled — awaiting commissioning', automation_not_released: 'Enabled — automation not released' };
function snapshot() {
  return { schemaVersion: 1, generation: 1, sessionId: 'fixture-policy-session', connected: true,
    zones: Object.fromEntries(['kitchen', 'living', 'bathroom', 'bedroom'].map(zone => [zone,
      { saved: 'OFF', authoritative: true, status: 'automation_off', label: labels.automation_off }])) };
}
const zone = (page, label) => page.getByRole('region', { name: `${label} shades`, exact: true });
const toggle = (page, label) => zone(page, label).getByRole('switch', { name: 'Automate recommendations', exact: true });

async function fixturePolicy(page, state, options = {}) {
  const writes = [];
  await page.route('**/api/shades-policy', async route => {
    const request = route.request();
    if (request.method() === 'GET') return route.fulfill({ json: state });
    expect(request.method()).toBe('POST');
    const body = request.postDataJSON();
    writes.push(body);
    if (options.beforeSave) await options.beforeSave(body);
    if (options.fail) return route.fulfill({ status: 502, json: { error: 'Save could not be verified' } });
    expect(body.expectedGeneration).toBe(state.generation);
    expect(body.expectedSessionId).toBe(state.sessionId);
    const prior = state.zones[body.zone];
    state.zones[body.zone] = { ...prior, saved: body.enabled ? 'ON' : 'OFF', authoritative: true,
      status: body.enabled ? options.paused && ['bathroom', 'bedroom'].includes(body.zone) ? 'nightly_override' : 'awaiting_commissioning' : 'automation_off',
      label: body.enabled ? options.paused && ['bathroom', 'bedroom'].includes(body.zone) ? labels.nightly_override : labels.awaiting_commissioning : labels.automation_off };
    state.generation++;
    return route.fulfill({ json: state });
  });
  return writes;
}

for (const size of [{ width: 1340, height: 800 }, { width: 1280, height: 720 }]) {
  test(`${size.width}×${size.height}: four zone headings expose bounded saved choice and backend status`, async ({ page }) => {
    await page.setViewportSize(size);
    const state = snapshot();
    state.zones.kitchen = { saved: 'ON', authoritative: true, status: 'awaiting_commissioning', label: labels.awaiting_commissioning };
    state.zones.living = { saved: 'ON', authoritative: true, status: 'automation_not_released', label: labels.automation_not_released };
    state.zones.bathroom = { saved: 'ON', authoritative: true, status: 'nightly_override', label: labels.nightly_override };
    state.zones.bedroom = { saved: null, authoritative: false, status: 'policy_unavailable', label: labels.policy_unavailable };
    const writes = await fixturePolicy(page, state);
    await page.goto(`${baseURL}#/shades`);
    for (const [view, names] of [['Kitchen + Living Room', ['Kitchen', 'Living Room']], ['Bathroom + Bedroom', ['Bathroom', 'Bedroom']]]) {
      await page.getByRole('button', { name: view, exact: true }).click();
      for (const name of names) {
        await expect(toggle(page, name)).toBeVisible();
        const geometry = await zone(page, name).locator('.zone-heading').evaluate(element => {
          const box = element.getBoundingClientRect();
          const controls = [...element.querySelectorAll('button')].map(button => {
            const rect = button.getBoundingClientRect();
            return { top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left, height: rect.height };
          });
          return { top: box.top, right: box.right, bottom: box.bottom, left: box.left,
            clipped: [...element.querySelectorAll('*')].some(child => child.scrollWidth > child.clientWidth + 1), controls };
        });
        expect(geometry.clipped).toBe(false);
        expect(geometry.right).toBeLessThanOrEqual(size.width);
        expect(geometry.bottom).toBeLessThanOrEqual(size.height);
        expect(geometry.controls.every(control => control.left >= geometry.left && control.right <= geometry.right + 1
          && control.top >= geometry.top && control.bottom <= geometry.bottom + 1)).toBe(true);
        expect(await toggle(page, name).evaluate(element => element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
      }
    }
    await expect(toggle(page, 'Bathroom')).toHaveAttribute('aria-checked', 'true');
    await expect(zone(page, 'Bathroom').getByText(labels.nightly_override, { exact: true })).toBeVisible();
    await expect(toggle(page, 'Bedroom')).toHaveAttribute('aria-checked', 'mixed');
    await expect(zone(page, 'Bedroom').getByText('Unknown', { exact: true })).toBeVisible();
    await page.reload();
    await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'true');
    expect(writes).toEqual([]);
  });
}

test('keyboard and touch save only addressed zones; enabling during override stays paused without preview writes', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  const state = snapshot();
  const writes = await fixturePolicy(page, state, { paused: true });
  const previewPositions = [25, 75, ...Array(24).fill(50)];
  await page.route('**/api/shades-preview/events', route => route.fulfill({
    contentType: 'text/event-stream', body: `data: ${JSON.stringify({ positions: previewPositions })}\n\n`,
  }));
  await page.goto(`${baseURL}#/shades`);
  await expect(page.getByRole('slider', { name: 'Kitchen Shade 01 local preview percent open', exact: true })).toHaveValue('25');
  await expect(page.getByRole('slider', { name: 'Kitchen Shade 02 local preview percent open', exact: true })).toHaveValue('75');
  for (const [view, names] of [['Kitchen + Living Room', ['Kitchen', 'Living Room']], ['Bathroom + Bedroom', ['Bathroom', 'Bedroom']]]) {
    await page.getByRole('button', { name: view, exact: true }).click();
    for (const name of names) {
      await toggle(page, name).focus();
      await toggle(page, name).press('Space');
      await expect(toggle(page, name)).toHaveAttribute('aria-checked', 'true');
      await expect(zone(page, name).getByText(['Bathroom', 'Bedroom'].includes(name) ? labels.nightly_override : labels.awaiting_commissioning, { exact: true })).toBeVisible();
    }
  }
  expect(writes.map(write => [write.zone, write.enabled])).toEqual(['kitchen', 'living', 'bathroom', 'bedroom'].map(id => [id, true]));
  await toggle(page, 'Bathroom').tap();
  await expect(toggle(page, 'Bathroom')).toHaveAttribute('aria-checked', 'false');
  await expect(toggle(page, 'Bedroom')).toHaveAttribute('aria-checked', 'true');
  expect(writes.at(-1)).toEqual({ zone: 'bathroom', enabled: false, expectedGeneration: 5, expectedSessionId: 'fixture-policy-session' });
  await page.getByRole('button', { name: 'Kitchen + Living Room', exact: true }).click();
  await expect(page.getByRole('slider', { name: 'Kitchen Shade 01 local preview percent open', exact: true })).toHaveValue('25');
  await expect(page.getByRole('slider', { name: 'Kitchen Shade 02 local preview percent open', exact: true })).toHaveValue('75');
});

test('pending and failed save never show confirmed ON; subsequent authoritative read recovers', async ({ page }) => {
  const state = snapshot();
  let release;
  const held = new Promise(resolve => release = resolve);
  await fixturePolicy(page, state, { fail: true, beforeSave: () => held });
  await page.clock.install();
  await page.goto(`${baseURL}#/shades`);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'false');
  await toggle(page, 'Kitchen').click();
  await expect(zone(page, 'Kitchen').getByText('Saving…', { exact: true })).toBeVisible();
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'false');
  await expect(toggle(page, 'Kitchen')).toBeDisabled();
  release();
  await expect(zone(page, 'Kitchen').getByRole('alert')).toContainText('Save not confirmed');
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'mixed');
  await page.clock.fastForward(5001);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'false');
});

test('multiple clients reconcile remote preferences and a new backend session with no lifecycle writes', async ({ page, context }) => {
  const state = snapshot();
  const writes = await fixturePolicy(page, state);
  await page.clock.install();
  await page.goto(`${baseURL}#/shades`);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'false');
  const second = await context.newPage();
  const secondWrites = await fixturePolicy(second, state);
  await second.goto(`${baseURL}#/shades`);
  await toggle(second, 'Kitchen').click();
  await expect(toggle(second, 'Kitchen')).toHaveAttribute('aria-checked', 'true');
  await page.clock.fastForward(5001);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'true');
  state.sessionId = 'new-backend-session'; state.generation = 0;
  state.connected = false;
  await page.clock.fastForward(5001);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'mixed');
  state.connected = true;
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'true');
  await page.getByRole('button', { name: 'Bathroom + Bedroom', exact: true }).click();
  await page.reload();
  expect(writes).toEqual([]);
  expect(secondWrites).toHaveLength(1);
  await second.close();
});


test('an older in-flight poll cannot overwrite a later confirmed save', async ({ page }) => {
  const state = snapshot();
  await page.clock.install();
  await fixturePolicy(page, state);
  await page.goto(`${baseURL}#/shades`);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'false');
  let release;
  const held = new Promise(resolve => release = resolve);
  let reading;
  const started = new Promise(resolve => reading = resolve);
  const oldSnapshot = structuredClone(state);
  await page.route('**/api/shades-policy', async route => {
    if (route.request().method() !== 'GET') return route.fallback();
    reading();
    await held;
    return route.fulfill({ json: oldSnapshot });
  });
  await page.clock.fastForward(5001);
  await started;
  await toggle(page, 'Kitchen').click();
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'true');
  const received = page.waitForResponse(response => response.url().endsWith('/api/shades-policy') && response.request().method() === 'GET');
  release();
  await (await received).finished();
  await page.clock.runFor(50);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'true');
});

test('a hung policy read expires to Unknown and the next poll recovers without refreshing', async ({ page }) => {
  const state = snapshot();
  state.zones.kitchen = { saved: 'ON', authoritative: true, status: 'awaiting_commissioning', label: labels.awaiting_commissioning };
  await page.clock.install();
  const writes = await fixturePolicy(page, state);
  await page.goto(`${baseURL}#/shades`);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'true');
  let release;
  const held = new Promise(resolve => release = resolve);
  let started;
  const reading = new Promise(resolve => started = resolve);
  let holdNextRead = true;
  await page.route('**/api/shades-policy', async route => {
    if (route.request().method() !== 'GET' || !holdNextRead) return route.fallback();
    holdNextRead = false;
    started();
    await held;
    await route.fulfill({ json: state }).catch(() => {});
  });
  await page.clock.fastForward(5001);
  await reading;
  await page.clock.fastForward(30_001);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'mixed');
  await expect(zone(page, 'Kitchen').getByText('Unknown', { exact: true })).toBeVisible();
  await page.clock.fastForward(5001);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'true');
  release();
  expect(writes).toEqual([]);
});

test('a hung policy save expires without confirming ON and polling recovers the saved choice', async ({ page }) => {
  const state = snapshot();
  await page.clock.install();
  await fixturePolicy(page, state);
  let release;
  const held = new Promise(resolve => release = resolve);
  await page.route('**/api/shades-policy', async route => {
    if (route.request().method() !== 'POST') return route.fallback();
    await held;
    await route.fulfill({ json: state }).catch(() => {});
  });
  await page.goto(`${baseURL}#/shades`);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'false');
  await toggle(page, 'Kitchen').click();
  await expect(zone(page, 'Kitchen').getByText('Saving…', { exact: true })).toBeVisible();
  await page.clock.fastForward(30_001);
  await expect(zone(page, 'Kitchen').getByRole('alert')).toContainText('Save not confirmed');
  await expect(zone(page, 'Kitchen').getByText('Saving…', { exact: true })).toHaveCount(0);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'mixed');
  await page.clock.fastForward(5001);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'false');
  release();
});

test('leaving Shades aborts its policy read and a late response cannot alter the remounted screen', async ({ page }) => {
  await page.addInitScript(() => {
    const originalFetch = window.fetch;
    window.policyReadAborts = 0;
    window.fetch = function(url, options) {
      if (String(url) === '/api/shades-policy' && options?.signal) {
        options.signal.addEventListener('abort', () => window.policyReadAborts++, { once: true });
      }
      return originalFetch.call(this, url, options);
    };
  });
  await page.clock.install();
  const state = snapshot();
  const oldState = structuredClone(state);
  oldState.zones.kitchen = { saved: 'ON', authoritative: true, status: 'awaiting_commissioning', label: labels.awaiting_commissioning };
  const writes = await fixturePolicy(page, state);
  let release;
  const held = new Promise(resolve => release = resolve);
  let started;
  const reading = new Promise(resolve => started = resolve);
  let holdFirst = true;
  await page.route('**/api/shades-policy', async route => {
    if (!holdFirst) return route.fallback();
    holdFirst = false;
    started();
    await held;
    await route.fulfill({ json: oldState }).catch(() => {});
  });
  await page.goto(`${baseURL}#/shades`);
  await reading;
  await page.evaluate(() => window.location.hash = '#/');
  await expect(page.getByRole('heading', { name: 'Window shades', exact: true })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.policyReadAborts)).toBe(1);
  await page.evaluate(() => window.location.hash = '#/shades');
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'false');
  release();
  await page.clock.runFor(50);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-checked', 'false');
  expect(writes).toEqual([]);
});
