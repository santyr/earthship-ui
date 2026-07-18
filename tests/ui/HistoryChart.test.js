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
});
