// @vitest-environment jsdom
import { cleanup, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `${process.cwd()}/node_modules/svelte/src/index-client.js`
));

const mocks = vi.hoisted(() => {
  const chart = { dispose: vi.fn(), resize: vi.fn(), setOption: vi.fn() };
  return { chart, init: vi.fn(() => chart) };
});

vi.mock('../../src/lib/charts/loadEcharts.js', () => ({
  getEcharts: async () => ({ init: mocks.init }),
}));

import Sparkline from '../../src/lib/ui/Sparkline.svelte';

describe('Sparkline', () => {
  beforeEach(() => {
    Object.defineProperties(HTMLElement.prototype, {
      clientWidth: { configurable: true, get: () => 200 },
      clientHeight: { configurable: true, get: () => 80 },
    });
    global.ResizeObserver = class {
      constructor(callback) { this.callback = callback; }
      observe() { this.callback([{ contentRect: { width: 200, height: 80 } }]); }
      disconnect() {}
    };
    mocks.chart.setOption.mockClear();
  });

  afterEach(cleanup);

  it('renders median-3 then EMA 0.25 as one non-interpolated compact line', async () => {
    render(Sparkline, {
      props: {
        data: [1, 100, 3, 4, 5].map((state, index) => ({ time: index * 1_000, state })),
      },
    });
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalled());
    const option = mocks.chart.setOption.mock.calls.at(-1)[0];
    expect(option.series[0].smooth).toBe(false);
    expect(option.series[0].data).toEqual([1, 1.5, 2.125, 2.59375, 3.1953125].map((value, index) => [index * 1000, value]));
    expect(option.series[0].data).not.toContain(null);
  });

  it('supports a validated per-instance EMA alpha for a calmer compact card', async () => {
    render(Sparkline, {
      props: {
        data: [1, 100, 3, 4, 5].map((state, index) => ({ time: index * 1_000, state })),
        smoothingAlpha: 0.12,
      },
    });
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalled());
    const option = mocks.chart.setOption.mock.calls.at(-1)[0];
    const expected = [1, 1.24, 1.5712, 1.862656, 2.23913728];
    expect(option.series[0].data).toHaveLength(expected.length);
    option.series[0].data.forEach(([timestamp, value], index) => {
      expect(timestamp).toBe(index * 1000);
      expect(value).toBeCloseTo(expected[index], 8);
    });
    expect(option.series[0].connectNulls).toBe(true);
    expect(option.series[0].data).not.toContain(null);
  });

  it.each([0, -0.1, 1.01, Number.NaN])('falls back to alpha 0.25 for invalid alpha %s', async (smoothingAlpha) => {
    render(Sparkline, {
      props: {
        data: [1, 100, 3, 4, 5].map((state, index) => ({ time: index * 1_000, state })),
        smoothingAlpha,
      },
    });
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalled());
    const option = mocks.chart.setOption.mock.calls.at(-1)[0];
    expect(option.series[0].data).toEqual([1, 1.5, 2.125, 2.59375, 3.1953125].map((value, index) => [index * 1000, value]));
  });

  it('preserves actual elapsed spacing for irregular change-only history', async () => {
    const start = Date.UTC(2026, 8, 10, 12);
    const timestamps = [start, start + 60_000, start + 3_600_000];
    render(Sparkline, { props: { data: timestamps.map((time, i) => ({time, state: 70 + i})) } });
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalled());
    const option = mocks.chart.setOption.mock.calls.at(-1)[0];
    expect(option.xAxis.type).toBe('time');
    expect(option.xAxis).not.toHaveProperty('data');
    expect(option.xAxis.boundaryGap).toEqual([0, 0]);
    expect(option.series[0].data.map(point => point[0])).toEqual(timestamps);
    expect(option.xAxis.show).toBe(false);
    expect(option.tooltip.show).toBe(false);
  });

  it('keeps distinct offset instants across the repeated DST hour', async () => {
    const times = ['2026-11-01T01:15:00-06:00', '2026-11-01T01:15:00-07:00'];
    render(Sparkline, { props: { data: times.map(time => ({time, state: 70})) } });
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalled());
    const points = mocks.chart.setOption.mock.calls.at(-1)[0].series[0].data;
    expect(points.map(point => point[0])).toEqual(times.map(Date.parse));
    expect(points[1][0] - points[0][0]).toBe(3_600_000);
  });
});
