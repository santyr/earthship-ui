export const PV_REPORT_NOW = Date.parse('2026-10-20T13:10:00Z');
export function pvPerformance({ collecting = false } = {}) {
  const c = { cohort_id:'a'.repeat(64),model_sha256:'b'.repeat(64),calibration_policy_sha256:'c'.repeat(64),scoring_runtime_sha256:'d'.repeat(64),
    hour_count:2,eligible_bins:collecting?0:12,adjusted_bins:collecting?0:12,missing_forecast_bins:0,censored_bins:collecting?24:12,unqualified_bins:0,low_generation_bins:0,unknown_coverage_bins:0,
    covered_seconds:collecting?0:3600,first_issue:'2026-10-20T09:00:00Z',last_issue:'2026-10-20T10:00:00Z',first_window_start:'2026-10-20T11:00:00Z',last_window_end:'2026-10-20T13:00:00Z',independent_target_days:collecting?0:1,
    baseline_mae_w:collecting?null:200,candidate_mae_w:collecting?null:125 };
  return {schema:'earthship-pv-potential-performance/v1',generated_at:new Date(PV_REPORT_NOW).toISOString(),valid_until:new Date(PV_REPORT_NOW+2*3600000).toISOString(),
    window_start:'2026-10-13T13:00:00Z',window_end:'2026-10-20T13:00:00Z',status:collecting?'collecting':'scored',cohorts:[c],omitted_cohort_count:0,scored_hours:2,unscored_hours:166,
    outcome_scope:'qualified_low_soc_charging_controller_input_proxy',metric_basis:'covered_duration_weighted_absolute_power_error',prospective_score:true,physical_calibration_qualified:false,automatic_actuation:false,view_sha256:'e'.repeat(64)};
}
export function componentPvPerformance(options={}) {
  const v=pvPerformance(options);v.schema='earthship-pv-potential-performance/v2';
  const c=v.cohorts[0];c.local_target_dates=c.independent_target_days;delete c.independent_target_days;
  Object.assign(c,{procedure_sha256:'f'.repeat(64),measurement_cohort_sha256:'1'.repeat(64),solar_grid_sha256:'2'.repeat(64),
    baseline_rule:'native_fdir_ssrd_isotropic_faiman_proxy_pvwatts_dc_v2',
    metric_population:'constituent_five_minute_power_of_published_daily_totals',target_timezone:'America/Denver'});
  return v;
}
