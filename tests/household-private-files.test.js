import { afterEach, expect, it } from 'vitest';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createServer } from 'vite';
const cleanup = [];
afterEach(async () => { for (const fn of cleanup.splice(0).reverse()) await fn(); });
it('withholds private staging through Vite filesystem aliases while serving public files', async () => {
  const root = await mkdtemp(join(tmpdir(), 'household-fs-')); cleanup.push(() => rm(root, { recursive: true, force: true }));
  await mkdir(join(root, '.superpowers'), { mode: 0o700 });
  await writeFile(join(root, '.superpowers', 'receipt.json'), '{"private":"operator-only-data"}', { mode: 0o600 });
  await writeFile(join(root, 'public.txt'), 'public-page-data');
  const server = await createServer({ configFile: resolve('vite.config.js'), configLoader: 'runner',
    cacheDir: resolve('.superpowers/test-cache/private-files'), root,
    server: { port: 0, host: '127.0.0.1', watch: null } });
  cleanup.push(() => server.close()); await server.listen();
  const base = server.resolvedUrls.local[0];
  expect(await (await fetch(`${base}public.txt`)).text()).toBe('public-page-data');
  for (const path of [`.superpowers/receipt.json`, `@fs${root}/.superpowers/receipt.json`, `%2Esuperpowers/receipt.json`]) {
    const response = await fetch(`${base}${path}`);
    expect(response.status).toBe(403);
    expect(await response.text()).not.toContain('operator-only-data');
  }
});
