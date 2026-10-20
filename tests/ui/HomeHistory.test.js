// @vitest-environment jsdom
import { cleanup, render } from '@testing-library/svelte';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
vi.mock('svelte', async () => import('../../node_modules/svelte/src/index-client.js'));
const mocks = vi.hoisted(() => ({ getHistory: vi.fn(), charts: [] }));
vi.mock('../../src/lib/charts/loadEcharts.js', () => ({
  getEcharts: async () => ({ init: element => {
    const chart = { element, setOption: vi.fn(), resize() {}, dispose: vi.fn() };
    mocks.charts.push(chart); return chart;
  } }),
}));
vi.mock('../../src/lib/openhab/index.js', async importOriginal => ({
  ...await importOriginal(), getClientOnce: () => ({ getHistory: mocks.getHistory }),
}));
// Optional household polling is unrelated to the OpenHAB histories under test.
vi.mock('../../src/lib/energy/forecastState.js', async () => {
  const { readable } = await import('svelte/store');
  return { energyForecastRaw: readable(null), energyForecastClock: readable(Date.now()) };
});
import Home from '../../src/screens/Home.svelte';
import { clientReady, items } from '../../src/lib/openhab/store.js';
const rollingNames = [
  'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature',
  'BMS_SOC',
  'AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative',
];
const parents = ['.outdoor-spark', '.battery-spark', '.baro-spark'];
const points = value => [{ time: Date.now() - 2000, state: String(value) }, { time: Date.now() - 1000, state: String(value) }];
const deferred = () => { let resolve; return { promise: new Promise(r => { resolve = r; }), resolve: value => resolve(value) }; };
async function settle() { await vi.advanceTimersByTimeAsync(0); }
function rolling(name, options) { return rollingNames.includes(name) && Date.parse(options.endtime) - Date.parse(options.starttime) === 6 * 3600000; }
function lastValue(parent) {
  const chart = mocks.charts.find(c => c.element.closest(parent));
  return chart?.setOption.mock.calls.at(-1)?.[0].series[0].data.at(-1)?.[1];
}
beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-20T18:00:00Z'));
  mocks.charts.length = 0; mocks.getHistory.mockReset();
  mocks.getHistory.mockResolvedValue([]); clientReady.set(false); items.set({});
});
afterEach(() => { cleanup(); clientReady.set(false); vi.useRealTimers(); });

it('keeps outdoor, battery and pressure histories from the newest refresh when older reads finish late', async () => {
  const older = new Map(rollingNames.map(name => [name, deferred()]));
  mocks.getHistory.mockImplementation((name, options) => rolling(name, options) ? older.get(name).promise : Promise.resolve([]));
  render(Home); clientReady.set(true); await settle();
  mocks.getHistory.mockImplementation((name, options) => Promise.resolve(rolling(name, options) ? points(88) : []));
  await vi.advanceTimersByTimeAsync(300000);
  for (const parent of parents) expect(lastValue(parent)).toBe(88);
  for (const request of older.values()) request.resolve(points(11));
  await settle();
  for (const parent of parents) expect(lastValue(parent)).toBe(88);
});

it('cancels every Home history request on navigation and never updates disposed charts', async () => {
  mocks.getHistory.mockReturnValue(new Promise(() => {}));
  const view = render(Home); clientReady.set(true); await settle();
  const signals = mocks.getHistory.mock.calls.map(([, options]) => options.signal);
  view.unmount(); await settle();
  expect(signals.length).toBeGreaterThanOrEqual(9);
  expect(signals.every(signal => signal?.aborted)).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
});

it('recovers the rolling histories on the next refresh after a stalled read', async () => {
  mocks.getHistory.mockReturnValue(new Promise(() => {}));
  render(Home); clientReady.set(true); await settle();
  const signals = mocks.getHistory.mock.calls.filter(([name, options]) => rolling(name, options)).map(([, options]) => options.signal);
  mocks.getHistory.mockImplementation((name, options) => Promise.resolve(rolling(name, options) ? points(44) : []));
  await vi.advanceTimersByTimeAsync(300000);
  expect(signals.every(signal => signal?.aborted)).toBe(true);
  for (const parent of parents) expect(lastValue(parent)).toBe(44);
});

it('waits through delayed startup and loads history when client readiness arrives', async () => {
  render(Home);
  await vi.advanceTimersByTimeAsync(600000);
  expect(mocks.getHistory).not.toHaveBeenCalled();
  clientReady.set(true); await settle();
  expect(mocks.getHistory.mock.calls.length).toBeGreaterThanOrEqual(9);
});
