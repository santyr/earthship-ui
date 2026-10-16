import {policyObservation} from './household-observation.js';
export function qualificationObservation(){
  const v=policyObservation();v.schema='earthship-household-observation/v3';
  const missing=[['independent_windows','intent_windows_not_qualified'],['input_stability','input_sensitivity_not_qualified'],
    ['model_error_uncertainty','action_model_error_not_qualified'],['baseline_comparison','policy_performance_not_qualified'],
    ['reason_codes','operator_interpretation_not_qualified'],['no_planner_rollback','separate_release_rollback_not_qualified'],
    ['no_provider_write_path','protected_write_audit_not_bound'],['owner_safety_recheck','owner_physical_safety_not_qualified']];
  const types=[['RUN_GREYWATER_CYCLE','greywater-request-v1','hex_southoutlet_cycle'],['RUN_FEEDER_CYCLE','feeder-request-v1','88bd9ec4de'],
    ['SET_NIGHT_LOAD_OVERRIDE','night-load-owner-v1','hex_night_load_override'],['SET_NIGHT_LOAD_DEVICE','night-load-owner-v1','hex_night_load_override']];
  v.qualification_report={schema:'earthship-household-intent-qualification/v1',scope:'original_plan_evidence',status:'not_qualified',
    receipt_sha256:v.receipt_sha256,snapshot_id:v.snapshot_id,decision_at:v.decision_at,release_authorized:false,automatic_actuation:false,
    families:types.map(([intent_type,capability_id,owner])=>({intent_type,capability_id,owner,proposal_count:intent_type==='RUN_GREYWATER_CYCLE'?1:0,
      status:'not_qualified',release_authorized:false,gates:[
        {id:'deterministic_replay',evidence_status:'observed',reason:'original_plan_replayed'},
        {id:'evidence_contracts',evidence_status:'observed',reason:'original_source_contracts_replayed'},
        {id:'hard_constraints',evidence_status:intent_type==='RUN_GREYWATER_CYCLE'?'observed':'unavailable',reason:intent_type==='RUN_GREYWATER_CYCLE'?'original_family_checks_replayed':'no_family_proposal'},
        {id:'unknown_fails_closed',evidence_status:intent_type==='RUN_GREYWATER_CYCLE'?'observed':'unavailable',reason:intent_type==='RUN_GREYWATER_CYCLE'?'unknown_checks_blocked_in_original':'unknown_case_not_observed'},
        ...missing.map(([id,reason])=>({id,evidence_status:'unavailable',reason})),
      ]}))};return v;
}
