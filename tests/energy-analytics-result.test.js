import { describe, expect, it } from 'vitest';

import {
  ENERGY_ANALYTICS_MAX_BYTES,
  ENERGY_ANALYTICS_REFRESH_MS,
  parseEnergyAnalyticsResult,
} from '../src/lib/energy/analyticsResult.js';
import {
  GENERATED_AT_MS,
  energyAnalyticsFixture,
  energyAnalyticsV2Fixture,
  energyAnalyticsV3Fixture,
} from './fixtures/energyAnalytics.js';


function parse(payload = energyAnalyticsFixture(), nowMs = GENERATED_AT_MS + 60_000) {
  return parseEnergyAnalyticsResult(JSON.stringify(payload), nowMs);
}


describe('Energy analytics closed payload parser', () => {
  it('accepts qualified v3 provenance without legacy or lifetime totals', () => {
    const result = parse(energyAnalyticsV3Fixture());
    expect(result.state).toBe('degraded');
    expect(result.accounting.missingDays).toBe(1);
    expect(result.accounting.latestRevision.id).toBe(12);
    expect(result.energy.latest.loadKwh).toBeNull();
    expect(result.lifecycle.endingCumulativeEfc).toBeNull();
    expect(Object.isFrozen(result.accounting.latestRevision)).toBe(true);
    expect(parse().accounting).toBeNull();
  });

  it.each([
    ['missing provenance', p => { delete p.accounting; }],
    ['extra provenance', p => { p.accounting.extra = 1; }],
    ['wrong policy', p => { p.accounting.policy = 'legacy'; }],
    ['bad coverage', p => { p.accounting.latestPvCoverage = 1.1; }],
    ['boolean coverage', p => { p.accounting.latestPvCoverage = false; }],
    ['day count mismatch', p => { p.accounting.daysPresent = 2; }],
    ['unfinished window', p => { p.accounting.windowEndExclusive = '2026-08-21'; }],
    ['future cutover', p => { p.accounting.cutover = '2030-01-01T00:00:00Z'; }],
    ['future revision', p => { p.accounting.latestRevision.computedAt = '2030-01-01T00:00:00Z'; }],
    ['revision before completed day', p => { p.accounting.latestRevision.computedAt = '2026-08-19T20:00:00Z'; }],
    ['partial battery claimed complete', p => { p.battery.status = 'ok'; }],
    ['bad digest', p => { p.accounting.latestRevision.sha256 = 'x'; }],
    ['unsafe revision ID', p => { p.accounting.latestRevision.id = 2 ** 54; }],
    ['legacy EFC', p => { p.lifecycle.endingCumulativeEfc = 40; }],
    ['unqualified load', p => { p.energy.latest.loadKwh = 5; }],
    ['negative throughput', p => { p.lifecycle.periodEfc = -1; }],
    ['missing days claimed complete', p => { p.status = 'ok'; }],
    ['empty series with totals', p => { p.accounting.daysPresent = 0; p.accounting.missingDays = 2; }],
  ])('rejects qualified v3 %s', (_label, mutate) => {
    const payload = energyAnalyticsV3Fixture();
    mutate(payload);
    expect(parse(payload).state).toBe('unavailable');
  });

  it('accepts an explicitly empty qualified series without fabricated zero totals', () => {
    const payload = energyAnalyticsV3Fixture();
    Object.assign(payload.accounting, { daysPresent: 0, missingDays: 2,
      latestRevision: null, latestBatteryCoverage: null, latestPvCoverage: null });
    payload.throughDate = null;
    payload.energy.latest = null;
    payload.battery.latestEfc = null;
    Object.assign(payload.lifecycle, { periodEfc: null, chargeKwh: null, dischargeKwh: null });
    expect(parse(payload).accounting.daysPresent).toBe(0);
  });
  it('refreshes freshness well before the stale boundary', () => {
    expect(ENERGY_ANALYTICS_REFRESH_MS).toBeGreaterThan(0);
    expect(ENERGY_ANALYTICS_REFRESH_MS).toBeLessThan(15 * 60_000);
  });

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
    expect(result.battery.latestDepthOfDischargePct).toBeNull();
    expect(result.battery.latestEfc).toBeNull();
  });

  it('accepts v2 battery cycle evidence', () => {
    const result = parse(energyAnalyticsV2Fixture());
    expect(result.battery.latestDepthOfDischargePct).toBe(16);
    expect(result.battery.latestEfc).toBe(0.16);
  });

  it.each([
    ['missing DoD', (value) => { delete value.battery.latestDepthOfDischargePct; }],
    ['extra battery field', (value) => { value.battery.extra = null; }],
  ])('rejects v2 with %s', (_label, mutate) => {
    const payload = energyAnalyticsV2Fixture();
    mutate(payload);
    expect(parse(payload).state).toBe('unavailable');
  });

  it.each([
    ['DoD string', (value) => { value.battery.latestDepthOfDischargePct = '16'; }],
    ['DoD boolean', (value) => { value.battery.latestDepthOfDischargePct = true; }],
    ['DoD negative', (value) => { value.battery.latestDepthOfDischargePct = -1; }],
    ['DoD above 100', (value) => { value.battery.latestDepthOfDischargePct = 101; }],
    ['EFC string', (value) => { value.battery.latestEfc = '0.16'; }],
    ['EFC boolean', (value) => { value.battery.latestEfc = false; }],
    ['EFC negative', (value) => { value.battery.latestEfc = -0.01; }],
  ])('rejects v2 %s', (_label, mutate) => {
    const payload = energyAnalyticsV2Fixture();
    mutate(payload);
    expect(parse(payload).state).toBe('unavailable');
  });

  it.each([null, 0])('accepts nullable or zero v2 battery evidence: %s', (value) => {
    const payload = energyAnalyticsV2Fixture();
    payload.battery.latestDepthOfDischargePct = value;
    payload.battery.latestEfc = value;
    const result = parse(payload);
    expect(result.battery.latestDepthOfDischargePct).toBe(value);
    expect(result.battery.latestEfc).toBe(value);
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
    expect(parse({ ...energyAnalyticsFixture(), schema: 'earthship-energy-ui/v3' }).state)
      .toBe('unavailable');
    expect(parse(energyAnalyticsFixture(), GENERATED_AT_MS - 1).state)
      .toBe('unavailable');
  });

  it.each([
    ['unknown top-level key', (value) => { value.extra = true; }],
    ['boolean number', (value) => { value.battery.latestMinSocPct = true; }],
    ['non-finite number', (value) => { value.energy.latest.pvKwh = Number.POSITIVE_INFINITY; }],
    ['unknown health status', (value) => { value.health.bms = 'healthy'; }],
    ['naive timestamp', (value) => { value.generatedAt = '2026-08-20T18:00:00'; }],
    ['impossible calendar date', (value) => { value.throughDate = '2026-02-30'; value.energy.latest.date = '2026-02-30'; }],
    ['calendar date suffix', (value) => { value.throughDate = '2026-08-19-extra'; value.energy.latest.date = '2026-08-19-extra'; }],
    ['through date after generated local date', (value) => { value.throughDate = '2026-08-21'; value.energy.latest.date = '2026-08-21'; }],
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

  it.each([
    ['v1 stale', energyAnalyticsFixture],
    ['v2 stale', energyAnalyticsV2Fixture],
    ['v3 stale', energyAnalyticsV3Fixture],
  ])('applies freshness gate to %s', (_label, fixture) => {
    expect(parse(fixture(), GENERATED_AT_MS + 15 * 60_000 + 1).state).toBe('stale');
  });

  it.each([
    ['v1', energyAnalyticsFixture],
    ['v2', energyAnalyticsV2Fixture],
    ['v3', energyAnalyticsV3Fixture],
  ])('applies size gate to %s', (_label, fixture) => {
    const raw = `${' '.repeat(ENERGY_ANALYTICS_MAX_BYTES)}${JSON.stringify(fixture())}`;
    expect(parseEnergyAnalyticsResult(raw, GENERATED_AT_MS).state).toBe('unavailable');
  });

  it('does not mutate or retain caller-owned objects', () => {
    const payload = energyAnalyticsFixture();
    const result = parse(payload);
    payload.battery.latestMinSocPct = 1;
    expect(result.battery.latestMinSocPct).toBe(67);
    expect(Object.isFrozen(result.battery)).toBe(true);
  });
});
