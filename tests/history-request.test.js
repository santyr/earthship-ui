import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadHistorySeries } from '../src/lib/charts/historyRequest.js';

const NOW = Date.UTC(2026, 6, 18, 12);
const HOUR = 60 * 60 * 1_000;
const REQUEST_TIMEOUT_MS = 15_000;

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('history request generation', () => {
  it('uses exact past-only history and future-only forecast bounds', async () => {
    const getHistory = vi.fn().mockResolvedValue([{ time: NOW, state: '1' }]);
    await loadHistorySeries({
      client: { getHistory },
      series: [
        { name: 'BMS_SOC' },
        { name: 'Forecast_Temp' },
      ],
      hours: 24,
      nowMs: NOW,
    });

    expect(getHistory.mock.calls[0][1]).toMatchObject({
      starttime: new Date(NOW - 24 * HOUR).toISOString(),
      endtime: new Date(NOW).toISOString(),
    });
    expect(getHistory.mock.calls[1][1]).toMatchObject({
      starttime: new Date(NOW).toISOString(),
      endtime: new Date(NOW + 18 * HOUR).toISOString(),
    });
  });

  it('distinguishes partial failure, full failure, and successful empty data', async () => {
    const partial = await loadHistorySeries({
      client: {
        getHistory: vi.fn()
          .mockResolvedValueOnce([{ time: NOW, state: '1' }])
          .mockRejectedValueOnce(new Error('offline')),
      },
      series: [{ name: 'BMS_SOC' }, { name: 'MPPT60_PV_Power' }],
      hours: 24,
      nowMs: NOW,
    });
    expect(partial.state).toBe('partial-error');
    expect(partial.pointsPerSeries).toEqual([[{ time: NOW, state: '1' }], []]);
    expect(partial.errors).toHaveLength(1);

    const failed = await loadHistorySeries({
      client: { getHistory: vi.fn().mockRejectedValue(new Error('offline')) },
      series: [{ name: 'BMS_SOC' }],
      hours: 24,
      nowMs: NOW,
    });
    expect(failed.state).toBe('error');

    const empty = await loadHistorySeries({
      client: { getHistory: vi.fn().mockResolvedValue([]) },
      series: [{ name: 'BMS_SOC' }],
      hours: 24,
      nowMs: NOW,
    });
    expect(empty.state).toBe('empty');
  });

  it('keeps completed series and times out every stalled series at one batch deadline', async () => {
    vi.useFakeTimers();
    const signals = [];
    const getHistory = vi.fn((name, { signal }) => {
      signals.push(signal);
      if (name === 'BMS_SOC') return Promise.resolve([{ time: NOW, state: '54' }]);
      return new Promise(() => {});
    });
    let result;
    let rejection;
    void loadHistorySeries({
      client: { getHistory },
      series: [
        { name: 'BMS_SOC' },
        { name: 'MPPT60_PV_Power' },
        { name: 'Forecast_Temp' },
      ],
      hours: 24,
      nowMs: NOW,
    }).then(
      (value) => { result = value; },
      (error) => { rejection = error; },
    );

    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS - 1);
    expect(result).toBeUndefined();
    await vi.advanceTimersByTimeAsync(1);

    expect(rejection).toBeUndefined();
    expect(result).toBeDefined();
    expect(result.state).toBe('partial-error');
    expect(result.timedOut).toBe(true);
    expect(result.pointsPerSeries).toEqual([[{ time: NOW, state: '54' }], [], []]);
    expect(result.errors.map(({ index, error }) => ({
      index,
      name: error?.name,
      code: error?.code,
    }))).toEqual([
      { index: 1, name: 'HistoryRequestTimeoutError', code: 'history-request-timeout' },
      { index: 2, name: 'HistoryRequestTimeoutError', code: 'history-request-timeout' },
    ]);
    expect(new Set(signals).size).toBe(1);
    expect(signals[0].aborted).toBe(true);
    expect(signals[0].reason?.code).toBe('history-request-timeout');
    expect(vi.getTimerCount()).toBe(0);
  });

  it('returns a distinct full-timeout outcome when every series stalls', async () => {
    vi.useFakeTimers();
    const getHistory = vi.fn(() => new Promise(() => {}));
    let result;
    void loadHistorySeries({
      client: { getHistory },
      series: [{ name: 'BMS_SOC' }, { name: 'MPPT60_PV_Power' }],
      hours: 24,
      nowMs: NOW,
    }).then((value) => { result = value; });

    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);

    expect(result).toBeDefined();
    expect(result.state).toBe('error');
    expect(result.timedOut).toBe(true);
    expect(result.errors).toHaveLength(2);
    expect(result.errors.every(({ error }) => error?.code === 'history-request-timeout')).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('composes caller cancellation, rejects promptly, and removes its listener and timer', async () => {
    vi.useFakeTimers();
    const caller = new AbortController();
    const add = vi.spyOn(caller.signal, 'addEventListener');
    const remove = vi.spyOn(caller.signal, 'removeEventListener');
    let requestSignal;
    const getHistory = vi.fn((name, { signal }) => {
      requestSignal = signal;
      return new Promise(() => {});
    });
    const reason = new DOMException('Chart closed', 'AbortError');
    let rejection;
    void loadHistorySeries({
      client: { getHistory },
      series: [{ name: 'BMS_SOC' }],
      hours: 24,
      nowMs: NOW,
      signal: caller.signal,
    }).catch((error) => { rejection = error; });

    caller.abort(reason);
    await vi.advanceTimersByTimeAsync(0);

    expect(rejection).toBe(reason);
    expect(requestSignal).not.toBe(caller.signal);
    expect(requestSignal.aborted).toBe(true);
    expect(requestSignal.reason).toBe(reason);
    expect(add).toHaveBeenCalledWith('abort', expect.any(Function), { once: true });
    expect(remove).toHaveBeenCalledWith('abort', expect.any(Function));
    expect(vi.getTimerCount()).toBe(0);
  });

  it('cleans its deadline and caller listener after a successful batch', async () => {
    vi.useFakeTimers();
    const caller = new AbortController();
    const add = vi.spyOn(caller.signal, 'addEventListener');
    const remove = vi.spyOn(caller.signal, 'removeEventListener');
    let requestSignal;
    const result = await loadHistorySeries({
      client: {
        getHistory: vi.fn((name, { signal }) => {
          requestSignal = signal;
          return Promise.resolve([{ time: NOW, state: '1' }]);
        }),
      },
      series: [{ name: 'BMS_SOC' }],
      hours: 24,
      nowMs: NOW,
      signal: caller.signal,
    });

    expect(result.state).toBe('ready');
    expect(result.timedOut).toBe(false);
    expect(requestSignal).not.toBe(caller.signal);
    expect(requestSignal.aborted).toBe(false);
    expect(add).toHaveBeenCalledWith('abort', expect.any(Function), { once: true });
    expect(remove).toHaveBeenCalledWith('abort', expect.any(Function));
    expect(vi.getTimerCount()).toBe(0);
  });
});
