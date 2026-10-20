import { uniqueObjectKeys } from './observation.js';
import { parseSourceTimestamp } from '../openhab/timestamp.js';
const fields = 'schema generated_at issued_at valid_until receipt_sha256 original_energy_receipt_sha256 calibration_model_sha256 view_sha256 status reason raw_potential_kwh calibrated_potential_kwh load_status load_model_sha256 load_trained_through load_training_cutoff load_total_ac_kwh profiled_storage_status profiled_storage_reason profiled_captured_pv_kwh raw_profiled_captured_pv_kwh initial_soc_pct nominal_bank_kwh trajectory source_freshness_basis confidence physical_calibration_qualified automatic_actuation'.split(' ');
const pointFields = 'at mean_ac_w minimum_support_days training_spread_ac_w calibrated_soc_pct raw_soc_pct'.split(' ');
const shape=(v, keys)=>v && typeof v==='object' && !Array.isArray(v) && Object.keys(v).length===keys.length && keys.every(k=>Object.hasOwn(v,k));
const num=(v,lo,hi)=>typeof v==='number' && Number.isFinite(v) && lo<=v && v<=hi;
const digest=v=>typeof v==='string' && /^[a-f0-9]{64}$/.test(v);
const time=v=>typeof v==='string' && v.length<=64 && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v)?parseSourceTimestamp(v,Number.MAX_SAFE_INTEGER):null;
const reason=v=>v===null || typeof v==='string' && /^[a-z][a-z0-9_]{0,95}$/.test(v);
export function parseCalibratedEnergy(raw,{nowMs=Date.now()}={}) {
 try {
  if(typeof raw!=='string' || new TextEncoder().encode(raw).length>32768 || !Number.isFinite(nowMs))return null;
  uniqueObjectKeys(raw);const v=JSON.parse(raw);
  if(!shape(v,fields) || v.schema!=='earthship-household-calibrated-energy-observation/v2' || ['receipt_sha256','original_energy_receipt_sha256','calibration_model_sha256','view_sha256'].some(k=>!digest(v[k]))
    || v.automatic_actuation!==false || v.physical_calibration_qualified!==false || v.confidence!=='provisional_empirical_short_horizon'
    || v.source_freshness_basis!=='qualified_original_issue_with_120_second_publication_deadline' || !reason(v.reason) || !reason(v.profiled_storage_reason))return null;
  const issue=time(v.issued_at),generated=time(v.generated_at),until=time(v.valid_until);
  if(issue===null || generated===null || until===null || generated<issue || generated>nowMs || generated-issue>120000 || until-issue!==15*60000)return null;
  const projected=v.status==='projected_provisional_calibrated_potential';
  if(!projected && v.status!=='unavailable' || projected && (v.reason!==null || !num(v.raw_potential_kwh,0,2000) || !num(v.calibrated_potential_kwh,0,2000)))return null;
  if(!projected && [v.raw_potential_kwh,v.calibrated_potential_kwh].some(n=>n!==null && !num(n,0,2000)))return null;
  const load=v.load_status==='projected',storage=v.profiled_storage_status==='conditional_nominal_simulation';
  if(!load && v.load_status!=='unavailable' || !storage && v.profiled_storage_status!=='unavailable' || !Array.isArray(v.trajectory) || v.trajectory.length!==(load?24:0))return null;
  if(v.load_model_sha256!==null && (!digest(v.load_model_sha256) || time(v.load_trained_through)===null || time(v.load_training_cutoff)===null || time(v.load_trained_through)>time(v.load_training_cutoff) || time(v.load_training_cutoff)>issue))return null;
  if(v.load_model_sha256===null && (v.load_trained_through!==null || v.load_training_cutoff!==null))return null;
  if(load && (v.load_model_sha256===null || !num(v.load_total_ac_kwh,0,480)) || !load && v.load_total_ac_kwh!==null)return null;
  if(storage && (!load || !projected || v.profiled_storage_reason!==null || !num(v.initial_soc_pct,0,100) || !num(v.nominal_bank_kwh,.001,10000)
    || !num(v.profiled_captured_pv_kwh,0,v.calibrated_potential_kwh+1e-7) || !num(v.raw_profiled_captured_pv_kwh,0,v.raw_potential_kwh+1e-7)))return null;
  if(!storage && ['initial_soc_pct','nominal_bank_kwh','profiled_captured_pv_kwh','raw_profiled_captured_pv_kwh'].some(k=>v[k]!==null))return null;
  let total=0;
  for(const [i,row] of v.trajectory.entries()) {
   if(!shape(row,pointFields) || time(row.at)!==issue+(i+1)*3600000 || !num(row.mean_ac_w,0,20000) || !Number.isInteger(row.minimum_support_days) || row.minimum_support_days<3 || row.minimum_support_days>14
    || !Array.isArray(row.training_spread_ac_w) || row.training_spread_ac_w.length!==2 || row.training_spread_ac_w.some(n=>!num(n,0,20000)) || row.training_spread_ac_w[0]>row.mean_ac_w || row.training_spread_ac_w[1]<row.mean_ac_w)return null;
   if(['calibrated_soc_pct','raw_soc_pct'].some(k=>storage?!num(row[k],0,100):row[k]!==null))return null;
   total+=row.mean_ac_w/1000;
  }
  if(load && Math.abs(total-v.load_total_ac_kwh)>1e-7*Math.max(1,total))return null;
  return {...v,expired:nowMs>=until};
 } catch {return null;}
}
