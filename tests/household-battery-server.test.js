import { afterEach, expect, it } from 'vitest';
import { mkdtemp, writeFile, chmod, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { batteryPerformance } from './fixtures/household-battery-performance.js';
import { householdObservationPlugin } from '../src/lib/household/observationServer.js';
const disposals = [];
afterEach(async () => { for (const f of disposals.splice(0).reverse()) await f(); });
it('serves only the curated fixed battery GET and refuses file selection or private fields', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'battery-performance-')); await chmod(dir, 0o700);
  disposals.push(() => rm(dir, { recursive: true, force: true }));
  const path = join(dir, 'battery.json'); await writeFile(path, JSON.stringify(batteryPerformance()), { mode: 0o600 });
  let handler;
  householdObservationPlugin({ batteryCachePath: path, now: () => Date.parse('2026-10-12T03:00:35Z') })
    .configureServer({ middlewares: { use(fn) { handler = fn; } } });
  const server = createServer((req, res) => handler(req, res, () => res.writeHead(404).end()));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  disposals.push(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  const url = `http://127.0.0.1:${server.address().port}/api/household-battery-performance`;
  const response = await fetch(url); expect(response.status).toBe(200); expect(await response.json()).toEqual(batteryPerformance());
  expect((await fetch(url, { method: 'POST' })).status).toBe(405);
  expect((await fetch(`${url}?file=/etc/passwd`)).status).toBe(400);
  await writeFile(path, JSON.stringify({ ...batteryPerformance(), private_path: '/private' }));
  const bad = await fetch(url); expect(bad.status).toBe(503); expect(await bad.json()).toEqual({ status: 'unavailable' });
});
