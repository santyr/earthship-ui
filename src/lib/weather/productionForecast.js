/** Confirmed as-issued production ranges; optional and bound to the core issue. */
import {uniqueObjectKeys} from '../household/observation.js';
export const MAX_PRODUCTION_BYTES=512*1024;
export const MAX_PRODUCTION_RECEIPT_BYTES=4096;
const HOUR=3600000,HASH=/^[a-f0-9]{64}$/;
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join('|')===[...keys].sort().join('|');
const finite=v=>typeof v==='number'&&Number.isFinite(v);
const hash=v=>typeof v==='string'&&HASH.test(v);
const object=v=>v&&typeof v==='object'&&!Array.isArray(v);
const clock=v=>typeof v==='string'&&v.length<=64&&/^\d{4}-\d\d-\d\dT/.test(v)&&/(?:Z|[+-]\d\d:\d\d)$/.test(v)?Date.parse(v):NaN;
const unavailable=()=>({state:'unavailable',rows:[],models:{},sources:{},localCoverageQualified:false});
const flags=p=>p.issued===true&&p.local_coverage_qualified===false&&p.probability_claim===false&&p.parallel_shadow_required===false&&p.automatic_actuation===false;
export function parseProductionWeather(raw,{nowMs=Date.now(),issueSha256=null}={}){
 try{
  if(typeof raw!=='string'||new TextEncoder().encode(raw).length>MAX_PRODUCTION_BYTES||!finite(nowMs))return unavailable();
  uniqueObjectKeys(raw);const p=JSON.parse(raw);
  if(!exact(p,['schema','issue_sha256','production_emission_sha256','generated_at','published_at','valid_until','sources','models','rows','issued','parallel_shadow_required','local_coverage_qualified','probability_claim','automatic_actuation','report_sha256'])||p.schema!=='earthship-confirmed-production-weather-view/v1'||!flags(p)||![p.issue_sha256,p.production_emission_sha256,p.report_sha256].every(hash)||issueSha256!==null&&p.issue_sha256!==issueSha256)return unavailable();
  const generated=clock(p.generated_at),published=clock(p.published_at),until=clock(p.valid_until);
  if(![generated,published,until].every(finite)||generated>published||published>generated+85000||published>nowMs||nowMs>=until||until<=generated||until>generated+1.5*HOUR)return unavailable();
  if(!object(p.sources)||!Object.keys(p.sources).length||Object.keys(p.sources).length>2||!object(p.models)||Object.keys(p.models).length>12||!Array.isArray(p.rows)||!p.rows.length||p.rows.length>672)return unavailable();
  for(const [pin,s] of Object.entries(p.sources)){
   const init=clock(s?.initialized_at),available=clock(s?.available_at);
   if(!hash(pin)||!exact(s,['initialized_at','available_at'])||![init,available].every(finite)||init>available||available>generated||until>init+24*HOUR)return unavailable();
  }
  for(const [pin,m] of Object.entries(p.models)){
   if(!hash(pin)||!exact(m,['method_family','bundle_sha256','admission_sha256','procedure_sha256','training_policy_sha256','training_availability_basis','cutoff','actual_completed_at','expires_at','support'])||!['empirical','temperature_normal','nonnegative'].includes(m.method_family)||![m.bundle_sha256,m.admission_sha256,m.procedure_sha256,m.training_policy_sha256].every(hash)||!['historical_assumed_availability','recorded_ingestion_availability'].includes(m.training_availability_basis))return unavailable();
   const cutoff=clock(m.cutoff),completed=clock(m.actual_completed_at),expiry=clock(m.expires_at);
   if(![cutoff,completed,expiry].every(finite)||cutoff>completed||completed>generated||generated>=expiry||!exact(m.support,['pairs','targets','local_dates'])||!Object.values(m.support).every(v=>Number.isSafeInteger(v)&&v>0)||m.support.local_dates>m.support.targets||m.support.targets>m.support.pairs)return unavailable();
  }
  const seen=new Set(),usedModels=new Set(),usedSources=new Set();let prior=-Infinity;
  for(const r of p.rows){
   if(!exact(r,['kind','profile','source_sha256','target_start','target_end','raw','local','reason'])||!['temperature','wind'].includes(r.kind)||!['extended','nearTerm'].includes(r.profile)||!Object.hasOwn(p.sources,r.source_sha256))return unavailable();
   const start=clock(r.target_start),end=clock(r.target_end),key=r.kind+'|'+end;
   if(![start,end].every(finite)||end<=generated||end>generated+336*HOUR||end<prior||seen.has(key)||(r.kind==='temperature'?start!==end:start<generated||end-start!==HOUR))return unavailable();
   prior=end;seen.add(key);usedSources.add(r.source_sha256);
   if(!exact(r.raw,['mean','p10','p50','p90','statistic'])||!finite(r.raw.mean)||r.raw.statistic!==(r.kind==='temperature'?'native_point':'native_boundary_mean_hour_approximation'))return unavailable();
   let previous=-Infinity;
   for(const field of ['p10','p50','p90']){const q=r.raw[field];if(q===null)continue;if(!finite(q)||q<previous||r.kind==='wind')return unavailable();previous=q;}
   if(r.kind==='wind'&&r.raw.mean<0)return unavailable();
   if(r.local===null){if(typeof r.reason!=='string'||!/^[a-z_]{1,128}$/.test(r.reason))return unavailable();continue;}
   const v=r.local,m=p.models[v.model_sha256];
   if(!exact(v,['model_sha256','point_estimate','point_estimate_kind','quantiles'])||!m||r.reason!==null||!finite(v.point_estimate)||!Array.isArray(v.quantiles)||v.quantiles.length!==5||!v.quantiles.every(finite)||v.quantiles.some((q,i)=>i&&q<v.quantiles[i-1]))return unavailable();
   if(m.method_family==='empirical'?(v.point_estimate_kind!=='model_median'||v.point_estimate!==v.quantiles[2]):v.point_estimate_kind!=='model_mean')return unavailable();
   if(r.kind==='temperature'?m.method_family==='nonnegative':m.method_family==='temperature_normal'||[v.point_estimate,...v.quantiles].some(v=>v<0))return unavailable();
   usedModels.add(v.model_sha256);
  }
  if(usedModels.size!==Object.keys(p.models).length||usedSources.size!==Object.keys(p.sources).length)return unavailable();
  return {state:'ready',rows:p.rows,models:p.models,sources:p.sources,issueSha256:p.issue_sha256,emissionSha256:p.production_emission_sha256,reportSha256:p.report_sha256,generatedAt:p.generated_at,publishedAt:p.published_at,validUntil:p.valid_until,localCoverageQualified:false};
 }catch{return unavailable();}
}
export function validateProductionViewReceipt(raw,{view,cacheBytesSha256,nowMs=Date.now()}={}){
 try{
  if(typeof raw!=='string'||new TextEncoder().encode(raw).length>MAX_PRODUCTION_RECEIPT_BYTES||view?.state!=='ready'||!finite(nowMs))return false;
  uniqueObjectKeys(raw);const p=JSON.parse(raw);
  return exact(p,['schema','issue_sha256','production_emission_sha256','report_sha256','cache_bytes_sha256','generated_at','published_at','valid_until','issued','automatic_actuation','receipt_sha256'])&&p.schema==='earthship-confirmed-production-view-receipt/v1'&&p.issued===true&&p.automatic_actuation===false&&hash(p.receipt_sha256)&&hash(p.cache_bytes_sha256)&&p.cache_bytes_sha256===cacheBytesSha256&&p.issue_sha256===view.issueSha256&&p.production_emission_sha256===view.emissionSha256&&p.report_sha256===view.reportSha256&&p.generated_at===view.generatedAt&&p.published_at===view.publishedAt&&p.valid_until===view.validUntil&&clock(p.published_at)<=nowMs&&nowMs<clock(p.valid_until);
 }catch{return false;}
}
export const productionWeatherAt=(view,at,kind)=>view?.state==='ready'?view.rows.find(r=>clock(r.target_end)===clock(at)&&r.kind===kind)??null:null;
