// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `${process.cwd()}/node_modules/svelte/src/index-client.js`
));

const mocks = vi.hoisted(() => {
  const chart = {
    dispose: vi.fn(),
    resize: vi.fn(),
    setOption: vi.fn(),
  };
  return {
    chart,
    getHistory: vi.fn(),
    init: vi.fn(() => chart),
  };
});

vi.mock('../../src/lib/charts/loadEcharts.js', () => ({
  getEcharts: async () => ({ init: mocks.init }),
}));
vi.mock('../../src/lib/openhab/index.js', async () => {
  const { readable: makeReadable } = await import('svelte/store');
  return {
    clientReady: makeReadable(true),
    getClientOnce: () => ({ getHistory: mocks.getHistory }),
  };
});

import HistoryChart from '../../src/lib/ui/HistoryChart.svelte';
import { items } from '../../src/lib/openhab/store.js';

describe('HistoryChart', () => {
  beforeEach(() => {
    global.ResizeObserver = class {
      observe() {}
      disconnect() {}
    };
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      get: () => 320,
    });
    mocks.getHistory.mockReset();
    mocks.getHistory.mockResolvedValue([
      { time: 0, state: 1 },
      { time: 1_000, state: 100 },
      { time: 2_000, state: 3 },
      { time: 3_000, state: 4 },
      { time: 4_000, state: 5 },
    ]);
    mocks.chart.setOption.mockClear();
    mocks.chart.resize.mockClear();
    mocks.chart.dispose.mockClear();
    mocks.init.mockClear();
    items.set({});
  });

  afterEach(cleanup);

  it('uses the shared period/option pipeline and stays bounded by its parent', async () => {
    const { container } = render(HistoryChart, {
      props: {
        series: [{
          name: 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature',
          label: 'Outdoor',
          color: '#f59e0b',
        }],
        initialHours: 24,
      },
    });

    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalledTimes(1));
    await fireEvent.click(screen.getByRole('button', { name: '7d' }));
    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalledTimes(2));

    expect(screen.getByRole('button', { name: '7d' }).getAttribute('aria-pressed'))
      .toBe('true');
    expect(mocks.getHistory).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalled());
    const option = mocks.chart.setOption.mock.calls.at(-1)[0];
    expect(option.series[0].smooth).toBe(false);
    expect(option.series[0].data[1][1]).toBe(100);
    expect(option.series[0].data[1][2]).toBe(100);
    expect(container.querySelector('.history-chart').getAttribute('style') || '')
      .not.toMatch(/height:\s*\d+px/i);
  });

  it('renders successful data and announces a partial series failure', async () => {
    mocks.getHistory
      .mockResolvedValueOnce([{ time: 0, state: '50 %' }])
      .mockRejectedValueOnce(new Error('offline'));
    render(HistoryChart, {
      props: {
        series: [{ name: 'BMS_SOC', label: 'SoC' }, { name: 'MPPT60_PV_Power', label: 'PV' }],
      },
    });

    expect(await screen.findByText('1 series unavailable')).toBeTruthy();
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalled());
  });

  it('names timed-out series instead of calling them generically unavailable', async () => {
    const timeout = Object.assign(
      new Error('History request timed out after 15 seconds'),
      { code: 'history-request-timeout' },
    );
    mocks.getHistory
      .mockResolvedValueOnce([{ time: 0, state: '50 %' }])
      .mockRejectedValueOnce(timeout)
      .mockRejectedValueOnce(timeout);
    render(HistoryChart, {
      props: {
        series: [
          { name: 'BMS_SOC', label: 'SoC' },
          { name: 'MPPT60_PV_Power', label: 'PV' },
          { name: 'Forecast_Temp', label: 'Forecast' },
        ],
      },
    });

    expect(await screen.findByText('2 series timed out')).toBeTruthy();
    expect(screen.queryByText('2 series unavailable')).toBeNull();
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalled());
  });

  it('surfaces the full timeout reason', async () => {
    mocks.getHistory.mockRejectedValueOnce(Object.assign(
      new Error('History request timed out after 15 seconds'),
      { code: 'history-request-timeout' },
    ));
    render(HistoryChart, {
      props: { series: [{ name: 'BMS_SOC', label: 'SoC' }] },
    });

    expect(await screen.findByText(/history request timed out after 15 seconds/i)).toBeTruthy();
  });

  it('keeps the battery chart visible and reuses it during a history refresh', async () => {
    let finishRefresh;
    mocks.getHistory
      .mockResolvedValueOnce([{ time: 0, state: '50 %' }])
      .mockImplementationOnce(() => new Promise((resolve) => { finishRefresh = resolve; }));
    const { container } = render(HistoryChart, {
      props: { series: [{ name: 'BMS_SOC', label: 'SoC' }], refreshMs: 100 },
    });

    await waitFor(() => expect(mocks.init).toHaveBeenCalledTimes(1));
    const canvas = container.querySelector('.hc-canvas');
    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalledTimes(2));
    expect(container.querySelector('.hc-canvas')).toBe(canvas);
    expect(screen.queryByText('Loading…')).toBeNull();
    expect(mocks.chart.dispose).not.toHaveBeenCalled();

    finishRefresh([{ time: 0, state: '51 %' }]);
    await waitFor(() => expect(mocks.chart.setOption.mock.calls.length).toBeGreaterThan(1));
    expect(mocks.init).toHaveBeenCalledTimes(1);
    expect(container.querySelector('.hc-canvas')).toBe(canvas);
    expect(mocks.chart.setOption.mock.calls.at(-1)[1]).toEqual({ replaceMerge: ['series'] });
    expect(mocks.chart.resize).toHaveBeenCalledTimes(1);
  });

  it('does not repaint an unchanged battery history response', async () => {
    const rows = [{ time: 0, state: '50 %' }];
    mocks.getHistory.mockResolvedValue(rows);
    const { container } = render(HistoryChart, {
      props: { series: [{ name: 'BMS_SOC', label: 'SoC' }], refreshMs: 200 },
    });

    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(1));
    const canvas = container.querySelector('.hc-canvas');
    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalledTimes(2));
    expect(mocks.chart.setOption).toHaveBeenCalledTimes(1);
    expect(container.querySelector('.hc-canvas')).toBe(canvas);
    expect(mocks.chart.dispose).not.toHaveBeenCalled();
  });

  it('advances a moving forecast overlay on refresh without replacing the canvas', async () => {
    mocks.getHistory.mockResolvedValue([{ time: 0, state: '50 %' }]);
    const { container } = render(HistoryChart, {
      props: {
        series: [
          { name: 'BMS_SOC', label: 'SoC' },
          { name: 'Predicted_SoC_Trough_Tomorrow', label: 'Predicted trough',
            dashedFromNow: true, projectionValue: 80, projectionHours: 18 },
        ],
        refreshMs: 200,
      },
    });

    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(1));
    const canvas = container.querySelector('.hc-canvas');
    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalledTimes(4));
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(2));
    expect(container.querySelector('.hc-canvas')).toBe(canvas);
    expect(mocks.chart.dispose).not.toHaveBeenCalled();
  });

  it('redraws SoC only when the fresh value changes or expires', async () => {
    const interval = vi.spyOn(globalThis, 'setInterval');
    try {
      render(HistoryChart, {
        props: { series: [{ name: 'BMS_SOC', label: 'SoC' }], refreshMs: 30 * 60_000 },
      });
      await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(1));
      const socTick = interval.mock.calls.find(([, ms]) => ms === 5 * 60_000)?.[0];
      expect(socTick).toBeTypeOf('function');

      const observedAt = Date.now() - 1_000;
      const receipt = (soc) => JSON.stringify({
        version: 1, streamEpoch: '123e4567-e89b-42d3-a456-426614174000',
        recordedAt: observedAt + 500, status: 'valid', reason: 'ok',
        observedAt, scaleObservedAt: observedAt,
        validUntil: observedAt + 120_000, soc,
      });
      items.set({ BMS_SOC_Evidence_JSON: receipt(75) });
      socTick();
      await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(2));
      socTick();
      expect(mocks.chart.setOption).toHaveBeenCalledTimes(2);

      items.set({ BMS_SOC_Evidence_JSON: receipt(76) });
      socTick();
      await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(3));
      items.set({});
      socTick();
      await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(4));
    } finally {
      interval.mockRestore();
    }
  });

  it('retains the last good battery plot when a scheduled refresh fails', async () => {
    mocks.getHistory
      .mockResolvedValueOnce([{ time: 0, state: '50 %' }])
      .mockRejectedValueOnce(new Error('temporary outage'));
    const { container } = render(HistoryChart, {
      props: { series: [{ name: 'BMS_SOC', label: 'SoC' }], refreshMs: 100 },
    });

    await waitFor(() => expect(mocks.init).toHaveBeenCalledTimes(1));
    const canvas = container.querySelector('.hc-canvas');
    expect(await screen.findByText(/showing last successful history/i)).toBeTruthy();
    expect(container.querySelector('.hc-canvas')).toBe(canvas);
    expect(mocks.chart.dispose).not.toHaveBeenCalled();
  });

  it('keeps the battery canvas when forecast presentation changes', async () => {
    const initialSeries = [{ name: 'BMS_SOC', label: 'SoC', color: '#f59e0b' }];
    const { container, rerender } = render(HistoryChart, {
      props: { series: initialSeries },
    });

    await waitFor(() => expect(mocks.init).toHaveBeenCalledTimes(1));
    const canvas = container.querySelector('.hc-canvas');
    await rerender({ series: [{ ...initialSeries[0], color: '#22c55e' }] });
    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalledTimes(2));

    expect(container.querySelector('.hc-canvas')).toBe(canvas);
    expect(mocks.chart.dispose).not.toHaveBeenCalled();
    expect(mocks.init).toHaveBeenCalledTimes(1);
  });
});
