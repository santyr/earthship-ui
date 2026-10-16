import { afterEach, expect, it } from 'vitest';
import { mkdtemp, writeFile, chmod, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { capturedPvPerformance } from './fixtures/household-captured-pv.js';
import { householdObservationPlugin } from '../src/lib/household/observationServer.js';
const disposals = [];
afterEach(async () => { for (const f of disposals.splice(0).reverse()) await f(); });
async function serve() {
  const dir = await mkdtemp(join(tmpdir(), 'captured-pv-')); await chmod(dir, 0o700);
  disposals.push(() => rm(dir, { recursive: true, force: true }));
  const path = join(dir, 'report.json'), raw = JSON.stringify(capturedPvPerformance());
  await writeFile(path, raw, { mode: 0o600 });
  let handler;
  householdObservationPlugin({ capturedPvCachePath: path, now: () => Date.parse('2026-10-12T03:00:35Z') })
    .configureServer({ middlewares: { use(fn) { handler = fn; } } });
  const server = createServer((req, res) => handler(req, res, () => res.writeHead(404).end()));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  disposals.push(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  return { path, raw, url: `http://127.0.0.1:${server.address().port}/api/household-captured-pv-performance` };
}
it('serves exact curated captured-PV bytes through a fixed GET without file selection or writes', async () => {
  const { url, raw } = await serve(); const response = await fetch(url);
  expect(response.status).toBe(200); expect(await response.text()).toBe(raw);
  expect(response.headers.get('cache-control')).toBe('no-store');
  expect((await fetch(url, { method: 'POST' })).status).toBe(405);
  expect((await fetch(`${url}?file=/etc/passwd`)).status).toBe(400);
});
it('withholds malformed, private or unsafe captured-PV cache files', async () => {
  const { path, url } = await serve();
  await writeFile(path, JSON.stringify({ ...capturedPvPerformance(), private_path: '/private' }));
  const bad = await fetch(url); expect(bad.status).toBe(503); expect(await bad.json()).toEqual({ status: 'unavailable' });
  await writeFile(path, JSON.stringify(capturedPvPerformance())); await chmod(path, 0o644);
  expect((await fetch(url)).status).toBe(503);
  await chmod(path, 0o600); const link = path + '.link'; await symlink(path, link);
  await rm(path); await symlink(link, path);
  expect((await fetch(url)).status).toBe(503);
});
