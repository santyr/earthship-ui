import { chromium } from '@playwright/test';
import { createServer } from 'vite';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Documentation previews must never inherit household credentials or mappings.
process.env.OPENHAB_PROXY_TARGET = 'http://127.0.0.1:9';
delete process.env.OPENHAB_TOKEN;
delete process.env.EARTHSHIP_SHADE_OWNER_PROFILE;
const root = dirname(dirname(fileURLToPath(import.meta.url)));
const server = await createServer({ root, logLevel: 'error', server: { port: 0, strictPort: false } });
let browser;

try {
  await server.listen();
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1340, height: 800 }, deviceScaleFactor: 1 });
  const violations = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== new URL(server.resolvedUrls.local[0]).origin || !['GET', 'HEAD'].includes(request.method())) {
      violations.push(`${request.method()} ${url.pathname}`);
      return route.abort('blockedbyclient');
    }
    if (url.pathname.startsWith('/api/') && !['/api/shades-installation','/api/shades-preview/events'].includes(url.pathname)) {
      return route.fulfill({ status: 503, json: { status: 'unavailable' } });
    }
    return route.continue();
  });
  await page.route('**/config.json', (route) => route.fulfill({ json: {
    openhabUrl: '/fixture-openhab', apiToken: 'fixture', staleBannerSeconds: 90,
  } }));
  await page.route('**/fixture-openhab/rest/items?*', (route) => route.fulfill({ json: [] }));
  await page.route('**/fixture-openhab/rest/things', (route) => route.fulfill({ json: [] }));
  await page.goto(`${server.resolvedUrls.local[0]}#/shades`, { waitUntil: 'domcontentloaded' });
  await page.getByText('Shared preview only · no shade commands').waitFor();
  if (await page.locator('.zone-policy,.policy-switch').count()) throw new Error('Automation preferences belong on Controls');

  for (const [view, filename] of [
    ['Kitchen + Living Room', 'shades-kitchen-living.png'],
    ['Bathroom + Bedroom', 'shades-bathroom-bedroom.png'],
  ]) {
    await page.getByRole('button', { name: view }).click();
    await page.locator('.shades-page').screenshot({
      path: join(root, 'docs', 'screenshots', filename), animations: 'disabled',
    });
  }
  await page.getByRole('button', { name: 'Set shade percentage' }).click();
  const editor = page.getByRole('dialog', { name: 'Set shade percentage' });
  await editor.getByRole('combobox', { name: 'Shades to adjust' }).selectOption({ label: 'Kitchen (all 8)' });
  await editor.screenshot({
    path: join(root, 'docs', 'screenshots', 'shades-percentage-editor.png'), animations: 'disabled',
  });
  if (violations.length || errors.length) throw new Error('Unsafe or failed screenshot capture: '+JSON.stringify({violations, errors}));
} finally {
  await browser?.close();
  await server.close();
}
