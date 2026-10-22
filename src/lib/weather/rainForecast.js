/** Original confirmed interval shadows, separate from the displayed forecast. */
import {uniqueObjectKeys} from '../household/observation.js';
export const MAX_RAIN_BYTES=256*1024,MAX_RAIN_EMISSION_BYTES=65536;
export const RAIN_LABEL='Local learned experimental interval forecast; not native Google probabilities';
export const RAIN_CONTRACT_SHA256='ff214305b9e05c40b59e6954d4883ce30b05deec66d774ed6af17b66a3ee0aac';
const HOUR=3600000,HEADS=['total_precipitation_1hr','imerg_tp_1hr','experimental_tp_1hr'];
const METHOD='two_part_logistic_occurrence_shifted_lognormal_positive_amount/v1';
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join('|')===[...keys].sort().join('|');
const finite=v=>typeof v==='number'&&Number.isFinite(v),hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const clock=v=>typeof v==='string'&&v.length<=64&&/^\d{4}-\d\d-\d\dT/.test(v)&&/(?:Z|[+-]\d\d:\d\d)$/.test(v)?Date.parse(v):NaN;
const unavailable=()=>({state:'unavailable',rows:[],localCoverageQualified:false});
function localValid(l,r){
 if(!exact(l,['status','reason','probability_wet','conditional_wet_mean_mm','subthreshold_mean_mm','mean_depth_mm','climatology_probability','target','forecast_sha256','model_sha256','method','source_label','native_google_probability','probability_calibration_qualified','physical_calibration_qualified','automatic_actuation'])||!hash(l.forecast_sha256)||(l.model_sha256!==null&&!hash(l.model_sha256))||l.method!==METHOD||l.source_label!==RAIN_LABEL[0].toLowerCase()+RAIN_LABEL.slice(1)||['native_google_probability','probability_calibration_qualified','physical_calibration_qualified','automatic_actuation'].some(k=>l[k]!==false))return false;
 if(!exact(l.target,['start','end','interval_kind','hours'])||Object.keys(l.target).some(k=>l.target[k]!==r[k]))return false;
 const numbers=['probability_wet','conditional_wet_mean_mm','subthreshold_mean_mm','mean_depth_mm','climatology_probability'];
 if(l.status==='insufficient_evidence')return typeof l.reason==='string'&&l.reason.length>0&&l.reason.length<=128&&numbers.every(k=>l[k]===null);
 if(l.status!=='experimental_prediction'||l.reason!==null||!hash(l.model_sha256)||!numbers.every(k=>finite(l[k])&&l[k]>=0)||l.probability_wet>1||l.climatology_probability>1||l.conditional_wet_mean_mm<=0||Object.values(r.raw_means_mm).some(v=>v===null))return false;
 const expected=l.probability_wet*l.conditional_wet_mean_mm+(1-l.probability_wet)*l.subthreshold_mean_mm;
 return Math.abs(expected-l.mean_depth_mm)<=1e-9*Math.max(1,expected);
}
export function parseRainShadow(raw,{nowMs=Date.now()}={}){
 try{
  if(typeof raw!=='string'||new TextEncoder().encode(raw).length>MAX_RAIN_BYTES||!finite(nowMs))return unavailable();
  uniqueObjectKeys(raw);const p=JSON.parse(raw),v2=p?.schema==='earthship-rain-shadow-view/v2';
  if(!exact(p,['schema','generated_at','valid_until','rows','product','native_google_probability','probability_calibration_qualified','physical_calibration_qualified','core_forecast_modified','automatic_actuation','report_sha256'])||(!v2&&p.schema!=='earthship-rain-shadow-view/v1')||p.product!=='read_only_unselected_interval_rain_shadow'||!hash(p.report_sha256)||['native_google_probability','probability_calibration_qualified','physical_calibration_qualified','core_forecast_modified','automatic_actuation'].some(k=>p[k]!==false))return unavailable();
  const generated=clock(p.generated_at),until=clock(p.valid_until);
  if(![generated,until].every(finite)||generated>nowMs+5000||until<=generated||until>generated+(v2?6:2)*HOUR||nowMs>=until||!Array.isArray(p.rows)||p.rows.length<1||p.rows.length>32)return unavailable();
  const seen=new Set();
  for(const r of p.rows){
   if(!exact(r,['issue_sha256','start','end','hours','interval_kind','raw_means_mm','local','source_available_at','initialized_at','availability_basis'])||!hash(r.issue_sha256)||r.availability_basis!=='recorded_ingestion_availability'||!exact(r.raw_means_mm,HEADS)||!Object.values(r.raw_means_mm).every(v=>v===null||finite(v)&&v>=0))return unavailable();
   const start=clock(r.start),end=clock(r.end),init=clock(r.initialized_at),available=clock(r.source_available_at),key=[r.interval_kind,start,end].join('|');
   if(![start,end,init,available].every(finite)||!(init<=available&&available<=generated&&generated<=init+24*HOUR&&until<=init+24*HOUR)||end<=start||end>init+360*HOUR||!Number.isInteger(r.hours)||r.hours!==(end-start)/HOUR||seen.has(key))return unavailable();
   if(r.interval_kind==='rolling_24_hours'?r.hours!==24:r.interval_kind==='local_calendar_day'?![23,24,25].includes(r.hours):r.interval_kind==='remaining_day'?r.hours<1||r.hours>24:true)return unavailable();
   seen.add(key);if(!localValid(r.local,r))return unavailable();
  }
  return {state:'ready',rows:p.rows,reportSha256:p.report_sha256,generatedAt:p.generated_at,validUntil:p.valid_until,label:RAIN_LABEL,localCoverageQualified:false};
 }catch{return unavailable();}
}
export function validateRainEmission(raw,{view,cacheBytesSha256,nowMs=Date.now()}={}){
 try{
  if(typeof raw!=='string'||new TextEncoder().encode(raw).length>MAX_RAIN_EMISSION_BYTES||view?.state!=='ready'||!finite(nowMs))return false;
  uniqueObjectKeys(raw);const p=JSON.parse(raw),at=clock(p.cache_write_completed_at);
  return exact(p,['schema','wrapper_sha256','cache_bytes_sha256','cache_write_completed_at','contract_sha256','automatic_actuation','emission_sha256'])&&p.schema==='earthship-confirmed-rain-emission/v1'&&p.contract_sha256===RAIN_CONTRACT_SHA256&&p.automatic_actuation===false&&[p.wrapper_sha256,p.cache_bytes_sha256,p.emission_sha256].every(hash)&&p.cache_bytes_sha256===cacheBytesSha256&&finite(at)&&clock(view.generatedAt)<=at&&at<clock(view.validUntil)&&at<=nowMs;
 }catch{return false;}
}
