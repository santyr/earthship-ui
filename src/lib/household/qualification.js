/** Original-plan evidence supports a separate per-intent release review. */
export const QUALIFICATION_GATES = [
  ['deterministic_replay','Deterministic replay'],['evidence_contracts','Source contracts'],
  ['hard_constraints','Hard constraints'],['unknown_fails_closed','Unknown inputs block action'],
  ['independent_windows','Independent outcome windows'],['input_stability','Input sensitivity'],
  ['model_error_uncertainty','Model error in uncertainty'],['baseline_comparison','Deterministic baseline skill'],
  ['reason_codes','Operator explanation'],['no_planner_rollback','Return to shadow mode'],
  ['no_provider_write_path','Protected write-path audit'],['owner_safety_recheck','Live owner safety checks'],
];
// Retained v1 reports and chronology keep their original identity catalog.
export const QUALIFICATION_FAMILIES = [
  ['RUN_GREYWATER_CYCLE','greywater-request-v1','Greywater cycle'],['RUN_FEEDER_CYCLE','feeder-request-v1','Feeder cycle'],
  ['SET_NIGHT_LOAD_OVERRIDE','night-load-owner-v1','Night-load override'],['SET_NIGHT_LOAD_DEVICE','night-load-owner-v1','Night-load device'],
];
// Feeder remains available only through manual and Lightning-payment owners.
export const AUTOMATED_QUALIFICATION_FAMILIES = QUALIFICATION_FAMILIES.filter(([kind])=>kind!=='RUN_FEEDER_CYCLE');
const MISSING = ['intent_windows_not_qualified','input_sensitivity_not_qualified','action_model_error_not_qualified',
  'policy_performance_not_qualified','operator_interpretation_not_qualified','separate_release_rollback_not_qualified',
  'protected_write_audit_not_bound','owner_physical_safety_not_qualified'];
const shape=(v,fields)=>v!==null&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===fields.length&&fields.every(k=>Object.hasOwn(v,k));
export function parseQualification(report,view){
 if(!shape(report,['schema','scope','status','receipt_sha256','snapshot_id','decision_at','release_authorized','automatic_actuation','families'])
  ||!['earthship-household-intent-qualification/v1','earthship-household-intent-qualification/v2','earthship-household-intent-qualification/v3'].includes(report.schema)||report.scope!=='original_plan_evidence'||report.status!=='not_qualified'
  ||report.release_authorized!==false||report.automatic_actuation!==false||report.receipt_sha256!==view.receipt_sha256
  ||report.snapshot_id!==view.snapshot_id||report.decision_at!==view.decision_at||!Array.isArray(report.families))return null;
 const families=report.schema==='earthship-household-intent-qualification/v3'?QUALIFICATION_FAMILIES.filter(([kind])=>kind==='SET_NIGHT_LOAD_DEVICE'):report.schema==='earthship-household-intent-qualification/v1'?QUALIFICATION_FAMILIES:AUTOMATED_QUALIFICATION_FAMILIES;
 if(report.families.length!==families.length)return null;
 for(let i=0;i<families.length;i++){
  const f=report.families[i],[type,capability]=families[i];
  if(!shape(f,['intent_type','capability_id','owner','proposal_count','status','release_authorized','gates'])||f.intent_type!==type
   ||f.capability_id!==capability||f.status!=='not_qualified'||f.release_authorized!==false
   ||!(f.owner===null||(typeof f.owner==='string'&&/^[A-Za-z0-9_]{1,64}$/.test(f.owner)))
   ||!Array.isArray(f.gates)||f.gates.length!==12)return null;
  const proposals=view.proposals.filter(p=>p.type===type),unknown=proposals.some(p=>p.hard_checks.some(c=>c.status==='unknown'));
  if(!Number.isInteger(f.proposal_count)||f.proposal_count!==proposals.length)return null;
  const expected=[['observed','original_plan_replayed'],
   [f.owner===null?'unavailable':'observed',f.owner===null?'registered_capability_unavailable':'original_source_contracts_replayed'],
   [proposals.length?'observed':'unavailable',proposals.length?'original_family_checks_replayed':'no_family_proposal'],
   [unknown?'observed':'unavailable',unknown?'unknown_checks_blocked_in_original':'unknown_case_not_observed'],
   ...MISSING.map(reason=>['unavailable',reason])];
  for(let j=0;j<12;j++){
   const g=f.gates[j];if(!shape(g,['id','evidence_status','reason'])||g.id!==QUALIFICATION_GATES[j][0]
    ||g.evidence_status!==expected[j][0]||g.reason!==expected[j][1])return null;
  }
 }
 return report;
}
