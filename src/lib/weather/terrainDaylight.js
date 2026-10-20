import {HOUSEHOLD_TIMEZONE} from '../site.js';
import {parseSourceTimestamp} from '../openhab/timestamp.js';
import {splitRoundedMinutes} from '../openhab/values.js';
import {localDateAt} from './forecastDetail.js';
const fields='schema method day timezone calculatedAt dayStartAt validUntil geometryAvailableAt geometrySha256 horizonSha256 sourceRuntimeSha256 daySeconds terrainSunlightSeconds unobstructedSunlightSeconds firstSunAt lastSunAt resolutionSeconds confidence physical_calibration_qualified automatic_actuation'.split(' ');
const HASH=/^[a-f0-9]{64}$/;
const stamp=value=>parseSourceTimestamp(value,8640000000000000);
function midnight(at,day){
 const parts=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:HOUSEHOLD_TIMEZONE,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(at).map(p=>[p.type,p.value]));
 return `${parts.year}-${parts.month}-${parts.day}`===day&&parts.hour==='00'&&parts.minute==='00'&&parts.second==='00';
}
export function parseTerrainDaylight(raw,{nowMs=Date.now()}={}){
 try{
  if(typeof raw!=='string'||new TextEncoder().encode(raw).length>16384||!Number.isFinite(nowMs))return null;
  const v=JSON.parse(raw);
  if(!v||Array.isArray(v)||Object.keys(v).length!==fields.length||!fields.every(k=>Object.hasOwn(v,k))
   ||v.schema!=='earthship-terrain-daylight/v1'||v.method!=='native-five-minute-terrain-endpoint-mask/v1'
   ||v.timezone!==HOUSEHOLD_TIMEZONE||v.day!==localDateAt(nowMs,HOUSEHOLD_TIMEZONE)
   ||v.confidence!=='unvalidated_map_estimate'||v.physical_calibration_qualified!==false||v.automatic_actuation!==false||v.resolutionSeconds!==300
   ||!['geometrySha256','horizonSha256','sourceRuntimeSha256'].every(k=>typeof v[k]==='string'&&HASH.test(v[k])))return null;
  const start=stamp(v.dayStartAt),end=stamp(v.validUntil),calculated=stamp(v.calculatedAt),available=stamp(v.geometryAvailableAt);
  const next=new Date(Date.parse(v.day+'T12:00:00Z')+86400000).toISOString().slice(0,10);
  if([start,end,calculated,available].includes(null)||!midnight(start,v.day)||!midnight(end,next)
   ||!(start<=calculated&&calculated<=nowMs&&nowMs<end&&available<=calculated)
   ||![82800,86400,90000].includes(v.daySeconds)||v.daySeconds!==(end-start)/1000
   ||!['terrainSunlightSeconds','unobstructedSunlightSeconds'].every(k=>Number.isInteger(v[k])&&v[k]>=0&&v[k]%300===0)
   ||v.terrainSunlightSeconds>v.unobstructedSunlightSeconds||v.unobstructedSunlightSeconds>v.daySeconds)return null;
  if(v.terrainSunlightSeconds===0){if(v.firstSunAt!==null||v.lastSunAt!==null)return null;}
  else{
   const first=stamp(v.firstSunAt),last=stamp(v.lastSunAt);
   if(first===null||last===null||first<start||last>end||first>=last||(last-first)/1000<v.terrainSunlightSeconds||(first-start)%300000||(last-start)%300000)return null;
  }
  return Object.freeze(v);
 }catch{return null;}
}
export function terrainDaylightText(report){
 if(!report)return '—';const {hours,minutes}=splitRoundedMinutes(report.terrainSunlightSeconds/60);return `~${hours}h ${minutes}m`;
}
