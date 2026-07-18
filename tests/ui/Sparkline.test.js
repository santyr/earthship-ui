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
    expect(option.series[0].data).toEqual([1, 1.5, 2.125, 2.59375, 3.1953125]);
    expect(option.series[0].data).not.toContain(null);
  });
});
