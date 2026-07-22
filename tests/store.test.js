import { describe, it, expect } from 'vitest';
import { get } from 'svelte/store';
import {
  applySnapshot,
  applyState,
  applyThingSnapshot,
  applyThingStatus,
  clientReady,
  connection,
  getClientOnce,
  getItemLastUpdated,
  items,
  thingStatuses,
} from '../src/lib/openhab/store.js';

describe('store', () => {
  it('applySnapshot seeds many items', () => {
    applySnapshot([{ name: 'A', state: '1' }, { name: 'B', state: '2' }]);
    expect(get(items).A).toBe('1');
    expect(get(items).B).toBe('2');
  });

  it('applyState updates a single item reactively', () => {
    applySnapshot([{ name: 'A', state: '1' }]);
    applyState('A', '9');
    expect(get(items).A).toBe('9');
  });

  it('applyState updates an existing item without disturbing others', () => {
    applySnapshot([{ name: 'A', state: '1' }, { name: 'B', state: '2' }]);
    applyState('A', '5');
    expect(get(items).A).toBe('5');
    expect(get(items).B).toBe('2');
  });

  it('applyState adds a new, previously-unseen item', () => {
    applySnapshot([{ name: 'A', state: '1' }]);
    applyState('C', '42');
    expect(get(items).C).toBe('42');
    expect(get(items).A).toBe('1');
  });

  it('applySnapshot merges into existing items rather than replacing the whole map', () => {
    applySnapshot([{ name: 'A', state: '1' }]);
    applyState('Z', '99');
    applySnapshot([{ name: 'B', state: '2' }]);
    expect(get(items).A).toBe('1');
    expect(get(items).Z).toBe('99');
    expect(get(items).B).toBe('2');
  });

  it('applySnapshot overwrites an existing item state', () => {
    applySnapshot([{ name: 'A', state: '1' }]);
    applySnapshot([{ name: 'A', state: '7' }]);
    expect(get(items).A).toBe('7');
  });

  it('applyThingSnapshot retains structured provider status by UID', () => {
    applyThingSnapshot([{
      UID: 'tplinksmarthome:kl125:E7FA31',
      statusInfo: {
        status: 'OFFLINE',
        statusDetail: 'COMMUNICATION_ERROR',
        description: 'No route to host',
      },
    }]);

    expect(get(thingStatuses)['tplinksmarthome:kl125:E7FA31']).toEqual({
      status: 'OFFLINE',
      statusDetail: 'COMMUNICATION_ERROR',
      description: 'No route to host',
    });
  });

  it('applyThingStatus updates a recovered provider reactively', () => {
    applyThingStatus('tplinksmarthome:kl125:E7FA31', {
      status: 'ONLINE', statusDetail: 'NONE', description: '',
    });

    expect(get(thingStatuses)['tplinksmarthome:kl125:E7FA31'].status).toBe('ONLINE');
  });

  it('records a lastUpdated timestamp per item on snapshot and statechanged', () => {
    const before = Date.now();
    applySnapshot([{ name: 'TS_A', state: '1' }]);
    applyState('TS_B', '2');
    const after = Date.now();

    const seen = getItemLastUpdated();
    expect(seen.TS_A).toBeGreaterThanOrEqual(before);
    expect(seen.TS_A).toBeLessThanOrEqual(after);
    expect(seen.TS_B).toBeGreaterThanOrEqual(before);
    expect(seen.TS_B).toBeLessThanOrEqual(after);
  });

  it('connection defaults to connecting', () => {
    expect(get(connection)).toBe('connecting');
  });

  it('connection can be updated via set', () => {
    connection.set('live');
    expect(get(connection)).toBe('live');
    connection.set('connecting');
  });

  it('getClientOnce returns null before initOpenhab has run', () => {
    expect(getClientOnce()).toBe(null);
  });

  it('clientReady defaults to false before initOpenhab has run', () => {
    expect(get(clientReady)).toBe(false);
  });
});
