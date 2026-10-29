import { expect, test } from './fixture-test.js';
import { createServer } from './fixture-server.js';

let server, baseURL;
test.beforeAll(async () => {
  server = await createServer({ plugins: [{
    name: 'isolated-sensor-component',
    configureServer(vite) {
      vite.middlewares.use('/sensor-qualification.html', (_request, response) => {
        response.setHeader('Content-Type', 'text/html');
        response.end('<!doctype html><html><body style="margin:0"><main id="sensor-qualification" style="height:100dvh;padding:12px;box-sizing:border-box"></main><script type="module" src="/tests/e2e/sensor-harness.js"></script></body></html>');
      });
    },
  }], logLevel: 'error' });
  await server.listen();
  baseURL = server.resolvedUrls.local[0];
});
test.afterAll(async () => { await server?.close(); });

function sensorDocument(now, state) {
  const at = offset => new Date(now + offset).toISOString();
  return { schema: 'earthship-sensor-view/v1', environment: 'simulation', authority: 'observation_only',
    generated_at: at(0), expires_at: at(45000), recent_events: [], daily_durations: [],
    sensors: Array.from({ length: 15 }, (_, i) => ({ sensor_id: `opening_${i + 1}`, name: `Opening ${i + 1}`,
      zone: 'Fixture', location: 'Synthetic', device_type: ['window', 'skylight', 'door'][i % 3],
      health: 'ONLINE', current_state: state, contact_state: state, valid: true,
      valid_until: at(120000), communication_valid_until: at(120000), offline_at: at(300000),
      last_observed_at: at(-1000), last_received_at: at(-1000), last_transition_at: at(-1000),
      battery: { percent: 90, condition: 'OK' },
    })),
  };
}

for (const [width, height] of [[1340, 800], [1280, 720]]) {
  test(`isolated sensor dashboard ${width}x${height}: transitions, expiry and bounded layout`, async ({ page }) => {
    const now = Date.now();
    await page.clock.install({ time: new Date(now) });
    await page.setViewportSize({ width, height });
    await page.addInitScript(() => {
      window.EventSource = class {
        constructor() { window.__sensorEvents = this; setTimeout(() => this.onopen?.({}), 0); }
        close() {}
      };
    });
    await page.route('**/rest/things**', route => route.fulfill({ json: [] }));
    await page.route('**/rest/items?*', route => route.fulfill({ json: [
      { name: 'Earthship_Sensor_View_JSON', state: JSON.stringify(sensorDocument(now, 'CLOSED')), type: 'String' },
      { name: 'Earthship_Sensor_Service', state: 'online', type: 'String' },
    ] }));
    await page.goto(`${baseURL}sensor-qualification.html`);
    await expect(page.locator('[data-sensor]')).toHaveCount(15);
    await expect(page.getByText('Synthetic demonstration')).toBeVisible();
    const first = page.locator('[data-sensor="opening_1"] .state strong');
    await expect(first).toHaveText('Closed');
    await page.evaluate(document => window.__sensorEvents.onmessage({ data: JSON.stringify({
      topic: 'openhab/items/Earthship_Sensor_View_JSON/statechanged',
      type: 'ItemStateChangedEvent', payload: JSON.stringify({ value: JSON.stringify(document) }),
    }) }), sensorDocument(now, 'OPEN'));
    await expect(first).toHaveText('Open');
    expect(await page.evaluate(() => {
      const screen = document.querySelector('[data-ventilation-screen]');
      const footer = screen.querySelector('footer').getBoundingClientRect();
      return { scroll: screen.scrollHeight > screen.clientHeight + 1,
        overflow: document.documentElement.scrollWidth > innerWidth,
        cards: [...document.querySelectorAll('[data-sensor]')].every(card => card.getBoundingClientRect().bottom <= footer.top + 1) };
    })).toEqual({ scroll: false, overflow: false, cards: true });
    await page.clock.fastForward(46000);
    await expect(first).toHaveText('Unknown');
    await expect(page.getByText(/Source stale \/ disconnected/)).toBeVisible();
  });
}
