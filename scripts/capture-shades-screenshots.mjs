import { chromium } from '@playwright/test';
import { createServer } from 'vite';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const server = await createServer({ root, logLevel: 'error', server: { port: 0, strictPort: false } });
let browser;

try {
  await server.listen();
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1340, height: 800 }, deviceScaleFactor: 1 });
  await page.route('**/config.json', (route) => route.fulfill({ json: {
    openhabUrl: '/fixture-openhab', apiToken: 'fixture', staleBannerSeconds: 90,
  } }));
  await page.route('**/fixture-openhab/rest/items?*', (route) => route.fulfill({ json: [] }));
  await page.route('**/fixture-openhab/rest/things', (route) => route.fulfill({ json: [] }));
  await page.goto(`${server.resolvedUrls.local[0]}#/shades`, { waitUntil: 'domcontentloaded' });
  await page.getByText('Shared preview only · no shade commands').waitFor();

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
} finally {
  await browser?.close();
  await server.close();
}
