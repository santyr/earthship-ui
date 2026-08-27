import { describe, expect, it } from 'vitest';
import {
  BITCOIN_CANDLE_COLORS,
  aggregateBitcoinCandles,
  bitcoinCandleInterval,
  describeLatestBitcoinCandle,
} from '../src/lib/charts/bitcoinCandles.js';

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
