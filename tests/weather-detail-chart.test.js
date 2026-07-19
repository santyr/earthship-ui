import { describe, expect, it } from 'vitest';
import { buildWeatherDetailOption } from '../src/lib/weather/detailChart.js';

const hours = Array.from({ length: 10 }, (_, index) => ({
  at: `2026-07-19T${String(index + 8).padStart(2, '0')}:00:00-06:00`,
  tempF: 60 + index,
  precipPct: index * 5,
  radiationWm2: index * 80,
  windMph: 5 + index,
  weatherCode: 1,
}));

describe('weather detail chart', () => {
  it('renders ten aligned temperature, precipitation, radiation, and wind values', () => {
    const option = buildWeatherDetailOption({ hours, widthPx: 900 });

    expect(option.xAxis.data).toHaveLength(10);
    expect(option.xAxis.data[0]).toBe('8 AM');
    expect(option.series.map(({ name }) => name)).toEqual([
      'Radiation',
      'Precipitation',
      'Temperature',
      'Wind',
    ]);
    expect(option.series.every(({ data }) => data.length === 10)).toBe(true);
    expect(option.series.filter(({ type }) => type === 'line')
      .every(({ smooth }) => smooth === false)).toBe(true);
    expect(option.animation).toBe(false);
  });

  it('uses dedicated bounded axes, measured margins, and a complete tooltip', () => {
    const compact = buildWeatherDetailOption({ hours, widthPx: 520 });
    const wide = buildWeatherDetailOption({ hours, widthPx: 1100 });

    expect(compact.yAxis).toHaveLength(4);
    expect(compact.yAxis[1]).toMatchObject({ min: 0, max: 100 });
    expect(compact.yAxis[2].show).toBe(false);
    expect(compact.yAxis[3]).toMatchObject({ position: 'right', offset: 42 });
    expect(compact.grid.left).toBeLessThan(wide.grid.left);
    expect(compact.grid.right).toBeLessThan(wide.grid.right);

    const tooltip = compact.tooltip.formatter([
      { axisValue: '8 AM', seriesName: 'Radiation', value: 0 },
      { axisValue: '8 AM', seriesName: 'Precipitation', value: 0 },
      { axisValue: '8 AM', seriesName: 'Temperature', value: 60 },
      { axisValue: '8 AM', seriesName: 'Wind', value: 5 },
    ]);
    expect(tooltip).toContain('60°F');
    expect(tooltip).toContain('0%');
    expect(tooltip).toContain('0 W/m²');
    expect(tooltip).toContain('5 mph');
  });
});
