export const ENERGY_NOW = Date.parse('2026-10-15T17:00:40Z');
export function energyObservation() {
  const issued = Date.parse('2026-10-15T16:55:15Z');
  return {
    schema: 'earthship-household-energy-observation/v1', generated_at: '2026-10-15T16:55:32Z', issued_at: new Date(issued).toISOString(), valid_until: '2026-10-15T17:10:15Z',
    receipt_sha256: 'a'.repeat(64), cohort_id: 'c'.repeat(64), status: 'available', reason: null, storage_status: 'conditional', storage_reason: null,
    potential_pv_24h_kwh: 12, potential_pv_remaining_today_kwh: 5, captured_pv_24h_kwh: 9.6, household_ac_load_w_assumption: 380,
    initial_soc_pct: 100, nominal_bank_kwh: 20.48,
    trajectory: Array.from({ length: 24 }, (_, i) => ({ at: new Date(issued + (i + 1) * 3600000).toISOString(), potential_pv_kwh: 0.5, captured_pv_kwh: 0.4, nominal_soc_pct: 100 })),
    terrain_status: 'unvalidated_map_estimate', confidence: 'provisional_uncalibrated', pv_energy_accuracy: 'unavailable_unmatched_meter_scope',
    physical_calibration_qualified: false, automatic_actuation: false, view_sha256: 'b'.repeat(64),
  };
}
export function energyPerformance() {
  const empty = () => ({ count: 0, attempted_count: 0, unique_origin_days: 0, mae_soc_pct: null, bias_soc_pct: null, rmse_soc_pct: null, rmse_skill: null, last_target_at: null });
  return {
    schema: 'earthship-household-solar-storage-performance/v1', generated_at: '2026-10-15T17:00:35Z', valid_until: '2026-10-15T17:30:35Z', cohort_id: 'c'.repeat(64),
    model_rule: 'array_potential_constant_AC_load_nominal_storage_v1',
    by_horizon: { '1': { count: 1, attempted_count: 1, unique_origin_days: 1, mae_soc_pct: { pv_load_scenario: 1, constant_power: 2, hold_soc: 3 }, bias_soc_pct: { pv_load_scenario: 1, constant_power: 2, hold_soc: 3 }, rmse_soc_pct: { pv_load_scenario: 1, constant_power: 2, hold_soc: 3 }, rmse_skill: { constant_power: 0.5, hold_soc: 1 - 1 / 3 }, last_target_at: '2026-10-15T16:55:15Z' }, '6': empty(), '12': empty(), '24': empty() },
    unique_origin_days: 1, last_target_at: '2026-10-15T16:55:15Z', next_mature_at: '2026-10-15T22:00:15Z', sampling_basis: 'one_origin_per_utc_hour', validation_scope: 'sealed_producer_endpoint_pairs',
    pv_energy_accuracy: 'unavailable_unmatched_meter_scope', physical_calibration_qualified: false, causal_benefit_qualified: false, graduated: false, automatic_actuation: false, report_sha256: 'd'.repeat(64),
  };
}
