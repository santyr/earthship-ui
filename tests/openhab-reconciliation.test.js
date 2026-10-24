import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import * as store from '../src/lib/openhab/store.js';

const deferred = () => {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return { promise, resolve };
};
let hooks;
let stop;
const makeClient = () => ({
  getAllItems: vi.fn().mockResolvedValue([{ name: 'A', state: 'OFF' }, { name: 'Removed', state: 'ON' }]),
  getAllThings: vi.fn().mockResolvedValue([{ UID: 'provider', statusInfo: { status: 'ONLINE' } }]),
  sendCommand: vi.fn(),
});
async function boot(client) {
  stop = vi.fn();
  await store.initOpenhab({}, {
    clientFactory: () => client,
    sseFactory: options => { hooks = options; return { start() {}, stop }; },
    retryBaseMs: 20, retryMaxMs: 40, requestTimeoutMs: 100,
  });
  hooks.onStatus('live');
}
beforeEach(() => {
  vi.useFakeTimers();
  store.items.set({}); store.thingStatuses.set({}); store.itemUpdateEvidence.set({});
});
afterEach(() => { store.stopOpenhab?.(); vi.useRealTimers(); });

it('keeps in-flight Item, Thing and source-evidence deltas when replacing a delayed snapshot', async () => {
  const client = makeClient();
  await boot(client);
  const items = deferred(), things = deferred();
  client.getAllItems.mockReturnValueOnce(items.promise);
  client.getAllThings.mockReturnValueOnce(things.promise);
  hooks.onReconnect();
  hooks.onState('A', 'ON');
  hooks.onState('New', 'ON');
  hooks.onThingStatus('provider', { status: 'OFFLINE' });
  hooks.onUpdateEvidence('Sun_TimeLeft', 1770000000000, '1 d');
  items.resolve([{ name: 'A', state: 'OFF' }]);
  things.resolve([{ UID: 'provider', statusInfo: { status: 'ONLINE' } }]);
  await vi.advanceTimersByTimeAsync(0);
  expect(get(store.items)).toMatchObject({ A: 'ON', New: 'ON', Sun_TimeLeft: '1 d' });
  expect(get(store.items).Removed).toBeUndefined();
  expect(get(store.itemUpdateEvidence).Sun_TimeLeft).toMatchObject({ available: true, lastKnown: 1770000000000 });
  expect(get(store.thingStatuses).provider.status).toBe('OFFLINE');
});

it('replaces removed resources with authoritative empty collections', async () => {
  const client = makeClient();
  await boot(client);
  client.getAllItems.mockResolvedValue([]); client.getAllThings.mockResolvedValue([]);
  hooks.onReconnect();
  await vi.advanceTimersByTimeAsync(0);
  expect(get(store.items)).toEqual({});
  expect(get(store.thingStatuses)).toEqual({});
});

it('retries a 503 while the stream remains open and does not advertise live until reconciled', async () => {
  const client = makeClient();
  await boot(client);
  client.getAllItems.mockRejectedValueOnce(new Error('503')).mockResolvedValue([{ name: 'A', state: 'ON' }]);
  hooks.onReconnect();
  await vi.advanceTimersByTimeAsync(0);
  hooks.onStatus('live');
  expect(get(store.connection)).not.toBe('live');
  await vi.advanceTimersByTimeAsync(20);
  expect(get(store.items).A).toBe('ON');
  expect(get(store.connection)).toBe('live');
  expect(client.sendCommand).not.toHaveBeenCalled();
});

it('bounds a hung Thing read, starts streaming with Items, then recovers without a disconnect', async () => {
  const client = makeClient();
  client.getAllThings.mockReturnValueOnce(new Promise(() => {}));
  const pending = boot(client);
  await vi.advanceTimersByTimeAsync(100);
  expect(get(store.clientReady)).toBe(true);
  await pending;
  expect(get(store.connection)).not.toBe('live');
  await vi.advanceTimersByTimeAsync(20);
  expect(get(store.connection)).toBe('live');
});

