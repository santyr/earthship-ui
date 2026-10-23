import {describe,it,expect} from 'vitest';
import {parseWeatherSensitivity,validateSensitivityReceipt} from '../src/lib/weather/sensitivity.js';
import {sensitivity,confirmation,nowMs} from './fixtures/weather-sensitivity.js';
const parse=v=>parseWeatherSensitivity(JSON.stringify(v),{nowMs});
it('retains zero values and original provenance for the three fixed cases',()=>{
 const v=sensitivity();for(const r of v.cases){r.raw_potential_pv_kwh=0;r.modeled_captured_pv_kwh=0;for(const p of r.trajectory)p.cumulative_raw_pv_kwh=0;}
 const p=parse(v);expect(p.state).toBe('ready');expect(p.cases[0].raw_potential_pv_kwh).toBe(0);expect(p.modelSha256).toBe(v.thermal_model_sha256);
});
it.each(['extra','private_case','private_point','probability','calibration','actions','recipe','duplicates','source_clock','stale','future','model','order','negative','nan','oversize','point_clock','through','soc','capture','pv_total','minimum','missing'])('refuses %s without substituting zeros',damage=>{
 const v=sensitivity();
 if(damage==='extra')v.raw_source='/private';if(damage==='private_case')v.cases[0].raw='/private';if(damage==='private_point')v.cases[0].trajectory[0].raw='/private';
 if(damage==='probability')v.probability_claim=true;if(damage==='calibration')v.physical_calibration_qualified=true;if(damage==='actions')v.automatic_actuation=true;
 if(damage==='recipe')v.cases[1].solar_multiplier=.6;if(damage==='duplicates')v.cases[1]=v.cases[0];if(damage==='source_clock')v.source_initialized_at=v.through;
 if(damage==='stale')v.valid_until='2026-10-23T17:18:00Z';if(damage==='future')v.generated_at='2026-10-23T18:18:00Z';if(damage==='model')v.thermal_model_sha256=null;
 if(damage==='order')v.cases.reverse();if(damage==='negative')v.cases[0].raw_potential_pv_kwh=-1;if(damage==='nan')v.nominal_bank_kwh=null;
 if(damage==='oversize')v.extra='x'.repeat(65537);if(damage==='point_clock')v.cases[0].trajectory[1].at=v.cases[0].trajectory[0].at;
 if(damage==='through')v.through=v.origin;if(damage==='soc')v.cases[0].trajectory[0].nominal_soc_pct=101;if(damage==='capture')v.cases[0].modeled_captured_pv_kwh=30;
 if(damage==='pv_total')v.cases[0].trajectory.at(-1).cumulative_raw_pv_kwh=2;if(damage==='minimum')v.cases[0].minimum_nominal_soc_pct=0;if(damage==='missing')delete v.cases;
 expect(parse(v).state).toBe('unavailable');
});
it('refuses duplicate JSON keys and expiry without reissuing clocks',()=>{
 expect(parseWeatherSensitivity(JSON.stringify(sensitivity()).replace('{','{"origin":"private",'),{nowMs}).state).toBe('unavailable');
 expect(parseWeatherSensitivity(JSON.stringify(sensitivity()),{nowMs:nowMs+2*3600000}).state).toBe('unavailable');
});
it('confirmation binds exact cache bytes, model report and original clocks',()=>{
 const v=sensitivity(),view=parse(v),bytes='3'.repeat(64);const valid=confirmation(v,bytes);
 expect(validateSensitivityReceipt(JSON.stringify(valid),{view,cacheBytesSha256:bytes,nowMs})).toBe(true);
 for(const key of ['cache_bytes_sha256','original_report_sha256','report_sha256','origin','generated_at','valid_until','automatic_actuation']){
  const bad={...valid,[key]:key==='automatic_actuation'?true:'changed'};expect(validateSensitivityReceipt(JSON.stringify(bad),{view,cacheBytesSha256:bytes,nowMs})).toBe(false);
 }
});
