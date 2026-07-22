// Boot resilience contract for initOpenhab():
// 1. The initial snapshot retries forever with capped doubling backoff, so a
//    kiosk that boots alongside openHAB self-heals instead of showing "—"
//    everywhere until a manual reload.
// 2. SSE starts only after the first successful snapshot (ordering preserved).
// 3. On SSE reconnect after a drop, the item + thing snapshots are re-fetched
//    so items that changed during an outage cannot stay stale under a green
//    "live" badge.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { get } from 'svelte/store';
import {
  initOpenhab,
  items,
  thingStatuses,
  connection,
  clientReady,
} from '../src/lib/openhab/store.js';

function makeClientStub({ failuresBeforeSuccess = 0, itemSnapshots, thingSnapshots = [] } = {}) {
  let itemCalls = 0;
  let thingCalls = 0;
  const client = {
    getAllItems: vi.fn(async () => {
      const call = itemCalls++;
      if (call < failuresBeforeSuccess) throw new Error('openHAB not up yet');
      const snapshotIndex = Math.min(call - failuresBeforeSuccess, itemSnapshots.length - 1);
      return itemSnapshots[snapshotIndex];
    }),
    getAllThings: vi.fn(async () => {
      const call = thingCalls++;
      const snapshotIndex = Math.min(call, Math.max(0, thingSnapshots.length - 1));
      return thingSnapshots[snapshotIndex] ?? [];
    }),
  };
  return client;
}

function makeSSEStub() {
  const stub = {
    options: null,
    start: vi.fn(),
    stop: vi.fn(),
  };
  const factory = vi.fn((options) => {
    stub.options = options;
    return { start: stub.start, stop: stub.stop };
  });
  return { stub, factory };
}