it('ignores an obsolete overlapping resync even if its fetch ignores abort', async () => {
  const client = makeClient();
  await boot(client);
  const old = deferred();
  client.getAllItems.mockReturnValueOnce(old.promise).mockResolvedValue([{ name: 'A', state: 'NEW' }]);
  hooks.onReconnect(); hooks.onReconnect();
  await vi.advanceTimersByTimeAsync(0);
  old.resolve([{ name: 'A', state: 'OLD' }]);
  await vi.advanceTimersByTimeAsync(0);
  expect(get(store.items).A).toBe('NEW');
});

it('does not mistake a failed Thing read for an authoritative empty collection', async () => {
  const client = makeClient();
  await boot(client);
  client.getAllThings.mockRejectedValueOnce(new Error('503'));
  hooks.onReconnect();
  await vi.advanceTimersByTimeAsync(0);
  expect(get(store.thingStatuses).provider.status).toBe('ONLINE');
  expect(get(store.connection)).not.toBe('live');
  await vi.advanceTimersByTimeAsync(20);
  expect(get(store.connection)).toBe('live');
});

it('stops the stream and pending retry on teardown, ignoring late callbacks', async () => {
  const client = makeClient();
  await boot(client);
  client.getAllItems.mockRejectedValue(new Error('503'));
  hooks.onReconnect(); await vi.advanceTimersByTimeAsync(0);
  const calls = client.getAllItems.mock.calls.length;
  store.stopOpenhab?.();
  hooks.onState('A', 'LATE'); hooks.onStatus('live');
  await vi.advanceTimersByTimeAsync(1000);
  expect(stop).toHaveBeenCalledOnce();
  expect(client.getAllItems).toHaveBeenCalledTimes(calls);
  expect(get(store.items).A).toBe('OFF');
  expect(get(store.clientReady)).toBe(false);
  expect(vi.getTimerCount()).toBe(0);
});

it('aborts a hung initial Item read and retries without starting a partial stream', async () => {
  const client = makeClient();
  client.getAllItems.mockReturnValueOnce(new Promise(() => {}));
  const pending = boot(client);
  await vi.advanceTimersByTimeAsync(100);
  expect(get(store.clientReady)).toBe(false);
  await vi.advanceTimersByTimeAsync(20);
  await pending;
  expect(get(store.items).A).toBe('OFF');
  expect(get(store.clientReady)).toBe(true);
});

it('cancels an initial retry wait and starts a replacement session without leaked timers', async () => {
  const first = makeClient(); first.getAllItems.mockRejectedValue(new Error('503'));
  const pending = store.initOpenhab({}, { clientFactory: () => first, retryBaseMs: 20 }).catch(error => error);
  await vi.advanceTimersByTimeAsync(0);
  store.stopOpenhab();
  expect((await pending).name).toBe('AbortError');
  await boot(makeClient());
  store.stopOpenhab();
  expect(vi.getTimerCount()).toBe(0);
});

it('reconciles a change in the boot snapshot to first stream open gap', async () => {
  const { createSSE } = await import('../src/lib/openhab/sse.js');
  let source;
  vi.stubGlobal('EventSource', class {
    constructor() { source = this; }
    close() {}
  });
  try {
    const client = makeClient();
    await store.initOpenhab({ openhabUrl: '' }, { clientFactory: () => client, sseFactory: createSSE });
    client.getAllItems.mockResolvedValue([{ name: 'A', state: 'ON' }]);
    source.onopen();
    expect(get(store.connection)).toBe('reconciling');
    await vi.advanceTimersByTimeAsync(0);
    expect(get(store.items).A).toBe('ON');
    expect(get(store.connection)).toBe('live');
    expect(client.sendCommand).not.toHaveBeenCalled();
  } finally { store.stopOpenhab(); vi.unstubAllGlobals(); }
});

