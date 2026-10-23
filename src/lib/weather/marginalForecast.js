import {uniqueObjectKeys} from '../household/observation.js';
export const MAX_MARGINAL_BYTES=256*1024;
export const MAX_MARGINAL_EMISSION_BYTES=8192;
export const MARGINAL_LABEL='Local marginal candidate (shadow; unqualified)';
const HOUR=3600000,HASH=/^[a-f0-9]{64}$/,LEVELS=[.1,.25,.5,.75,.9];
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join('|')===[...keys].sort().join('|');
const finite=v=>typeof v==='number'&&Number.isFinite(v);
const hash=v=>typeof v==='string'&&HASH.test(v);
const clock=v=>typeof v==='string'&&v.length<=64&&/^\d{4}-\d\d-\d\dT/.test(v)&&/(?:Z|[+-]\d\d:\d\d)$/.test(v)?Date.parse(v):NaN;
const unavailable=()=>({state:'unavailable',rows:[],localCoverageQualified:false});
function localValid(v,family,kind){
 if(v===null)return true;
 if(!exact(v,['mean','quantile_levels','quantiles','point_estimate','point_estimate_kind','model_sha256'])||!hash(v.model_sha256)||!Array.isArray(v.quantile_levels)||v.quantile_levels.join('|')!==LEVELS.join('|')||!Array.isArray(v.quantiles)||v.quantiles.length!==5||!v.quantiles.every(finite)||v.quantiles.some((q,i)=>i&&q<v.quantiles[i-1])||!finite(v.point_estimate))return false;
 if(kind!=='temperature'&&[...v.quantiles,v.point_estimate,...(v.mean===null?[]:[v.mean])].some(x=>!finite(x)||x<0))return false;
 return family==='empirical'?v.mean===null&&v.point_estimate_kind==='model_median'&&v.point_estimate===v.quantiles[2]:finite(v.mean)&&v.point_estimate_kind==='model_mean'&&v.point_estimate===v.mean;
}
export function parseWeatherMarginals(raw,{nowMs=Date.now()}={}){
 try{
  if(typeof raw!=='string'||new TextEncoder().encode(raw).length>MAX_MARGINAL_BYTES||!finite(nowMs))return unavailable();
  uniqueObjectKeys(raw);const p=JSON.parse(raw);
  if(!exact(p,['schema','issue_sha256','generated_at','valid_until','status','rows','contract_sha256','policy_sha256','issued','product','core_forecast_modified','local_coverage_qualified','probability_claim','automatic_actuation','report_sha256'])||p.schema!=='earthship-local-marginal-shadow-view/v1'||p.product!=='read_only_unselected_shadow'||p.issued!==true||p.core_forecast_modified!==false||p.local_coverage_qualified!==false||p.probability_claim!==false||p.automatic_actuation!==false||![p.issue_sha256,p.contract_sha256,p.policy_sha256,p.report_sha256].every(hash))return unavailable();
  const generated=clock(p.generated_at),until=clock(p.valid_until);
  if(![generated,until].every(finite)||generated>nowMs+5000||nowMs>=until||until<=generated||until>generated+2*HOUR||!Array.isArray(p.rows)||p.rows.length>96)return unavailable();
  const seen=new Set(),rows=[];let previous=-Infinity,active=false;
  for(const r of p.rows){
   if(!exact(r,['kind','target_start','target_end','source_sha256','raw','local','adaptive','status','reason'])||!['temperature','wind','solar_proxy'].includes(r.kind)||!hash(r.source_sha256)||!exact(r.raw,['mean','p10','p50','p90'])||!finite(r.raw.mean))return unavailable();
   const start=clock(r.target_start),end=clock(r.target_end),key=r.kind+'|'+end;
   if(![start,end].every(finite)||end<=generated||end>generated+336*HOUR||end<previous||seen.has(key)||(r.kind==='temperature'?start!==end:end-start!==HOUR||start<generated))return unavailable();
   previous=end;seen.add(key);let prior=-Infinity;
   for(const name of ['p10','p50','p90']){const q=r.raw[name];if(q===null)continue;if(!finite(q)||q<prior)return unavailable();prior=q;}
   if(r.kind!=='temperature'&&Object.values(r.raw).some(v=>v!==null&&v<0))return unavailable();
   const families=r.kind==='temperature'?['empirical','temperature_normal']:['empirical','nonnegative'];
   if(!exact(r.local,families)||!families.every(f=>localValid(r.local[f],f,r.kind)))return unavailable();
   if(r.kind!=='temperature'&&r.adaptive!==null)return unavailable();
   if(r.adaptive!==null&&(!exact(r.adaptive,['value','candidate_used','model_sha256'])||!finite(r.adaptive.value)||typeof r.adaptive.candidate_used!=='boolean'||(r.adaptive.candidate_used?!hash(r.adaptive.model_sha256):r.adaptive.model_sha256!==null)))return unavailable();
   const used=Object.values(r.local).some(v=>v!==null)||r.adaptive?.candidate_used===true;
   if(used?(r.status!=='read_only_shadow_candidates'||r.reason!==null):(r.status!=='raw_fallback'||typeof r.reason!=='string'||r.reason.length<1||r.reason.length>128))return unavailable();
   active ||=used;
   rows.push({...r,unit:{temperature:'degC',wind:'m_s',solar_proxy:'W_m2_reported_proxy'}[r.kind],label:MARGINAL_LABEL});
  }
  if(!rows.length||p.status!==(active?'read_only_shadow_candidates':'raw_fallback'))return unavailable();
  return {state:'ready',rows,issueSha256:p.issue_sha256,reportSha256:p.report_sha256,contractSha256:p.contract_sha256,generatedAt:p.generated_at,validUntil:p.valid_until,label:MARGINAL_LABEL,localCoverageQualified:false};
 }catch{return unavailable();}
}
export function validateMarginalEmission(raw,{view,cacheBytesSha256,nowMs=Date.now()}={}){
 try{
  if(typeof raw!=='string'||new TextEncoder().encode(raw).length>MAX_MARGINAL_EMISSION_BYTES||view?.state!=='ready')return false;
  uniqueObjectKeys(raw);const p=JSON.parse(raw),completed=clock(p.cache_write_completed_at);
  return exact(p,['schema','issue_sha256','wrapper_sha256','report_sha256','cache_write_completed_at','contract_sha256','automatic_actuation','emission_sha256','cache_bytes_sha256'])&&p.schema==='earthship-confirmed-marginal-emission/v2'&&p.automatic_actuation===false&&[p.issue_sha256,p.wrapper_sha256,p.report_sha256,p.contract_sha256,p.emission_sha256].every(hash)&&hash(p.cache_bytes_sha256)&&p.cache_bytes_sha256===cacheBytesSha256&&p.issue_sha256===view.issueSha256&&p.report_sha256===view.reportSha256&&p.contract_sha256===view.contractSha256&&finite(completed)&&clock(view.generatedAt)<=completed&&completed<clock(view.validUntil)&&completed<=nowMs;
 }catch{return false;}
}
