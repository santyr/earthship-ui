import { describe, expect, it } from 'vitest';
import {
  buildExtremaMarkPoint,
  describeExtremaMarkers,
  findHistoryExtrema,
  formatHistoryValue,
} from '../src/lib/charts/extremaMarkers.js';

describe('history extrema markers', () => {
  it('rounds positive and negative decimal ties half away from zero', () => {
    expect(formatHistoryValue(0.5005)).toBe('0.501');
    expect(formatHistoryValue(-0.5005)).toBe('-0.501');
  });

  it('selects the earliest matching extrema without mutating normalized points', () => {
    const points = [
      { time: 300, value: 9, rawValue: 9.1234 },
      { time: 100, value: 9, rawValue: 9 },
      { time: 200, value: 1, rawValue: 1.25 },
      { time: 400, value: 1, rawValue: 1 },
    ];
    const snapshot = structuredClone(points);

    expect(findHistoryExtrema(points)).toEqual({
      min: { time: 200, value: 1, rawValue: 1.25 },
      max: { time: 100, value: 9, rawValue: 9 },
    });
    expect(points).toEqual(snapshot);
  });

  it('ignores unusable points and returns no marker config for empty data', () => {
    expect(findHistoryExtrema([
      { time: 1, value: Number.NaN },
      { time: Number.NaN, value: 5 },
    ])).toEqual({ min: null, max: null });
    expect(buildExtremaMarkPoint([], { markers: ['min', 'max'] })).toBeUndefined();
  });

  it('builds High and Low pins with units and matching accessible text', () => {
    const markPoint = buildExtremaMarkPoint([
      { time: 100, value: 62, rawValue: 62 },
      { time: 200, value: 87.5555, rawValue: 87.5555 },
      { time: 300, value: 41.25, rawValue: 41.25 },
    ], {
      markers: ['min', 'max'],
      unit: '%',
      color: '#22c55e',
    });

    expect(markPoint.data).toEqual([
      { name: 'High', coord: [200, 87.5555], value: 87.5555, markerUnit: '%' },
      { name: 'Low', coord: [300, 41.25], value: 41.25, markerUnit: '%' },
    ]);
    expect(markPoint.itemStyle.color).toBe('#22c55e');
    // Balloon label is black for contrast against the bright pin fill.
    expect(markPoint.label.color).toBe('#000');
    expect(markPoint.label.formatter({
      name: 'High',
      value: 87.5555,
      data: markPoint.data[0],
    })).toBe('High\n87.556%');
    expect(describeExtremaMarkers([{ name: 'SoC', markPoint }]))
      .toBe('SoC: High 87.556%, Low 41.25%.');
  });

  it('separates High and Low pins for a flat series without changing either record', () => {
    const markPoint = buildExtremaMarkPoint([
      { time: 100, value: 62, rawValue: 62 },
      { time: 200, value: 62, rawValue: 62 },
    ], {
      markers: ['min', 'max'],
      unit: '%',
    });

    expect(markPoint.data).toEqual([
      {
        name: 'High',
        coord: [100, 62],
        value: 62,
        markerUnit: '%',
        symbolOffset: [0, -28],
      },
      {
        name: 'Low',
        coord: [100, 62],
        value: 62,
        markerUnit: '%',
        symbolOffset: [0, 28],
      },
    ]);
    expect(describeExtremaMarkers([{ name: 'SoC', markPoint }]))
      .toBe('SoC: High 62%, Low 62%.');
  });

  it('separates both extrema pins for a single-point series', () => {
    const markPoint = buildExtremaMarkPoint([
      { time: 100, value: 71.25, rawValue: 71.25 },
    ], {
      markers: ['min', 'max'],
      unit: '°',
    });

    expect(markPoint.data).toHaveLength(2);
    expect(markPoint.data.map(({ name, coord, value, markerUnit, symbolOffset }) => ({
      name,
      coord,
      value,
      markerUnit,
      symbolOffset,
    }))).toEqual([
      {
        name: 'High',
        coord: [100, 71.25],
        value: 71.25,
        markerUnit: '°',
        symbolOffset: [0, -28],
      },
      {
        name: 'Low',
        coord: [100, 71.25],
        value: 71.25,
        markerUnit: '°',
        symbolOffset: [0, 28],
      },
    ]);
  });

  it('supports either marker independently', () => {
    const points = [
      { time: 100, value: 10, rawValue: 10 },
      { time: 200, value: 20, rawValue: 20 },
    ];

    expect(buildExtremaMarkPoint(points, { markers: ['min'] }).data)
      .toEqual([{ name: 'Low', coord: [100, 10], value: 10, markerUnit: '' }]);
    expect(buildExtremaMarkPoint(points, { markers: ['max'] }).data)
      .toEqual([{ name: 'High', coord: [200, 20], value: 20, markerUnit: '' }]);
  });
});
