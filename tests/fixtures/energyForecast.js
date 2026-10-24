/** Complete current-load forecast; 12 kWh potential, 9 kWh captured. */
export function energyForecastFixture(issuedAt = '2026-10-24T12:45:00Z') {
  const issued = Date.parse(issuedAt);
  return {
    schema: 'earthship-household-energy-observation/v1',
    generated_at: new Date(issued + 1000).toISOString(),
    issued_at: issuedAt, valid_until: new Date(issued + 900000).toISOString(),
    receipt_sha256: 'a'.repeat(64), cohort_id: 'b'.repeat(64), view_sha256: 'c'.repeat(64),
    status: 'available', reason: null, storage_status: 'conditional', storage_reason: null,
    potential_pv_24h_kwh: 12, potential_pv_remaining_today_kwh: 8,
    captured_pv_24h_kwh: 9, household_ac_load_w_assumption: 200,
    initial_soc_pct: 90, nominal_bank_kwh: 20.48,
    trajectory: Array.from({ length: 24 }, (_, i) => ({
      at: new Date(issued + (i + 1) * 3600000).toISOString(),
      potential_pv_kwh: .5, captured_pv_kwh: .375, nominal_soc_pct: 100,
    })),
    terrain_status: 'unvalidated_map_estimate', confidence: 'provisional_uncalibrated',
    pv_energy_accuracy: 'unavailable_unmatched_meter_scope',
    physical_calibration_qualified: false, automatic_actuation: false,
  };
}
