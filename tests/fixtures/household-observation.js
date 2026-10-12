export const AT = Date.parse('2026-10-12T03:00:35Z');
export function observation() {
  return {
    schema: 'earthship-household-observation/v1', receipt_sha256: 'a'.repeat(64), snapshot_id: 'b'.repeat(64),
    snapshot_as_of: '2026-10-12T03:00:15+00:00', decision_at: '2026-10-12T03:00:30+00:00',
    verified_at: '2026-10-12T03:00:35+00:00', valid_until: '2026-10-12T03:01:00+00:00',
    planner_mode: 'shadow', planner_version: 'bounded_exhaustive_v1', authority: 'none', automatic_actuation: false,
    plan_status: 'input_incomplete', model_identities: [{ domain: 'energy', artifact_sha256: null, runtime_sha256: null,
      projection_sha256: 'c'.repeat(64), confidence: 'unavailable', qualification: 'not_assessed' }],
    candidate_generation: { status: 'generated_shadow_only', reason: null, input_qualification: 'not_assessed' },
    proposals: [], source_quality: [{ domain: 'energy', role: 'battery_soc', quality_at_issue: 'qualified',
      current_quality: 'qualified', reason: null, received_at: '2026-10-12T03:00:10+00:00', valid_until: '2026-10-12T03:01:00+00:00' }],
    confidence: 'unavailable', effects_qualified: false, policy_comparison: { status: 'unavailable', reason: 'source_unavailable' },
  };
}
export function proposal() {
  return { intent_id: 'd'.repeat(64), type: 'RUN_FEEDER_CYCLE', selected: false, confidence: 'low',
    reasons: ['no_optional_action'], expected_effects: { batteryKwh: null, socPct: null, thermalF: null, water: null, wearCost: null },
    effect_units: { batteryKwh: 'kWh', socPct: 'percentage_points', thermalF: 'degF', water: 'litre', wearCost: 'normalized_cycle_cost' },
    decision_status: 'unknown', decision_reason: 'unqualified_effect',
    hard_checks: [{ rule: 'battery_reserve', status: 'unknown', reason: 'unqualified_effect' }] };
}
