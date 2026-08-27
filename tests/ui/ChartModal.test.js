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

const BITCOIN_SERIES = [{ name: 'BTC_USD_Price', label: 'BTC/USD', color: '#f7931a' }];
const CANDLE_PERIODS = [
  ['4h', 4, { unit: 'minutes', value: 15 }],
  ['24h', 24, { unit: 'minutes', value: 60 }],
  ['7d', 168, { unit: 'minutes', value: 360 }],
  ['30d', 720, { unit: 'day', value: 1 }],
];

function candleBucketStart(timeMs, interval) {
  if (interval.unit === 'day') {
    const date = new Date(timeMs);
    return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  }
  const intervalMs = interval.value * 60_000;
  return Math.floor(timeMs / intervalMs) * intervalMs;
}

function openBitcoinChart(initialHours) {
  openChart({
    title: 'Bitcoin (USD)',
    series: BITCOIN_SERIES,
    presentation: 'candlestick',
    initialHours,
  });
}

function modalDescription() {
  const dialog = screen.getByRole('dialog', { name: 'Bitcoin (USD)' });
  return document.getElementById(dialog.getAttribute('aria-describedby'));
}

describe('ChartModal history periods', () => {
  let observers;

  beforeEach(() => {
    observers = [];
    global.ResizeObserver = class {
      constructor(callback) {
        this.callback = callback;
        observers.push(this);
      }
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

  it('clears stale extrema immediately while a reopened modal is loading', async () => {
    mocks.getHistory.mockResolvedValueOnce([
      { time: 100, state: '62 %' },
      { time: 200, state: '71 %' },
    ]);

    render(ChartModal);
    const chartConfig = {
      title: 'Battery SoC',
      series: [{
        name: 'BMS_SOC',
        label: 'SoC',
        color: '#22c55e',
        markers: ['min', 'max'],
        markerUnit: '%',
      }],
      hours: 24,
    };
    openChart(chartConfig);

    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(1));
    let dialog = screen.getByRole('dialog', { name: 'Battery SoC' });
    let description = document.getElementById(dialog.getAttribute('aria-describedby'));
    expect(description.textContent).toMatch(/SoC: High 71%, Low 62%/);

    closeChart();
    flushSync();
    mocks.getHistory.mockImplementationOnce(() => new Promise(() => {}));
    openChart(chartConfig);
    flushSync();

    dialog = screen.getByRole('dialog', { name: 'Battery SoC' });
    description = document.getElementById(dialog.getAttribute('aria-describedby'));
    expect(description.textContent).toMatch(/Loading history/);
    expect(description.textContent).not.toMatch(/SoC: High 71%, Low 62%/);
  });

  it('does not announce extrema when the chart option fails to render', async () => {
    mocks.getHistory.mockResolvedValueOnce([
      { time: 100, state: '41 %' },
      { time: 200, state: '88 %' },
    ]);
    mocks.chart.setOption.mockImplementationOnce(() => {
      throw new Error('render failed');
    });

    render(ChartModal);
    openChart({
      title: 'Battery SoC',
      series: [{
        name: 'BMS_SOC',
        label: 'SoC',
        color: '#22c55e',
        markers: ['min', 'max'],
        markerUnit: '%',
      }],
      hours: 24,
    });

    expect(await screen.findByText('History unavailable')).toBeTruthy();
    const dialog = screen.getByRole('dialog', { name: 'Battery SoC' });
    const description = document.getElementById(dialog.getAttribute('aria-describedby'));
    expect(mocks.chart.setOption).toHaveBeenCalledWith(expect.any(Object), true);
    expect(description.textContent).toMatch(/render failed/);
    expect(description.textContent).not.toMatch(/SoC: High 88%, Low 41%/);
  });

  it('recomputes and announces extrema when the selected period changes', async () => {
    mocks.getHistory
      .mockResolvedValueOnce([
        { time: 100, state: '62 %' },
        { time: 200, state: '71 %' },
      ])
      .mockResolvedValueOnce([
        { time: 100, state: '41 %' },
        { time: 200, state: '88 %' },
      ]);

    render(ChartModal);
    openChart({
      title: 'Battery SoC',
      series: [{
        name: 'BMS_SOC',
        label: 'SoC',
        color: '#22c55e',
        markers: ['min', 'max'],
        markerUnit: '%',
      }],
      hours: 24,
    });

    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(1));
    let option = mocks.chart.setOption.mock.calls.at(-1)[0];
    expect(option.series[0].markPoint.data.map((marker) => marker.value))
      .toEqual([71, 62]);

    const dialog = screen.getByRole('dialog', { name: 'Battery SoC' });
    const description = document.getElementById(dialog.getAttribute('aria-describedby'));
    expect(description.textContent).toMatch(/SoC: High 71%, Low 62%/);

    await fireEvent.click(screen.getByRole('button', { name: '7d' }));
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(2));
    option = mocks.chart.setOption.mock.calls.at(-1)[0];
    expect(option.series[0].markPoint.data.map((marker) => marker.value))
      .toEqual([88, 41]);
    expect(description.textContent).toMatch(/SoC: High 88%, Low 41%/);
  });

  it.each(CANDLE_PERIODS)(
    'renders the %s Bitcoin selector with its mapped candle interval and latest OHLC',
    async (label, hours, interval) => {
      const pointTime = Date.now() - 60_000;
      mocks.getHistory.mockResolvedValue([
        { time: pointTime, state: '100000 USD' },
        { time: pointTime, state: '101000 USD' },
        { time: pointTime, state: '99500 USD' },
        { time: pointTime, state: '100500 USD' },
      ]);

      render(ChartModal);
      openBitcoinChart(hours === 24 ? 4 : 24);
      await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(1));

      await fireEvent.click(screen.getByRole('button', { name: label }));
      await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(2));

      const option = mocks.chart.setOption.mock.calls.at(-1)[0];
      expect(screen.getByRole('button', { name: label }).getAttribute('aria-pressed')).toBe('true');
      expect(option.xAxis.data).toEqual([candleBucketStart(pointTime, interval)]);
      expect(option.series[0].type).toBe('candlestick');
      expect(option.series[0].data).toEqual([[100000, 100500, 99500, 101000]]);
      expect(modalDescription().textContent).toContain(
        'Latest candle: open $100,000, high $101,000, low $99,500, close $100,500.',
      );
    },
  );

  it('retains valid Bitcoin candles when persistence mixes malformed rows', async () => {
    const pointTime = Date.now() - 60_000;
    mocks.getHistory.mockResolvedValue([
      { time: pointTime, state: '100000 USD' },
      { time: 'not-a-time', state: '100250 USD' },
      { time: pointTime, state: 'UNDEF' },
      { time: pointTime, state: '99999 EUR' },
      { time: pointTime + 1, state: '100500 $' },
    ]);

    render(ChartModal);
    openBitcoinChart(24);

    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(1));
    const option = mocks.chart.setOption.mock.calls.at(-1)[0];
    expect(option.series[0].data).toEqual([[100000, 100500, 100000, 100500]]);
    expect(modalDescription().textContent).toContain(
      'Latest candle: open $100,000, high $100,500, low $100,000, close $100,500.',
    );
  });

  it('clears stale candle OHLC immediately on reload, error, and empty history', async () => {
    const pointTime = Date.now() - 60_000;
    mocks.getHistory.mockResolvedValueOnce([
      { time: pointTime, state: '100000' },
      { time: pointTime, state: '101000' },
    ]);

    render(ChartModal);
    openBitcoinChart(24);
    await waitFor(() => expect(modalDescription().textContent).toContain('Latest candle:'));

    mocks.getHistory.mockImplementationOnce(() => new Promise(() => {}));
    await fireEvent.click(screen.getByRole('button', { name: '7d' }));
    await waitFor(() => expect(mocks.getHistory).toHaveBeenCalledTimes(2));
    expect(modalDescription().textContent).toContain('Loading history');
    expect(modalDescription().textContent).not.toContain('Latest candle:');

    closeChart();
    mocks.getHistory.mockRejectedValueOnce(new Error('offline'));
    openBitcoinChart(24);
    expect(await screen.findByText('History unavailable')).toBeTruthy();
    expect(modalDescription().textContent).not.toContain('Latest candle:');

    closeChart();
    mocks.getHistory.mockResolvedValueOnce([]);
    openBitcoinChart(24);
    expect(await screen.findByText('No data')).toBeTruthy();
    expect(modalDescription().textContent).not.toContain('Latest candle:');
  });

  it('clears candle OHLC when candlestick option rendering fails', async () => {
    const pointTime = Date.now() - 60_000;
    mocks.getHistory.mockResolvedValue([
      { time: pointTime, state: '100000' },
      { time: pointTime, state: '101000' },
    ]);

    render(ChartModal);
    openBitcoinChart(24);
    await waitFor(() => expect(modalDescription().textContent).toContain('Latest candle:'));

    closeChart();
    mocks.chart.setOption.mockImplementationOnce(() => {
      throw new Error('candle render failed');
    });
    openBitcoinChart(24);

    expect(await screen.findByText('History unavailable')).toBeTruthy();
    expect(modalDescription().textContent).toContain('candle render failed');
    expect(modalDescription().textContent).not.toContain('Latest candle:');
  });

  it('keeps candlestick rendering through resize and disposes it on close', async () => {
    const pointTime = Date.now() - 60_000;
    mocks.getHistory.mockResolvedValue([
      { time: pointTime, state: '100000' },
      { time: pointTime, state: '101000' },
    ]);

    render(ChartModal);
    openBitcoinChart(24);
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(1));
    expect(mocks.chart.setOption.mock.calls.at(-1)[0].series[0].type).toBe('candlestick');

    observers[0].callback([{ contentRect: { width: 920, height: 480 } }]);
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalledTimes(2));
    expect(mocks.chart.setOption.mock.calls.at(-1)[0].series[0].type).toBe('candlestick');

    closeChart();
    await waitFor(() => expect(mocks.chart.dispose).toHaveBeenCalledTimes(1));
  });
});
