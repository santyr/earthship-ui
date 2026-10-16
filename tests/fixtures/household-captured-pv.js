export function capturedPvPerformance() {
  const empty = () => ({ count: 0, attempted_count: 0, unique_origin_days: 0, mae_kwh: null, bias_kwh: null,
    rmse_kwh: null, persistence_mae_kwh: null, persistence_rmse_kwh: null, rmse_skill: null, last_target_at: null });
  const horizon = h => ({ horizon_hours: h, models: { constant_load_pv: empty(), profiled_load_pv: empty() } });
  const report = {
    schema: 'earthship-household-captured-pv-performance/v1', generated_at: '2026-10-12T03:00:30Z', valid_until: '2026-10-12T03:30:30Z',
    cohort: { comparison_rule: 'frozen_ending_hour_means_over_identical_qualified_duration_v1',
      original_solar_cohort: { bank_epoch: 'discover_4_module_2026', horizon_sha256: 'a'.repeat(64),
        model_rule: 'array_potential_constant_AC_load_nominal_storage_v1', model_sources_sha256: 'b'.repeat(64), nominal_bank_kwh: 20.48,
        source_epoch: 'source-epoch', system_sha256: 'c'.repeat(64), topology_sha256: 'd'.repeat(64) },
      power_source_epoch: 'power-epoch', prediction_target: 'reported_controller_DC_output_energy_after_acceptance' },
    cohort_id: 'e'.repeat(64), by_horizon: { '1': horizon(1), '6': horizon(6), '12': horizon(12), '24': horizon(24) },
    unique_origin_days: 1, last_target_at: '2026-10-12T02:45:15Z', next_mature_at: '2026-10-12T03:50:15Z',
    prediction_target: 'reported_controller_DC_output_energy_after_acceptance',
    evaluation_scope: 'provisional_scenarios_under_actual_behavior_not_causal_benefit',
    sampling_basis: 'first_qualified_original_per_UTC_hour_with_independent_Denver_origin_days',
    potential_array_accuracy: 'unavailable_unmatched_meter_scope', physical_calibration_qualified: false,
    causal_benefit_qualified: false, graduated: false, automatic_actuation: false, report_sha256: 'f'.repeat(64),
  };
  // A 0.30 kWh model error and 0.20 kWh reference error give -50% RMSE skill.
  report.by_horizon['1'].models.constant_load_pv = { count: 1, attempted_count: 2, unique_origin_days: 1,
    mae_kwh: .3, bias_kwh: .3, rmse_kwh: .3, persistence_mae_kwh: .2, persistence_rmse_kwh: .2,
    rmse_skill: -.5, last_target_at: report.last_target_at };
  return report;
}
export function emptyCapturedPvPerformance() {
  const r = capturedPvPerformance();
  r.by_horizon['1'].models.constant_load_pv = { ...r.by_horizon['6'].models.constant_load_pv };
  r.unique_origin_days = 0; r.last_target_at = null;
  return r;
}
