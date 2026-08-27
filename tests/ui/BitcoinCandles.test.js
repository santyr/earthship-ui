// @vitest-environment jsdom
import { cleanup, render, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  process.cwd() + '/node_modules/svelte/src/index-client.js'
));

const mocks = vi.hoisted(() => {
  const chart = { dispose: vi.fn(), resize: vi.fn(), setOption: vi.fn() };
  return { chart, init: vi.fn(() => chart) };
});

vi.mock('../../src/lib/charts/loadEcharts.js', () => ({
  getEcharts: async () => ({ init: mocks.init }),
}));

import BitcoinCandles from '../../src/lib/ui/BitcoinCandles.svelte';

describe('BitcoinCandles', () => {
  let observers;

  beforeEach(() => {
    observers = [];
    Object.defineProperties(HTMLElement.prototype, {
      clientWidth: { configurable: true, get: () => 200 },
      clientHeight: { configurable: true, get: () => 80 },
    });
    global.ResizeObserver = class {
      constructor(callback) {
        this.callback = callback;
        observers.push(this);
      }
      observe() {}
      disconnect() {}
    };
    mocks.init.mockClear();
    mocks.chart.dispose.mockClear();
    mocks.chart.resize.mockClear();
    mocks.chart.setOption.mockClear();
  });

  afterEach(cleanup);

  it('lazily renders compact SVG candles, resizes, and disposes its chart', async () => {
    const { container, unmount } = render(BitcoinCandles, {
      props: {
        points: [
          { time: 1_000, state: '100' },
          { time: 20_000, state: '102' },
          { time: 40_000, state: '98' },
        ],
        startMs: 0,
        endMs: 60_000,
        interval: { unit: 'minutes', value: 1 },
      },
    });

    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalled());
    const element = container.querySelector('.bitcoin-candles');
    expect(mocks.init).toHaveBeenLastCalledWith(element, null, { renderer: 'svg' });
    const option = mocks.chart.setOption.mock.calls.at(-1)[0];
    expect(option.series[0].type).toBe('candlestick');
    expect(option.tooltip).toEqual({ show: false });
    expect(mocks.chart.setOption.mock.calls.at(-1)[1]).toBe(true);

    observers[0].callback([{ contentRect: { width: 240, height: 96 } }]);
    await waitFor(() => expect(mocks.chart.resize).toHaveBeenCalledWith({ width: 240, height: 96 }));

    unmount();
    expect(mocks.chart.dispose).toHaveBeenCalledTimes(1);
  });
});
