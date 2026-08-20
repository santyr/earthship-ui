import { describe, expect, it } from 'vitest';

import {
  ENERGY_ANALYTICS_MAX_BYTES,
  parseEnergyAnalyticsResult,
} from '../src/lib/energy/analyticsResult.js';
import {
  GENERATED_AT_MS,
  energyAnalyticsFixture,
} from './fixtures/energyAnalytics.js';


function parse(payload = energyAnalyticsFixture(), nowMs = GENERATED_AT_MS + 60_000) {
  return parseEnergyAnalyticsResult(JSON.stringify(payload), nowMs);
}


describe('Energy analytics closed payload parser', () => {
  it('accepts the exact contract and exposes bounded display evidence', () => {
    const result = parse();

    expect(result.state).toBe('degraded');
    expect(result.generatedAtMs).toBe(GENERATED_AT_MS);
    expect(result.throughDate).toBe('2026-08-19');
    expect(result.epochId).toBe('discover_4_module_2026');
    expect(result.battery.latestMinSocPct).toBe(67);
    expect(result.energy.latest.pvKwh).toBe(8);
    expect(result.lifecycle.endingCumulativeEfc).toBe(4.36);
    expect(result.forecast.pv24hKwh).toBe(7.2);
    expect(result.reasons).toEqual([]);
  });

  it('marks an otherwise valid payload stale after fifteen minutes', () => {
    const result = parse(energyAnalyticsFixture(), GENERATED_AT_MS + 15 * 60_000 + 1);
    expect(result.state).toBe('stale');
    expect(result.reasons).toContain('analytics_payload_stale');
  });

  it('fails closed for null sentinels, bad JSON, unsupported versions, and future data', () => {
    for (const raw of ['NULL', 'UNDEF', '', '{bad']) {
      expect(parseEnergyAnalyticsResult(raw, GENERATED_AT_MS).state).toBe('unavailable');
    }
    expect(parse({ ...energyAnalyticsFixture(), schema: 'earthship-energy-ui/v2' }).state)
      .toBe('unavailable');
    expect(parse(energyAnalyticsFixture(), GENERATED_AT_MS - 2 * 60_000 - 1).state)
      .toBe('unavailable');
  });

  it.each([
    ['unknown top-level key', (value) => { value.extra = true; }],
    ['boolean number', (value) => { value.battery.latestMinSocPct = true; }],
    ['non-finite number', (value) => { value.energy.latest.pvKwh = Number.POSITIVE_INFINITY; }],
    ['unknown health status', (value) => { value.health.bms = 'healthy'; }],
    ['naive timestamp', (value) => { value.generatedAt = '2026-08-20T18:00:00'; }],
    ['HTML reason', (value) => { value.health.reasons = ['<img src=x onerror=1>']; }],
  ])('rejects %s', (_label, mutate) => {
    const payload = energyAnalyticsFixture();
    mutate(payload);
    expect(parse(payload).state).toBe('unavailable');
  });

  it('counts complete raw UTF-8 bytes before trimming', () => {
    const raw = `${' '.repeat(ENERGY_ANALYTICS_MAX_BYTES)}${JSON.stringify(energyAnalyticsFixture())}`;
    const result = parseEnergyAnalyticsResult(raw, GENERATED_AT_MS);
    expect(result.state).toBe('unavailable');
    expect(result.reasons).toContain('analytics_payload_too_large');
  });

  it('does not mutate or retain caller-owned objects', () => {
    const payload = energyAnalyticsFixture();
    const result = parse(payload);
    payload.battery.latestMinSocPct = 1;
    expect(result.battery.latestMinSocPct).toBe(67);
    expect(Object.isFrozen(result.battery)).toBe(true);
  });
});
