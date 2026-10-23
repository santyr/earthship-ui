/** Fixed supplemental contract. No local calibration follows from a raw range. */
import {parseAtmosphericGroup} from './atmosphericForecast.js';
import {uniqueObjectKeys} from '../household/observation.js';
export const MAX_CAPABILITY_BYTES=256*1024;
export const CAPABILITY_LABEL='WeatherNext p10–p90; local coverage not yet verified';
const HOUR=3600000, HASH=/^[a-f0-9]{64}$/;
const unavailable=()=>({state:'unavailable',hours:[],sources:[],reportSha256:null});
const exact=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join('|')===[...keys].sort().join('|');
const finite=value=>typeof value==='number'&&Number.isFinite(value);
function clock(value){return typeof value==='string'&&value.length<=64&&/^\d{4}-\d\d-\d\dT/.test(value)&&/(?:Z|[+-]\d\d:\d\d)$/.test(value)?Date.parse(value):NaN;}
const f=value=>value===null?null:value*1.8+32;
export function parseWeatherCapabilities(raw,{nowMs=Date.now()}={}){
 try{
  if(typeof raw!=='string'||new TextEncoder().encode(raw).length>MAX_CAPABILITY_BYTES||!Number.isFinite(nowMs))return unavailable();
  const p=JSON.parse(raw);uniqueObjectKeys(raw);
  const v2=p?.schema==='earthship-weathernext-capabilities/v2';
  if(!exact(p,['schema','provider','generated_at','valid_until','timezone','status','sources','groups','automatic_actuation','release_authorized','report_sha256'])||(!v2&&p.schema!=='earthship-weathernext-capabilities/v1')||p.provider!=='weathernext3'||p.automatic_actuation!==false||p.release_authorized!==false||!HASH.test(p.report_sha256))return unavailable();
  const generated=clock(p.generated_at),until=clock(p.valid_until);
  if(!Number.isFinite(generated)||!Number.isFinite(until)||generated>nowMs+5000||nowMs>=until||until<=generated||until>generated+90*60000)return unavailable();
  if(typeof p.timezone!=='string')return unavailable();new Intl.DateTimeFormat('en-US',{timeZone:p.timezone});
  if(!Array.isArray(p.sources)||p.sources.length>16||!exact(p.groups,v2?['temperature','atmosphere']:['temperature']))return unavailable();
  const sources=new Map();
  for(const source of p.sources){
   if(!exact(source,['snapshot_sha256','profile_sha256','run_id','initialized_at','first_seen_at','available_at','grid_sha256'])||![source.snapshot_sha256,source.profile_sha256,source.grid_sha256].every(x=>typeof x==='string'&&HASH.test(x)))return unavailable();
   const init=clock(source.initialized_at),seen=clock(source.first_seen_at),available=clock(source.available_at);
   if(![init,seen,available].every(Number.isFinite)||!(init<=seen&&seen<=available&&available<=generated&&generated<=init+24*HOUR)||typeof source.run_id!=='string'||source.run_id.length>128||sources.has(source.snapshot_sha256))return unavailable();
   if(until>init+24*HOUR)return unavailable();
   const run=source.run_id;
   const nativeRun=/^(\d{4})(\d{2})(\d{2})_(\d{2})hr_\d{2}_preds$/.exec(run);
   const runInit=run.startsWith('ee:')?clock(run.slice(3)):nativeRun?Date.parse(`${nativeRun[1]}-${nativeRun[2]}-${nativeRun[3]}T${nativeRun[4]}:00:00Z`):NaN;
   if(runInit!==init)return unavailable();
   sources.set(source.snapshot_sha256,source);
  }
  const t=p.groups.temperature;
  if(!exact(t,['method','label','nominal_interval_probability','local_coverage_qualified','hours'])||t.method!=='raw-native-statistics/v1'||t.label!==CAPABILITY_LABEL||t.nominal_interval_probability!==.8||t.local_coverage_qualified!==false||!Array.isArray(t.hours)||t.hours.length>337)return unavailable();
  let prior=-Infinity;const used=new Set();const hours=[];
  for(const h of t.hours){
   if(!exact(h,['valid_at','source_sha256','mean_c','p10_c','p25_c','p50_c','p75_c','p90_c','range_status'])||!sources.has(h.source_sha256)||!finite(h.mean_c))return unavailable();
   const at=clock(h.valid_at),source=sources.get(h.source_sha256);
   if(!Number.isFinite(at)||at<=generated||at<=prior||at>clock(source.initialized_at)+360*HOUR)return unavailable();prior=at;used.add(h.source_sha256);
   let previous=-Infinity;
   for(const key of ['p10_c','p25_c','p50_c','p75_c','p90_c']){const value=h[key];if(value===null)continue;if(!finite(value)||value<previous-1e-9)return unavailable();previous=value;}
   const range=h.p10_c!==null&&h.p90_c!==null;
   if(!['available','missing_quantiles','crossing_quantiles'].includes(h.range_status)||(h.range_status==='available')!==range||h.range_status==='crossing_quantiles'&&['p10_c','p25_c','p50_c','p75_c','p90_c'].some(k=>h[k]!==null))return unavailable();
   hours.push({at:h.valid_at,atMs:at,meanF:f(h.mean_c),p10F:f(h.p10_c),p25F:f(h.p25_c),p50F:f(h.p50_c),p75F:f(h.p75_c),p90F:f(h.p90_c),spreadF:range?(h.p90_c-h.p10_c)*1.8:null,rangeStatus:h.range_status,source});
  }
  const atmosphere=v2?parseAtmosphericGroup(p.groups.atmosphere,{generatedMs:generated,validUntilMs:until,nowMs}):null;
  const declaredAvailable=hours.length>0||(v2&&p.groups.atmosphere.hours.length>0);
  if(used.size!==sources.size||p.status!==(declaredAvailable?'available':'unavailable')||!hours.length&&atmosphere?.state!=='ready')return unavailable();
  return {state:'ready',hours,sources:[...sources.values()],reportSha256:p.report_sha256,generatedAt:p.generated_at,validUntil:p.valid_until,label:CAPABILITY_LABEL,localCoverageQualified:false,...(v2?{atmosphere}:{})};
 }catch{return unavailable();}
}
export function temperatureCapabilityAt(product,at){return product?.state==='ready'?product.hours.find(h=>h.atMs===clock(at))??null:null;}
