import { describe, expect, it } from 'vitest';
import fixture from './fixtures/weathernext-shadow-v2.json';
import { parseProviderForecast } from '../src/lib/weather/providerForecast.js';
const nowMs = Date.parse('2026-01-01T00:31:00Z');
const raw = JSON.stringify(fixture);
const parse = (value = fixture, options = {}) => {
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  return parseProviderForecast(text, text, text, { nowMs, ...options });
};
describe('WeatherNext shadow publication contract', () => {
  it('reads the real Python-produced synthetic contract and converts Celsius', () => {
    const result = parse();
    expect(result.status).toBe('ready');
    expect(result.hours[0].rawF).toBeCloseTo(50);
    expect(result.hours[0].localF).toBeCloseTo(53.6);
    expect(result.model.sampleCount).toBe(1);
    expect(result.model.validation).toBeNull();
    expect(result.source.runId).toBe('ee:2026-01-01T00:00:00+00:00');
  });
  it('withholds a partial three-Item publication', () => {
    expect(parseProviderForecast(raw, 'NULL', raw, { nowMs }).status).toBe('unavailable');
    expect(parseProviderForecast(raw, JSON.stringify({ ...fixture, generation: 'b'.repeat(64) }), raw, { nowMs }).status).toBe('unavailable');
  });
  it('does not turn absent values or untrained models into zero forecasts', () => {
    const value = structuredClone(fixture);
    value.model = { status: 'UNTRAINED', sha256: null, fittedAt: null, trainingEnd: null, sampleCount: 0, targetDates: 0, validation: null };
    value.hours = value.hours.map((row) => ({ ...row, localC: null }));
    const result = parse(value);
    expect(result.status).toBe('ready');
    expect(result.hours[0].localF).toBeNull();
  });
  it('hides stale or disconnected forecast values', () => {
    const stale = parse(fixture, { nowMs: nowMs + 3 * 3600000 });
    expect(stale.status).toBe('stale');
    expect(stale.hours).toEqual([]);
    expect(parse(fixture, { connected: false }).hours).toEqual([]);
  });
  it('rejects unsupported versions, extra fields, authority and oversized input', () => {
    for (const value of [{ ...fixture, version: 1 }, { ...fixture, command: 'ON' }, { ...fixture, automaticActuation: true }, 'x'.repeat(65536)]) {
      expect(parse(value).status).toBe('unavailable');
    }
  });
  it('rejects missing offsets, future source availability and model clocks', () => {
    for (const change of ['offset', 'availability', 'model', 'future']) {
      const value = structuredClone(fixture);
      if (change === 'offset') value.decisionAt = '2026-01-01T00:30:00';
      if (change === 'availability') value.source.ingestedAt = '2026-01-01T00:32:00Z';
      if (change === 'model') value.model.fittedAt = '2026-01-01T01:00:00Z';
      if (change === 'future') value.generatedAt = '2026-01-02T00:00:00Z';
      expect(parse(value).status).toBe('unavailable');
    }
  });
  it('rejects nonfinite values, duplicate hours and unsupported model claims', () => {
    expect(parse(raw.replace('"rawC":10', '"rawC":1e309')).status).toBe('unavailable');
    const duplicate = structuredClone(fixture); duplicate.hours.push(duplicate.hours[0]);
    expect(parse(duplicate).status).toBe('unavailable');
    const unsupported = structuredClone(fixture); unsupported.model.validation = { confidence: 99 };
    expect(parse(unsupported).status).toBe('unavailable');
  });
});
