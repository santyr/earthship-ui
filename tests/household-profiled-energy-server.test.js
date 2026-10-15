import { afterEach, expect, it } from 'vitest';
import { mkdtemp, writeFile, chmod, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { profiledObservation, profiledPerformance, PROFILE_NOW } from './fixtures/household-profiled-energy.js';
import { householdObservationPlugin } from '../src/lib/household/observationServer.js';
const cleanup = [];
afterEach(async () => { for (const task of cleanup.splice(0).reverse()) await task(); });
it.each([['/api/household-profiled-energy-observation', profiledObservation], ['/api/household-profiled-energy-performance', profiledPerformance]])(
  'serves fixed curated GET %s without allowing file selection or authority', async (endpoint, fixture) => {
    const dir = await mkdtemp(join(tmpdir(), 'energy-monitoring-')); await chmod(dir, 0o700); cleanup.push(() => rm(dir, { recursive: true, force: true }));
    const path = join(dir, 'value.json'); await writeFile(path, JSON.stringify(fixture()), { mode: 0o600 });
    let handler;
    householdObservationPlugin({ profiledCachePath: path, profiledPerformanceCachePath: path, now: () => PROFILE_NOW })
      .configureServer({ middlewares: { use(fn) { handler = fn; } } });
    const server = createServer((req, res) => handler(req, res, () => res.writeHead(404).end()));
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); cleanup.push(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
    const url = `http://127.0.0.1:${server.address().port}${endpoint}`;
    const response = await fetch(url); expect(response.status).toBe(200); expect(await response.json()).toEqual(fixture());
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect((await fetch(url, { method: 'POST' })).status).toBe(405); expect((await fetch(`${url}?path=/etc/passwd`)).status).toBe(400);
    await writeFile(path, JSON.stringify({ ...fixture(), original_path: '/operator-private' }));
    const refused = await fetch(url); expect(refused.status).toBe(503); expect(await refused.json()).toEqual({ status: 'unavailable' });
  },
);
