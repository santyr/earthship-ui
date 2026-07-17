import { describe, it, expect } from 'vitest';
import { get } from 'svelte/store';
import { items, connection, applyState, applySnapshot } from '../src/lib/openhab/store.js';

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

  it('connection defaults to connecting', () => {
    expect(get(connection)).toBe('connecting');
  });

  it('connection can be updated via set', () => {
    connection.set('live');
    expect(get(connection)).toBe('live');
    connection.set('connecting');
  });
});
