import { describe, expect, it } from 'vitest';
import { parseThermalModelResult } from '../src/lib/thermal/modelResult.js';
import { temperatureForecast, INDOOR } from '../src/lib/charts/temperatureForecast.js';
import { rawInstalledPublication, installedPublication } from './fixtures/installed-publication.js';
const NOW = Date.parse('2026-12-19T07:05:00Z');
const parse = (value, now = NOW) => parseThermalModelResult(JSON.stringify(value), now);

describe('raw calibrated production display', () => {
  it('displays production mode, original targets, calibrated uncertainty and withheld advice', () => {
    const result = parse(rawInstalledPublication());
    expect(result.state).toBe('ready'); expect(result.mode).toBe('forecast_active');
    expect(result.badge).toBe('FORECAST'); expect(result.confidence).toBe('high');
    expect(result.artifactRevision).toBe('a'.repeat(64)); expect(result.actionConfidence).toBe('withheld');
    expect(result.trajectory).toHaveLength(24);
    expect(result.trajectory.filter(p => p.lowF !== null)).toHaveLength(4);
    expect(result.trajectory[0]).toMatchObject({ hallwayF: 74, lowF: 73, highF: 75, actions: [] });
    expect(result.trajectory[1].lowF).toBeNull(); expect(result.ventWindow).toBeNull();
    expect(result.uncertaintyMode).toBe('calibrated_targets');
  });
  it('keeps raw unqualified forecasts shadow and accepts honest withdrawal', () => {
    expect(parse(rawInstalledPublication('shadow'))).toMatchObject({ state:'ready', mode:'shadow', badge:'SHADOW', confidence:'low' });
    expect(parse(rawInstalledPublication('unavailable'))).toMatchObject({ state:'unavailable', mode:'unavailable', badge:'UNAVAILABLE' });
  });
  it.each(['publicationSchema','releaseSchema','numericSchema','baseNumeric','manual','missingProof','policy','calibration','advice','advisory','actuation','epoch','revision','band','uncertainty','futureQualification'])('refuses %s without forecast display', damage => {
    const value = rawInstalledPublication();
    if (damage === 'publicationSchema') value.schema = 'earthship-installed-shade-publication/v1';
    if (damage === 'releaseSchema') value.release.schema = 'earthship-installed-shade-release/v1';
    if (damage === 'numericSchema') value.forecast.schema = 'earthship-installed-shade-forecast/v2';
    if (damage === 'baseNumeric') value.forecast.schema = 'earthship-installed-shade-forecast/v1';
    if (damage === 'manual') value.active = true;
    if (damage === 'missingProof') value.release.originCaptureSha256 = null;
    if (damage === 'policy') value.release.policySha256 = null;
    if (damage === 'calibration') value.release.calibrationSha256 = null;
    if (damage === 'advice') value.forecast.advice = ['open shade'];
    if (damage === 'advisory') value.release.advisoryQualified = true;
    if (damage === 'actuation') value.release.automaticActuation = true;
    if (damage === 'epoch') value.release.sensorEpochs.air = '00000000-0000-0000-0000-000000000000';
    if (damage === 'revision') value.forecast.runtime_sha256 = '1'.repeat(64);
    if (damage === 'band') value.forecast.prediction_intervals[0].upper_air_f = 70;
    if (damage === 'uncertainty') value.forecast.prediction_intervals = null;
    if (damage === 'futureQualification') value.release.qualifiedAt = '2026-12-19T07:05:00.000001Z';
    expect(parse(value)).toMatchObject({ state:'unavailable', mode:'unavailable', badge:'UNAVAILABLE' });
  });
  it('refuses raw numeric data in the historical publication profile', () => {
    const value = installedPublication(); value.forecast.schema = 'earthship-installed-shade-forecast/v3';
    expect(parse(value).state).toBe('unavailable');
  });
  it('preserves submillisecond expiry ordering at the browser clock and rejects a future issue', () => {
    const value = rawInstalledPublication();value.validUntil = '2026-12-19T07:05:00.000001Z';
    expect(parse(value, NOW).state).toBe('ready');
    expect(parse(value, NOW + 1)).toMatchObject({ state:'unavailable', mode:'unavailable', badge:'UNAVAILABLE' });
    expect(parse(rawInstalledPublication(), NOW - 1)).toMatchObject({ state:'unavailable', mode:'unavailable', badge:'UNAVAILABLE' });
  });
  it('plots only fresh validated raw production targets', () => {
    const value = rawInstalledPublication();
    const result = temperatureForecast([{ name:INDOOR }], { Thermal_Model_JSON:JSON.stringify(value) }, NOW);
    expect(result.source.label).toBe('Indoor forecast · production'); expect(result.points).toHaveLength(24);
    expect(result.points[0].state).toBe(74);
    expect(temperatureForecast([{ name:INDOOR }], { Thermal_Model_JSON:JSON.stringify(value) }, Date.parse(value.validUntil)).points).toEqual([]);
  });
});
