import { parseSourceTimestamp } from '../openhab/timestamp.js';
import { OBSERVATION_MAX_BYTES, uniqueObjectKeys } from './observation.js';
const fields = 'schema generated_at valid_until cohort cohort_id by_horizon unique_origin_days last_target_at next_mature_at prediction_target evaluation_scope sampling_basis potential_array_accuracy physical_calibration_qualified causal_benefit_qualified graduated automatic_actuation report_sha256'.split(' ');
const metricFields = 'count attempted_count unique_origin_days mae_kwh bias_kwh rmse_kwh persistence_mae_kwh persistence_rmse_kwh rmse_skill last_target_at'.split(' ');
const models = ['constant_load_pv', 'profiled_load_pv'];
const target = 'reported_controller_DC_output_energy_after_acceptance';
const shape = (v, keys) => v !== null && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v, k));
const digest = v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const epoch = v => typeof v === 'string' && /^[a-zA-Z0-9_-]{1,128}$/.test(v);
const count = v => Number.isInteger(v) && v >= 0 && v <= 192;
const num = (v, min = 0, max = 100000) => typeof v === 'number' && Number.isFinite(v) && v >= min && v <= max;
const close = (a, b) => Math.abs(a - b) <= 1e-7 * Math.max(1, Math.abs(a), Math.abs(b));
const time = v => typeof v === 'string' && v.length <= 64 && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v)
  ? parseSourceTimestamp(v, Number.MAX_SAFE_INTEGER) : null;

/** Curated report only; no source packets, model execution or control semantics. */
export function parseCapturedPvPerformance(raw, { nowMs = Date.now() } = {}) {
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > OBSERVATION_MAX_BYTES || !Number.isFinite(nowMs)) return null;
  try {
    const v = JSON.parse(raw); uniqueObjectKeys(raw);
    if (!shape(v, fields) || v.schema !== 'earthship-household-captured-pv-performance/v1'
      || !digest(v.cohort_id) || !digest(v.report_sha256) || v.prediction_target !== target
      || v.evaluation_scope !== 'provisional_scenarios_under_actual_behavior_not_causal_benefit'
      || v.sampling_basis !== 'first_qualified_original_per_UTC_hour_with_independent_Denver_origin_days'
      || v.potential_array_accuracy !== 'unavailable_unmatched_meter_scope'
      || ['physical_calibration_qualified', 'causal_benefit_qualified', 'graduated', 'automatic_actuation'].some(k => v[k] !== false)) return null;
    const c = v.cohort, original = c?.original_solar_cohort;
    if (!shape(c, ['comparison_rule', 'original_solar_cohort', 'power_source_epoch', 'prediction_target'])
      || c.comparison_rule !== 'frozen_ending_hour_means_over_identical_qualified_duration_v1' || c.prediction_target !== target || !epoch(c.power_source_epoch)
      || !shape(original, ['bank_epoch', 'horizon_sha256', 'model_rule', 'model_sources_sha256', 'nominal_bank_kwh', 'source_epoch', 'system_sha256', 'topology_sha256'])
      || !epoch(original.bank_epoch) || !epoch(original.source_epoch) || !num(original.nominal_bank_kwh, .001, 10000)
      || original.model_rule !== 'array_potential_constant_AC_load_nominal_storage_v1'
      || ['horizon_sha256', 'model_sources_sha256', 'system_sha256', 'topology_sha256'].some(k => !digest(original[k]))) return null;
    const generated = time(v.generated_at), until = time(v.valid_until), next = time(v.next_mature_at);
    if (generated === null || until === null || generated > nowMs || until - generated !== 30 * 60000
      || v.next_mature_at !== null && (next === null || next < generated || next > generated + 24 * 3600000 + 5 * 60000)
      || !shape(v.by_horizon, ['1', '6', '12', '24']) || !count(v.unique_origin_days) || v.unique_origin_days > 8) return null;
    let latest = null, maxDays = 0, sumDays = 0;
    for (const [h, row] of Object.entries(v.by_horizon)) {
      if (!shape(row, ['horizon_hours', 'models']) || row.horizon_hours !== Number(h) || !shape(row.models, models)) return null;
      for (const m of Object.values(row.models)) {
        if (!shape(m, metricFields) || !count(m.count) || !count(m.attempted_count) || m.count > m.attempted_count
          || !count(m.unique_origin_days) || m.unique_origin_days > Math.min(m.count, 8)) return null;
        maxDays = Math.max(maxDays, m.unique_origin_days); sumDays += m.unique_origin_days;
        if (!m.count) {
          if (m.unique_origin_days || metricFields.slice(3).some(k => m[k] !== null)) return null;
          continue;
        }
        const at = time(m.last_target_at);
        if (m.unique_origin_days < 1 || at === null || at > generated - 5 * 60000
          || !num(m.bias_kwh, -100000) || ['mae_kwh', 'rmse_kwh', 'persistence_mae_kwh', 'persistence_rmse_kwh'].some(k => !num(m[k]))
          || Math.abs(m.bias_kwh) > m.mae_kwh + 1e-7 || m.mae_kwh > m.rmse_kwh + 1e-7
          || m.persistence_mae_kwh > m.persistence_rmse_kwh + 1e-7) return null;
        if (m.persistence_rmse_kwh === 0 ? m.rmse_skill !== null
          : !num(m.rmse_skill, -Number.MAX_VALUE, 1) || !close(m.rmse_skill, 1 - m.rmse_kwh / m.persistence_rmse_kwh)) return null;
        latest = Math.max(latest ?? at, at);
      }
    }
    if (v.unique_origin_days < maxDays || v.unique_origin_days > sumDays
      || (latest === null ? v.last_target_at !== null : time(v.last_target_at) !== latest)) return null;
    return { ...v, expired: nowMs >= until };
  } catch { return null; }
}
