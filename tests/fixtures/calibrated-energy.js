export const CALIBRATED_NOW = Date.parse('2026-10-15T17:00:20Z');
export function calibratedEnergy() {
  const issue = CALIBRATED_NOW - 5000, digest = 'a'.repeat(64);
  return { schema: 'earthship-household-calibrated-energy-observation/v2', generated_at: new Date(CALIBRATED_NOW).toISOString(), issued_at: new Date(issue).toISOString(), valid_until: new Date(issue + 15 * 60000).toISOString(),
    receipt_sha256: digest, original_energy_receipt_sha256: digest, calibration_model_sha256: digest, view_sha256: digest,
    status: 'projected_provisional_calibrated_potential', reason: null, raw_potential_kwh: 20, calibrated_potential_kwh: 14,
    load_status: 'projected', load_model_sha256: digest, load_trained_through: '2026-10-15T06:00:00Z', load_training_cutoff: '2026-10-15T06:00:00Z', load_total_ac_kwh: 9.6,
    profiled_storage_status: 'conditional_nominal_simulation', profiled_storage_reason: null, profiled_captured_pv_kwh: 6.4, raw_profiled_captured_pv_kwh: 6.3, initial_soc_pct: 96, nominal_bank_kwh: 20.48,
    trajectory: Array.from({ length: 24 }, (_, i) => ({ at: new Date(issue + (i + 1) * 3600000).toISOString(), mean_ac_w: 400, minimum_support_days: 12, training_spread_ac_w: [300, 600], calibrated_soc_pct: 96, raw_soc_pct: 97 })),
    source_freshness_basis: 'qualified_original_issue_with_120_second_publication_deadline', confidence: 'provisional_empirical_short_horizon', physical_calibration_qualified: false, automatic_actuation: false };
}
