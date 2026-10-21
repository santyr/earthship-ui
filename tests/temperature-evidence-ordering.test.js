import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import * as store from '../src/lib/openhab/store.js';
import { parseUpdateEvidenceSSEMessage } from '../src/lib/openhab/sse.js';
import { computeStaleEssentials, TEMPERATURE_ITEMS } from '../src/lib/alerts/staleness.js';

const NOW = Date.parse('2026-10-21T12:06:00Z');
const NEW = NOW - 60000, OLD = NOW - 3960000;
const names = TEMPERATURE_ITEMS.map(item => item.name);
const warnings = name => computeStaleEssentials(get(store.itemUpdateEvidence), NOW,
  { values: get(store.items), ready: true }).filter(item => item.name === name);
const snapshot = (name, state = '70', lastStateUpdate = NEW) => [{ name, state, lastStateUpdate }];
beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(NOW);
  store.items.set({}); store.itemUpdateEvidence.set({});
});
afterEach(() => { store.stopOpenhab(); vi.useRealTimers(); });

it.each(names)('rejects an older snapshot value and retains its accepted source pair: %s', name => {
  store.applySnapshot(snapshot(name));
  store.applySnapshot(snapshot(name, '40', OLD));
  expect(get(store.items)[name]).toBe('70');
  expect(get(store.itemUpdateEvidence)[name]).toMatchObject({ lastKnown: NEW, state: '70', available: true });
  expect(warnings(name)).toEqual([]);
});
it.each(names)('carries the value and clock through temperature stateupdated parsing: %s', name => {
  expect(parseUpdateEvidenceSSEMessage(JSON.stringify({ topic: `openhab/items/${name}/stateupdated`,
    payload: JSON.stringify({ value: '71', lastStateUpdate: NEW }) })))
    .toEqual({ name, state: '71', lastStateUpdate: NEW });
});
it.each(['snapshot', 'update'])('withholds equal-time conflicts until a newer source pair arrives (%s)', mode => {
  const name = names[0]; store.applySnapshot(snapshot(name));
  if (mode === 'snapshot') store.applySnapshot(snapshot(name, '40'));
  else store.applyUpdateEvidence(name, NEW, '40');
  expect(get(store.items)[name]).toBe('70');
  expect(warnings(name)[0]).toMatchObject({ unavailable: true });
  store.applyUpdateEvidence(name, NEW + 1, '71');
  expect(get(store.items)[name]).toBe('71'); expect(warnings(name)).toEqual([]);
});
it('accepts newer and same-value heartbeats but rejects older update pairs', () => {
  const name = names[0]; store.applySnapshot(snapshot(name, '70', OLD));
  expect(warnings(name)).toHaveLength(1);
  store.applyUpdateEvidence(name, NEW, '70'); expect(warnings(name)).toEqual([]);
  store.applyUpdateEvidence(name, NEW + 1, '71');
  store.applyUpdateEvidence(name, OLD, '40');
  expect(get(store.items)[name]).toBe('71');
  expect(get(store.itemUpdateEvidence)[name]).toMatchObject({ state: '71', lastKnown: NEW + 1 });
});
it.each([undefined, 'bad', NOW + 1])('does not attach a retained clock to a replacement with invalid clock %s', at => {
  const name = names[0]; store.applySnapshot(snapshot(name));
  store.applySnapshot([{ name, state: '40', lastStateUpdate: at }]);
  expect(warnings(name)[0]).toMatchObject({ unavailable: true });
});
it('timestamp-only evidence cannot authorize freshness for a changed value', () => {
  const name = names[0]; store.applySnapshot(snapshot(name));
  store.applyState(name, '40');
  store.applyUpdateEvidence(name, NEW + 1);
  expect(warnings(name)[0]).toMatchObject({ unavailable: true });
});
it.each(['change-first', 'update-first'])('keeps statechanged/stateupdated coherent (%s)', order => {
  const name = names[0]; store.applySnapshot(snapshot(name));
  if (order === 'change-first') {
    store.applyState(name, '71'); expect(warnings(name)[0]).toMatchObject({ unavailable: true });
    store.applyUpdateEvidence(name, NEW + 1, '71');
  } else {
    store.applyUpdateEvidence(name, NEW + 1, '71'); store.applyState(name, '71');
  }
  expect(get(store.items)[name]).toBe('71'); expect(warnings(name)).toEqual([]);
});
it('withdraws removed Items without silently resetting their source epoch', () => {
  const name = names[0]; store.applySnapshot(snapshot(name)); store.applySnapshot([]);
  expect(get(store.items)[name]).toBeUndefined(); expect(warnings(name)[0]).toMatchObject({ unavailable: true });
  store.applySnapshot(snapshot(name, '40', OLD));
  expect(get(store.items)[name]).toBeUndefined(); expect(warnings(name)[0]).toMatchObject({ unavailable: true });
});
it('freshness projection refuses evidence for a different displayed value', () => {
  const name = names[0];
  const alerts = computeStaleEssentials({ [name]: { available: true, state: '70', lastKnown: NEW } }, NOW,
    { ready: true, values: { [name]: '40' } });
  expect(alerts.find(item => item.name === name)).toMatchObject({ unavailable: true });
});

it('does not advance the accepted clock from a timestamp lacking its value', () => {
  const name = names[0]; store.applySnapshot(snapshot(name));
  store.applyUpdateEvidence(name, NEW + 1000);
  expect(get(store.itemUpdateEvidence)[name]).toMatchObject({ lastKnown: NEW, available: false });
  store.applyUpdateEvidence(name, NEW + 1, '71');
  expect(get(store.items)[name]).toBe('71'); expect(warnings(name)).toEqual([]);
});
it('does not resolve an equal-time contradiction by whichever duplicate arrives last', () => {
  const name = names[0]; store.applySnapshot(snapshot(name));
  store.applyUpdateEvidence(name, NEW, '40'); store.applyUpdateEvidence(name, NEW, '70');
  expect(warnings(name)[0]).toMatchObject({ unavailable: true });
});
it.each(['UNDEF', 'NULL', 'nonnumeric'])('does not label an unavailable temperature as fresh (%s)', state => {
  const name = names[0]; store.applySnapshot(snapshot(name, state));
  expect(warnings(name)[0]).toMatchObject({ unavailable: true });
});
