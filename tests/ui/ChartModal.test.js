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

vi.mock('../../src/lib/charts/loadEcharts.js', () => ({
  getEcharts: async () => ({ init: mocks.init }),
}));
vi.mock('../../src/lib/openhab/index.js', () => ({
  getClientOnce: () => ({ getHistory: mocks.getHistory }),
}));

import ChartModal from '../../src/lib/ui/ChartModal.svelte';
import { closeChart, openChart } from '../../src/lib/ui/chartStore.js';

describe('ChartModal history periods', () => {
  beforeEach(() => {
    global.ResizeObserver = class {
      observe() {}
      disconnect() {}
    };
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
      .toBe(168 * 60 * 60 * 1_000);
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

  it('labels the dialog, focuses the active period, traps focus, closes on Escape, and restores focus', async () => {
    const opener = document.createElement('button');
    opener.textContent = 'Open chart';
    document.body.append(opener);
    opener.focus();
    render(ChartModal);
    openChart({
      title: 'Outdoor',
      series: [{ name: 'BMS_SOC', label: 'SoC' }],
      hours: 24,
    });

    const dialog = await screen.findByRole('dialog', { name: 'Outdoor' });
    expect(dialog.getAttribute('aria-describedby')).toBeTruthy();
    await waitFor(() => expect(document.activeElement)
      .toBe(screen.getByRole('button', { name: '24h' })));
    const close = screen.getByRole('button', { name: 'Close chart' });
    close.focus();
    await fireEvent.keyDown(dialog, { key: 'Tab' });
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '4h' }));
    await fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(opener);
  });

  it('refreshes an active modal every five minutes', async () => {
    const interval = vi.spyOn(globalThis, 'setInterval');
    render(ChartModal);
    openChart({ title: 'Battery', series: [{ name: 'BMS_SOC', label: 'SoC' }], hours: 24 });
    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalledTimes(1));
    expect(interval).toHaveBeenCalledWith(expect.any(Function), 300_000);
    interval.mockRestore();
  });

  it('keeps successful series visible while announcing partial failures', async () => {
    mocks.getHistory
      .mockResolvedValueOnce([{ time: Date.now(), state: '54 %' }])
      .mockRejectedValueOnce(new Error('offline'));
    render(ChartModal);
    openChart({
      title: 'Energy',
      series: [{ name: 'BMS_SOC', label: 'SoC' }, { name: 'MPPT60_PV_Power', label: 'PV' }],
      hours: 24,
    });

    expect(await screen.findByText('1 series unavailable')).toBeTruthy();
    await waitFor(() => expect(mocks.init).toHaveBeenCalled());
  });

  it('distinguishes a failed request from successful no-data', async () => {
    mocks.getHistory.mockRejectedValueOnce(new Error('offline'));
    render(ChartModal);
    openChart({ title: 'Broken', series: [{ name: 'BMS_SOC', label: 'SoC' }] });
    expect(await screen.findByText('History unavailable')).toBeTruthy();

    closeChart();
    mocks.getHistory.mockResolvedValueOnce([]);
    openChart({ title: 'Empty', series: [{ name: 'BMS_SOC', label: 'SoC' }] });
    expect(await screen.findByText('No data')).toBeTruthy();
  });

  it('names timed-out series instead of calling them generically unavailable', async () => {
    const timeout = Object.assign(
      new Error('History request timed out after 15 seconds'),
      { code: 'history-request-timeout' },
    );
    mocks.getHistory
      .mockResolvedValueOnce([{ time: Date.now(), state: '54 %' }])
      .mockRejectedValueOnce(timeout)
      .mockRejectedValueOnce(timeout);
    render(ChartModal);
    openChart({
      title: 'Energy',
      series: [
        { name: 'BMS_SOC', label: 'SoC' },
        { name: 'MPPT60_PV_Power', label: 'PV' },
        { name: 'Forecast_Temp', label: 'Forecast' },
      ],
      hours: 24,
    });

    expect(await screen.findByText('2 series timed out')).toBeTruthy();
    expect(screen.queryByText('2 series unavailable')).toBeNull();
    await waitFor(() => expect(mocks.init).toHaveBeenCalled());
  });

  it('surfaces the full timeout reason', async () => {
    mocks.getHistory.mockRejectedValueOnce(Object.assign(
      new Error('History request timed out after 15 seconds'),
      { code: 'history-request-timeout' },
    ));
    render(ChartModal);
    openChart({ title: 'Slow', series: [{ name: 'BMS_SOC', label: 'SoC' }] });

    expect(await screen.findByText(
      /history request timed out after 15 seconds/i,
      { selector: 'small' },
    )).toBeTruthy();
    const dialog = screen.getByRole('dialog', { name: 'Slow' });
    const description = document.getElementById(dialog.getAttribute('aria-describedby'));
    expect(description.textContent).toMatch(/history request timed out after 15 seconds/i);
  });
});
