/** Curated prospective counts only; no qualification or command interpretation. */
import {OBSERVATION_MAX_BYTES,uniqueObjectKeys} from './observation.js';
import {QUALIFICATION_FAMILIES} from './qualification.js';
import {parseSourceTimestamp} from '../openhab/timestamp.js';
const TYPES=QUALIFICATION_FAMILIES.map(r=>r[0]);
const COUNT_FIELDS='raw_decisions origin_days non_overlapping_windows planner_available decisions_with_unavailable_sources proposals selected hard_blocked unknown_blocked'.split(' ');
const FIELDS='schema generated_at valid_until window_start window_days timezone sampling_basis counts families policy_comparisons first_decision_at last_decision_at last_receipt_sha256 retained_set_sha256 version_groups missing_evidence statistical_independence_assessed release_authorized automatic_actuation report_sha256'.split(' ');
const MISSING=['statistical_independence','action_effects','baseline_performance','owner_safety','objective_decomposition'];
const shape=(v,keys)=>v!==null&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const digest=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const count=v=>Number.isInteger(v)&&v>=0&&v<=32768;
const time=v=>typeof v==='string'&&v.length<=64&&/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v)?parseSourceTimestamp(v,Number.MAX_SAFE_INTEGER):null;
function counts(v,family=false){
 if(!shape(v,COUNT_FIELDS)||!Object.values(v).every(count)||v.raw_decisions>4096||v.origin_days>Math.min(8,v.raw_decisions)
  ||v.non_overlapping_windows>Math.min(29,v.raw_decisions)||v.planner_available>v.raw_decisions
  ||v.decisions_with_unavailable_sources>v.raw_decisions||v.proposals>8*v.raw_decisions
  ||v.selected+v.hard_blocked>v.proposals||v.unknown_blocked>v.hard_blocked)return false;
 if(!v.raw_decisions)return Object.values(v).every(n=>n===0);
 return v.origin_days>0&&v.non_overlapping_windows>0&&(!family||v.proposals>=v.raw_decisions);
}
function families(v,total){
 if(!shape(v,TYPES)||!TYPES.every(k=>counts(v[k],true)&&v[k].raw_decisions<=total.raw_decisions
  &&v[k].origin_days<=total.origin_days&&v[k].planner_available<=total.planner_available
  &&v[k].decisions_with_unavailable_sources<=total.decisions_with_unavailable_sources))return false;
 return ['proposals','selected','hard_blocked','unknown_blocked'].every(k=>TYPES.reduce((s,t)=>s+v[t][k],0)===total[k]);
}
function versions(v){
 if(!shape(v,['planner_version','runtime_sha256','registry_sha256','config_sha256','models'])
  ||typeof v.planner_version!=='string'||!/^[a-z][a-z0-9_]{0,63}$/.test(v.planner_version)
  ||!['runtime_sha256','registry_sha256','config_sha256'].every(k=>digest(v[k]))
  ||!Array.isArray(v.models)||v.models.length>2||new Set(v.models.map(m=>m?.domain)).size!==v.models.length)return false;
 return v.models.every(m=>shape(m,['domain','artifact_sha256','runtime_sha256'])&&['energy','thermal'].includes(m.domain)
  &&['artifact_sha256','runtime_sha256'].every(k=>m[k]===null||digest(m[k])));
}
export function parseChronologicalSummary(raw,{nowMs=Date.now()}={}){
 if(typeof raw!=='string'||new TextEncoder().encode(raw).length>OBSERVATION_MAX_BYTES||!Number.isFinite(nowMs))return null;
 try{
  const r=JSON.parse(raw);uniqueObjectKeys(raw);
  if(!shape(r,FIELDS)||r.schema!=='earthship-household-chronological-summary/v1'||r.window_days!==7
   ||r.timezone!=='America/Denver'||r.sampling_basis!=='distinct_original_replayed_plans'
   ||['statistical_independence_assessed','release_authorized','automatic_actuation'].some(k=>r[k]!==false)
   ||!digest(r.report_sha256)||!digest(r.retained_set_sha256)||JSON.stringify(r.missing_evidence)!==JSON.stringify(MISSING)
   ||!counts(r.counts)||!families(r.families,r.counts))return null;
  const generated=time(r.generated_at),until=time(r.valid_until),start=time(r.window_start);
  if([generated,until,start].includes(null)||generated>nowMs||until-generated!==15*60000||generated-start!==7*86400000)return null;
  if(!r.counts.raw_decisions){if(r.first_decision_at!==null||r.last_decision_at!==null||r.last_receipt_sha256!==null)return null;}
  else{const first=time(r.first_decision_at),last=time(r.last_decision_at);
   if(first===null||last===null||first<start||first>last||last>generated||!digest(r.last_receipt_sha256))return null;
  }
  if(!shape(r.policy_comparisons,['matching_block','different_gate_result','unknown'])
   ||!Object.values(r.policy_comparisons).every(count)
   ||Object.values(r.policy_comparisons).reduce((a,b)=>a+b,0)>r.families.RUN_GREYWATER_CYCLE.proposals
   ||!Array.isArray(r.version_groups)||r.version_groups.length>16||new Set(r.version_groups.map(g=>g?.version_id)).size!==r.version_groups.length)return null;
  for(const g of r.version_groups){
   if(!shape(g,['version_id','versions','counts','families'])||!digest(g.version_id)||!versions(g.versions)
    ||!counts(g.counts)||!g.counts.raw_decisions||!families(g.families,g.counts))return null;
  }
  for(const kind of [null,...TYPES])for(const key of COUNT_FIELDS){
   const total=(kind===null?r.counts:r.families[kind])[key];
   const values=r.version_groups.map(g=>(kind===null?g.counts:g.families[kind])[key]);
   const sum=values.reduce((a,b)=>a+b,0),max=Math.max(0,...values);
   if(['origin_days','non_overlapping_windows'].includes(key)){if(total<max||total>sum)return null;}
   else if(total!==sum)return null;
  }
  return {...r,expired:nowMs>=until};
 }catch{return null;}
}
