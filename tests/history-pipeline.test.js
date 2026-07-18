import { describe, expect, it } from 'vitest';
import {
  normalizeHistory,
  prepareHistorySeries,
} from '../src/lib/charts/historyPipeline.js';

function rows(values, { start = 0, cadence = 1_000 } = {}) {
  return values.map((state, index) => ({
    time: start + index * cadence,
    state,
  }));
}

describe('bounded history pipeline', () => {
  it('normalizes chronologically and keeps the last arrival at a duplicate timestamp', () => {
    const result = normalizeHistory([
      { time: 2_000, state: '2' },
      { time: 1_000, state: '1' },
      { time: 2_000, state: '22' },
      { time: 'invalid', state: '9' },
      { time: 3_000, state: 'UNDEF' },
    ]);

    expect(result).toEqual([
      { time: 1_000, value: 1, rawValue: 1 },
      { time: 2_000, value: 22, rawValue: 22 },
    ]);
  });

  it('keeps zero, one, and two points unchanged', () => {
    for (const values of [[], [7], [7, 11]]) {
      const result = prepareHistorySeries(rows(values), {
        smoothing: 'median3-ema',
        expectedCadenceMs: 1_000,
        widthPx: 200,
      });
      expect(result.displaySegments.flat().map((point) => point.value)).toEqual(values);
    }
  });

  it('applies median-of-three then EMA alpha 0.25 while retaining raw tooltip values', () => {
    const result = prepareHistorySeries(rows([1, 100, 3, 4, 5]), {
      smoothing: 'median3-ema',
      alpha: 0.25,
      expectedCadenceMs: 1_000,
      widthPx: 200,
    });

    expect(result.displaySegments.flat().map((point) => point.value)).toEqual([
      1,
      1.5,
      2.125,
      2.59375,
      3.1953125,
    ]);
    expect(result.displaySegments.flat().map((point) => point.rawValue)).toEqual([
      1,
      100,
      3,
      4,
      5,
    ]);
  });

  it('never smooths across a gap greater than three cadences', () => {
    const input = [
      ...rows([10, 11, 12], { start: 0, cadence: 1_000 }),
      ...rows([30, 31, 32], { start: 10_000, cadence: 1_000 }),
    ];
    const result = prepareHistorySeries(input, {
      smoothing: 'median3-ema',
      expectedCadenceMs: 1_000,
      widthPx: 200,
    });

    expect(result.displaySegments).toHaveLength(2);
    expect(result.displaySegments[1][0]).toMatchObject({
      time: 10_000,
      value: 30,
      rawValue: 30,
    });
  });

  it('leaves unsmoothed numeric step lines byte-for-byte unchanged', () => {
    const input = rows([0, 0, 100, 100]);
    const result = prepareHistorySeries(input, {
      smoothing: 'none',
      expectedCadenceMs: 1_000,
      widthPx: 200,
    });

    expect(result.displaySegments.flat()).toEqual(result.raw);
  });

  it('bounds one series to two samples per CSS pixel and retains raw data separately', () => {
    const result = prepareHistorySeries(rows(Array.from({ length: 1_000 }, (_, i) => i)), {
      smoothing: 'none',
      expectedCadenceMs: 1_000,
      widthPx: 200,
    });

    expect(result.raw).toHaveLength(1_000);
    expect(result.displaySegments.flat()).toHaveLength(400);
    expect(result.displaySegments[0][0].time).toBe(0);
    expect(result.displaySegments[0].at(-1).time).toBe(999_000);
  });

  it('retains normalized raw samples but renders nothing at zero width', () => {
    const result = prepareHistorySeries(rows([1, 2, 3]), {
      smoothing: 'median3-ema',
      expectedCadenceMs: 1_000,
      widthPx: 0,
    });

    expect(result.raw).toHaveLength(3);
    expect(result.displaySegments).toEqual([]);
  });

  it('keeps the hard point cap even when gaps create more fragments than the budget', () => {
    const input = Array.from({ length: 20 }, (_, index) => ({
      time: index * 10_000,
      state: index,
    }));
    const result = prepareHistorySeries(input, {
      smoothing: 'none',
      maxGapMs: 1_000,
      widthPx: 1,
    });

    expect(result.displaySegments.flat().length).toBeLessThanOrEqual(2);
  });
});
