import { describe, expect, it } from 'vitest';
import { createShadePolicyOwner, shadePolicyPlugin } from '../src/lib/shades/policyServer.js';
import { SHADE_POLICY_ITEMS, SHADE_POLICY_REVISION_ITEM, SHADE_POLICY_SESSION_ITEM } from '../src/lib/shades/policyModel.js';
import { EventEmitter } from 'node:events';

function fixture({ truncateQueryTimes = false } = {}) {
  let tick = 2000;
  const values = Object.fromEntries([...Object.values(SHADE_POLICY_ITEMS).map((name) => [name, 'OFF']), ['OverrideSwitch', 'OFF']]);
  values[SHADE_POLICY_SESSION_ITEM] = '10000000-0000-4000-8000-000000000001';
  const history = {};
  const writes = [];
  const generations = [];
  function publish() {
    const generation = `00000000-0000-4000-8000-${String(++tick).padStart(12, '0')}`;
    const preferences = Object.fromEntries(Object.entries(SHADE_POLICY_ITEMS).map(([zone, name]) => [zone, values[name]]));
    const persistedAt = Object.fromEntries(Object.keys(SHADE_POLICY_ITEMS).map((zone) => [zone, tick]));
    for (const name of Object.values(SHADE_POLICY_ITEMS)) history[name] = { state: values[name], time: tick };
    values[SHADE_POLICY_REVISION_ITEM] = JSON.stringify({ schemaVersion: 1, generation, ownerSession: values[SHADE_POLICY_SESSION_ITEM], at: tick,
      preferences, persistedAt, override: values.OverrideSwitch, durable: true });
    history[SHADE_POLICY_REVISION_ITEM] = { state: values[SHADE_POLICY_REVISION_ITEM], time: tick };
    generations.push(generation);
  }
  publish();
  let failPersistence = false, failRead = false;
  const fetchImpl = async (raw, options = {}) => {
    const url = new URL(raw); const name = decodeURIComponent(url.pathname.split('/').at(-1));
    if (failRead) throw new Error('offline');
    expect(options.headers.Authorization).toBe('Bearer test');
    if (options.method === 'POST') {
      writes.push({ name, value: options.body });
      values[name] = options.body;
      if (!failPersistence) publish();
      else history[name] = { state: options.body, time: 1 };
      return { ok: true };
    }
    if (url.pathname.startsWith('/rest/persistence/items/')) {
      expect(url.searchParams.get('pagelength')).toBe('1000');
      expect(url.searchParams.get('boundary')).toBe('false');
      expect(url.searchParams.get('itemState')).toBe('false');
      expect(url.searchParams.has('pageSize')).toBe(false);
      let start = Date.parse(url.searchParams.get('starttime'));
      let end = Date.parse(url.searchParams.get('endtime'));
      if (truncateQueryTimes) { start = Math.floor(start / 1000) * 1000; end = Math.floor(end / 1000) * 1000; }
      expect(Number.isFinite(start) && Number.isFinite(end) && end > start).toBe(true);
      const rows = Array.isArray(history[name]) ? history[name] : history[name] ? [history[name]] : [];
      return { ok: true, json: async () => ({ data: rows.filter((row) => row.time >= start && row.time <= end).sort((a, b) => a.time - b.time) }) };
    }
    return { ok: name in values, json: async () => ({ name, state: values[name], type: [SHADE_POLICY_REVISION_ITEM, SHADE_POLICY_SESSION_ITEM].includes(name) ? 'String' : 'Switch' }) };
  };
  let sessions = 0;
  const owner = createShadePolicyOwner({ upstream: 'http://openhab', authorization: 'Bearer test', fetchImpl,
    now: () => tick, sessionIdFactory: () => `session-${++sessions}` });
  return { owner, values, history, writes, publish, generations, fetchImpl, now: () => tick,
    failPersistence: () => { failPersistence = true; }, failRead: () => { failRead = true; },
    recover: () => { failRead = false; } };
}
const update = (snapshot, zone, enabled) => ({ zone, enabled, expectedGeneration: snapshot.generation, expectedSessionId: snapshot.sessionId });

