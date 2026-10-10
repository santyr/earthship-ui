import { compressedInstalledPublication } from './compressed-installed-publication.js';
import { rawInstalledPublication, installedPublication } from './installed-publication.js';
import { parseThermalModelResult } from '../../src/lib/thermal/modelResult.js';
import { temperatureForecast, INDOOR } from '../../src/lib/charts/temperatureForecast.js';
const NOW = Date.parse('2026-12-19T07:05:00Z');
const parse = (value, now = NOW) => parseThermalModelResult(JSON.stringify(value), now);
export const compressedInstalledCases = [
  ['displays calibrated production with exact issued uncertainty and withheld advice', assert => {
    const result = parse(compressedInstalledPublication());
    assert.equal(result.state,'ready'); assert.equal(result.badge,'FORECAST'); assert.equal(result.mode,'forecast_active');
    assert.equal(result.actionConfidence,'withheld'); assert.equal(result.artifactRevision,'a'.repeat(64));
    assert.equal(result.uncertaintyMode,'calibrated_targets'); assert.equal(result.trajectory.length,24);
    assert.equal(result.trajectory.filter(p => p.lowF !== null).length,4); assert.equal(result.ventWindow,null);
  }],
  ['preserves shadow and honest unavailable states', assert => {
    assert.equal(parse(compressedInstalledPublication('shadow')).badge,'SHADOW');
    const result = parse(compressedInstalledPublication('unavailable')); assert.equal(result.state,'unavailable'); assert.equal(result.badge,'UNAVAILABLE');
  }],
  ['base bootstrap remains uncalibrated shadow', assert => {
    const result = parse(compressedInstalledPublication('shadow',true));
    assert.equal(result.state,'ready'); assert.equal(result.badge,'SHADOW'); assert.equal(result.uncertaintyMode,'none');
    assert.ok(result.trajectory.every(p => p.lowF === null && p.highF === null));
  }],
  ['preserves older installed profiles', assert => {
    for (const value of [installedPublication(),rawInstalledPublication()]) assert.equal(parse(value).badge,'FORECAST');
  }],
  ['plots only fresh validated production data', assert => {
    const value = compressedInstalledPublication(); const items = {Thermal_Model_JSON:JSON.stringify(value)};
    const result = temperatureForecast([{name:INDOOR}],items,NOW);
    assert.equal(result.source.label,'Indoor forecast · production'); assert.equal(result.points.length,24);
    assert.equal(temperatureForecast([{name:INDOOR}],items,Date.parse(value.validUntil)).points.length,0);
  }],
  ['preserves submillisecond expiry and refuses future issue', assert => {
    const value = compressedInstalledPublication(); value.validUntil = '2026-12-19T07:05:00.000001Z';
    assert.equal(parse(value).state,'ready'); assert.equal(parse(value,NOW+1).badge,'UNAVAILABLE');
    assert.equal(parse(compressedInstalledPublication(),NOW-1).badge,'UNAVAILABLE');
  }],
];
const damage = {
  publicationSchema: v => { v.schema='earthship-installed-shade-publication/v3'; },
  releaseSchema: v => { v.release.schema='earthship-installed-shade-release/v3'; },
  numericSchema: v => { v.forecast.schema='earthship-installed-shade-forecast/v4'; },
  missingOrigin: v => { delete v.release.nativeOriginBindingSha256; },
  wrongOrigin: v => { v.forecast.native_origin_binding_sha256='2'.repeat(64); },
  missingQualification: v => { v.release.sourceQualificationSchema=null; },
  oldQualification: v => { v.release.sourceQualificationSchema='earthship-installed-shade-qualification-report/v6'; },
  markerOnly: v => { v.release.forecastQualified=false; },
  manual: v => { v.active=true; },
  advisory: v => { v.release.advisoryQualified=true; },
  actuation: v => { v.forecast.automatic_actuation=true; },
  missingCalibration: v => { v.release.calibrationSha256=null; },
  staleQualification: v => { v.release.expiresAt=v.generatedAt; },
  futureQualification: v => { v.release.qualifiedAt='2026-12-19T07:05:00.000001Z'; },
  wrongBand: v => { v.forecast.prediction_intervals[0].calibration_sha256='2'.repeat(64); },
  badEpoch: v => { v.release.sensorEpochs.air='00000000-0000-0000-0000-000000000000'; },
  baseCannotActivate: v => { v.forecast.schema='earthship-installed-shade-forecast/v6'; },
  fabricatedWithdrawal: v => { Object.assign(v,compressedInstalledPublication('unavailable'));v.release.nativeOriginBindingSha256='1'.repeat(64); },
  newFieldsInOldProfile: v => { v.version=5;v.schema='earthship-installed-shade-publication/v2';v.release.schema='earthship-installed-shade-release/v2';v.forecast.schema='earthship-installed-shade-forecast/v3'; },
};
for (const [name, change] of Object.entries(damage)) compressedInstalledCases.push([`refuses ${name} without an active badge`, assert => {
  const value=compressedInstalledPublication();change(value);const result=parse(value);
  assert.equal(result.state,'unavailable');assert.notEqual(result.badge,'FORECAST');
}]);
