import { describe, it, expect } from 'vitest';
import thermal from './fixtures/thermal-shadow-v1-available.json';
import { temperatureForecast, OUTDOOR, INDOOR } from '../src/lib/charts/temperatureForecast.js';
import { buildHistoryOption } from '../src/lib/charts/options.js';

describe('temperature modal forecasts', () => {
  const now = Date.parse('2026-09-20T12:00:00-06:00');
  const forecast = JSON.stringify({ version: 1, generatedAt: new Date(now).toISOString(), timezone: 'America/Denver', days: [{
    date: '2026-09-20', label: 'Today',
    summary: { highF: 80, lowF: 40, precipPct: 0, weatherCode: 0, pvKwh: 5 },
    hours: [12,13,14].map((hour) => ({ at: `2026-09-20T${hour}:00:00-06:00`, tempF: 65.5 + hour,
      precipPct: 0, radiationWm2: 500, windMph: 2, weatherCode: 0 })),
  }] });
  it('plots corrected JSON temperatures as an hourly dashed series without persistence', () => {
    const result = temperatureForecast([{ name: OUTDOOR }], { Forecast_10Day_JSON: forecast }, now);
    expect(result.points.map(p => p.state)).toEqual([77.5,78.5,79.5]);
    const option = buildHistoryOption({ series: [result.source], pointsPerSeries: [result.points], nowMs: now, widthPx: 800 });
    expect(option.series.at(-1).lineStyle.type).toBe('dashed');
    expect(option.series.at(-1).data).toHaveLength(3);
  });
  it('uses validated learned indoor values and identifies the shadow model', () => {
    const result = temperatureForecast([{ name: INDOOR }], { Thermal_Model_JSON: JSON.stringify(thermal) }, Date.parse(thermal.generatedAt));
    expect(result.points.length).toBeGreaterThan(0);
    expect(result.description).toContain('shadow model');
    expect(result.points[0].state).toBe(thermal.forecast.trajectory[0].hallwayF);
  });
  it('does not invent forecasts for stale, malformed or unrelated sources', () => {
    expect(temperatureForecast([{ name: OUTDOOR }], { Forecast_10Day_JSON: forecast }, now + 5 * 3600000).points).toEqual([]);
    expect(temperatureForecast([{ name: INDOOR }], { Thermal_Model_JSON: '{}' }, now).points).toEqual([]);
    expect(temperatureForecast([{ name: 'BTC_USD_Price' }], {}, now)).toBe(null);
  });
});
