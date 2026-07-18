import { describe, expect, it } from 'vitest';
import {
  buildHistoryOption,
  formatHistoryTooltip,
} from '../src/lib/charts/options.js';

describe('history chart option adapter', () => {
  it('renders unsmoothed source values without ECharts interpolation or visible gap markers', () => {
    const option = buildHistoryOption({
      series: [{
        name: 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature',
        label: 'Outdoor',
        color: '#f59e0b',
      }],
      pointsPerSeries: [[
        { time: 0, state: 1 },
        { time: 1_000, state: 100 },
        { time: 2_000, state: 3 },
        { time: 3_000, state: 4 },
        { time: 4_000, state: 5 },
      ]],
      widthPx: 300,
      grid: { left: 10 },
    });

    expect(option.series[0].smooth).toBe(false);
    expect(option.series[0].data[1][1]).toBe(100);
    expect(option.series[0].data[1][2]).toBe(100);
    expect(option.series[0].data.some((point) => point[1] === null)).toBe(false);
    expect(formatHistoryTooltip([{
      seriesName: 'Outdoor',
      data: option.series[0].data[1],
      marker: '',
    }])).toContain('100');
  });

  it('does not soften SoC, gust, rain, or other step-like numeric lines', () => {
    const points = [
      { time: 0, state: 0 },
      { time: 1_000, state: 100 },
      { time: 2_000, state: 0 },
    ];
    const option = buildHistoryOption({
      series: [
        { name: 'BMS_SOC', label: 'SoC' },
        { name: 'AmbientWeatherWS2902A_WindGust', label: 'Gust' },
        { name: 'AmbientWeatherWS2902A_RainFallDay', label: 'Rain' },
      ],
      pointsPerSeries: [points, points, points],
      widthPx: 300,
    });

    for (const rendered of option.series) {
      expect(rendered.smooth).toBe(false);
      expect(rendered.data.map((point) => point[1])).toEqual([0, 100, 0]);
      expect(rendered.data.map((point) => point[2])).toEqual([0, 100, 0]);
    }
  });

  it('renders scalar trough history plus a dashed projection through tonight', () => {
    const nowMs = Date.UTC(2026, 6, 18, 12);
    const option = buildHistoryOption({
      series: [{
        name: 'Predicted_SoC_Trough_Tomorrow',
        label: 'Predicted trough',
        color: '#8b5cf6',
        dashedFromNow: true,
        projectionValue: 51,
        projectionHours: 18,
      }],
      pointsPerSeries: [[{ time: nowMs - 60_000, state: '52' }]],
      widthPx: 300,
      nowMs,
    });

    const [history, projection] = option.series;
    expect(history.name).toBe('Predicted trough');
    expect(history.data).toEqual([[nowMs - 60_000, 52, 52]]);
    expect(projection.name).toBe('Predicted trough (forecast)');
    expect(projection.lineStyle.type).toBe('dashed');
    expect(projection.data).toEqual([
      [nowMs, 51, 51],
      [nowMs + 18 * 60 * 60 * 1_000, 51, 51],
    ]);
  });

  it('shares a four-CSS-pixels-per-chart point cap across all series', () => {
    const points = rows(1_000);
    const option = buildHistoryOption({
      series: [
        { name: 'BMS_SOC', label: 'SoC' },
        { name: 'AmbientWeatherWS2902A_WindGust', label: 'Gust' },
        { name: 'AmbientWeatherWS2902A_RainFallDay', label: 'Rain' },
      ],
      pointsPerSeries: [points, points, points],
      widthPx: 200,
    });

    const total = option.series.reduce(
      (sum, rendered) => sum + rendered.data.filter((point) => point[1] !== null).length,
      0,
    );
    expect(total).toBeLessThanOrEqual(800);
  });
});

function rows(count) {
  return Array.from({ length: count }, (_, index) => ({
    time: index * 1_000,
    state: index,
  }));
}
