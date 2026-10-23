import {describe,it,expect} from 'vitest';
import {parseWeatherCapabilities,temperatureCapabilityAt,MAX_CAPABILITY_BYTES} from '../src/lib/weather/capabilityForecast.js';
import {buildWeatherDetailOption} from '../src/lib/weather/detailChart.js';
const now=Date.parse('2026-10-21T18:00:00Z');
function fixture(){return {
 schema:'earthship-weathernext-capabilities/v1',provider:'weathernext3',generated_at:new Date(now).toISOString(),valid_until:new Date(now+3600000).toISOString(),timezone:'America/Denver',status:'available',
 sources:[{snapshot_sha256:'a'.repeat(64),profile_sha256:'b'.repeat(64),run_id:'ee:2026-10-21T12:00:00+00:00',initialized_at:'2026-10-21T12:00:00+00:00',first_seen_at:'2026-10-21T17:00:00+00:00',available_at:'2026-10-21T17:01:00+00:00',grid_sha256:'c'.repeat(64)}],
 groups:{temperature:{method:'raw-native-statistics/v1',label:'WeatherNext p10–p90; local coverage not yet verified',nominal_interval_probability:.8,local_coverage_qualified:false,hours:[{valid_at:'2026-10-21T19:00:00Z',source_sha256:'a'.repeat(64),mean_c:20,p10_c:0,p25_c:null,p50_c:null,p75_c:null,p90_c:10,range_status:'available'}]}},
 automatic_actuation:false,release_authorized:false,report_sha256:'d'.repeat(64)
};}
describe('raw native supplemental forecast',()=>{
 it('converts values and spread independently without manufacturing a median',()=>{
  const p=parseWeatherCapabilities(JSON.stringify(fixture()),{nowMs:now});expect(p.state).toBe('ready');
  const h=temperatureCapabilityAt(p,'2026-10-21T13:00:00-06:00');
  expect(h.meanF).toBe(68);expect(h.p10F).toBe(32);expect(h.p90F).toBe(50);expect(h.spreadF).toBe(18);expect(h.p50F).toBeNull();
 });
 it('refuses stale, future, malformed or authority-bearing supplements while the old chart remains usable',()=>{
  for(const alter of [p=>p.automatic_actuation=true,p=>p.groups.temperature.local_coverage_qualified=true,p=>p.sources[0].available_at='2026-10-22T00:00:00Z',p=>p.groups.temperature.hours[0].p10_c=11]){
   const raw=fixture();alter(raw);expect(parseWeatherCapabilities(JSON.stringify(raw),{nowMs:now}).state).toBe('unavailable');
  }
  expect(parseWeatherCapabilities(JSON.stringify(fixture()),{nowMs:now+3600000}).state).toBe('unavailable');
  expect(parseWeatherCapabilities('x'.repeat(MAX_CAPABILITY_BYTES+1),{nowMs:now}).state).toBe('unavailable');
  expect(buildWeatherDetailOption({hours:[{at:'2026-10-21T19:00:00Z',tempF:70}]}).series.map(s=>s.name)).toEqual(['Radiation','Precipitation','Temperature','Wind']);
 });
 it('draws the native interval around its own raw mean while keeping the displayed point separate',()=>{
  const capabilities=parseWeatherCapabilities(JSON.stringify(fixture()),{nowMs:now});
  const option=buildWeatherDetailOption({hours:[{at:'2026-10-21T19:00:00Z',tempF:75}],capabilities});
  expect(option.series.find(s=>s.name==='Temperature').data).toEqual([75]);
  expect(option.series.find(s=>s.name==='WeatherNext raw mean').data).toEqual([68]);
  expect(option.series.find(s=>s.name==='WeatherNext p10–p90').data).toEqual([[0,32,50]]);
 });
 it('keeps missing optional quantiles separate from an available mean',()=>{
  const raw=fixture();Object.assign(raw.groups.temperature.hours[0],{p10_c:null,p90_c:null,range_status:'missing_quantiles'});
  const p=parseWeatherCapabilities(JSON.stringify(raw),{nowMs:now});expect(p.state).toBe('ready');expect(temperatureCapabilityAt(p,'2026-10-21T19:00:00Z').meanF).toBe(68);expect(temperatureCapabilityAt(p,'2026-10-21T19:00:00Z').spreadF).toBeNull();
 });
 it('does not renew a source near its original expiry by refreshing the report',()=>{
  const raw=fixture();const source=raw.sources[0];source.initialized_at='2026-10-20T18:30:00Z';source.run_id='ee:'+source.initialized_at;source.first_seen_at='2026-10-20T19:00:00Z';source.available_at='2026-10-20T19:01:00Z';
  expect(parseWeatherCapabilities(JSON.stringify(raw),{nowMs:now}).state).toBe('unavailable');
 });
});
