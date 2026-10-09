import { describe, expect, it } from 'vitest';
import { parseThermalModelResult } from '../src/lib/thermal/modelResult.js';
import { installedPublication } from './fixtures/installed-publication.js';
const NOW = Date.parse(installedPublication().generatedAt);
const parse = (value, now = NOW) => parseThermalModelResult(JSON.stringify(value), now);

describe('installed-shade production publication', () => {
  it('shows production state and only the four original calibrated intervals', () => {
    const result = parse(installedPublication());
    expect(result.state).toBe('ready'); expect(result.mode).toBe('forecast_active');
    expect(result.badge).toBe('FORECAST'); expect(result.confidence).toBe('high');
    expect(result.artifactRevision).toBe('a'.repeat(64)); expect(result.actionConfidence).toBe('withheld');
    expect(result.trajectory).toHaveLength(24);
    expect(result.trajectory.filter((p) => p.lowF !== null)).toHaveLength(4);
    expect(result.trajectory[0].lowF).toBe(73); expect(result.trajectory[1].lowF).toBeNull();
    expect(result.uncertaintyMode).toBe('calibrated_targets'); expect(result.ventWindow).toBeNull();
  });
  it('keeps an unqualified numeric forecast visibly shadow', () => {
    expect(parse(installedPublication('shadow')).badge).toBe('SHADOW');
    expect(parse(installedPublication('shadow')).confidence).toBe('low');
  });
  it.each(['expired', 'future', 'manual', 'missingProof', 'advice', 'actuation', 'epoch', 'band', 'revision', 'numericRelease', 'booleanShade', 'removedShade', 'regime', 'mode', 'futureMicros'])('refuses %s without an active badge', (damage) => {
    const value = installedPublication();
    if (damage === 'expired') value.validUntil = value.generatedAt;
    if (damage === 'future') value.release.qualifiedAt = new Date(NOW + 1).toISOString();
    if (damage === 'manual') value.active = true;
    if (damage === 'missingProof') value.release.originCaptureSha256 = null;
    if (damage === 'advice') value.forecast.advice = ['open shade'];
    if (damage === 'actuation') value.release.automaticActuation = true;
    if (damage === 'epoch') value.release.sensorEpochs.air = '00000000-0000-0000-0000-000000000000';
    if (damage === 'band') value.forecast.prediction_intervals[1].at = value.forecast.prediction_intervals[0].at;
    if (damage === 'revision') value.forecast.artifact_sha256 = '1'.repeat(64);
    if (damage === 'booleanShade') value.forecast.origin_actions.outdoor_shade_present = true;
    if (damage === 'removedShade') value.forecast.origin_actions.outdoor_shade_present = 0;
    if (damage === 'regime') value.forecast.prediction_intervals[0].regime = 'winter';
    if (damage === 'mode') value.forecast.origin_actions.mode = 'invented';
    if (damage === 'futureMicros') value.release.qualifiedAt = '2026-12-19T07:05:00.000001Z';
    if (damage === 'numericRelease') value.forecast.release_authorized = true;
    const result = parse(value); expect(result.state).toBe('unavailable'); expect(result.badge).not.toBe('FORECAST');
  });
  it('withdraws the published mode at the exact freshness deadline', () => {
    const value = installedPublication(); expect(parse(value, Date.parse(value.validUntil)).state).toBe('unavailable');
  });
  it('accepts exact uncalibrated source format only as shadow with no invented bands', () => {
    const value = installedPublication('shadow');value.forecast.schema = 'earthship-installed-shade-forecast/v1';
    value.forecast.prediction_intervals = null;value.release.calibrationSha256 = null;
    const result = parse(value);expect(result.state).toBe('ready');
    expect(result.trajectory.every((p) => p.lowF === null && p.highF === null)).toBe(true);
    value.status = 'forecast_active';value.confidence.grade = 'high';value.release.forecastQualified = true;
    expect(parse(value).state).toBe('unavailable');
  });
});

it('reports the current origin vent assumption without inventing a vent schedule', () => {
  const value = installedPublication();value.forecast.origin_actions.vent_open = 1;
  value.forecast.origin_actions.vent_provenance = 'manual_dm';
  const result = parse(value);expect(result.state).toBe('ready');
  expect(result.baselineVentAssumption).toBe('Venting assumed from origin state');
  expect(result.ventWindow).toBeNull();
});

it('refuses a structurally valid future origin as explicitly unavailable', () => {
  const value = installedPublication();const result = parse(value, NOW - 1);
  expect(result.state).toBe('unavailable');expect(result.mode).toBe('unavailable');expect(result.badge).toBe('UNAVAILABLE');
});
