import { createServer } from 'node:http';
import { mkdtemp, readFile, stat, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { afterEach, expect, it } from 'vitest';
import { localRuntimeTransport, verifiedRuntimeBackup, main } from '../../scripts/runtime-cache-deploy.mjs';

const cleanup = [];
afterEach(async () => { for (const close of cleanup.splice(0).reverse()) await close(); });
async function transport(handler, timeoutMs = 1000) {
  const server = createServer(handler);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  cleanup.push(() => new Promise(resolve => { server.closeAllConnections(); server.close(resolve); }));
  return localRuntimeTransport({ token: 'fixture-not-a-secret', port: server.address().port, timeoutMs });
}
it('reads JSON from loopback and sends only scoped writes', async () => {
  const calls = [];
  const request = await transport((req, res) => {
    calls.push([req.method, req.url, req.headers.authorization]);
    res.end('{}');
  });
  expect(await request({ path: '/rest/' })).toEqual({});
  await request({ method: 'POST', path: '/rest/rules/hex_bms_ttd_smooth/enable', body: 'false' });
  expect(calls.map(c => c.slice(0, 2))).toEqual([['GET', '/rest/'], ['POST', '/rest/rules/hex_bms_ttd_smooth/enable']]);
  expect(calls[0][2]).toBe('Bearer fixture-not-a-secret');
});
it.each([
  { path: '/rest/rules/other' },
  { method: 'POST', path: '/rest/rules/hex_bms_ttd_smooth/runnow' },
  { method: 'PUT', path: '/rest/items/BMS_SOC/state', body: '60' },
  { method: 'POST', path: '/rest/rules/hex_bms_ttd_smooth/enable', body: 'invalid' },
])('rejects out of scope requests without connecting: %j', async operation => {
  const request = localRuntimeTransport({ token: 'fixture', port: 1 });
  await expect(request(operation)).rejects.toThrow('outside runtime release scope');
});
it('does not follow redirects or leak response contents', async () => {
  const request = await transport((_req, res) => { res.writeHead(302, { Location: 'http://example.invalid/SECRET' }); res.end('SECRET'); });
  await expect(request({ path: '/rest/' })).rejects.toThrow('HTTP 302');
});
it('enforces a wall-clock request deadline', async () => {
  const request = await transport(() => {}, 25);
  await expect(request({ path: '/rest/' })).rejects.toThrow('local runtime request failed');
});
it('rejects oversized and invalid JSON responses', async () => {
  const large = await transport((_req, res) => res.end('x'.repeat(1024 * 1024 + 1)));
  await expect(large({ path: '/rest/' })).rejects.toThrow();
  const invalid = await transport((_req, res) => res.end('SECRET invalid JSON'));
  await expect(invalid({ path: '/rest/' })).rejects.toThrow('invalid local runtime JSON');
});
it('writes an exclusive private fsynced backup and verifies its canonical digest', async () => {
  const parent = await mkdtemp(join(tmpdir(), 'runtime-backup-test-'));
  cleanup.push(() => rm(parent, { recursive: true }));
  const snapshot = { z: [3, 2], a: { b: 1 } };
  const receipt = await verifiedRuntimeBackup(snapshot, parent);
  const contents = await readFile(receipt.file, 'utf8');
  expect(contents).toBe('{"a":{"b":1},"z":[3,2]}\n');
  expect(receipt.sha256).toBe(createHash('sha256').update(contents.trim()).digest('hex'));
  expect(receipt.verified).toBe(true);
  expect((await stat(receipt.file)).mode & 0o777).toBe(0o600);
  expect((await stat(join(receipt.file, '..'))).mode & 0o777).toBe(0o700);
  const second = await verifiedRuntimeBackup(snapshot, parent);
  expect(second.file).not.toBe(receipt.file);
});
it('requires an explicit recognized mode before reading credentials', async () => {
  await expect(main([])).rejects.toThrow('use --check');
  await expect(main(['--apply'])).rejects.toThrow('use --check');
});
