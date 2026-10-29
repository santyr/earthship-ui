// @vitest-environment node
import { test, expect } from 'vitest';
import { createServer, fixtureOrigins } from './e2e/fixture-server.js';

test('disposable server refuses unstubbed backend reads and writes before any proxy', async () => {
  const server = await createServer({ configFile: false, logLevel: 'silent' });
  try {
    await server.listen();
    const origin = server.resolvedUrls.local[0];
    expect(fixtureOrigins.has(new URL(origin).origin)).toBe(true);
    expect(fixtureOrigins.has('http://127.0.0.1:5190')).toBe(false);
    for (const path of ['rest/items', 'rest/things', 'api/household-observation', 'api/household-energy-observation']) {
      const response = await fetch(new URL(path, origin));
      expect(response.status).toBe(503);
      expect(await response.json()).toEqual({ status: 'unavailable' });
    }
    expect((await fetch(new URL('rest/items/FakeFixtureItem', origin), { method: 'POST', body: 'ON' })).status).toBe(503);
    expect(await fetch(new URL('config.json', origin)).then(response => response.json())).toMatchObject({ apiToken: '', openhabUrl: '' });
  } finally { await server.close(); }
  expect(fixtureOrigins.size).toBe(0);
});
