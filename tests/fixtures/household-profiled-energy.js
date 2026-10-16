export const PROFILE_NOW = Date.parse('2026-10-15T17:00:20Z');
const issue = PROFILE_NOW - 5000;
const hash = 'a'.repeat(64);
export function profiledObservation() {
  return { schema: 'earthship-household-profiled-energy-observation/v1', generated_at: new Date(PROFILE_NOW).toISOString(), issued_at: new Date(issue).toISOString(),
    valid_until: new Date(issue + 15 * 60000).toISOString(), receipt_sha256: hash, original_energy_receipt_sha256: hash, cohort_id: hash,
    status: 'conditional', reason: null, model_artifact_sha256: hash, model_sha256: hash, trained_through: '2026-10-15T06:00:00Z', training_cutoff: '2026-10-15T06:00:00Z',
    model_valid_until: '2026-10-16T18:00:00Z', total_ac_kwh: 9.6, initial_soc_pct: 98, nominal_bank_kwh: 20.48, current_ac_w: 500,
    profiled_captured_pv_24h_kwh: 10, constant_captured_pv_24h_kwh: 12,
    trajectory: Array.from({ length: 24 }, (_, i) => ({ at: new Date(issue + (i + 1) * 3600000).toISOString(), profiled_ac_w: 400, constant_ac_w: 500,
      profiled_soc_pct: 98, constant_soc_pct: 97, minimum_support_days: 12, training_spread_ac_w: [300, 600] })), confidence: 'provisional_uncalibrated',
    physical_calibration_qualified: false, automatic_actuation: false, view_sha256: hash };
}
export function profiledPerformance() {
  const empty = unit => ({ count: 0, attempted_count: 0, unique_origin_days: 0, model_version_count: 0, [`mae_${unit}`]: null, [`bias_${unit}`]: null,
    [`rmse_${unit}`]: null, status: 'collecting', excluded_count: 0 });
  const by_horizon = Object.fromEntries(['1', '6', '12', '24'].map(h => [h, { load: empty('kwh'), soc: empty('soc_pct') }]));
  const load = { profiled_load: .05, current_load: .1 }, soc = { profiled_load_pv: .5, constant_load_pv: 1, constant_power: 2, hold_soc: 3 };
  for (const [domain, values, unit] of [['load', load, 'kwh'], ['soc', soc, 'soc_pct']]) by_horizon['1'][domain] = { count: 1, attempted_count: 1,
    unique_origin_days: 1, model_version_count: 1, [`mae_${unit}`]: values, [`bias_${unit}`]: values, [`rmse_${unit}`]: values, status: 'observed', excluded_count: 0 };
  return { schema: 'earthship-household-profiled-energy-performance/v1', generated_at: new Date(PROFILE_NOW).toISOString(), valid_until: new Date(PROFILE_NOW + 30 * 60000).toISOString(),
    cohort_id: hash, evaluation_scope: 'rolling_as_issued_model_versions', model_version_count: 1, by_horizon, next_mature_at: null,
    load_window: 'hour_ending_at_lead_time', load_coverage_policy: 'at_least_99_percent_both_predictions_on_identical_covered_intervals', pv_energy_accuracy: 'unavailable_unmatched_meter_scope',
    physical_calibration_qualified: false, causal_benefit_qualified: false, graduated: false, automatic_actuation: false, report_sha256: hash };
}