it('preserves an Astro statechanged delta before its matching stateupdated evidence arrives', async () => {
  const client = makeClient();
  const old = { name: 'Sun_TimeLeft', state: '10 d', lastStateUpdate: 1770000000000 };
  client.getAllItems.mockResolvedValue([old]);
  await boot(client);
  const snapshot = deferred();
  client.getAllItems.mockReturnValueOnce(snapshot.promise);
  hooks.onReconnect();
  hooks.onState('Sun_TimeLeft', '9 d');
  snapshot.resolve([old]);
  await vi.advanceTimersByTimeAsync(0);
  expect(get(store.items).Sun_TimeLeft).toBe('9 d');
  // Old evidence must retain its original state/clock; no evidence timestamp
  // is manufactured for the newer transport delta.
  expect(get(store.itemUpdateEvidence).Sun_TimeLeft).toMatchObject({ lastKnown: 1770000000000, state: '10 d' });
});


it('keeps a temperature update pair received during a delayed snapshot', async () => {
  const name = 'AmbientWeatherWS2902A_IndoorSensor_Temperature';
  const at = Date.now() - 60000;
  const client = makeClient(); client.getAllItems.mockResolvedValue([{ name, state: '70', lastStateUpdate: at }]);
  await boot(client);
  const snapshot = deferred(); client.getAllItems.mockReturnValueOnce(snapshot.promise);
  client.getItem = vi.fn().mockResolvedValue({ name, state: '71', lastStateUpdate: at + 1 });
  hooks.onReconnect(); hooks.onUpdateEvidence(name, at + 1, '71');
  snapshot.resolve([{ name, state: '40', lastStateUpdate: at - 1000 }]);
  await vi.advanceTimersByTimeAsync(0);
  expect(get(store.items)[name]).toBe('71');
  expect(get(store.itemUpdateEvidence)[name]).toMatchObject({ state: '71', lastKnown: at + 1, available: true });
  expect(client.sendCommand).not.toHaveBeenCalled();
});

it.each([[null], [{ name: 'A' }], [{ name: 'A', state: '1' }, { name: 'A', state: '2' }]])(
  'retries a malformed collection without an unhandled rejection (%j)', async (...rows) => {
    const client = makeClient(); await boot(client);
    client.getAllItems.mockResolvedValueOnce(rows).mockResolvedValue([{ name: 'A', state: 'RECOVERED' }]);
    hooks.onReconnect(); await vi.advanceTimersByTimeAsync(0);
    expect(get(store.connection)).not.toBe('live'); expect(get(store.items).A).toBe('OFF');
    await vi.advanceTimersByTimeAsync(20);
    expect(get(store.items).A).toBe('RECOVERED'); expect(get(store.connection)).toBe('live');
    expect(client.sendCommand).not.toHaveBeenCalled();
  });

it('starts a declared new session without clocks or state from the previous source', async () => {
  const name = 'AmbientWeatherWS2902A_IndoorSensor_Temperature'; const at = Date.now() - 60000;
  const first = makeClient(); first.getAllItems.mockResolvedValue([{ name, state: '70', lastStateUpdate: at }]);
  await boot(first);
  const second = makeClient(); second.getAllItems.mockResolvedValue([{ name, state: '40', lastStateUpdate: at - 1000 }]);
  await boot(second);
  expect(get(store.items)[name]).toBe('40');
  expect(get(store.itemUpdateEvidence)[name]).toMatchObject({ state: '40', lastKnown: at - 1000, available: true });
});


it('recovers a malformed Thing status on reconnect without another stream reconnect', async () => {
  const client = makeClient(); await boot(client);
  client.getAllThings.mockResolvedValueOnce([{ UID: 'provider', statusInfo: null }])
    .mockResolvedValue([{ UID: 'provider', statusInfo: { status: 'OFFLINE' } }]);
  hooks.onReconnect(); await vi.advanceTimersByTimeAsync(0);
  expect(get(store.reconciliation)).toBe('retrying');
  expect(get(store.connection)).toBe('reconciling');
  expect(get(store.thingStatuses).provider.status).toBe('ONLINE');
  await vi.advanceTimersByTimeAsync(20);
  expect(get(store.reconciliation)).toBe('ready');
  expect(get(store.connection)).toBe('live');
  expect(get(store.thingStatuses).provider.status).toBe('OFFLINE');
  expect(client.getAllThings).toHaveBeenCalledTimes(3);
  expect(client.sendCommand).not.toHaveBeenCalled();
});

