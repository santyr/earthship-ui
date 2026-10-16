import { parseSourceTimestamp } from '../openhab/timestamp.js';
import { OBSERVATION_MAX_BYTES, uniqueObjectKeys } from './observation.js';
const shape = (v, fields) => v !== null && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).length === fields.length && fields.every(k => Object.hasOwn(v, k));
const num = (v, low, high) => typeof v === 'number' && Number.isFinite(v) && v >= low && v <= high;
const digest = v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const count = v => Number.isInteger(v) && v >= 0 && v <= 192;
const close = (a, b) => Math.abs(a - b) <= 1e-7 * Math.max(1, Math.abs(a), Math.abs(b));
const reason = v => v === null || typeof v === 'string' && /^[a-z][a-z0-9_]{0,95}$/.test(v);
const time = v => typeof v === 'string' && v.length <= 64 && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v)
  ? parseSourceTimestamp(v, Number.MAX_SAFE_INTEGER) : null;
const horizons = ['1', '6', '12', '24'];
function decode(raw, nowMs) {
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > OBSERVATION_MAX_BYTES || !Number.isFinite(nowMs)) throw new Error('unavailable');
  uniqueObjectKeys(raw); return JSON.parse(raw);
}
const VIEW_FIELDS = 'schema generated_at issued_at valid_until receipt_sha256 original_energy_receipt_sha256 cohort_id status reason model_artifact_sha256 model_sha256 trained_through training_cutoff model_valid_until total_ac_kwh initial_soc_pct nominal_bank_kwh current_ac_w profiled_captured_pv_24h_kwh constant_captured_pv_24h_kwh trajectory confidence physical_calibration_qualified automatic_actuation view_sha256'.split(' ');
export function parseProfiledObservation(raw, { nowMs = Date.now() } = {}) {
  try {
    const v = decode(raw, nowMs);
    if (!shape(v, VIEW_FIELDS) || v.schema !== 'earthship-household-profiled-energy-observation/v1'
      || !digest(v.receipt_sha256) || !digest(v.original_energy_receipt_sha256) || !digest(v.view_sha256) || v.cohort_id !== null && !digest(v.cohort_id)
      || !['conditional', 'unavailable'].includes(v.status) || !reason(v.reason) || v.confidence !== 'provisional_uncalibrated'
      || v.physical_calibration_qualified !== false || v.automatic_actuation !== false) return null;
    const issued = time(v.issued_at), generated = time(v.generated_at), until = time(v.valid_until);
    if (issued === null || generated === null || until === null || issued > generated || generated > nowMs || generated >= until || until > issued + 15 * 60000) return null;
    const trained = time(v.trained_through), cutoff = time(v.training_cutoff), modelUntil = time(v.model_valid_until);
    if (v.model_artifact_sha256 === null) {
      if (['model_sha256', 'trained_through', 'training_cutoff', 'model_valid_until'].some(k => v[k] !== null)) return null;
    } else if (!digest(v.model_artifact_sha256) || !digest(v.model_sha256) || cutoff === null || cutoff > issued
      || (v.trained_through === null ? v.model_valid_until !== null : trained === null || trained > cutoff || modelUntil === null || modelUntil - trained !== 36 * 3600000)) return null;
    const available = v.status === 'conditional';
    if (!Array.isArray(v.trajectory) || v.trajectory.length !== (available ? 24 : 0)) return null;
    if (!available) {
      if (v.reason === null || ['total_ac_kwh', 'initial_soc_pct', 'nominal_bank_kwh', 'current_ac_w', 'profiled_captured_pv_24h_kwh', 'constant_captured_pv_24h_kwh'].some(k => v[k] !== null)) return null;
      return { ...v, expired: nowMs >= until };
    }
    if (v.reason !== null || trained === null || modelUntil <= generated || until > modelUntil
      || !num(v.total_ac_kwh, 0, 480) || !num(v.initial_soc_pct, 0, 100) || !num(v.nominal_bank_kwh, .001, 10000)
      || !num(v.current_ac_w, 0, 20000) || !num(v.profiled_captured_pv_24h_kwh, 0, 100000) || !num(v.constant_captured_pv_24h_kwh, 0, 100000)) return null;
    let total = 0;
    for (const [i, row] of v.trajectory.entries()) {
      if (!shape(row, ['at', 'profiled_ac_w', 'constant_ac_w', 'profiled_soc_pct', 'constant_soc_pct', 'minimum_support_days', 'training_spread_ac_w'])
        || time(row.at) !== issued + (i + 1) * 3600000 || !num(row.profiled_ac_w, 0, 20000) || !num(row.constant_ac_w, 0, 20000) || !close(row.constant_ac_w, v.current_ac_w)
        || !num(row.profiled_soc_pct, 0, 100) || !num(row.constant_soc_pct, 0, 100) || !Number.isInteger(row.minimum_support_days) || row.minimum_support_days < 3 || row.minimum_support_days > 14
        || !Array.isArray(row.training_spread_ac_w) || row.training_spread_ac_w.length !== 2 || row.training_spread_ac_w.some(n => !num(n, 0, 20000))
        || row.training_spread_ac_w[0] > row.profiled_ac_w || row.training_spread_ac_w[1] < row.profiled_ac_w) return null;
      total += row.profiled_ac_w / 1000;
    }
    if (!close(total, v.total_ac_kwh)) return null;
    return { ...v, expired: nowMs >= until };
  } catch { return null; }
}
const REPORT_FIELDS = 'schema generated_at valid_until cohort_id evaluation_scope model_version_count by_horizon next_mature_at load_window load_coverage_policy pv_energy_accuracy physical_calibration_qualified causal_benefit_qualified graduated automatic_actuation report_sha256'.split(' ');
export function parseProfiledPerformance(raw, { nowMs = Date.now() } = {}) {
  try {
    const v = decode(raw, nowMs);
    if (!shape(v, REPORT_FIELDS) || v.schema !== 'earthship-household-profiled-energy-performance/v1' || !digest(v.cohort_id) || !digest(v.report_sha256)
      || v.evaluation_scope !== 'rolling_as_issued_model_versions' || !count(v.model_version_count) || !shape(v.by_horizon, horizons)
      || v.load_window !== 'hour_ending_at_lead_time' || v.load_coverage_policy !== 'at_least_99_percent_both_predictions_on_identical_covered_intervals'
      || v.pv_energy_accuracy !== 'unavailable_unmatched_meter_scope' || ['physical_calibration_qualified', 'causal_benefit_qualified', 'graduated', 'automatic_actuation'].some(k => v[k] !== false)) return null;
    const generated = time(v.generated_at), until = time(v.valid_until), next = time(v.next_mature_at);
    if (generated === null || until === null || generated > nowMs || until - generated !== 30 * 60000 || v.next_mature_at !== null && (next === null || next < generated - 7 * 86400000 || next > generated + 24 * 3600000 + 5 * 60000)) return null;
    for (const pair of Object.values(v.by_horizon)) {
      if (!shape(pair, ['load', 'soc'])) return null;
      for (const [domain, unit, maximum, models] of [['load', 'kwh', 20, ['profiled_load', 'current_load']], ['soc', 'soc_pct', 100, ['profiled_load_pv', 'constant_load_pv', 'constant_power', 'hold_soc']]]) {
        const row = pair[domain]; const metrics = [`mae_${unit}`, `bias_${unit}`, `rmse_${unit}`];
        if (!shape(row, ['count', 'attempted_count', 'unique_origin_days', 'model_version_count', ...metrics, 'status', 'excluded_count'])
          || !count(row.count) || !count(row.attempted_count) || !count(row.unique_origin_days) || row.unique_origin_days > Math.min(8, row.count)
          || !count(row.model_version_count) || row.model_version_count > Math.min(v.model_version_count, row.count)
          || !count(row.excluded_count) || row.count + row.excluded_count !== row.attempted_count || row.status !== (row.count ? 'observed' : 'collecting')) return null;
        if (!row.count) { if (row.unique_origin_days || row.model_version_count || metrics.some(k => row[k] !== null)) return null; continue; }
        if (row.unique_origin_days < 1 || row.model_version_count < 1) return null;
        for (const field of metrics) if (!shape(row[field], models) || Object.values(row[field]).some(n => !num(n, field.startsWith('bias') ? -maximum : 0, maximum))) return null;
        for (const model of models) if (Math.abs(row[`bias_${unit}`][model]) > row[`mae_${unit}`][model] + 1e-7 || row[`mae_${unit}`][model] > row[`rmse_${unit}`][model] + 1e-7) return null;
      }
    }
    return { ...v, expired: nowMs >= until };
  } catch { return null; }
}
