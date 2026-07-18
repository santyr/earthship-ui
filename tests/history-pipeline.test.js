import { describe, expect, it } from 'vitest';
import {
  normalizeHistory,
  prepareHistorySeries,
  prepareSparklineSeries,
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
    ]);

    expect(result).toEqual([
      { time: 1_000, value: 1, rawValue: 1 },
      { time: 2_000, value: 22, rawValue: 22 },
    ]);
  });

  it('rejects malformed timestamps, partial numeric states, and unapproved units', () => {
    expect(() => normalizeHistory([{ time: 'invalid', state: '9' }]))
      .toThrow(/timestamp/i);
    expect(() => normalizeHistory([{ time: 1_000, state: '54 bananas' }], {
      allowedUnits: ['', '°F'],
    })).toThrow(/unit/i);
    expect(() => normalizeHistory([{ time: 1_000, state: '54°F trailing' }], {
      allowedUnits: ['', '°F'],
    })).toThrow(/unit/i);
    expect(() => normalizeHistory([{ time: 1_000, state: '54watts' }], {
      allowedUnits: ['', 'W'],
    })).toThrow(/unit/i);
    expect(() => normalizeHistory([{ time: 1_000, state: 'UNDEF' }]))
      .toThrow(/state/i);
  });

  it('accepts only an entire numeric state plus an explicitly allowed unit', () => {
    expect(normalizeHistory([
      { time: 1_000, state: '54.5 °F' },
      { time: 2_000, state: '-2.0e1°F' },
    ], { allowedUnits: ['', '°F'] }).map((point) => point.value)).toEqual([54.5, -20]);
  });

  it('keeps zero, one, and two main-chart points unchanged', () => {
    for (const values of [[], [7], [7, 11]]) {
      const result = prepareHistorySeries(rows(values), {
        expectedCadenceMs: 1_000,
        widthPx: 200,
      });
      expect(result.displaySegments.flat().map((point) => point.value)).toEqual(values);
    }
  });

  it('never smooths modal or inline history values', () => {
    const result = prepareHistorySeries(rows([1, 100, 3, 4, 5]), {
      expectedCadenceMs: 1_000,
      widthPx: 200,
    });

    expect(result.displaySegments.flat().map((point) => point.value)).toEqual([
      1,
      100,
      3,
      4,
      5,
    ]);
    expect(result.displaySegments.flat().map((point) => point.rawValue)).toEqual([
      1,
      100,
      3,
      4,
      5,
    ]);
  });

  it('renders one continuous source line across telemetry gaps', () => {
    const input = [
      ...rows([10, 11, 12], { start: 0, cadence: 1_000 }),
      ...rows([30, 31, 32], { start: 10_000, cadence: 1_000 }),
    ];
    const result = prepareHistorySeries(input, {
      expectedCadenceMs: 1_000,
      widthPx: 200,
    });

    expect(result.displaySegments).toHaveLength(1);
    expect(result.displaySegments[0][3]).toMatchObject({
      time: 10_000,
      value: 30,
      rawValue: 30,
    });
  });

  it('leaves numeric step lines byte-for-byte unchanged', () => {
    const input = rows([0, 0, 100, 100]);
    const result = prepareHistorySeries(input, {
      expectedCadenceMs: 1_000,
      widthPx: 200,
    });

    expect(result.displaySegments.flat()).toEqual(result.raw);
  });

  it('bounds one series to two samples per CSS pixel and retains raw data separately', () => {
    const result = prepareHistorySeries(rows(Array.from({ length: 1_000 }, (_, i) => i)), {
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
      expectedCadenceMs: 1_000,
      widthPx: 0,
    });

    expect(result.raw).toHaveLength(3);
    expect(result.displaySegments).toEqual([]);
  });

  it('fails truthfully when discontinuities exceed the endpoint render budget', () => {
    const input = Array.from({ length: 20 }, (_, index) => ({
      time: index * 10_000,
      state: index,
    }));
    expect(() => prepareHistorySeries(input, {
      maxGapMs: 1_000,
      widthPx: 1,
    })).toThrow(/data too fragmented for this range/i);
  });

  it('applies median-3 then EMA 0.25 only for compact sparklines, continuously', () => {
    const input = [
      ...rows([1, 100, 3], { start: 0, cadence: 1_000 }),
      ...rows([4, 5], { start: 10_000, cadence: 1_000 }),
    ];
    const result = prepareSparklineSeries(input, { widthPx: 200 });

    expect(result.map((point) => point.value)).toEqual([
      1,
      1.5,
      2.125,
      2.59375,
      3.1953125,
    ]);
    expect(result.map((point) => point.rawValue)).toEqual([1, 100, 3, 4, 5]);
  });
});
