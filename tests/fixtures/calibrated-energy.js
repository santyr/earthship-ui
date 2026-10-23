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
export function calibratedPerformance() {
 const digest='a'.repeat(64),issue=new Date(CALIBRATED_NOW-70*60000).toISOString();
 return {schema:'earthship-household-calibrated-energy-performance/v1',generated_at:new Date(CALIBRATED_NOW).toISOString(),valid_until:new Date(CALIBRATED_NOW+3600000).toISOString(),
  cohort_id:digest,calibration_model_sha256:digest,view_sha256:digest,model_version_count:1,independent_origin_days:1,first_issue:issue,last_issue:issue,
  by_horizon:Object.fromEntries([1,6,12,24].map(h=>[String(h),{
   soc:{attempted_count:h===1?1:0,count:h===1?1:0,mae_soc_pct:{calibrated_pv:h===1?1:null,raw_pv:h===1?1.2:null,hold_soc:h===1?2:null}},
   load:{attempted_count:h===1?1:0,count:h===1?1:0,current_count:0,mae_kwh:{learned_ac:h===1?.05:null,current_ac:null}},
  }])),physical_calibration_qualified:false,causal_benefit_qualified:false,graduated:false,automatic_actuation:false};
}

export function componentEnergy() {
 const v=calibratedEnergy(),hash='b'.repeat(64);
 return {...v,schema:'earthship-household-calibrated-energy-observation/v4',
  calibration_policy_sha256:hash,calibration_sha256:hash,procedure_sha256:hash,cohort_id:'a'.repeat(64),measurement_cohort_sha256:hash,
  baseline_rule:'native_fdir_ssrd_isotropic_faiman_proxy_pvwatts_dc_v2',
  calibration_scope:'mixed_native_and_raw_fallback',calibration_mode:'experimental_production',
  source_support:{native_hours:12,fallback_hours:13,fallback_reasons:{no_daylight_support:13}},
  confidence:'experimental_native_component_model',source_freshness_basis:'qualified_original_issue_with_85_second_publication_deadline'};
}
export function componentPerformance() {
 return {...calibratedPerformance(),schema:'earthship-household-calibrated-energy-performance/v3',
  calibration_policy_sha256:'b'.repeat(64),procedure_sha256:'b'.repeat(64),measurement_cohort_sha256:'b'.repeat(64),
  baseline_rule:'native_fdir_ssrd_isotropic_faiman_proxy_pvwatts_dc_v2'};
}
