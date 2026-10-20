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
  const calibrated=v?.schema==='earthship-daily-pv-potential/v2';
  if(!shape(v,['schema','provider','generatedAt','validUntil','timezone','weatherSha256','geometrySha256','systemSha256','horizonSha256','confidence','automatic_actuation','physical_calibration_qualified','days',...(calibrated?['calibration']:[])])
    ||(!calibrated&&v.schema!=='earthship-daily-pv-potential/v1')||v.provider!=='weathernext3'||v.timezone!==HOUSEHOLD_TIMEZONE
    ||v.confidence!==(calibrated?'provisional_empirical_short_horizon':'provisional_uncalibrated')||v.automatic_actuation!==false||v.physical_calibration_qualified!==false
    ||!['weatherSha256','geometrySha256','systemSha256','horizonSha256'].every(k=>hash(v[k])))return null;
  const generated=stamp(v.generatedAt),until=stamp(v.validUntil);
  if(generated===null||until===null||generated>nowMs||until-generated!==90*60000||nowMs>=until
    ||!Array.isArray(v.days)||v.days.length<1||v.days.length>10)return null;
  if(calibrated){
   const c=v.calibration;
   if(!shape(c,['modelSha256','trainingThrough','assessedThrough','applyThroughAt','independentTargetDays','baselineMaeW','candidateMaeW','qualification'])
     ||!hash(c.modelSha256)||stamp(c.trainingThrough)===null||stamp(c.assessedThrough)===null
     ||stamp(c.trainingThrough)>generated||stamp(c.assessedThrough)>generated||stamp(c.applyThroughAt)!==generated+24*3600000
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
    if(!['none','mixed','empirical_short_horizon'].includes(d.calibrationScope))return null;
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
