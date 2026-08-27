import { describe, expect, it } from 'vitest';
import {
  BITCOIN_CANDLE_COLORS,
  aggregateBitcoinCandles,
  bitcoinCandleInterval,
  buildBitcoinCandleOption,
  describeLatestBitcoinCandle,
} from '../src/lib/charts/bitcoinCandles.js';
import { HOME_STATE_COLORS } from '../src/lib/ui/homeCardState.js';

const MINUTE = 60_000;

describe('Bitcoin candle aggregation', () => {
  it('aggregates unsorted unit-suffixed observations into honest OHLC candles', () => {
    const candles = aggregateBitcoinCandles([
      { time: 3_000, state: '102 USD' },
      { time: 1_000, state: '100' },
      { time: 2_000, state: '98' },
    ], { interval: { unit: 'minutes', value: 1 }, startMs: 0, endMs: MINUTE });

    expect(candles).toEqual([{
      startMs: 0,
      endMs: MINUTE,
      open: 100,
      high: 102,
      low: 98,
      close: 102,
      direction: 'up',
      count: 3,
    }]);
  });

  it('keeps arrival order when valid observations share a timestamp', () => {
    const candles = aggregateBitcoinCandles([
      { time: 1_000, state: '100' },
      { time: 1_000, state: '98 USD' },
      { time: 2_000, state: '105' },
    ], { interval: { unit: 'minutes', value: 1 }, startMs: 0, endMs: MINUTE });

    expect(candles[0]).toMatchObject({ open: 100, high: 105, low: 98, close: 105, count: 3 });
  });

  it('omits invalid and out-of-window rows while retaining exact start boundaries', () => {
    const candles = aggregateBitcoinCandles([
      { time: -1, state: '99' },
      { time: 0, state: '100' },
      { time: 10_000, state: 'ON' },
      { time: 'invalid', state: '101' },
      { time: 59_999, state: '102 $' },
      { time: 60_000, state: '103' },
      { time: null, state: '104' },
    ], { interval: { unit: 'minutes', value: 1 }, startMs: 0, endMs: MINUTE });

    expect(candles).toEqual([expect.objectContaining({
      startMs: 0,
      endMs: MINUTE,
      open: 100,
      high: 102,
      low: 100,
      close: 102,
      count: 2,
    })]);
  });

  it('uses epoch-aligned buckets and omits intervals with no observations', () => {
    const candles = aggregateBitcoinCandles([
      { time: 59_999, state: '100' },
      { time: 120_001, state: '102' },
    ], { interval: { unit: 'minutes', value: 1 }, startMs: 0, endMs: 3 * MINUTE });

    expect(candles.map(({ startMs, endMs, count }) => ({ startMs, endMs, count }))).toEqual([
      { startMs: 0, endMs: MINUTE, count: 1 },
      { startMs: 2 * MINUTE, endMs: 3 * MINUTE, count: 1 },
    ]);
  });

  it('makes a one-sample candle neutral with a zero body', () => {
    const candles = aggregateBitcoinCandles([
      { time: 1_000, state: '100' },
    ], { interval: { unit: 'minutes', value: 1 }, startMs: 0, endMs: MINUTE });

    expect(candles).toEqual([expect.objectContaining({
      open: 100,
      high: 100,
      low: 100,
      close: 100,
      direction: 'neutral',
      count: 1,
    })]);
  });

  it('keeps an equal open and close neutral across multiple observations', () => {
    const candles = aggregateBitcoinCandles([
      { time: 1_000, state: '100' },
      { time: 2_000, state: '101' },
      { time: 3_000, state: '100' },
    ], { interval: { unit: 'minutes', value: 1 }, startMs: 0, endMs: MINUTE });

    expect(candles).toEqual([expect.objectContaining({
      open: 100,
      high: 101,
      low: 100,
      close: 100,
      direction: 'neutral',
      count: 3,
    })]);
  });

  it('marks a decreasing multi-sample candle down', () => {
    const candles = aggregateBitcoinCandles([
      { time: 1_000, state: '102' },
      { time: 2_000, state: '98' },
    ], { interval: { unit: 'minutes', value: 1 }, startMs: 0, endMs: MINUTE });

    expect(candles[0]).toMatchObject({ open: 102, close: 98, direction: 'down', count: 2 });
  });

  it('uses browser-local midnight boundaries through the spring DST day', () => {
    const dstDayStart = new Date(2026, 2, 8).getTime();
    const nextDayStart = new Date(2026, 2, 9).getTime();
    const followingDayStart = new Date(2026, 2, 10).getTime();
    const candles = aggregateBitcoinCandles([
      { time: new Date(2026, 2, 8, 0, 30).getTime(), state: '100' },
      { time: new Date(2026, 2, 8, 23, 30).getTime(), state: '110' },
      { time: new Date(2026, 2, 9, 0, 30).getTime(), state: '105' },
    ], {
      interval: { unit: 'day', value: 1 },
      startMs: dstDayStart,
      endMs: followingDayStart,
    });

    expect(candles.map(({ startMs, endMs, open, close }) => ({ startMs, endMs, open, close }))).toEqual([
      { startMs: dstDayStart, endMs: nextDayStart, open: 100, close: 110 },
      { startMs: nextDayStart, endMs: followingDayStart, open: 105, close: 105 },
    ]);
    expect(candles[0].endMs - candles[0].startMs).toBe(23 * 60 * MINUTE);
  });

  it.each([
    [4, { unit: 'minutes', value: 15 }],
    [24, { unit: 'minutes', value: 60 }],
    [168, { unit: 'minutes', value: 360 }],
    [720, { unit: 'day', value: 1 }],
  ])('maps %sh to the expected candle interval', (hours, expected) => {
    expect(bitcoinCandleInterval(hours)).toEqual(expected);
  });

  it('describes the latest candle with whole-dollar accessible text', () => {
    expect(describeLatestBitcoinCandle([{
      open: 100_000.4,
      high: 101_499.5,
      low: 99_500.49,
      close: 100_001.5,
    }])).toBe('Latest candle: open $100,000, high $101,500, low $99,500, close $100,002.');
    expect(describeLatestBitcoinCandle([])).toBe('');
  });

  it('exports the established up, down, and neutral colors', () => {
    expect(BITCOIN_CANDLE_COLORS).toEqual({
      up: '#22c55e',
      down: '#ef4444',
      neutral: '#f7931a',
    });
  });
});


