import { describe, expect, it } from 'vitest';
import {
  HISTORY_PERIODS,
  HISTORY_PERIOD_PRESETS,
  createHistoryWindow,
  getSeriesRequestWindow,
  snapHistoryPeriod,
} from '../src/lib/charts/periods.js';

describe('history periods', () => {
  it('exposes only the supported 4h, 24h, 7d, and 30d windows', () => {
    expect(HISTORY_PERIODS).toEqual([4, 24, 168, 720]);
    expect(HISTORY_PERIOD_PRESETS).toEqual([
      { label: '4h', hours: 4 },
      { label: '24h', hours: 24 },
      { label: '7d', hours: 168 },
      { label: '30d', hours: 720 },
    ]);
  });

  it('snaps an initial value but rejects unsupported interactive selections', () => {
    expect(snapHistoryPeriod(23)).toBe(24);
    expect(snapHistoryPeriod(169)).toBe(168);
    expect(snapHistoryPeriod(Number.NaN)).toBe(24);
    expect(() => createHistoryWindow(12, { nowMs: 1_000 })).toThrow(/period/i);
  });

  it('captures deterministic but non-overlapping history and forecast windows', () => {
    const nowMs = Date.UTC(2026, 6, 18, 12);
    const window = createHistoryWindow(168, {
      nowMs,
      lookaheadMs: 18 * 60 * 60 * 1_000,
    });

    expect(Date.parse(window.starttime)).toBe(nowMs - 168 * 60 * 60 * 1_000);
    expect(Date.parse(window.historyEndtime)).toBe(nowMs);
    expect(Date.parse(window.forecastStarttime)).toBe(nowMs);
    expect(Date.parse(window.endtime)).toBe(nowMs + 18 * 60 * 60 * 1_000);
    expect(window.hours).toBe(168);
    expect(window.nowMs).toBe(nowMs);
    expect(window.history).toEqual({
      starttime: new Date(nowMs - 168 * 60 * 60 * 1_000).toISOString(),
      endtime: new Date(nowMs).toISOString(),
    });
    expect(window.forecast).toEqual({
      starttime: new Date(nowMs).toISOString(),
      endtime: new Date(nowMs + 18 * 60 * 60 * 1_000).toISOString(),
    });
  });

  it('selects exact request bounds from the series domain', () => {
    const nowMs = Date.UTC(2026, 6, 18, 12);
    const window = createHistoryWindow(24, { nowMs, lookaheadMs: 60_000 });

    expect(getSeriesRequestWindow({ name: 'BMS_SOC' }, window)).toEqual(window.history);
    expect(getSeriesRequestWindow(
      { name: 'Predicted_SoC_Trough_Tomorrow' }, window,
    )).toEqual(window.history);
    expect(getSeriesRequestWindow({ name: 'Forecast_Temp' }, window)).toEqual(window.forecast);
  });
});
