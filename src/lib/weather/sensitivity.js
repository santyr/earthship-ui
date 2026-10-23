/** Curated deterministic weather cases. No path, model execution or probabilities. */
import {uniqueObjectKeys} from '../household/observation.js';
export const MAX_SENSITIVITY_BYTES=65536,MAX_SENSITIVITY_RECEIPT_BYTES=4096;
const HOUR=3600000,POLICY='4d1f3bfb5e8b82d460e8d2848fa78c01aed7cad06d4b21f02670fb70320990f5';
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join('|')===[...keys].sort().join('|');
const finite=v=>typeof v==='number'&&Number.isFinite(v),hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const clock=v=>typeof v==='string'&&v.length<=64&&/^\d{4}-\d\d-\d\dT/.test(v)&&/(?:Z|[+-]\d\d:\d\d)$/.test(v)?Date.parse(v):NaN;
const range=(v,min,max)=>finite(v)&&v>=min&&v<=max,close=(a,b)=>Math.abs(a-b)<=1e-8*Math.max(1,Math.abs(a),Math.abs(b));
const unavailable=()=>({state:'unavailable',cases:[]});
export function parseWeatherSensitivity(raw,{nowMs=Date.now()}={}){
 try{
  if(typeof raw!=='string'||new TextEncoder().encode(raw).length>MAX_SENSITIVITY_BYTES||!finite(nowMs))return unavailable();
  uniqueObjectKeys(raw);const p=JSON.parse(raw);
  if(!exact(p,['schema','generated_at','origin','through','valid_until','source_forecast_sha256','source_initialized_at','original_report_sha256','policy_sha256','source_package_sha256','thermal_model_sha256','producer_deployment_sha256','initial_soc_pct','nominal_bank_kwh','fixed_load_ac_w','cases','joint_status','probability_claim','physical_calibration_qualified','automatic_actuation','report_sha256'])||p.schema!=='earthship-production-weather-sensitivity/v1'||p.policy_sha256!==POLICY||p.probability_claim!==false||p.physical_calibration_qualified!==false||p.automatic_actuation!==false||p.joint_status!=='insufficient_evidence')return unavailable();
  if(!['source_forecast_sha256','original_report_sha256','source_package_sha256','thermal_model_sha256','producer_deployment_sha256','report_sha256'].every(k=>hash(p[k])))return unavailable();
  const origin=clock(p.origin),generated=clock(p.generated_at),through=clock(p.through),until=clock(p.valid_until),initialized=clock(p.source_initialized_at),hours=(through-origin)/HOUR;
  if(![origin,generated,through,until,initialized].every(finite)||initialized>origin||origin>generated||generated>origin+17*60000||generated>nowMs||nowMs>=until||until!==Math.min(origin+2*HOUR,through,initialized+24*HOUR)||!Number.isInteger(hours)||hours<1||hours>24)return unavailable();
  if(!range(p.initial_soc_pct,0,100)||!finite(p.nominal_bank_kwh)||p.nominal_bank_kwh<=0||!finite(p.fixed_load_ac_w)||p.fixed_load_ac_w<0||!Array.isArray(p.cases)||p.cases.length!==3)return unavailable();
  const recipes=[['central',0,1],['reduced_solar',0,.5],['warm_high_gain',3,1.2]];
  for(let i=0;i<3;i++){
   const r=p.cases[i],recipe=recipes[i];
   if(!exact(r,['name','temperature_delta_c','solar_multiplier','raw_potential_pv_kwh','modeled_captured_pv_kwh','minimum_nominal_soc_pct','indoor_air_f','north_wall_f','thermal_status','trajectory'])||r.name!==recipe[0]||r.temperature_delta_c!==recipe[1]||r.solar_multiplier!==recipe[2]||!finite(r.raw_potential_pv_kwh)||r.raw_potential_pv_kwh<0||!range(r.modeled_captured_pv_kwh,0,r.raw_potential_pv_kwh+1e-8)||!range(r.minimum_nominal_soc_pct,0,100)||!['unqualified_native_model_sensitivity','unavailable'].includes(r.thermal_status)||!Array.isArray(r.trajectory)||r.trajectory.length!==hours)return unavailable();
   const thermal=r.thermal_status==='unqualified_native_model_sensitivity';
   if(thermal?![r.indoor_air_f,r.north_wall_f].every(v=>range(v,-40,160)):r.indoor_air_f!==null||r.north_wall_f!==null)return unavailable();
   let prior=0;
   for(let h=0;h<hours;h++){
    const row=r.trajectory[h];
    if(!exact(row,['at','nominal_soc_pct','cumulative_raw_pv_kwh','air_f','north_wall_f'])||clock(row.at)!==origin+(h+1)*HOUR||!range(row.nominal_soc_pct,0,100)||!finite(row.cumulative_raw_pv_kwh)||row.cumulative_raw_pv_kwh<prior-1e-8||row.cumulative_raw_pv_kwh>r.raw_potential_pv_kwh+1e-8||(thermal?![row.air_f,row.north_wall_f].every(v=>range(v,-40,160)):row.air_f!==null||row.north_wall_f!==null))return unavailable();
    prior=row.cumulative_raw_pv_kwh;
   }
   if(!close(prior,r.raw_potential_pv_kwh)||!close(r.minimum_nominal_soc_pct,Math.min(p.initial_soc_pct,...r.trajectory.map(t=>t.nominal_soc_pct)))||thermal&&(!close(r.indoor_air_f,r.trajectory.at(-1).air_f)||!close(r.north_wall_f,r.trajectory.at(-1).north_wall_f)))return unavailable();
  }
  return {state:'ready',cases:p.cases,origin:p.origin,generatedAt:p.generated_at,validUntil:p.valid_until,through:p.through,reportSha256:p.report_sha256,originalReportSha256:p.original_report_sha256,modelSha256:p.thermal_model_sha256,sourceSha256:p.source_forecast_sha256,initialSocPct:p.initial_soc_pct,nominalBankKwh:p.nominal_bank_kwh,fixedLoadAcW:p.fixed_load_ac_w};
 }catch{return unavailable();}
}
export function validateSensitivityReceipt(raw,{view,cacheBytesSha256,nowMs=Date.now()}={}){
 try{
  if(typeof raw!=='string'||new TextEncoder().encode(raw).length>MAX_SENSITIVITY_RECEIPT_BYTES||view?.state!=='ready'||!finite(nowMs))return false;
  uniqueObjectKeys(raw);const p=JSON.parse(raw),published=clock(p.published_at);
  return exact(p,['schema','original_report_sha256','capsule_sha256','report_sha256','cache_bytes_sha256','origin','generated_at','valid_until','published_at','automatic_actuation','receipt_sha256'])&&p.schema==='earthship-confirmed-scenario-view/v1'&&p.automatic_actuation===false&&[p.capsule_sha256,p.receipt_sha256,p.cache_bytes_sha256].every(hash)&&p.cache_bytes_sha256===cacheBytesSha256&&p.report_sha256===view.reportSha256&&p.original_report_sha256===view.originalReportSha256&&p.origin===view.origin&&p.generated_at===view.generatedAt&&p.valid_until===view.validUntil&&finite(published)&&clock(p.generated_at)<=published&&published<=nowMs&&nowMs<clock(p.valid_until);
 }catch{return false;}
}