beforeEach(() => {
  vi.useFakeTimers();
  items.set({});
  thingStatuses.set({});
  connection.set('connecting');
  clientReady.set(false);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('initOpenhab boot retry', () => {
  it('loads the snapshot and starts SSE on the happy path', async () => {
    const client = makeClientStub({
      itemSnapshots: [[{ name: 'A', state: '1' }]],
      thingSnapshots: [[{ UID: 'x:y:z', statusInfo: { status: 'ONLINE' } }]],
    });
    const { stub, factory } = makeSSEStub();

    await initOpenhab({}, { clientFactory: () => client, sseFactory: factory });

    expect(get(items).A).toBe('1');
    expect(get(thingStatuses)['x:y:z'].status).toBe('ONLINE');
    expect(get(clientReady)).toBe(true);
    expect(stub.start).toHaveBeenCalledTimes(1);
  });

  it('retries a failing snapshot with 2s doubling backoff and recovers', async () => {
    const client = makeClientStub({
      failuresBeforeSuccess: 3,
      itemSnapshots: [[{ name: 'BMS_SOC', state: '62' }]],
    });
    const { stub, factory } = makeSSEStub();

    const pending = initOpenhab({}, { clientFactory: () => client, sseFactory: factory });
    await vi.advanceTimersByTimeAsync(0);

    // First attempt failed; display stays honestly "connecting"; no SSE yet.
    expect(client.getAllItems).toHaveBeenCalledTimes(1);
    expect(get(connection)).toBe('connecting');
    expect(get(clientReady)).toBe(false);
    expect(stub.start).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(2000); // retry #1 (fails)
    expect(client.getAllItems).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(4000); // retry #2 (fails)
    expect(client.getAllItems).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(8000); // retry #3 (succeeds)
    expect(client.getAllItems).toHaveBeenCalledTimes(4);

    await pending;
    expect(get(items).BMS_SOC).toBe('62');
    expect(get(clientReady)).toBe(true);
    expect(stub.start).toHaveBeenCalledTimes(1);
  });

  it('caps the retry delay at 30s and keeps retrying forever', async () => {
    const client = makeClientStub({
      failuresBeforeSuccess: 7,
      itemSnapshots: [[{ name: 'A', state: '1' }]],
    });
    const { factory } = makeSSEStub();

    const pending = initOpenhab({}, { clientFactory: () => client, sseFactory: factory });
    await vi.advanceTimersByTimeAsync(0);

    // Delays: 2, 4, 8, 16, 30 (capped), 30, 30 ... seconds.
    for (const delay of [2000, 4000, 8000, 16000, 30000]) {
      await vi.advanceTimersByTimeAsync(delay);
    }
    expect(client.getAllItems).toHaveBeenCalledTimes(6);

    // A capped attempt fires after exactly 30s more, not 32s+.
    await vi.advanceTimersByTimeAsync(29999);
    expect(client.getAllItems).toHaveBeenCalledTimes(6);
    await vi.advanceTimersByTimeAsync(1);
    expect(client.getAllItems).toHaveBeenCalledTimes(7);

    await vi.advanceTimersByTimeAsync(30000);
    expect(client.getAllItems).toHaveBeenCalledTimes(8);
    await pending;
    expect(get(clientReady)).toBe(true);
  });

  it('tolerates a things fetch failure without blocking the item snapshot', async () => {
    const client = {
      getAllItems: vi.fn(async () => [{ name: 'A', state: '1' }]),
      getAllThings: vi.fn(async () => { throw new Error('things route missing'); }),
    };
    const { factory } = makeSSEStub();

    await initOpenhab({}, { clientFactory: () => client, sseFactory: factory });

    expect(get(items).A).toBe('1');
    expect(get(clientReady)).toBe(true);
  });
});

describe('initOpenhab resync on SSE reconnect', () => {
  it('re-fetches and applies both snapshots when the SSE hook fires', async () => {
    const client = makeClientStub({
      itemSnapshots: [
        [{ name: 'A', state: '1' }],
        [{ name: 'A', state: '9' }, { name: 'B', state: '2' }],
      ],
      thingSnapshots: [
        [{ UID: 'x:y:z', statusInfo: { status: 'ONLINE' } }],
        [{ UID: 'x:y:z', statusInfo: { status: 'OFFLINE', statusDetail: 'COMMUNICATION_ERROR' } }],
      ],
    });
    const { stub, factory } = makeSSEStub();

    await initOpenhab({}, { clientFactory: () => client, sseFactory: factory });
    expect(get(items).A).toBe('1');
    expect(typeof stub.options.onReconnect).toBe('function');

    stub.options.onReconnect();
    await vi.advanceTimersByTimeAsync(0);

    expect(client.getAllItems).toHaveBeenCalledTimes(2);
    expect(get(items).A).toBe('9');
    expect(get(items).B).toBe('2');
    expect(get(thingStatuses)['x:y:z'].status).toBe('OFFLINE');
  });

  it('survives a failing resync fetch without an unhandled rejection', async () => {
    let calls = 0;
    const client = {
      getAllItems: vi.fn(async () => {
        if (calls++ === 0) return [{ name: 'A', state: '1' }];
        throw new Error('openHAB dropped again');
      }),
      getAllThings: vi.fn(async () => []),
    };
    const { stub, factory } = makeSSEStub();

    await initOpenhab({}, { clientFactory: () => client, sseFactory: factory });
    stub.options.onReconnect();
    await vi.advanceTimersByTimeAsync(0);

    expect(get(items).A).toBe('1');
  });

  it('forwards item state, thing status, and connection status to the stores', async () => {
    const client = makeClientStub({ itemSnapshots: [[{ name: 'A', state: '1' }]] });
    const { stub, factory } = makeSSEStub();

    await initOpenhab({}, { clientFactory: () => client, sseFactory: factory });

    stub.options.onState('A', '5');
    expect(get(items).A).toBe('5');
    stub.options.onThingStatus('x:y:z', { status: 'ONLINE' });
    expect(get(thingStatuses)['x:y:z'].status).toBe('ONLINE');
    stub.options.onStatus('live');
    expect(get(connection)).toBe('live');
  });
});
