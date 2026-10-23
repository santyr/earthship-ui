import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import * as store from '../src/lib/openhab/store.js';
import { computeStaleEssentials } from '../src/lib/alerts/staleness.js';

const name = 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature';
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
let hooks, client, at;
async function boot() {
  at = Date.now() - 60000;
  client = {
    getAllItems: vi.fn().mockResolvedValue([{ name, state: '61.52', lastStateUpdate: at }]),
    getAllThings: vi.fn().mockResolvedValue([]),
    getItem: vi.fn(), sendCommand: vi.fn(),
  };
  await store.initOpenhab({}, { clientFactory: () => client,
    sseFactory: options => { hooks = options; return { start() {}, stop() {} }; }, requestTimeoutMs: 100 });
}
const evidence = () => get(store.itemUpdateEvidence)[name];
beforeEach(async () => { vi.useFakeTimers(); await boot(); });
afterEach(() => { store.stopOpenhab(); vi.useRealTimers(); });

it('recovers the live prior-clock event using the atomic REST value and update time', async () => {
  // The live server emitted a new value with the previous REST update clock.
  client.getItem.mockResolvedValue({ name, state: '61.7', lastStateUpdate: at + 30000 });
  hooks.onState(name, '61.7'); hooks.onUpdateEvidence(name, at, '61.7');
  await vi.advanceTimersByTimeAsync(0);
  expect(get(store.items)[name]).toBe('61.7');
  expect(evidence()).toEqual({ lastKnown: at + 30000, state: '61.7', available: true });
  expect(computeStaleEssentials(get(store.itemUpdateEvidence), Date.now(), { values: get(store.items), ready: true }).some(x => x.name === name)).toBe(false);
  expect(client.sendCommand).not.toHaveBeenCalled();
});

it('does not renew freshness from an event clock when the confirming REST read fails', async () => {
  client.getItem.mockRejectedValue(new Error('503'));
  hooks.onState(name, '61.7'); hooks.onUpdateEvidence(name, at + 30000, '61.7');
  await vi.advanceTimersByTimeAsync(0);
  expect(evidence()).toMatchObject({ lastKnown: at, state: '61.52', available: false });
});

it('coalesces notifications and discards a read overtaken by another value event', async () => {
  const first = deferred(), second = deferred();
  client.getItem.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  hooks.onUpdateEvidence(name, at, '61.7');
  hooks.onState(name, '62');
  for (let i = 0; i < 20; i++) hooks.onUpdateEvidence(name, at, '62');
  first.resolve({ name, state: '61.7', lastStateUpdate: at + 10000 });
  await vi.advanceTimersByTimeAsync(0);
  expect(get(store.items)[name]).toBe('62');
  expect(evidence().available).toBe(false);
  expect(client.getItem).toHaveBeenCalledTimes(2);
  second.resolve({ name, state: '62', lastStateUpdate: at + 30000 });
  await vi.advanceTimersByTimeAsync(0);
  expect(evidence()).toEqual({ lastKnown: at + 30000, state: '62', available: true });
});

it('cancels a pending temperature read on teardown even when the transport ignores abort', async () => {
  const read = deferred(); client.getItem.mockReturnValue(read.promise);
  hooks.onUpdateEvidence(name, at + 30000, '61.7');
  store.stopOpenhab(); read.resolve({ name, state: '61.7', lastStateUpdate: at + 30000 });
  await vi.advanceTimersByTimeAsync(0);
  expect(get(store.items)[name]).toBe('61.52');
  expect(evidence()).toEqual({ lastKnown: at, state: '61.52', available: true });
  expect(vi.getTimerCount()).toBe(0);
});

it('bounds a hung read and recovers on the next notification without a polling loop', async () => {
  client.getItem.mockReturnValueOnce(new Promise(() => {}));
  hooks.onState(name, '61.7'); hooks.onUpdateEvidence(name, at, '61.7');
  await vi.advanceTimersByTimeAsync(1000);
  expect(evidence().available).toBe(false);
  expect(client.getItem).toHaveBeenCalledOnce();
  client.getItem.mockResolvedValue({ name, state: '61.7', lastStateUpdate: at + 30000 });
  hooks.onUpdateEvidence(name, at, '61.7');
  await vi.advanceTimersByTimeAsync(0);
  expect(evidence()).toEqual({ lastKnown: at + 30000, state: '61.7', available: true });
});

it.each(['different_name', 'older_clock', 'same_clock_conflict', 'missing_clock'])('refuses a %s REST pair while retaining the original evidence clock', async kind => {
  const row = { name, state: '61.7', lastStateUpdate: at + 30000 };
  if (kind === 'different_name') row.name = 'other';
  if (kind === 'older_clock') row.lastStateUpdate = at - 1000;
  if (kind === 'same_clock_conflict') row.lastStateUpdate = at;
  if (kind === 'missing_clock') delete row.lastStateUpdate;
  client.getItem.mockResolvedValue(row);
  hooks.onState(name, '61.7'); hooks.onUpdateEvidence(name, at + 30000, '61.7');
  await vi.advanceTimersByTimeAsync(0);
  expect(evidence()).toMatchObject({ lastKnown: at, state: '61.52', available: false });
});

it.each(['before_reconnect', 'during_reconnect', 'coalesced_before_removal'])('does not resurrect an Item removed by authoritative reconciliation (%s)', async order => {
  const read = deferred(), snapshot = deferred();
  client.getItem.mockReturnValue(read.promise);
  client.getAllItems.mockReturnValueOnce(snapshot.promise);
  if (order === 'during_reconnect') hooks.onReconnect();
  hooks.onUpdateEvidence(name, at, '61.7');
  if (order === 'coalesced_before_removal') hooks.onUpdateEvidence(name, at, '62');
  if (order !== 'during_reconnect') hooks.onReconnect();
  snapshot.resolve([]);
  await vi.advanceTimersByTimeAsync(0);
  expect(get(store.items)[name]).toBeUndefined();
  read.resolve({ name, state: '61.7', lastStateUpdate: at + 30000 });
  await vi.advanceTimersByTimeAsync(0);
  expect(get(store.items)[name]).toBeUndefined();
  expect(evidence().available).toBe(false);
  expect(client.getItem).toHaveBeenCalledOnce();
});