describe('Bitcoin candle ECharts options', () => {
  const candles = [{
    startMs: 1_700_000_000_000,
    endMs: 1_700_000_060_000,
    open: 100,
    close: 102,
    low: 98,
    high: 103,
    direction: 'up',
    count: 3,
  }, {
    startMs: 1_700_000_060_000,
    endMs: 1_700_000_120_000,
    open: 102,
    close: 102,
    low: 101,
    high: 104,
    direction: 'neutral',
    count: 2,
  }];

  it('uses ECharts OHLC ordering, timestamp categories, and green/red candle colors', () => {
    const option = buildBitcoinCandleOption({ candles });

    expect(option.xAxis).toMatchObject({
      type: 'category',
      data: candles.map(({ startMs }) => startMs),
    });
    expect(option.yAxis).toMatchObject({ type: 'value', scale: true });
    expect(option.series[0]).toMatchObject({
      type: 'candlestick',
      itemStyle: {
        color: HOME_STATE_COLORS.positive,
        color0: HOME_STATE_COLORS.negative,
        borderColor: HOME_STATE_COLORS.positive,
        borderColor0: HOME_STATE_COLORS.negative,
      },
    });
    expect(option.series[0].data[0]).toEqual([100, 102, 98, 103]);
    expect(option.series[0].data[1]).toEqual({
      value: [102, 102, 101, 104],
      itemStyle: {
        color: HOME_STATE_COLORS.bitcoin,
        borderColor: HOME_STATE_COLORS.bitcoin,
      },
    });
    expect(option.dataZoom).toBeUndefined();
    expect(option.animation).toBe(false);
  });

  it('removes compact-chart axes and tooltip while preserving a scaled candle series', () => {
    const option = buildBitcoinCandleOption({ candles, compact: true });

    expect(option.xAxis).toMatchObject({ show: false });
    expect(option.yAxis).toMatchObject({ show: false, scale: true });
    expect(option.tooltip).toEqual({ show: false });
    expect(option.animation).toBe(false);
    expect(option.series[0].type).toBe('candlestick');
  });

  it('formats and escapes the full OHLC tooltip', () => {
    const option = buildBitcoinCandleOption({ candles });
    const html = option.tooltip.formatter([{
      axisValueLabel: '<script>alert(1)</script>',
      marker: '<i>marker</i>',
      data: [100, 102, 98, 103],
    }]);

    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;');
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('<i>marker</i>');
    expect(html).toContain('Open: $100');
    expect(html).toContain('High: $103');
    expect(html).toContain('Low: $98');
    expect(html).toContain('Close: $102');
  });
});