it.each([
  [null], [7], [[]], [{}], [{ UID: '' }], [{ UID: ' provider ', statusInfo: { status: 'ONLINE' } }],
  [{ UID: 'provider', statusInfo: null }], [{ UID: 'provider', statusInfo: [] }],
  [{ UID: 'provider', statusInfo: { status: 1 } }],
  [{ UID: 'provider', statusInfo: { status: 'ONLINE', statusDetail: {} } }],
  [{ UID: 'provider', statusInfo: { status: 'ONLINE', description: null } }],
  [{ UID: 'provider', statusInfo: { status: 'OFFLINE' } }, { UID: 'provider', statusInfo: { status: 'ONLINE' } }],
])('rejects the entire malformed Thing inventory before publication (%j)', async (...rows) => {
  const client = makeClient(); await boot(client);
  // A good first row must not be published when a subsequent row is invalid.
  const bad = [{ UID: 'partial', statusInfo: { status: 'ONLINE' } }, ...rows];
  client.getAllThings.mockResolvedValueOnce(bad);
  hooks.onReconnect(); await vi.advanceTimersByTimeAsync(0);
  expect(get(store.thingStatuses)).toEqual({ provider: { status: 'ONLINE', statusDetail: '', description: '' } });
  expect(get(store.reconciliation)).toBe('retrying');
  expect(get(store.connection)).toBe('reconciling');
  await vi.advanceTimersByTimeAsync(20);
  expect(get(store.reconciliation)).toBe('ready');
  expect(client.sendCommand).not.toHaveBeenCalled();
});

it('retries processing errors with one capped backoff while the stream remains open', async () => {
  const client = makeClient(); await boot(client);
  const broken = Object.defineProperty({}, 'name', { get() { throw new Error('malformed decoded row'); } });
  client.getAllItems.mockResolvedValue([broken]);
  hooks.onReconnect(); await vi.advanceTimersByTimeAsync(0);
  expect(get(store.reconciliation)).toBe('retrying');
  expect(get(store.items).A).toBe('OFF');
  await vi.advanceTimersByTimeAsync(19); expect(client.getAllItems).toHaveBeenCalledTimes(2);
  await vi.advanceTimersByTimeAsync(1); expect(client.getAllItems).toHaveBeenCalledTimes(3);
  await vi.advanceTimersByTimeAsync(39); expect(client.getAllItems).toHaveBeenCalledTimes(3);
  await vi.advanceTimersByTimeAsync(1); expect(client.getAllItems).toHaveBeenCalledTimes(4);
  await vi.advanceTimersByTimeAsync(40); expect(client.getAllItems).toHaveBeenCalledTimes(5);
  client.getAllItems.mockResolvedValue([{ name: 'A', state: 'RECOVERED' }]);
  await vi.advanceTimersByTimeAsync(40);
  expect(get(store.items).A).toBe('RECOVERED'); expect(get(store.connection)).toBe('live');
  expect(vi.getTimerCount()).toBe(0);
  expect(client.sendCommand).not.toHaveBeenCalled();
});

it('does not let a late Thing response or callback mutate a replacement session', async () => {
  const first = makeClient(); await boot(first); const oldHooks = hooks;
  const staleThings = deferred(); first.getAllThings.mockReturnValueOnce(staleThings.promise);
  oldHooks.onReconnect(); await vi.advanceTimersByTimeAsync(0);
  const second = makeClient(); second.getAllThings.mockResolvedValue([{ UID: 'current', statusInfo: { status: 'OFFLINE' } }]);
  await boot(second);
  staleThings.resolve([{ UID: 'obsolete', statusInfo: { status: 'ONLINE' } }]);
  oldHooks.onThingStatus('obsolete', { status: 'ONLINE' }); oldHooks.onReconnect();
  await vi.advanceTimersByTimeAsync(1000);
  expect(get(store.thingStatuses)).toEqual({ current: { status: 'OFFLINE', statusDetail: '', description: '' } });
  expect(get(store.reconciliation)).toBe('ready');
  expect(second.getAllThings).toHaveBeenCalledOnce();
  store.stopOpenhab(); expect(vi.getTimerCount()).toBe(0);
});
