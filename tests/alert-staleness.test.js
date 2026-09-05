import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { createSSE } from '../src/lib/openhab/sse.js';
import { initOpenhab, items, clientReady, itemUpdateEvidence, applySnapshot } from '../src/lib/openhab/store.js';
import { alertContext, consoleAlerts, startStalenessMonitor } from '../src/lib/alerts/alertStore.js';
import { ESSENTIAL_ITEMS, computeStaleEssentials } from '../src/lib/alerts/staleness.js';

const OUT = ESSENTIAL_ITEMS[0].name;
const IN = ESSENTIAL_ITEMS[1].name;
const NOW = Date.parse('2026-09-05T18:00:00Z');
let stream, stop, snapshot;
class FakeES { static all = []; constructor(url) { this.url = url; FakeES.all.push(this); } close() {} }
function emit(name, suffix, payload) {
  FakeES.all.at(-1).onmessage({ data: JSON.stringify({ topic: `openhab/items/${name}/${suffix}`, payload: JSON.stringify(payload) }) });
}
function healthy(at = Date.now()) {
  return [
    { name: OUT, state: '70', lastStateUpdate: at }, { name: IN, state: '69', lastStateUpdate: at },
    { name: 'BMS_SOC', state: '100', lastStateUpdate: at - 6 * 3600000 },
    { name: 'BMS_SOC_LastUpdate', state: new Date(at).toISOString() },
    { name: 'BMS_Comms_Status', state: 'OK' }, { name: 'BMS_DevicePresent', state: '1' },
  ];
}
async function boot(rows = healthy()) {
  snapshot = rows;
  const client = { getAllItems: vi.fn(async () => snapshot), getAllThings: async () => [] };
  await initOpenhab({ openhabUrl: '', staleBannerSeconds: 90 }, {
    clientFactory: () => client,
    sseFactory: (options) => { stream = createSSE(options); return stream; },
  });
  FakeES.all.at(-1).onopen();
  return client;
}
const warnings = () => get(consoleAlerts).alerts.filter(a => a.priorityKey === 'telemetry-stale');
beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(NOW); vi.stubGlobal('EventSource', FakeES);
  FakeES.all = []; items.set({}); clientReady.set(false); itemUpdateEvidence.set({});
  alertContext.set({ staleEssentials: [], batteryAlarms: [] }); stop = startStalenessMonitor();
});
afterEach(() => { stop(); stream?.stop(); stream = null; vi.unstubAllGlobals(); vi.useRealTimers(); });

