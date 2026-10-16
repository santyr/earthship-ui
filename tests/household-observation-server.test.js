import { afterEach, describe, expect, it } from 'vitest';
import { mkdtemp, writeFile, chmod, symlink, rm, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { observation } from './fixtures/household-observation.js';
import { householdObservationPlugin } from '../src/lib/household/observationServer.js';

const disposals = [];
afterEach(async () => { for (const dispose of disposals.splice(0).reverse()) await dispose(); });
async function endpoint(transform = value => value, fileChange = async () => {}) {
  const dir = await mkdtemp(join(tmpdir(), 'household-observe-'));
  await chmod(dir, 0o700); disposals.push(() => rm(dir, { recursive: true, force: true }));
  const file = join(dir, 'observation.json');
  await writeFile(file, JSON.stringify(transform(observation())), { mode: 0o600 });
  const configuredPath = await fileChange(file, dir) || file;
  let handler;
  householdObservationPlugin({ cachePath: configuredPath, now: () => Date.parse('2026-10-12T03:02:00Z') })
    .configureServer({ middlewares: { use(fn) { handler = fn; } } });
  const server = createServer((req, res) => handler(req, res, () => { res.writeHead(404).end(); }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  disposals.push(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  return `http://127.0.0.1:${server.address().port}`;
}

describe('bounded observation endpoint', () => {
  it('serves the original closed artifact without renewing historical clocks', async () => {
    const base = await endpoint(); const response = await fetch(`${base}/api/household-observation`);
    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(await response.json()).toEqual(observation());
  });
  it('supports only the fixed GET path with no query-selected file', async () => {
    const base = await endpoint();
    expect((await fetch(`${base}/api/household-observation`, { method: 'POST' })).status).toBe(405);
    expect((await fetch(`${base}/api/household-observation?file=/etc/passwd`)).status).toBe(400);
    expect((await fetch(`${base}/api/household-observation/other`)).status).toBe(404);
  });
  it.each(['extra', 'oversize', 'missing', 'symlink', 'ancestor', 'permissions', 'directory'])(
    'withholds %s files with no private details', async damage => {
      const base = await endpoint(value => damage === 'extra' ? { ...value, private_path: '/operator-only-path' } : value, async (file, dir) => {
        if (damage === 'oversize') await writeFile(file, 'x'.repeat(32769));
        if (damage === 'missing') await rm(file);
        if (damage === 'permissions') await chmod(file, 0o644);
        if (damage === 'directory') { await rm(file); await mkdir(file); }
        if (damage === 'symlink') { const copy = join(dir, 'private.json'); await writeFile(copy, '{}', { mode: 0o600 }); await rm(file); await symlink(copy, file); }
        if (damage === 'ancestor') { const alias = `${dir}-alias`; await symlink(dir, alias); disposals.push(() => rm(alias)); return join(alias, 'observation.json'); }
      });
      const response = await fetch(`${base}/api/household-observation`);
      expect(response.status).toBe(503);
      expect(await response.json()).toEqual({ status: 'unavailable' });
    });
});

it('never serves a private payload hidden behind a duplicate public key', async () => {
  const base = await endpoint(value => value, async file => {
    await writeFile(file, JSON.stringify(observation()).replace('{', '{"source_quality":[{"raw_source":"operator-only-data"}],'));
  });
  const response = await fetch(`${base}/api/household-observation`);
  expect(response.status).toBe(503);
  expect(await response.text()).toBe('{"status":"unavailable"}');
});
it('serves the compatible policy observation version without permitting private nested originals', async()=>{
  const {policyObservation}=await import('./fixtures/household-observation.js');
  const base=await endpoint(()=>policyObservation());const response=await fetch(`${base}/api/household-observation`);
  expect(response.status).toBe(200);expect(await response.json()).toEqual(policyObservation());
  const denied=await endpoint(()=>{const r=policyObservation();r.policy_comparison.comparisons[0].raw='private';return r;});
  const bad=await fetch(`${denied}/api/household-observation`);expect(bad.status).toBe(503);expect(await bad.json()).toEqual({status:'unavailable'});
});
