import { describe, it, expect } from 'vitest';
import { parseForecast10Day } from '../src/lib/weather/forecastDetail.js';

const nowMs=Date.parse('2026-10-22T12:00:00-06:00');
function original() {
 return { version:3,provider:'weathernext3',providerStatus:'AVAILABLE',generatedAt:'2026-10-22T12:00:00-06:00',timezone:'America/Denver',
  productionModel:{issueSha256:'a'.repeat(64),status:'MIXED_WITH_RAW_FALLBACK',localCoverageQualified:false,probabilityClaim:false,temperatureStatistic:'model_point_with_declared_raw_fallback',windStatistic:'native_instantaneous_with_separate_local_hour_mean'},
  days:[{date:'2026-10-22',summary:{highF:63,lowF:61,precipPct:null,weatherCode:null,pvKwh:null,temperatureScope:'remaining',temperatureStatistic:'extrema_of_hourly_point_forecasts'},hours:[
   {at:'2026-10-22T13:00:00-06:00',tempF:61,windMph:10,windMeanMph:6,radiationWm2:300},
   {at:'2026-10-22T14:00:00-06:00',tempF:63,windMph:12,radiationWm2:400}]}] };
}

describe('selected production forecast reader',()=>{
 it('serves corrected temperature and local hourly wind while retaining native wind and scope',()=>{
  const parsed=parseForecast10Day(JSON.stringify(original()),{nowMs});
  expect(parsed.status).toBe('ready');expect(parsed.productionModel.issueSha256).toBe('a'.repeat(64));
  expect(parsed.days[0].hours[0]).toMatchObject({tempF:61,windMph:6,nativeWindMph:10,windStatistic:'local_hour_mean',precipPct:null,weatherCode:null});
  expect(parsed.days[0].hours[1]).toMatchObject({windMph:12,nativeWindMph:12,windStatistic:'native_instantaneous'});
  expect(parsed.days[0].summary).toMatchObject({temperatureScope:'remaining',temperatureStatistic:'extrema_of_hourly_point_forecasts'});
 });
 it('refuses malformed production identity and unsupported probability claims',()=>{
  for(const override of [{issueSha256:'bad'},{localCoverageQualified:true},{probabilityClaim:true},{windStatistic:'instantaneous_equals_hourly'}]){
   const raw=original();Object.assign(raw.productionModel,override);
   expect(parseForecast10Day(JSON.stringify(raw),{nowMs})).toMatchObject({status:'unavailable',legacyFallbackAllowed:false});
  }
 });
 it('does not apply new hourly-wind semantics to legacy raw payloads',()=>{
  const raw=original();raw.version=1;delete raw.productionModel;raw.days[0].hours.forEach(h=>Object.assign(h,{precipPct:null,weatherCode:null}));
  const parsed=parseForecast10Day(JSON.stringify(raw),{nowMs});
  expect(parsed.status).toBe('ready');expect(parsed.days[0].hours[0].windMph).toBe(10);
 });
});
