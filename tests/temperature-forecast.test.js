import { describe, it, expect } from 'vitest';
import { installedPublication } from './fixtures/installed-publication.js';
import thermal from './fixtures/thermal-shadow-v1-available.json';
import { temperatureForecast, OUTDOOR, INDOOR } from '../src/lib/charts/temperatureForecast.js';
import { buildHistoryOption } from '../src/lib/charts/options.js';
import { parseThermalModelResult } from '../src/lib/thermal/modelResult.js';

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
  it('identifies native provisional forecasts without changing their plotted values', () => {
    // Synthetic native v9 contract; no claim of physical qualification.
    const installed = installedPublication();
    const value = {
      schema: 'earthship-provisional-thermal-publication/v2', version: 9, status: 'provisional',
      generatedAt: installed.generatedAt,
      validUntil: new Date(Date.parse(installed.generatedAt) + 15 * 60000).toISOString(),
      model: { artifactSha256: 'a'.repeat(64), runtimeSha256: 'b'.repeat(64),
        createdAt: installed.model.createdAt, trainedThrough: installed.model.trainedThrough,
        fitExecuted: true, independentOriginDates: 2, horizonSupport: { 1: 2, 6: 2, 12: 1, 24: 1 }, regularizationStrength: 1 },
      forecast: { ...installed.forecast, schema: 'earthship-provisional-thermal-forecast/v2',
        status: 'provisional', confidence: 'low', prediction_intervals: null, graduated: false,
        model_rule: 'earthship-native-irradiance-shade-dynamics/v4', geometry_series_sha256: 'c'.repeat(64) },
      confidence: { grade: 'low', actionLabels: 'withheld' },
      graduation: { forecastQualified: false, stabilityAssessed: false, calibrationAssessed: false },
      automaticActuation: false, reasons: ['Synthetic provisional forecast; action advice withheld'],
    };
    delete value.forecast.release_authorized;
    const raw = JSON.stringify(value);
    const issued = Date.parse(value.generatedAt);
    expect(parseThermalModelResult(raw, issued)).toMatchObject({ state: 'ready', mode: 'provisional' });
    const result = temperatureForecast([{ name: INDOOR }], { Thermal_Model_JSON: raw }, issued);
    expect(result.source).toMatchObject({ name: 'Indoor_Thermal_Forecast', label: 'Indoor forecast · provisional model',
      forecastLabel: 'Indoor forecast · provisional model', dashedFromNow: true, markers: [] });
    expect(result.description).toBe('Indoor forecast · provisional model · next 24h');
    expect(result.points).toEqual(value.forecast.trajectory.map(row => ({ time: Date.parse(row.at), state: row.air_f })));
  });
  it('labels qualified installed-shade forecasts as production', () => {
    const value = installedPublication();
    const result = temperatureForecast([{ name: INDOOR }], { Thermal_Model_JSON: JSON.stringify(value) }, Date.parse(value.generatedAt));
    expect(result.source.label).toBe('Indoor forecast · production');
    expect(result.points).toHaveLength(24);
  });
  it('does not invent forecasts for stale, malformed or unrelated sources', () => {
    expect(temperatureForecast([{ name: OUTDOOR }], { Forecast_10Day_JSON: forecast }, now + 5 * 3600000).points).toEqual([]);
    expect(temperatureForecast([{ name: INDOOR }], { Thermal_Model_JSON: '{}' }, now).points).toEqual([]);
    expect(temperatureForecast([{ name: 'BTC_USD_Price' }], {}, now)).toBe(null);
  });
});
