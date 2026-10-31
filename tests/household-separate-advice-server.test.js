import { afterEach, expect, it } from 'vitest';
import { mkdtemp, chmod, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { householdObservationPlugin } from '../src/lib/household/observationServer.js';
import { separateAdvice, commandProposal, ADVICE_AT } from './fixtures/household-separate-advice.js';
const dispose = [];
afterEach(async () => { for (const fn of dispose.splice(0).reverse()) await fn(); });
it('serves the separate-advice artifact on the maintained fixed endpoint with original clocks and refuses commands', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'advice-contract-')); await chmod(dir, 0o700);
  dispose.push(() => rm(dir, { recursive: true, force: true }));
  const file = join(dir, 'observation.json'); const row = separateAdvice();
  await writeFile(file, JSON.stringify(row), { mode: 0o600 });
  let handler;
  householdObservationPlugin({ cachePath: file, now: () => ADVICE_AT }).configureServer({ middlewares: { use(fn) { handler = fn; } } });
  const server = createServer((req, res) => handler(req, res, () => res.writeHead(404).end()));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  dispose.push(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  const url = `http://127.0.0.1:${server.address().port}/api/household-observation`;
  const response = await fetch(url); expect(response.status).toBe(200);
  expect(response.headers.get('cache-control')).toBe('no-store'); expect(await response.json()).toEqual(row);
  expect((await fetch(url, { method: 'POST' })).status).toBe(405);
  expect((await fetch(url + '?file=/private')).status).toBe(400);
  for (const mutate of [v => v.proposals.push(commandProposal()), v => v.qualification_report.release_authorized = true,
    v => v.qualification_report.private = '/private', v => v.qualification_report.snapshot_id = '9'.repeat(64)]) {
    const invalid = separateAdvice(); mutate(invalid); await writeFile(file, JSON.stringify(invalid));
    const denied = await fetch(url); expect(denied.status).toBe(503); expect(await denied.text()).toBe('{"status":"unavailable"}');
  }
  await chmod(file, 0o644); await writeFile(file, JSON.stringify(row)); expect((await fetch(url)).status).toBe(503);
});
