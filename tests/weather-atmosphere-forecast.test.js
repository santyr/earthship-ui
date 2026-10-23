import {describe,it,expect} from 'vitest';
import originals from './fixtures/weather-atmosphere.json';
import {parseWeatherCapabilities,temperatureCapabilityAt} from '../src/lib/weather/capabilityForecast.js';
import {CAPABILITY_NOW as now} from './fixtures/weather-capabilities.js';
const fixture=(kind='outdoor')=>structuredClone(originals[kind]);
const read=(p,at=now)=>parseWeatherCapabilities(JSON.stringify(p),{nowMs:at});
const group=p=>p.groups.atmosphere;
const first=p=>group(p).hours[0];

describe('source-bound atmospheric supplement from the actual Python producer',()=>{
 it('keeps temperature, independent cloud layers, scalar wind and mean-vector quantities distinct',()=>{
  const p=read(fixture());expect(p.state).toBe('ready');expect(temperatureCapabilityAt(p,'2026-10-21T19:00:00Z').meanF).toBe(50);
  const a=p.atmosphere;expect(a.state).toBe('ready');expect(a.hours).toHaveLength(24);
  const h=a.hours[0];expect(h.dewpointF).toBe(41);expect(h.pressureHpa).toBe(900);expect(h.scalarSpeedMph).toBeCloseTo(2*2.2369362920544);
  expect(h.vectorMagnitudeMph).toBeCloseTo(Math.SQRT2*2.2369362920544);expect(h.windFromDegrees).toBe(135);
  expect(h.clouds).toEqual({total:40,high:40,medium:40,low:40});expect(h.relativeHumidityPct).toBeCloseTo(71.03,1);
  expect(h.fieldSources.temperature.snapshot_sha256).not.toBe(h.fieldSources.u.snapshot_sha256);
  expect(a.moisture.mode).toBe('outdoor_only');expect(a.moisture.missingDependencies).toContain('qualified_indoor_temperature_and_relative_humidity');
 });
 it('accepts an atmospheric-only report and still validates the empty temperature contract',()=>{
  const p=fixture();p.groups.temperature.hours=[];p.sources=[];
  expect(read(p).state).toBe('ready');expect(read(p).hours).toEqual([]);expect(read(p).atmosphere.hours).toHaveLength(24);
  p.groups.temperature.local_coverage_qualified=true;expect(read(p).state).toBe('unavailable');
 });
 for(const [u,v,direction,reason] of [[1,0,270,null],[0,-1,0,null],[-1,0,90,null],[0,1,180,null],[0,0,null,'calm_or_cancelling_mean_vector']]){
  it(`recomputes meteorological direction for u=${u} v=${v}`,()=>{
   const p=fixture(),h=first(p);h.fields.u.value=u;h.fields.v.value=v;h.wind_from_degrees=direction;h.vector_magnitude_m_s=Math.hypot(u,v);h.direction_reason=reason;
   expect(read(p).atmosphere.hours[0].windFromDegrees).toBe(direction);
  });
 }
 it('withdraws only expired atmosphere while the separately sourced temperature remains usable',()=>{
  const p=fixture();group(p).valid_until=new Date(now+60000).toISOString();
  const result=read(p,now+60001);expect(result.state).toBe('ready');expect(result.hours).toHaveLength(24);expect(result.atmosphere.state).toBe('unavailable');expect(result.atmosphere.hours).toEqual([]);
 });
 it('withdraws an expired qualified indoor comparison without losing outdoor moisture or temperature',()=>{
  const p=fixture('qualified'),before=read(p);expect(before.atmosphere.moisture.mode).toBe('qualified_comparison');
  expect(before.atmosphere.moisture.indoorTemperatureF).toBeCloseTo(71.6);expect(before.atmosphere.moisture.indoorRelativeHumidityPct).toBe(60);
  const expires=Date.parse(group(p).moisture.valid_until),after=read(p,expires);
  expect(after.state).toBe('ready');expect(after.atmosphere.state).toBe('ready');expect(after.atmosphere.moisture.mode).toBe('outdoor_only');
  expect(after.atmosphere.moisture.comparison).toBeNull();expect(after.atmosphere.moisture.indoorTemperatureF).toBeNull();expect(after.atmosphere.moisture.missingDependencies).toContain('indoor_evidence_expired');
  expect(after.atmosphere.moisture.outdoorVaporPressureHpa).toBeGreaterThan(0);
 });
 it('withholds RH and direction for incompatible actual native assets',()=>{
  const p=fixture();const h=first(p);h.fields.dewpoint.native_asset_sha256='f'.repeat(64);h.fields.u.native_asset_sha256='f'.repeat(64);
  Object.assign(h,{relative_humidity_pct:null,relative_humidity_reason:'compatible_station_pair_unavailable',wind_from_degrees:null,vector_magnitude_m_s:null,direction_reason:'mean_components_unavailable'});
  expect(read(p).atmosphere.hours[0].relativeHumidityPct).toBeNull();expect(read(p).atmosphere.hours[0].windFromDegrees).toBeNull();
 });
 const changes={
  root:p=>p.private_path='secret',groups:p=>p.groups.private_path='secret',temperature:p=>p.groups.temperature.private_path='secret',
  group:p=>group(p).private_path='secret',source:p=>group(p).sources[0].latitude=40,hour:p=>first(p).private_path='secret',
  fields:p=>first(p).fields.latitude=40,field:p=>first(p).fields.pressure.device_id='secret',moisture:p=>group(p).moisture.registry_raw='secret',
  future:p=>group(p).sources[0].available_at=new Date(now+1000).toISOString(),
  run:p=>group(p).sources[0].run_id='private-account-name',
  sourceRef:p=>first(p).fields.u.source_ref='f'.repeat(64),nativeAsset:p=>first(p).fields.u.native_asset_sha256='f'.repeat(64),
  grid:p=>group(p).sources.find(s=>s.ref_sha256===first(p).fields.pressure.source_ref).native_grid='station',
  cloud:p=>first(p).fields.high.value=101,pressure:p=>first(p).fields.pressure.value=1300,speed:p=>first(p).fields.speed.value=-1,
  derivedRh:p=>first(p).relative_humidity_pct=50,direction:p=>first(p).wind_from_degrees=15,vector:p=>first(p).vector_magnitude_m_s=20,
  scalarAsVector:p=>first(p).vector_magnitude_m_s=first(p).fields.speed.value,
  modelClaim:p=>group(p).temperature_model_uses_fields=true,authority:p=>group(p).moisture.automatic_actuation=true,
  condensation:p=>group(p).moisture.condensation_assessed=true,
  duplicateTarget:p=>group(p).hours.push(first(p)),emptyHour:p=>{for(const k of Object.keys(first(p).fields))first(p).fields[k]=null;},
  unsupportedReason:p=>group(p).moisture.missing_dependencies=['arbitrary-secret'],
  comparisonWithoutIndoor:p=>group(p).moisture.comparison='forecast_air_drier',
  zeroSource:p=>group(p).sources=[],unusedSource:p=>group(p).sources.push({...group(p).sources[0],ref_sha256:'f'.repeat(64)}),
  blankTimezone:p=>p.timezone='invalid/timezone',sourceExpiry:p=>group(p).valid_until=new Date(now+2*3600000).toISOString(),
 };
 for(const [name,damage] of Object.entries(changes))it(`refuses ${name} before the fixed route can disclose raw JSON`,()=>{
  const p=fixture();damage(p);expect(read(p).state).toBe('unavailable');
 });
 for(const [name,damage] of Object.entries({longFreshness:p=>group(p).moisture.valid_until=new Date(now+120001).toISOString(),indoorValue:p=>group(p).moisture.indoor_vapor_pressure_hpa=0,missingProof:p=>group(p).moisture.indoor_evidence_sha256s=[],inventedDirection:p=>group(p).moisture.comparison='safe_to_vent'}))it(`refuses qualified moisture ${name}`,()=>{
  const p=fixture('qualified');damage(p);expect(read(p).state).toBe('unavailable');
 });
});
