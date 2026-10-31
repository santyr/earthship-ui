import { test as base, expect } from '@playwright/test';
import { createServer } from './fixture-server.js';

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
const zone = (page, label) => page.locator('[data-shade-automation-zone="'+({Kitchen:'kitchen','Living Room':'living',Bathroom:'bathroom',Bedroom:'bedroom'}[label])+'"]');
const toggle = (page, label) => zone(page, label).getByRole('button');
async function holdToggle(page, label) { await toggle(page, label).focus(); await page.keyboard.down('Space'); await page.waitForTimeout(650); await page.keyboard.up('Space'); }

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
  test(`${size.width}×${size.height}: Controls shows four conventional shade policy cards and no policy switches remain on Shades`, async ({ page }) => {
    await page.setViewportSize(size);
    const state = snapshot();
    state.zones.kitchen = { saved: 'ON', authoritative: true, status: 'awaiting_commissioning', label: labels.awaiting_commissioning };
    state.zones.living = { saved: 'ON', authoritative: true, status: 'automation_not_released', label: labels.automation_not_released };
    state.zones.bathroom = { saved: 'ON', authoritative: true, status: 'nightly_override', label: labels.nightly_override };
    state.zones.bedroom = { saved: null, authoritative: false, status: 'policy_unavailable', label: labels.policy_unavailable };
    const writes = await fixturePolicy(page, state);
    await page.goto(`${baseURL}#/controls`);
    for (const name of ['Kitchen', 'Living Room', 'Bathroom', 'Bedroom']) {
      await expect(toggle(page, name)).toBeVisible();
      await expect(toggle(page, name)).toHaveClass(/control/);
      expect(await toggle(page, name).evaluate(element => element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    }
    await expect(toggle(page, 'Bathroom')).toHaveAttribute('aria-pressed', 'true');
    await expect(zone(page, 'Bathroom').getByText(labels.nightly_override, { exact: true })).toBeVisible();
    await expect(toggle(page, 'Bedroom')).not.toHaveAttribute('aria-pressed');
    await expect(zone(page, 'Bedroom').getByText('Unavailable', { exact: true })).toBeVisible();
    await page.reload();
    await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'true');
    await page.goto(`${baseURL}#/shades`);
    await expect(page.getByRole('switch')).toHaveCount(0);
    await expect(page.locator('.zone-policy')).toHaveCount(0);
    expect(writes).toEqual([]);
  });
}

test('shade policies use hold interaction and submit only their authoritative policy request', async ({page}) => {
  const state = snapshot(); const writes = await fixturePolicy(page, state, {paused:true});
  await page.goto(`${baseURL}#/controls`);
  await expect(toggle(page, 'Kitchen')).toContainText('Hold 600 ms');
  await toggle(page, 'Kitchen').tap();
  expect(writes).toEqual([]);
  for(const name of ['Kitchen','Living Room','Bathroom','Bedroom']) {
    await holdToggle(page,name);
    await expect(toggle(page,name)).toHaveAttribute('aria-pressed','true');
  }
  expect(writes.map(write=>[write.zone,write.enabled])).toEqual(['kitchen','living','bathroom','bedroom'].map(id=>[id,true]));
  await expect(zone(page,'Bathroom').getByText(labels.nightly_override,{exact:true})).toBeVisible();
  await page.goto(`${baseURL}#/shades`);
  await expect(page.getByRole('switch')).toHaveCount(0);
  await expect(page.locator('.policy-switch')).toHaveCount(0);
});

test('cancels a held policy switch when the source generation changes or Controls unmounts', async ({page}) => {
  await page.clock.install();
  const state = snapshot(); const writes = await fixturePolicy(page, state);
  await page.goto(`${baseURL}#/controls`);
  await expect(toggle(page, 'Kitchen')).toBeEnabled();
  await toggle(page, 'Kitchen').focus(); await page.keyboard.down('Space');
  state.generation++;
  const reread = page.waitForResponse(response => response.url().endsWith('/api/shades-policy'));
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await reread; await page.clock.runFor(50); await page.clock.fastForward(650);
  await page.keyboard.up('Space'); expect(writes).toEqual([]);
  await toggle(page, 'Kitchen').focus(); await page.keyboard.down('Space');
  await page.evaluate(() => window.location.hash = '#/shades');
  await expect(page.locator('[data-shades-page]')).toBeVisible();
  await page.clock.fastForward(650); await page.keyboard.up('Space');
  expect(writes).toEqual([]);
});

