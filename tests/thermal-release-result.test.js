import { describe, expect, it } from 'vitest';
import base from './fixtures/thermal-shadow-v1-available.json';
import { parseThermalModelResult } from '../src/lib/thermal/modelResult.js';

const NOW = Date.parse(base.generatedAt);
const EPOCH = '864142d5-99ee-4b7a-b5fc-e6a96e7274d8';
function payload(mode = 'forecast_active') {
  const value = structuredClone(base);
  value.version = 2;
  value.status = mode;
  value.confidence.grade = mode === 'shadow' ? 'low' : 'high';
  value.schedule.candidate = null;
  value.schedule.effect = { morningMassDeltaF: 0, hallwayPeakDeltaF: 0 };
  value.forecast.trajectory.forEach((row) => { row.actions = []; });
  value.release = {
    schema: 'earthship-thermal-release/v1',
    qualifiedAt: value.generatedAt,
    expiresAt: new Date(NOW + 24 * 60 * 60_000).toISOString(),
    artifactSha256: 'a'.repeat(64), runtimeSha256: 'b'.repeat(64),
    policySha256: 'c'.repeat(64), reportSha256: 'd'.repeat(64),
    sensorEpochs: { air: EPOCH, mass: EPOCH, outdoor: EPOCH },
    forecastQualified: mode !== 'shadow', advisoryQualified: false, automaticActuation: false,
  };
  return value;
}

const parse = (value, now = NOW) => parseThermalModelResult(JSON.stringify(value), now);

describe('version 2 thermal publication', () => {
  it('shows explicit forecast mode and separate withheld action confidence', () => {
    const result = parse(payload());
    expect(result.state).toBe('ready');
    expect(result.mode).toBe('forecast_active');
    expect(result.badge).toBe('FORECAST');
    expect(result.confidence).toBe('high');
    expect(result.actionConfidence).toBe('withheld');
    expect(result.artifactRevision).toBe('a'.repeat(64));
    expect(result.ventWindow).toBeNull();
    expect(result.trajectory).toHaveLength(base.forecast.trajectory.length);
  });

  it('keeps unqualified version 2 forecast explicitly shadow', () => {
    const result = parse(payload('shadow'));
    expect(result.state).toBe('ready');
    expect(result.mode).toBe('shadow');
    expect(result.badge).toBe('SHADOW');
    expect(result.confidence).toBe('low');
  });

  it.each(['missingProof', 'manualFlag', 'expired', 'future', 'unknownEpoch', 'actionAdvice', 'actuation', 'badHash'])('refuses %s rather than displaying an active badge', (damage) => {
    const value = payload();
    if (damage === 'missingProof') value.release.forecastQualified = false;
    if (damage === 'manualFlag') value.active = true;
    if (damage === 'expired') value.release.expiresAt = new Date(NOW).toISOString();
    if (damage === 'future') value.release.qualifiedAt = new Date(NOW + 1).toISOString();
    if (damage === 'unknownEpoch') value.release.sensorEpochs.air = 'unknown';
    if (damage === 'actionAdvice') value.forecast.trajectory[0].actions = ['vent_open'];
    if (damage === 'actuation') value.release.automaticActuation = true;
    if (damage === 'badHash') value.release.artifactSha256 = 'short';
    expect(parse(value).state).toBe('unavailable');
    expect(parse(value).badge).not.toBe('FORECAST');
  });

  it('expires otherwise valid forecast qualification at its exact deadline', () => {
    const value = payload();
    expect(parse(value, Date.parse(value.release.expiresAt)).state).toBe('unavailable');
  });

  it('preserves exact version 1 shadow compatibility', () => {
    expect(parse(base).badge).toBe('SHADOW');
    expect(parse(base).state).toBe('ready');
  });
});

describe('native sensor-phase publication v3', () => {
  function nativePayload(mode = 'forecast_active') {
    const value = payload(mode);
    value.version = 3;
    value.release.schema = 'earthship-thermal-release/v2';
    value.release.sensorEpochSemantics = 'declared_hardware_phase';
    return value;
  }
  it('shows qualified forecasting and withheld advice for native v3', () => {
    const result = parse(nativePayload());
    expect(result.state).toBe('ready');
    expect(result.badge).toBe('FORECAST');
    expect(result.actionConfidence).toBe('withheld');
    expect(result.ventWindow).toBeNull();
  });
  it('preserves the shadow badge when native forecasting is unqualified', () => {
    expect(parse(nativePayload('shadow')).badge).toBe('SHADOW');
  });
  it('requires complete hardware phases for native shadow output', () => {
    const value = nativePayload('shadow');
    value.release.sensorEpochs = {};
    expect(parse(value).state).toBe('unavailable');
  });
  it('refuses a nil phase on native shadow output', () => {
    const value = nativePayload('shadow');
    value.release.sensorEpochs.air = '00000000-0000-0000-0000-000000000000';
    expect(parse(value).state).toBe('unavailable');
  });
  it.each(['legacySchema', 'missingSemantics', 'sessionSemantics', 'expired', 'missingProof', 'nilEpoch'])('refuses native %s', (damage) => {
    const value = nativePayload();
    if (damage === 'legacySchema') value.release.schema = 'earthship-thermal-release/v1';
    if (damage === 'missingSemantics') delete value.release.sensorEpochSemantics;
    if (damage === 'sessionSemantics') value.release.sensorEpochSemantics = 'collector_session';
    if (damage === 'expired') value.release.expiresAt = value.generatedAt;
    if (damage === 'missingProof') value.release.forecastQualified = false;
    if (damage === 'nilEpoch') value.release.sensorEpochs.air = '00000000-0000-0000-0000-000000000000';
    expect(parse(value).state).toBe('unavailable');
  });
});
