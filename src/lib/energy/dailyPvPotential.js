import { uniqueObjectKeys } from '../household/observation.js';
import { HOUSEHOLD_TIMEZONE } from '../site.js';
const shape=(v,keys)=>v!==null&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const stamp=v=>typeof v==='string'&&/T.*(?:Z|[+-]\d\d:\d\d)$/.test(v)&&Number.isFinite(Date.parse(v))?Date.parse(v):null;
const hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const localDate=ms=>new Intl.DateTimeFormat('en-CA',{timeZone:HOUSEHOLD_TIMEZONE,year:'numeric',month:'2-digit',day:'2-digit'}).format(ms);
const localHour=ms=>new Intl.DateTimeFormat('en-GB',{timeZone:HOUSEHOLD_TIMEZONE,hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(ms);
/** Curated separate array potential, never a captured-energy claim. */
export function parseDailyPvPotential(raw,{nowMs=Date.now()}={}){
 try{
  if(typeof raw!=='string'||raw.length>32768)return null;
  uniqueObjectKeys(raw);
  const v=JSON.parse(raw);
  if(v?.schema==='earthship-daily-pv-potential/v4')return parseComponentDaily(v,nowMs);
  const extended=v?.schema==='earthship-daily-pv-potential/v3';
  const calibrated=extended||v?.schema==='earthship-daily-pv-potential/v2';
  if(!shape(v,['schema','provider','generatedAt','validUntil','timezone','weatherSha256','geometrySha256','systemSha256','horizonSha256','confidence','automatic_actuation','physical_calibration_qualified','days',...(calibrated?['calibration']:[])])
    ||(!calibrated&&v.schema!=='earthship-daily-pv-potential/v1')||v.provider!=='weathernext3'||v.timezone!==HOUSEHOLD_TIMEZONE
    ||v.confidence!==(extended?'provisional_empirical_supported_horizon':calibrated?'provisional_empirical_short_horizon':'provisional_uncalibrated')||v.automatic_actuation!==false||v.physical_calibration_qualified!==false
    ||!['weatherSha256','geometrySha256','systemSha256','horizonSha256'].every(k=>hash(v[k])))return null;
  const generated=stamp(v.generatedAt),until=stamp(v.validUntil);
  if(generated===null||until===null||generated>nowMs||until-generated!==90*60000||nowMs>=until
    ||!Array.isArray(v.days)||v.days.length<1||v.days.length>10)return null;
  if(calibrated){
   const c=v.calibration;
   if(!shape(c,['modelSha256','trainingThrough','assessedThrough','applyThroughAt','independentTargetDays','baselineMaeW','candidateMaeW','qualification',...(extended?['policySha256']:[])])
     ||!hash(c.modelSha256)||extended&&!hash(c.policySha256)||stamp(c.trainingThrough)===null||stamp(c.assessedThrough)===null
     ||stamp(c.trainingThrough)>generated||stamp(c.assessedThrough)>generated||stamp(c.applyThroughAt)!==generated+(extended?336:24)*3600000
     ||!Number.isInteger(c.independentTargetDays)||c.independentTargetDays<2||c.independentTargetDays>90
     ||![c.baselineMaeW,c.candidateMaeW].every(x=>typeof x==='number'&&Number.isFinite(x)&&x>=0&&x<=20000)
     ||c.candidateMaeW>=c.baselineMaeW||c.qualification!=='retrospective_development_assessment_not_prospective_or_metrology')return null;
  }
  let previous='';
  for(const d of v.days){
   if(!shape(d,['date','status','reason','potentialKwh','fromAt','throughAt','scope',...(calibrated?['uncalibratedPotentialKwh','calibrationScope']:[])])||typeof d.date!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(d.date)||d.date<=previous||d.date<localDate(generated))return null;
   const start=stamp(d.fromAt),end=stamp(d.throughAt);
   if(start===null||end===null||start<generated||end<=start||end-start>25*3600000||localDate(start)!==d.date||localDate(end-1)!==d.date||localHour(end)!=='00:00:00')return null;
   if(!['remaining','full_day'].includes(d.scope)||d.scope==='full_day'&&localHour(start)!=='00:00:00')return null;
   if(d.status==='available'){
    if(d.reason!==null||typeof d.potentialKwh!=='number'||!Number.isFinite(d.potentialKwh)||d.potentialKwh<0||d.potentialKwh>1000)return null;
   }else if(d.status!=='unavailable'||d.potentialKwh!==null||typeof d.reason!=='string'||!/^[a-z_]{1,95}$/.test(d.reason))return null;
   if(calibrated){
    if(!['none','mixed',extended?'empirical_supported_horizon':'empirical_short_horizon'].includes(d.calibrationScope))return null;
    if(d.status==='unavailable'){
     if(d.uncalibratedPotentialKwh!==null||d.calibrationScope!=='none')return null;
    }else if(typeof d.uncalibratedPotentialKwh!=='number'||!Number.isFinite(d.uncalibratedPotentialKwh)||d.uncalibratedPotentialKwh<0||d.uncalibratedPotentialKwh>1000
      ||d.calibrationScope==='none'&&d.uncalibratedPotentialKwh!==d.potentialKwh
      ||d.calibrationScope!=='none'&&start>=stamp(v.calibration.applyThroughAt))return null;
   }
   previous=d.date;
  }
  return v;
 }catch{return null;}
}
export function dailyPvForDate(view,date){return view?.days.find(d=>d.date===date&&d.status==='available')??null;}


function parseComponentDaily(v,nowMs){
 if(!Number.isFinite(nowMs)||!shape(v,['schema','provider','generatedAt','validUntil','timezone','weatherSha256','geometrySha256','systemSha256','horizonSha256','confidence','automatic_actuation','physical_calibration_qualified','days','calibration'])
  ||v.provider!=='weathernext3'||v.timezone!==HOUSEHOLD_TIMEZONE||v.confidence!=='experimental_native_component_model'||v.automatic_actuation!==false||v.physical_calibration_qualified!==false
  ||!['weatherSha256','geometrySha256','systemSha256','horizonSha256'].every(k=>hash(v[k])))return null;
 const generated=stamp(v.generatedAt),until=stamp(v.validUntil),c=v.calibration;
 if(generated===null||until===null||generated>nowMs||until<=generated||until>generated+90*60000||nowMs>=until||!Array.isArray(v.days)||!v.days.length||v.days.length>10)return null;
 if(!shape(c,['modelSha256','calibrationSha256','procedureSha256','policySha256','trainedAt','trainingThrough','validUntil','targets','localTargetDates','baselineRule','mode','physicalCalibrationQualified'])
  ||!['modelSha256','calibrationSha256','procedureSha256','policySha256'].every(k=>hash(c[k]))||c.physicalCalibrationQualified!==false
  ||c.baselineRule!=='native_fdir_ssrd_isotropic_faiman_proxy_pvwatts_dc_v2'||!['experimental_production','raw_component_fallback'].includes(c.mode)
  ||!Number.isSafeInteger(c.targets)||c.targets<24||c.targets>10000||!Number.isSafeInteger(c.localTargetDates)||c.localTargetDates<3||c.localTargetDates>c.targets)return null;
 const trained=stamp(c.trainedAt),cutoff=stamp(c.trainingThrough),expiry=stamp(c.validUntil);
 if([trained,cutoff,expiry].some(t=>t===null)||cutoff>trained||expiry!==trained+14*86400000||c.mode==='experimental_production'&&!(trained<=generated&&generated<expiry))return null;
 let previous='',active=false;
 for(const d of v.days){
  if(!shape(d,['date','status','reason','potentialKwh','uncalibratedPotentialKwh','fromAt','throughAt','scope','calibrationScope','sourceSupport','projectionSha256'])
   ||typeof d.date!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(d.date)||d.date<=previous||d.date<localDate(generated))return null;
  const start=stamp(d.fromAt),end=stamp(d.throughAt);
  if(start===null||end===null||start<generated||end<=start||end-start>25*3600000||localDate(start)!==d.date||localDate(end-1)!==d.date||localHour(end)!=='00:00:00'
   ||!['remaining','full_day'].includes(d.scope)||d.scope==='full_day'&&localHour(start)!=='00:00:00')return null;
  if(d.status==='unavailable'){
   if(d.potentialKwh!==null||d.uncalibratedPotentialKwh!==null||d.sourceSupport!==null||d.projectionSha256!==null||d.calibrationScope!=='none'||d.reason!=='incomplete_weather_or_geometry')return null;
  }else{
   if(d.status!=='available'||![d.potentialKwh,d.uncalibratedPotentialKwh].every(n=>typeof n==='number'&&Number.isFinite(n)&&n>=0&&n<=1000)
    ||!hash(d.projectionSha256)||!['none','native_components_only','mixed_native_and_raw_fallback','raw_total_only_fallback'].includes(d.calibrationScope)
    ||![null,'registered_model_expired','registered_model_not_yet_available','registered_solar_grid_unavailable'].includes(d.reason))return null;
   const support=d.sourceSupport;
   if(!shape(support,['native_hours','fallback_hours','fallback_reasons'])||![support.native_hours,support.fallback_hours].every(n=>Number.isSafeInteger(n)&&n>=0&&n<=26)
    ||!support.fallback_reasons||typeof support.fallback_reasons!=='object'||Array.isArray(support.fallback_reasons)
    ||Object.entries(support.fallback_reasons).some(([k,n])=>!/^[a-z_]{1,95}$/.test(k)||!Number.isSafeInteger(n)||n<=0||n>26)
    ||Object.values(support.fallback_reasons).reduce((a,b)=>a+b,0)!==support.fallback_hours||support.native_hours+support.fallback_hours>26)return null;
   const adjusted=['native_components_only','mixed_native_and_raw_fallback'].includes(d.calibrationScope);
   if(adjusted?(c.mode!=='experimental_production'||d.reason!==null):d.uncalibratedPotentialKwh!==d.potentialKwh)return null;
   if(d.calibrationScope==='native_components_only'&&support.fallback_hours!==0||d.calibrationScope==='raw_total_only_fallback'&&support.native_hours!==0)return null;
   active ||=adjusted;
  }
  previous=d.date;
 }
 if(active!==(c.mode==='experimental_production'))return null;
 return v;
}
