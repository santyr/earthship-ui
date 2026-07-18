// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { flushSync } from 'svelte';
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

vi.mock('echarts', () => ({ init: mocks.init }));
vi.mock('../../src/lib/openhab/index.js', () => ({
  getClientOnce: () => ({ getHistory: mocks.getHistory }),
}));

import ChartModal from '../../src/lib/ui/ChartModal.svelte';
import { closeChart, openChart } from '../../src/lib/ui/chartStore.js';

describe('ChartModal history periods', () => {
  beforeEach(() => {
    mocks.getHistory.mockReset();
    mocks.getHistory.mockResolvedValue([
      { time: Date.now() - 1_000, state: 10 },
      { time: Date.now(), state: 11 },
    ]);
    mocks.init.mockClear();
    mocks.chart.setOption.mockClear();
    mocks.chart.resize.mockClear();
    mocks.chart.dispose.mockClear();
  });

  afterEach(() => {
    closeChart();
    cleanup();
  });

  it('keeps 7d selected and refetches that window exactly once', async () => {
    render(ChartModal);
    openChart({
      title: 'Outdoor',
      series: [{
        name: 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature',
        label: 'Outdoor',
        color: '#f59e0b',
      }],
      hours: 24,
    });

    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalledTimes(1));
    await fireEvent.click(screen.getByRole('button', { name: '7d' }));

    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalledTimes(2));
    await Promise.resolve();
    await Promise.resolve();

    expect(screen.getByRole('button', { name: '7d' }).getAttribute('aria-pressed'))
      .toBe('true');
    expect(screen.getByRole('button', { name: '24h' }).getAttribute('aria-pressed'))
      .toBe('false');
    expect(mocks.getHistory).toHaveBeenCalledTimes(2);

    const request = mocks.getHistory.mock.calls[1][1];
    expect(Date.parse(request.endtime) - Date.parse(request.starttime))
      .toBeGreaterThanOrEqual(168 * 60 * 60 * 1_000);
  });

  it('aborts the superseded request when a new period is chosen', async () => {
    let resolveFirst;
    mocks.getHistory
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce([{ time: Date.now(), state: 11 }]);

    render(ChartModal);
    openChart({
      title: 'Outdoor',
      series: [{
        name: 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature',
        label: 'Outdoor',
      }],
      hours: 24,
    });
    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalledTimes(1));
    const firstSignal = mocks.getHistory.mock.calls[0][1].signal;

    await fireEvent.click(screen.getByRole('button', { name: '4h' }));
    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalledTimes(2));
    expect(firstSignal.aborted).toBe(true);

    resolveFirst([{ time: Date.now(), state: 99 }]);
  });

  it('does not start a queued request after the modal closes', async () => {
    render(ChartModal);
    openChart({
      title: 'Closing',
      series: [{ name: 'closing-series', label: 'Closing' }],
      hours: 24,
    });
    flushSync();
    closeChart();
    flushSync();

    await Promise.resolve();
    await Promise.resolve();
    expect(mocks.getHistory).not.toHaveBeenCalled();
  });

  it('lets only the latest queued open load during a rapid close and reopen', async () => {
    render(ChartModal);
    openChart({
      title: 'Old',
      series: [{ name: 'old-series', label: 'Old' }],
      hours: 24,
    });
    flushSync();
    closeChart();
    flushSync();
    openChart({
      title: 'New',
      series: [{ name: 'new-series', label: 'New' }],
      hours: 168,
    });
    flushSync();

    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalledTimes(1));
    expect(mocks.getHistory.mock.calls[0][0]).toBe('new-series');
  });
});
