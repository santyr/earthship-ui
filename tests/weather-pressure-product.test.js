import { describe, expect, it } from 'vitest';
import { stationPresentation } from '../src/lib/weather/stationPresentation.js';
import { pressureProduct } from '../src/lib/weather/pressureProduct.js';
import { buildHistoryOption } from '../src/lib/charts/options.js';

const now = Date.parse('2026-10-24T12:00:00Z');
const legacyItem = 'AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative';
function report() {
  return { schema: 'earthship-station-ingestion/v2', generatedAt: new Date(now).toISOString(),
    flat: { WeatherStation_PressureAbsoluteV2: 23.89 },
    fields: { WeatherStation_PressureAbsoluteV2: { value: 23.89, role: 'indoor', status: 'fresh',
      receivedAt: new Date(now).toISOString(), validUntil: new Date(now + 120000).toISOString() } } };
}
const selected = states => pressureProduct(stationPresentation(states, { nowMs: now }), states);

describe('selected station pressure product', () => {
  it('retains the declared legacy relative quantity without numerical correction', () => {
    expect(selected({ [legacyItem]: '30.12 inHg' })).toEqual({
      item: legacyItem, value: '30.12 inHg', label: 'Relative pressure', chartTitle: 'Relative pressure (legacy)',
    });
  });
  it('uses qualified absolute pressure with the corresponding chart identity', () => {
    expect(selected({ [legacyItem]: '30.12', WeatherStation_Quality_JSON: JSON.stringify(report()) })).toEqual({
      item: 'WeatherStation_PressureAbsoluteV2', value: 23.89, label: 'Station pressure', chartTitle: 'Station pressure (absolute)',
    });
  });
  it.each([
    ['legacy', 'Relative pressure (legacy)', 30.12],
    ['v2', 'Station pressure (absolute)', 23.89],
  ])('keeps the %s chart tooltip on its original quantity and value', (mode, label, value) => {
    const states = { [legacyItem]: '30.12' };
    if (mode === 'v2') states.WeatherStation_Quality_JSON = JSON.stringify(report());
    const product = selected(states);
    const option = buildHistoryOption({ series: [{ name: product.item, label: product.chartTitle }],
      pointsPerSeries: [[{ time: now - 60000, state: product.value }]], nowMs: now, widthPx: 800 });
    const series = option.series[0];
    expect(series.name).toBe(label);
    expect(series.data[0][2]).toBe(value);
    expect(option.tooltip.formatter([{ seriesName: series.name, data: series.data[0] }])).toContain(`${label}: ${value}`);
  });
  it.each(['malformed', 'null', 'undefined', 'stale-report', 'stale-field'])('keeps %s v2 unavailable with its absolute identity', damage => {
    const value = report();
    if (damage === 'stale-report') value.generatedAt = new Date(now - 91000).toISOString();
    if (damage === 'stale-field') value.fields.WeatherStation_PressureAbsoluteV2.validUntil = new Date(now - 1).toISOString();
    const raw = damage === 'malformed' ? '{broken' : damage === 'null' ? 'NULL' : damage === 'undefined' ? 'UNDEF' : JSON.stringify(value);
    expect(selected({ [legacyItem]: '30.12', WeatherStation_Quality_JSON: raw })).toEqual({
      item: 'WeatherStation_PressureAbsoluteV2', value: null, label: 'Station pressure', chartTitle: 'Station pressure (absolute)',
    });
  });
});