it('does not manufacture boot alarms; an empty successful snapshot warns', async () => {
  expect(warnings()).toEqual([]); await boot([]);
  expect(warnings()).toHaveLength(3);
  expect(warnings().every(a => a.severity === 'warning' && a.shortText.includes('unavailable'))).toBe(true);
  expect(get(consoleAlerts).alerts.some(a => a.priorityKey === 'battery-critical')).toBe(false);
});
it('keeps hours of constant SoC healthy using the heartbeat value', async () => {
  await boot();
  for (let i = 0; i < 48; i++) {
    vi.advanceTimersByTime(5 * 60000); emit('BMS_SOC_LastUpdate', 'statechanged', { value: new Date(Date.now()).toISOString() });
    for (const name of [OUT, IN]) emit(name, 'stateupdated', { value: '70', lastStateUpdate: Date.now() });
    expect(warnings()).toEqual([]);
  }
  expect(get(items).BMS_SOC).toBe('100');
});
it('subscribes only to two update topics and never renders their duplicate values', async () => {
  await boot();
  expect(new URL(FakeES.all[0].url, 'http://fixture').searchParams.get('topics').split(',')).toEqual([
    'openhab/items/*/statechanged', 'openhab/things/*/status', `openhab/items/${OUT}/stateupdated`, `openhab/items/${IN}/stateupdated`]);
  const seen = vi.fn(); const unsubscribe = items.subscribe(seen); seen.mockClear();
  emit(OUT, 'statechanged', { value: '71' }); emit(OUT, 'stateupdated', { value: '71', lastStateUpdate: '2026-09-05T11:59:59.123456789-06:00[America/Denver]' });
  emit('Other', 'stateupdated', { value: '2', lastStateUpdate: NOW });
  expect(seen).toHaveBeenCalledTimes(1); expect(get(items)[OUT]).toBe('71'); expect(get(itemUpdateEvidence).Other).toBeUndefined(); unsubscribe();
});
it('statechanged cannot cure stale temperatures but equal-value updates can', async () => {
  await boot(healthy(NOW - 16 * 60000)); expect(warnings().map(a => a.id)).toContain(`telemetry-stale:${OUT}`);
  emit(OUT, 'statechanged', { value: '70' }); expect(warnings().map(a => a.id)).toContain(`telemetry-stale:${OUT}`);
  emit(OUT, 'stateupdated', { value: '70', lastStateUpdate: '2026-09-05T11:59:59.123456789-06:00[America/Denver]' });
  expect(get(itemUpdateEvidence)[OUT]).toEqual({ lastKnown: NOW - 877, available: true }); expect(warnings().map(a => a.id)).not.toContain(`telemetry-stale:${OUT}`);
});
it('retains diagnostic time on invalid evidence and ignores older valid evidence', async () => {
  await boot(); emit(OUT, 'stateupdated', { lastStateUpdate: 'bad' }); expect(get(itemUpdateEvidence)[OUT]).toEqual({ lastKnown: NOW, available: false });
  emit(OUT, 'stateupdated', { lastStateUpdate: NOW - 1 }); expect(get(itemUpdateEvidence)[OUT]).toEqual({ lastKnown: NOW, available: false });
  emit(OUT, 'stateupdated', { lastStateUpdate: NOW }); expect(get(itemUpdateEvidence)[OUT]).toEqual({ lastKnown: NOW, available: true });
  emit(OUT, 'stateupdated', {}); expect(get(itemUpdateEvidence)[OUT].available).toBe(false);
  emit(OUT, 'stateupdated', { lastStateUpdate: NOW + 1 }); expect(get(itemUpdateEvidence)[OUT]).toEqual({ lastKnown: NOW, available: false });
});
it('reconnect requests another snapshot without rejuvenating stale evidence', async () => {
  const client = await boot(healthy(NOW - 16 * 60000)); snapshot = healthy(NOW - 30 * 60000); FakeES.all[0].onerror(); await vi.advanceTimersByTimeAsync(1000); FakeES.all.at(-1).onopen(); await Promise.resolve(); await Promise.resolve();
  expect(client.getAllItems).toHaveBeenCalledTimes(2); expect(get(itemUpdateEvidence)[OUT].lastKnown).toBe(NOW - 16 * 60000); expect(warnings().map(a => a.id)).toContain(`telemetry-stale:${OUT}`);
  applySnapshot([]); expect(get(itemUpdateEvidence)[OUT]).toEqual({ lastKnown: NOW - 16 * 60000, available: false }); expect(get(items).BMS_SOC_LastUpdate).toBeUndefined();
});
it.each([undefined, 'NULL', 'UNDEF', 'bad', '2026-09-05T18:00:01Z', '2026-09-05T17:47:59Z'])('warns on unusable or expired heartbeat %s', async value => {
  await boot(); if (value === undefined) applySnapshot(healthy().filter(row => row.name !== 'BMS_SOC_LastUpdate')); else emit('BMS_SOC_LastUpdate', 'statechanged', { value });
  expect(warnings().map(a => a.id)).toContain('telemetry-stale:BMS_SOC');
});
it.each([undefined, 'NULL', 'UNDEF', ''])('missing comms %s warns without becoming a critical fault', async value => {
  await boot(); emit('BMS_Comms_Status', 'statechanged', { value: value ?? 'UNDEF' }); expect(warnings().map(a => a.id)).toContain('telemetry-stale:BMS_SOC'); expect(get(consoleAlerts).alerts.some(a => a.priorityKey === 'battery-critical')).toBe(false);
});
it.each([['BMS_Comms_Status', 'FAULT'], ['BMS_DevicePresent', 'OFF']])('explicit %s failure suppresses only redundant battery freshness', async (name, value) => {
  await boot(healthy(NOW - 16 * 60000)); emit(name, 'statechanged', { value }); expect(get(consoleAlerts).alerts.some(a => a.priorityKey === 'battery-critical')).toBe(true); expect(warnings().map(a => a.id)).not.toContain('telemetry-stale:BMS_SOC'); expect(warnings().map(a => a.id)).toContain(`telemetry-stale:${OUT}`);
});
it('checks exact thresholds and stops both reactive and timer updates', async () => {
  await boot(); const evaluate = elapsed => computeStaleEssentials(get(itemUpdateEvidence), NOW + elapsed, { values: get(items), ready: true }).map(a => a.name);
  expect(evaluate(12 * 60000)).not.toContain('BMS_SOC'); expect(evaluate(12 * 60000 + 1)).toContain('BMS_SOC'); expect(evaluate(15 * 60000)).not.toContain(OUT); expect(evaluate(15 * 60000 + 1)).toContain(OUT);
  stop(); const before = get(alertContext); emit('BMS_Comms_Status', 'statechanged', { value: 'UNDEF' }); vi.advanceTimersByTime(20 * 60000); expect(get(alertContext)).toBe(before);
});