test('pending and failed save never show confirmed ON; subsequent authoritative read recovers', async ({ page }) => {
  const state = snapshot();
  let release;
  const held = new Promise(resolve => release = resolve);
  await fixturePolicy(page, state, { fail: true, beforeSave: () => held });
  await page.clock.install();
  await page.goto(`${baseURL}#/controls`);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'false');
  await holdToggle(page, 'Kitchen');
  await expect(zone(page, 'Kitchen').getByText('Saving…', { exact: true })).toBeVisible();
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'false');
  await expect(toggle(page, 'Kitchen')).toBeDisabled();
  release();
  await expect(zone(page, 'Kitchen').getByRole('alert')).toContainText('Save not confirmed');
  await expect(toggle(page, 'Kitchen')).not.toHaveAttribute('aria-pressed');
  await page.clock.fastForward(5001);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'false');
});

test('multiple clients reconcile remote preferences and a new backend session with no lifecycle writes', async ({ page, context }) => {
  const state = snapshot();
  const writes = await fixturePolicy(page, state);
  await page.clock.install();
  await page.goto(`${baseURL}#/controls`);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'false');
  const second = await context.newPage();
  const secondWrites = await fixturePolicy(second, state);
  await second.goto(`${baseURL}#/controls`);
  await holdToggle(second, 'Kitchen');
  await expect(toggle(second, 'Kitchen')).toHaveAttribute('aria-pressed', 'true');
  await page.clock.fastForward(5001);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'true');
  state.sessionId = 'new-backend-session'; state.generation = 0;
  state.connected = false;
  await page.clock.fastForward(5001);
  await expect(toggle(page, 'Kitchen')).not.toHaveAttribute('aria-pressed');
  state.connected = true;
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  expect(writes).toEqual([]);
  expect(secondWrites).toHaveLength(1);
  await second.close();
});


test('an older in-flight poll cannot overwrite a later confirmed save', async ({ page }) => {
  const state = snapshot();
  await page.clock.install();
  await fixturePolicy(page, state);
  await page.goto(`${baseURL}#/controls`);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'false');
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
  await holdToggle(page, 'Kitchen');
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'true');
  const received = page.waitForResponse(response => response.url().endsWith('/api/shades-policy') && response.request().method() === 'GET');
  release();
  await (await received).finished();
  await page.clock.runFor(50);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'true');
});

test('a hung policy read expires to Unknown and the next poll recovers without refreshing', async ({ page }) => {
  const state = snapshot();
  state.zones.kitchen = { saved: 'ON', authoritative: true, status: 'awaiting_commissioning', label: labels.awaiting_commissioning };
  await page.clock.install();
  const writes = await fixturePolicy(page, state);
  await page.goto(`${baseURL}#/controls`);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'true');
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
  await expect(toggle(page, 'Kitchen')).not.toHaveAttribute('aria-pressed');
  await expect(zone(page, 'Kitchen').getByText('Unavailable', { exact: true })).toBeVisible();
  await page.clock.fastForward(5001);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'true');
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
  await page.goto(`${baseURL}#/controls`);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'false');
  await holdToggle(page, 'Kitchen');
  await expect(zone(page, 'Kitchen').getByText('Saving…', { exact: true })).toBeVisible();
  await page.clock.fastForward(30_001);
  await expect(zone(page, 'Kitchen').getByRole('alert')).toContainText('Save not confirmed');
  await expect(zone(page, 'Kitchen').getByText('Saving…', { exact: true })).toHaveCount(0);
  await expect(toggle(page, 'Kitchen')).not.toHaveAttribute('aria-pressed');
  await page.clock.fastForward(5001);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'false');
  release();
});

test('leaving Controls aborts its policy read and a late response cannot alter the remounted screen', async ({ page }) => {
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
  await page.goto(`${baseURL}#/controls`);
  await reading;
  await page.evaluate(() => window.location.hash = '#/');
  await expect(page.getByRole('region', {name:'Shade automation',exact:true})).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.policyReadAborts)).toBe(1);
  await page.evaluate(() => window.location.hash = '#/controls');
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'false');
  release();
  await page.clock.runFor(50);
  await expect(toggle(page, 'Kitchen')).toHaveAttribute('aria-pressed', 'false');
  expect(writes).toEqual([]);
});
