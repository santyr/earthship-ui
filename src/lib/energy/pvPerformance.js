import { OBSERVATION_MAX_BYTES } from '../household/observation.js';
const rootFields=['schema','generated_at','valid_until','window_start','window_end','status','cohorts','omitted_cohort_count','scored_hours','unscored_hours','outcome_scope','metric_basis','prospective_score','physical_calibration_qualified','automatic_actuation','view_sha256'];
const counts=['eligible_bins','missing_forecast_bins','censored_bins','unqualified_bins','low_generation_bins','unknown_coverage_bins'];
const cohortFields=['cohort_id','model_sha256','calibration_policy_sha256','scoring_runtime_sha256','hour_count','adjusted_bins','covered_seconds','first_issue','last_issue','first_window_start','last_window_end','independent_target_days','baseline_mae_w','candidate_mae_w',...counts];
const componentCohortFields=cohortFields.filter(k=>k!=='independent_target_days').concat(['local_target_dates','procedure_sha256','measurement_cohort_sha256','solar_grid_sha256','baseline_rule','metric_population','target_timezone']);
const shape=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const stamp=v=>typeof v==='string'&&/(Z|[+-]\d\d:\d\d)$/.test(v)&&Number.isFinite(Date.parse(v))?Date.parse(v):null;
const integer=(v,max)=>Number.isSafeInteger(v)&&v>=0&&v<=max;
const number=(v,min,max)=>typeof v==='number'&&Number.isFinite(v)&&v>=min&&v<=max;
export function parsePvPerformance(raw,{nowMs=Date.now()}={}){
  try{
    const value=typeof raw==='string'?JSON.parse(raw):raw;
    if(!shape(value,rootFields)||new TextEncoder().encode(JSON.stringify(value)).length>OBSERVATION_MAX_BYTES||!['earthship-pv-potential-performance/v1','earthship-pv-potential-performance/v2'].includes(value.schema)
      ||value.outcome_scope!=='qualified_low_soc_charging_controller_input_proxy'||value.metric_basis!=='covered_duration_weighted_absolute_power_error'
      ||value.prospective_score!==true||value.physical_calibration_qualified!==false||value.automatic_actuation!==false||!hash(value.view_sha256))return null;
    const generated=stamp(value.generated_at),expires=stamp(value.valid_until),start=stamp(value.window_start),end=stamp(value.window_end);
    if([generated,expires,start,end].includes(null)||generated>nowMs||expires-generated!==2*3600000||end-start!==168*3600000||end%3600000!==0||end+300000>generated
      ||!Array.isArray(value.cohorts)||value.cohorts.length>16||!integer(value.omitted_cohort_count,168)||!integer(value.scored_hours,168)||!integer(value.unscored_hours,168)||value.scored_hours+value.unscored_hours!==168)return null;
    const component=value.schema==='earthship-pv-potential-performance/v2',dateKey=component?'local_target_dates':'independent_target_days';
    const seen=new Set();
    for(const c of value.cohorts){
      if(!shape(c,component?componentCohortFields:cohortFields)||['cohort_id','model_sha256','scoring_runtime_sha256'].some(k=>!hash(c[k]))||c.calibration_policy_sha256!==null&&!hash(c.calibration_policy_sha256)||seen.has(c.cohort_id))return null;
      if(component){
        const pins=['procedure_sha256','measurement_cohort_sha256','solar_grid_sha256'];
        if(c.metric_population==='constituent_five_minute_power_of_published_daily_totals'){
          if(pins.some(k=>!hash(c[k]))||!hash(c.calibration_policy_sha256)||c.baseline_rule!=='native_fdir_ssrd_isotropic_faiman_proxy_pvwatts_dc_v2')return null;
        }else if(c.metric_population!=='legacy_original_five_minute_power'||pins.some(k=>c[k]!==null)||c.baseline_rule!==null)return null;
        if(typeof c.target_timezone!=='string'||c.target_timezone.length>128)return null;
        new Intl.DateTimeFormat('en-US',{timeZone:c.target_timezone}).format(0);
      }
      seen.add(c.cohort_id);
      const first=stamp(c.first_window_start),last=stamp(c.last_window_end),issue=stamp(c.first_issue),lastIssue=stamp(c.last_issue);
      if([first,last,issue,lastIssue].includes(null)||first<start||last>end||first>=last||first%3600000||last%3600000||issue>first||lastIssue>=last||issue>lastIssue||lastIssue>generated
        ||!integer(c.hour_count,168)||c.hour_count<1||last-first<c.hour_count*3600000||counts.some(k=>!integer(c[k],2016))||counts.reduce((s,k)=>s+c[k],0)!==c.hour_count*12
        ||!integer(c.adjusted_bins,c.eligible_bins)||!integer(c[dateKey],8)||c[dateKey]>c.hour_count)return null;
      if(c.eligible_bins===0){if(c.covered_seconds!==0||c.baseline_mae_w!==null||c.candidate_mae_w!==null||c[dateKey]!==0)return null;}
      else if(!number(c.covered_seconds,285*c.eligible_bins,300*c.eligible_bins)||!number(c.baseline_mae_w,0,30000)||!number(c.candidate_mae_w,0,30000)||c[dateKey]<1)return null;
    }
    if(value.status!==(value.cohorts.some(c=>c.eligible_bins>0)?'scored':'collecting'))return null;
    return {...value,expired:nowMs>expires};
  }catch{return null;}
}