describe('persisted source policy reconciliation and narrow writes', () => {
  it('does not confirm a missing policy Item, receipt or unrestored preference', async () => {
    const f = fixture(); delete f.values[SHADE_POLICY_ITEMS.bedroom];
    const result = await f.owner.read();
    expect(result.zones.bedroom).toMatchObject({ saved: null, authoritative: false });
    expect(result.zones.kitchen.saved).toBe('OFF');
    delete f.values[SHADE_POLICY_REVISION_ITEM];
    expect((await f.owner.read()).zones.kitchen.saved).toBe(null);
  });
  it('blocks restored old receipts until a current non-restored owner session is ready', async () => {
    const f = fixture(); delete f.values[SHADE_POLICY_SESSION_ITEM];
    expect((await f.owner.read()).connected).toBe(false);
    expect((await f.owner.read()).zones.kitchen.saved).toBe(null);
    f.values[SHADE_POLICY_SESSION_ITEM] = '10000000-0000-4000-8000-000000000002';
    expect((await f.owner.read()).connected).toBe(false);
    f.publish();
    expect((await f.owner.read()).zones.kitchen.saved).toBe('OFF');
  });
  it('uses actual matching history times rather than an oldest first row or synthetic current boundary', async () => {
    const f = fixture();
    const actual = f.history[SHADE_POLICY_REVISION_ITEM];
    f.history[SHADE_POLICY_REVISION_ITEM] = [{ state: 'obsolete receipt', time: actual.time - 1 }, actual];
    for (const name of Object.values(SHADE_POLICY_ITEMS)) {
      const current = f.history[name]; f.history[name] = [{ state: 'ON', time: current.time - 1 }, { state: 'ON', time: current.time }, current];
    }
    expect((await f.owner.read()).zones.kitchen.saved).toBe('OFF');
  });
  it('reads exact receipt timestamps through a provider that truncates query bounds to seconds', async () => {
    const f = fixture({ truncateQueryTimes: true });
    for (const name of Object.values(SHADE_POLICY_ITEMS)) {
      const actual = f.history[name];
      f.history[name] = [actual, { state: 'ON', time: actual.time + 20 }];
    }
    const current = await f.owner.read();
    expect(current.connected).toBe(true);
    expect(Object.values(current.zones).map(zone => zone.saved)).toEqual(['OFF', 'OFF', 'OFF', 'OFF']);
    expect(f.writes).toEqual([]);
  });
  it('accepts unchanged all-night policy after successful current reads without a Boolean age TTL', async () => {
    const f = fixture(); f.values.OverrideSwitch = 'ON'; f.values[SHADE_POLICY_ITEMS.bathroom] = 'ON'; f.publish();
    const owner = createShadePolicyOwner({ upstream: 'http://openhab', authorization: 'Bearer test', fetchImpl: f.fetchImpl, now: () => 100 * 86400_000 });
    const first = await owner.read(); const second = await owner.read();
    expect(first.zones.bathroom).toMatchObject({ saved: 'ON', status: 'nightly_override' });
    expect(second.generation).toBe(first.generation);
    expect(second.sessionId).toBe(first.sessionId);
  });
  it('does not publish an old generation when policy changes during slow source reads', async () => {
    const f = fixture(); let altered = false;
    const fetchImpl = async (url, options) => {
      const result = await f.fetchImpl(url, options);
      if (!altered && new URL(url).pathname === `/rest/persistence/items/${SHADE_POLICY_ITEMS.bedroom}`) {
        altered = true; await new Promise((resolve) => setTimeout(resolve, 0));
        f.values.OverrideSwitch = 'ON'; f.publish();
      }
      return result;
    };
    const owner = createShadePolicyOwner({ upstream: 'http://openhab', authorization: 'Bearer test', fetchImpl, now: () => 1e6 });
    expect((await owner.read()).connected).toBe(false);
    expect((await owner.read()).override.state).toBe('ON');
  });
  it('saves exactly one named policy Switch and confirms it only with durable generation readback', async () => {
    const f = fixture(); const before = await f.owner.read();
    const saved = await f.owner.update(update(before, 'bathroom', true));
    expect(saved.zones.bathroom.saved).toBe('ON');
    expect(saved.zones.kitchen.saved).toBe('OFF');
    expect(saved.generation).toBeGreaterThan(before.generation);
    expect(f.writes).toEqual([{ name: SHADE_POLICY_ITEMS.bathroom, value: 'ON' }]);
    f.values.OverrideSwitch = 'ON'; f.publish();
    expect((await f.owner.read()).zones.bathroom.status).toBe('nightly_override');
  });
  it('waits for delayed durable policy readback without reposting the command', async () => {
    const f = fixture(); f.failPersistence();
    const fetchImpl = async (url, options = {}) => {
      const response = await f.fetchImpl(url, options);
      if (options.method === 'POST') setTimeout(() => f.publish(), 1200);
      return response;
    };
    const owner = createShadePolicyOwner({ upstream: 'http://openhab', authorization: 'Bearer test', fetchImpl, now: f.now });
    const before = await owner.read();
    expect((await owner.update(update(before, 'kitchen', true))).zones.kitchen.saved).toBe('ON');
    expect(f.writes).toEqual([{ name: SHADE_POLICY_ITEMS.kitchen, value: 'ON' }]);
  });
  it('does not treat accepted command or matching historical ON as successful persistence', async () => {
    const f = fixture(); const before = await f.owner.read(); f.failPersistence();
    await expect(f.owner.update(update(before, 'kitchen', true))).rejects.toMatchObject({ code: 'save_unconfirmed' });
    expect((await f.owner.read()).zones.kitchen.saved).toBe(null);
  });
  it('detects unseen ON OFF ON via durable source generation even when all scalar values return to their former state', async () => {
    const f = fixture(); const first = await f.owner.read();
    f.values[SHADE_POLICY_ITEMS.kitchen] = 'ON'; f.publish();
    f.values[SHADE_POLICY_ITEMS.kitchen] = 'OFF'; f.publish();
    const second = await f.owner.read();
    expect(second.generation).toBeGreaterThan(first.generation);
    await expect(f.owner.update(update(first, 'living', true))).rejects.toMatchObject({ code: 'policy_conflict' });
    expect(f.writes).toHaveLength(0);
  });
  it('invalidates session after connectivity loss and rejects stale client generations across a restart', async () => {
    const f = fixture(); const first = await f.owner.read();
    f.failRead(); const offline = await f.owner.read();
    expect(offline.connected).toBe(false);
    expect(offline.sessionId).not.toBe(first.sessionId);
    f.recover(); const fresh = await f.owner.read();
    expect(fresh.zones.kitchen.saved).toBe('OFF');
    await expect(f.owner.update(update(first, 'kitchen', true))).rejects.toMatchObject({ code: 'policy_conflict' });
  });
  it('blocks arbitrary Items, caller source labels, and unauthenticated owners', async () => {
    const f = fixture(); const before = await f.owner.read();
    for (const change of [{ ...update(before, 'OverrideSwitch', true) },
      { ...update(before, 'kitchen', true), source: 'manual' }, { zone: 'kitchen', enabled: true }]) {
      await expect(f.owner.update(change)).rejects.toMatchObject({ code: 'invalid_change' });
    }
    expect(f.writes).toHaveLength(0);
    const owner = createShadePolicyOwner({ upstream: 'http://openhab', fetchImpl: () => { throw new Error('must not call'); } });
    expect((await owner.read()).connected).toBe(false);
    await expect(owner.update(update(before, 'kitchen', true))).rejects.toMatchObject({ code: 'authentication_unavailable' });
  });
  it('serializes conflicting clients and preserves OFF across owner recreation without motor commands', async () => {
    const f = fixture(); const before = await f.owner.read();
    const results = await Promise.allSettled([f.owner.update(update(before, 'kitchen', true)), f.owner.update(update(before, 'living', true))]);
    expect(results.map((entry) => entry.status)).toEqual(['fulfilled', 'rejected']);
    const after = await f.owner.read();
    await f.owner.update(update(after, 'kitchen', false));
    expect((await f.owner.read()).zones.kitchen.saved).toBe('OFF');
    expect(f.writes.every(({ name }) => Object.values(SHADE_POLICY_ITEMS).includes(name))).toBe(true);
  });
});

