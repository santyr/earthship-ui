// Hand-derived public contract: no runtime payload, paths or household values.
export const ADVICE_AT = Date.parse('2026-10-24T12:00:20Z');
export function separateAdvice({ shadow = false } = {}) {
  return {
    schema: 'earthship-household-observation/v4', receipt_sha256: '1'.repeat(64), snapshot_id: '2'.repeat(64),
    snapshot_as_of: '2026-10-24T12:00:00Z', decision_at: '2026-10-24T12:00:10Z',
    verified_at: '2026-10-24T12:00:20Z', valid_until: '2026-10-24T12:01:00Z',
    planner_mode: shadow ? 'shadow' : 'unavailable', planner_version: 'bounded_exhaustive_v1',
    authority: 'none', automatic_actuation: false, plan_status: 'input_incomplete',
    model_identities: shadow ? [{ domain: 'energy', artifact_sha256: null, runtime_sha256: null,
      projection_sha256: '3'.repeat(64), confidence: 'unavailable', qualification: 'not_assessed' }] : [],
    candidate_generation: { status: 'human_advice_separate', reason: null, input_qualification: 'not_assessed' },
    proposals: [], source_quality: [{ domain: 'energy', role: 'battery_soc', quality_at_issue: 'qualified',
      current_quality: 'qualified', reason: null, received_at: '2026-10-24T11:59:55Z', valid_until: '2026-10-24T12:01:00Z' }],
    confidence: 'unavailable', effects_qualified: false,
    policy_comparison: { schema: 'earthship-household-policy-block-comparison/v1', status: 'unavailable',
      reason: 'source_unavailable', owner: 'hex_southoutlet_cycle', owner_reason: null, owner_scheduling: null,
      evaluated_at: null, valid_until: null, source_sha256: null, rule_sha256: null, gate: null, comparisons: [],
      performance_status: 'unavailable', performance_reason: 'unqualified_effect', physical_permission: false, automatic_actuation: false },
    qualification_report: { schema: 'earthship-household-intent-qualification/v3', scope: 'original_plan_evidence',
      status: 'not_qualified', receipt_sha256: '1'.repeat(64), snapshot_id: '2'.repeat(64), decision_at: '2026-10-24T12:00:10Z',
      release_authorized: false, automatic_actuation: false, families: [] },
  };
}
// Complete command proposal used only to prove the advice profile cannot carry one.
export function commandProposal() {
  return { parameters: { device: 'dishwasher', command: 'OFF' }, created_at: '2026-10-24T12:00:10Z', expires_at: '2026-10-24T12:01:00Z',
    intent_id: '4'.repeat(64), type: 'SET_NIGHT_LOAD_DEVICE', selected: true, confidence: 'low', reasons: ['no_optional_action'],
    expected_effects: { batteryKwh: null, socPct: null, thermalF: null, water: null, wearCost: null },
    effect_units: { batteryKwh: 'kWh', socPct: 'percentage_points', thermalF: 'degF', water: 'litre', wearCost: 'normalized_cycle_cost' },
    decision_status: 'accepted', decision_reason: null, hard_checks: [] };
}

// Retained command-report catalogs are hand-derived from their original public
// contract. Accepting separate advice must not make malformed originals valid.
export function retainedCommandObservation(version) {
  const view = separateAdvice({ shadow: true });
  view.schema = 'earthship-household-observation/v3';
  view.candidate_generation.status = 'generated_shadow_only';
  view.qualification_report.schema = `earthship-household-intent-qualification/${version}`;
  const families = [['RUN_GREYWATER_CYCLE', 'greywater-request-v1'], ['RUN_FEEDER_CYCLE', 'feeder-request-v1'],
    ['SET_NIGHT_LOAD_OVERRIDE', 'night-load-owner-v1'], ['SET_NIGHT_LOAD_DEVICE', 'night-load-owner-v1']];
  const gates = [
    ['deterministic_replay', 'observed', 'original_plan_replayed'],
    ['evidence_contracts', 'unavailable', 'registered_capability_unavailable'],
    ['hard_constraints', 'unavailable', 'no_family_proposal'],
    ['unknown_fails_closed', 'unavailable', 'unknown_case_not_observed'],
    ['independent_windows', 'unavailable', 'intent_windows_not_qualified'],
    ['input_stability', 'unavailable', 'input_sensitivity_not_qualified'],
    ['model_error_uncertainty', 'unavailable', 'action_model_error_not_qualified'],
    ['baseline_comparison', 'unavailable', 'policy_performance_not_qualified'],
    ['reason_codes', 'unavailable', 'operator_interpretation_not_qualified'],
    ['no_planner_rollback', 'unavailable', 'separate_release_rollback_not_qualified'],
    ['no_provider_write_path', 'unavailable', 'protected_write_audit_not_bound'],
    ['owner_safety_recheck', 'unavailable', 'owner_physical_safety_not_qualified'],
  ];
  view.qualification_report.families = families.filter(([type]) => version === 'v1' || type !== 'RUN_FEEDER_CYCLE')
    .map(([intent_type, capability_id]) => ({ intent_type, capability_id, owner: null, proposal_count: 0,
      status: 'not_qualified', release_authorized: false,
      gates: gates.map(([id, evidence_status, reason]) => ({ id, evidence_status, reason })) }));
  return view;
}
