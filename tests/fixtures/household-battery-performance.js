export function batteryPerformance() {
  const empty = () => ({ count: 0, attempted_count: 0, unique_origin_days: 0, mae_soc_pct: null, bias_soc_pct: null, last_target_at: null });
  return {
    schema: 'earthship-household-battery-performance/v1', generated_at: '2026-10-12T03:00:30Z', valid_until: '2026-10-12T03:30:30Z',
    cohort_id: 'a'.repeat(64), model_rule: 'constant_net_dc_power_nominal_capacity_v1',
    by_horizon: { '1': { count: 1, attempted_count: 1, unique_origin_days: 1,
      mae_soc_pct: { constant_power: 2.55859375, hold_soc: 5 }, bias_soc_pct: { constant_power: 2.55859375, hold_soc: 5 },
      last_target_at: '2026-10-12T02:45:15Z' }, '6': empty(), '12': empty(), '24': empty() },
    unique_origin_days: 1, last_target_at: '2026-10-12T02:45:15Z', next_mature_at: '2026-10-12T03:50:15Z',
    sampling_basis: 'one_origin_per_utc_hour', validation_scope: 'sealed_producer_endpoint_pairs',
    physical_calibration_qualified: false, causal_benefit_qualified: false, graduated: false, automatic_actuation: false,
    report_sha256: 'b'.repeat(64),
  };
}
