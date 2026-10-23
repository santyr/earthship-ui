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
  const component=v.schema==='earthship-household-calibrated-energy-observation/v4';
  const policy=component||v.schema==='earthship-household-calibrated-energy-observation/v3';
  if(!shape(v,[...fields,...(policy?['calibration_policy_sha256']:[]),...(component?'calibration_sha256 procedure_sha256 baseline_rule calibration_scope calibration_mode source_support cohort_id measurement_cohort_sha256'.split(' '):[])]) || (!policy&&v.schema!=='earthship-household-calibrated-energy-observation/v2') || policy&&!digest(v.calibration_policy_sha256) || ['receipt_sha256','original_energy_receipt_sha256','calibration_model_sha256','view_sha256'].some(k=>!digest(v[k]))
    || v.automatic_actuation!==false || v.physical_calibration_qualified!==false || v.confidence!==(component?'experimental_native_component_model':'provisional_empirical_short_horizon')
    || v.source_freshness_basis!==(component?'qualified_original_issue_with_85_second_publication_deadline':'qualified_original_issue_with_120_second_publication_deadline') || !reason(v.reason) || !reason(v.profiled_storage_reason))return null;
  const issue=time(v.issued_at),generated=time(v.generated_at),until=time(v.valid_until);
  if(issue===null || generated===null || until===null || generated<issue || generated>nowMs || generated-issue>(component?85000:120000) || until-issue!==15*60000)return null;
  if(component){
   const support=v.source_support;
   if(!['calibration_sha256','procedure_sha256','cohort_id','measurement_cohort_sha256'].every(k=>digest(v[k]))
    ||v.baseline_rule!=='native_fdir_ssrd_isotropic_faiman_proxy_pvwatts_dc_v2'
    ||!['none','native_components_only','mixed_native_and_raw_fallback','raw_total_only_fallback'].includes(v.calibration_scope)
    ||!['experimental_production','raw_component_fallback'].includes(v.calibration_mode)
    ||!shape(support,['native_hours','fallback_hours','fallback_reasons'])
    ||![support.native_hours,support.fallback_hours].every(n=>Number.isSafeInteger(n)&&n>=0&&n<=26)
    ||!support.fallback_reasons||typeof support.fallback_reasons!=='object'||Array.isArray(support.fallback_reasons)
    ||Object.entries(support.fallback_reasons).some(([k,n])=>!/^[a-z_]{1,95}$/.test(k)||!Number.isSafeInteger(n)||n<=0||n>26)
    ||Object.values(support.fallback_reasons).reduce((a,b)=>a+b,0)!==support.fallback_hours||support.native_hours+support.fallback_hours>26
    ||v.calibration_scope==='native_components_only'&&support.fallback_hours!==0
    ||v.calibration_scope==='raw_total_only_fallback'&&support.native_hours!==0)return null;
   const adjusted=['native_components_only','mixed_native_and_raw_fallback'].includes(v.calibration_scope);
   if(adjusted?v.calibration_mode!=='experimental_production':v.calibration_mode!=='raw_component_fallback'||v.raw_potential_kwh!==v.calibrated_potential_kwh)return null;
  }
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

const performanceFields='schema generated_at valid_until cohort_id calibration_model_sha256 model_version_count independent_origin_days first_issue last_issue by_horizon physical_calibration_qualified causal_benefit_qualified graduated automatic_actuation view_sha256'.split(' ');
const count=v=>Number.isInteger(v)&&v>=0&&v<=512;
export function parseCalibratedPerformance(raw,{nowMs=Date.now()}={}) {
 try {
  if(typeof raw!=='string'||new TextEncoder().encode(raw).length>32768||!Number.isFinite(nowMs))return null;
  uniqueObjectKeys(raw);const v=JSON.parse(raw);
  const component=v.schema==='earthship-household-calibrated-energy-performance/v3';
  const policy=component||v.schema==='earthship-household-calibrated-energy-performance/v2';
  if(!shape(v,[...performanceFields,...(policy?['calibration_policy_sha256']:[]),...(component?['procedure_sha256','baseline_rule','measurement_cohort_sha256']:[])])||(!policy&&v.schema!=='earthship-household-calibrated-energy-performance/v1')||policy&&!digest(v.calibration_policy_sha256)||['cohort_id','calibration_model_sha256','view_sha256'].some(k=>!digest(v[k]))
    ||['physical_calibration_qualified','causal_benefit_qualified','graduated','automatic_actuation'].some(k=>v[k]!==false)
    ||!count(v.model_version_count)||!Number.isInteger(v.independent_origin_days)||v.independent_origin_days<0||v.independent_origin_days>8)return null;
  if(component&&(!digest(v.procedure_sha256)||!digest(v.measurement_cohort_sha256)||v.baseline_rule!=='native_fdir_ssrd_isotropic_faiman_proxy_pvwatts_dc_v2'))return null;
  const generated=time(v.generated_at),until=time(v.valid_until),first=v.first_issue===null?null:time(v.first_issue),last=v.last_issue===null?null:time(v.last_issue);
  if(generated===null||until===null||generated>nowMs||until-generated!==3600000)return null;
  if(v.independent_origin_days===0?(v.first_issue!==null||v.last_issue!==null):(first===null||last===null||first>last||last>generated||generated-first>7*86400000))return null;
  if(!shape(v.by_horizon,['1','6','12','24']))return null;
  for(const row of Object.values(v.by_horizon)) {
   if(!shape(row,['soc','load'])||!shape(row.soc,['attempted_count','count','mae_soc_pct'])||!shape(row.load,['attempted_count','count','current_count','mae_kwh']))return null;
   const soc=row.soc,load=row.load;
   if(!count(soc.count)||!count(soc.attempted_count)||soc.count>soc.attempted_count||!count(load.count)||!count(load.attempted_count)||load.count>load.attempted_count||!count(load.current_count)||load.current_count>load.count||soc.attempted_count!==load.attempted_count)return null;
   if(!shape(soc.mae_soc_pct,['calibrated_pv','raw_pv','hold_soc'])||!shape(load.mae_kwh,['learned_ac','current_ac']))return null;
   if(Object.values(soc.mae_soc_pct).some(n=>soc.count?!num(n,0,100):n!==null)||
     (load.count?!num(load.mae_kwh.learned_ac,0,20):load.mae_kwh.learned_ac!==null)||
     (load.current_count?!num(load.mae_kwh.current_ac,0,20):load.mae_kwh.current_ac!==null))return null;
   if((soc.count||load.count)&&(!v.model_version_count||!v.independent_origin_days))return null;
  }
  return {...v,expired:nowMs>=until};
 } catch {return null;}
}
