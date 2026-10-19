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
  if(!shape(v,['schema','provider','generatedAt','validUntil','timezone','weatherSha256','geometrySha256','systemSha256','horizonSha256','confidence','automatic_actuation','physical_calibration_qualified','days'])
    ||v.schema!=='earthship-daily-pv-potential/v1'||v.provider!=='weathernext3'||v.timezone!==HOUSEHOLD_TIMEZONE
    ||v.confidence!=='provisional_uncalibrated'||v.automatic_actuation!==false||v.physical_calibration_qualified!==false
    ||!['weatherSha256','geometrySha256','systemSha256','horizonSha256'].every(k=>hash(v[k])))return null;
  const generated=stamp(v.generatedAt),until=stamp(v.validUntil);
  if(generated===null||until===null||generated>nowMs||until-generated!==90*60000||nowMs>=until
    ||!Array.isArray(v.days)||v.days.length<1||v.days.length>10)return null;
  let previous='';
  for(const d of v.days){
   if(!shape(d,['date','status','reason','potentialKwh','fromAt','throughAt','scope'])||typeof d.date!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(d.date)||d.date<=previous||d.date<localDate(generated))return null;
   const start=stamp(d.fromAt),end=stamp(d.throughAt);
   if(start===null||end===null||start<generated||end<=start||end-start>25*3600000||localDate(start)!==d.date||localDate(end-1)!==d.date||localHour(end)!=='00:00:00')return null;
   if(!['remaining','full_day'].includes(d.scope)||d.scope==='full_day'&&localHour(start)!=='00:00:00')return null;
   if(d.status==='available'){
    if(d.reason!==null||typeof d.potentialKwh!=='number'||!Number.isFinite(d.potentialKwh)||d.potentialKwh<0||d.potentialKwh>1000)return null;
   }else if(d.status!=='unavailable'||d.potentialKwh!==null||typeof d.reason!=='string'||!/^[a-z_]{1,95}$/.test(d.reason))return null;
   previous=d.date;
  }
  return v;
 }catch{return null;}
}
export function dailyPvForDate(view,date){return view?.days.find(d=>d.date===date&&d.status==='available')??null;}