describe('same-origin policy endpoint', () => {
  async function request(method, body, extra = {}, ownerOverride = null) {
    const f = fixture(); let middleware;
    shadePolicyPlugin({ owner: ownerOverride ?? f.owner }).configureServer({ middlewares: { use: (_path, handler) => { middleware = handler; } } });
    const req = new EventEmitter(); Object.assign(req, { method, url: '/', headers: { host: 'console', origin: 'http://console', 'content-type': 'application/json' }, ...extra });
    let status, responseBody;
    const res = { writeHead: (code) => { status = code; return res; }, end: (data) => { responseBody = data; } };
    const done = middleware(req, res);
    if (method === 'POST') { req.emit('data', JSON.stringify(body)); req.emit('end'); }
    await done;
    return { status, body: responseBody && JSON.parse(responseBody), writes: f.writes };
  }
  it('contains unexpected read failures and rejects malformed paths and oversized payloads without writes', async () => {
    expect((await request('GET', null, {}, { read: async () => { throw new Error('bad receipt'); } })).status).toBe(503);
    expect((await request('GET', null, { url: '/unexpected?item=OverrideSwitch' })).status).toBe(400);
    const oversized = await request('POST', { data: 'x'.repeat(2048) });
    expect(oversized.status).toBe(413);
    expect(oversized.writes).toHaveLength(0);
  });
  it('allows read reconciliation and rejects cross-origin writes without opening proxy paths', async () => {
    expect((await request('GET')).status).toBe(200);
    const denied = await request('POST', {}, { headers: { host: 'console', origin: 'http://attacker', 'content-type': 'application/json' } });
    expect(denied.status).toBe(403);
    expect(denied.writes).toHaveLength(0);
  });
});
