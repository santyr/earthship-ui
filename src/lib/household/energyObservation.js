import { parseSourceTimestamp } from '../openhab/timestamp.js';
import { OBSERVATION_MAX_BYTES, uniqueObjectKeys } from './observation.js';
const shape = (v, fields) => v !== null && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).length === fields.length && fields.every(k => Object.hasOwn(v, k));
const num = (v, low, high) => typeof v === 'number' && Number.isFinite(v) && v >= low && v <= high;
const digest = v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const reason = v => v === null || typeof v === 'string' && /^[A-Za-z][A-Za-z0-9_]{0,95}$/.test(v);
const count = v => Number.isInteger(v) && v >= 0 && v <= 192;
const models = ['pv_load_scenario', 'constant_power', 'hold_soc'];
const horizons = ['1', '6', '12', '24'];
const close = (a, b) => Math.abs(a - b) <= 1e-7 * Math.max(1, Math.abs(a), Math.abs(b));
const time = v => typeof v === 'string' && v.length <= 64 && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v)
  ? parseSourceTimestamp(v, Number.MAX_SAFE_INTEGER) : null;
function decode(raw, nowMs) {
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > OBSERVATION_MAX_BYTES || !Number.isFinite(nowMs)) throw new Error('unavailable');
  const value = JSON.parse(raw); uniqueObjectKeys(raw); return value;
}
const VIEW_FIELDS = 'schema generated_at issued_at valid_until receipt_sha256 cohort_id status reason storage_status storage_reason potential_pv_24h_kwh potential_pv_remaining_today_kwh captured_pv_24h_kwh household_ac_load_w_assumption initial_soc_pct nominal_bank_kwh trajectory terrain_status confidence pv_energy_accuracy physical_calibration_qualified automatic_actuation view_sha256'.split(' ');
export function parseEnergyObservation(raw, { nowMs = Date.now() } = {}) {
  try {
    const v = decode(raw, nowMs);
    if (!shape(v, VIEW_FIELDS) || v.schema !== 'earthship-household-energy-observation/v1'
      || !digest(v.receipt_sha256) || !digest(v.view_sha256) || v.cohort_id !== null && !digest(v.cohort_id)
      || !['available', 'unavailable'].includes(v.status) || !['conditional', 'unavailable'].includes(v.storage_status)
      || !reason(v.reason) || !reason(v.storage_reason) || v.confidence !== 'provisional_uncalibrated'
      || v.pv_energy_accuracy !== 'unavailable_unmatched_meter_scope' || v.physical_calibration_qualified !== false || v.automatic_actuation !== false
      || !['unvalidated_map_estimate', 'unavailable'].includes(v.terrain_status)) return null;
    const issued = time(v.issued_at), generated = time(v.generated_at), until = time(v.valid_until);
    if (issued === null || generated === null || until === null || issued > generated || generated > nowMs || generated >= until || until - issued !== 15 * 60000) return null;
    const available = v.status === 'available', conditional = v.storage_status === 'conditional';
    if (!Array.isArray(v.trajectory) || v.trajectory.length !== (available ? 24 : 0) || available && v.reason !== null
      || !available && (v.reason === null || conditional)) return null;
    if (available) {
      if (!num(v.potential_pv_24h_kwh, 0, 100000) || !num(v.potential_pv_remaining_today_kwh, 0, v.potential_pv_24h_kwh + 1e-7)) return null;
    } else if (v.potential_pv_24h_kwh !== null || v.potential_pv_remaining_today_kwh !== null) return null;
    if (conditional) {
      if (v.storage_reason !== null || !num(v.captured_pv_24h_kwh, 0, v.potential_pv_24h_kwh + 1e-7)
        || !num(v.household_ac_load_w_assumption, 0, 100000) || !num(v.initial_soc_pct, 0, 100) || !num(v.nominal_bank_kwh, .001, 10000)) return null;
    } else if (v.storage_reason === null || ['captured_pv_24h_kwh', 'household_ac_load_w_assumption', 'initial_soc_pct', 'nominal_bank_kwh'].some(k => v[k] !== null)) return null;
    let potential = 0, captured = 0;
    for (const [i, row] of v.trajectory.entries()) {
      if (!shape(row, ['at', 'potential_pv_kwh', 'captured_pv_kwh', 'nominal_soc_pct']) || time(row.at) !== issued + (i + 1) * 3600000 || !num(row.potential_pv_kwh, 0, 100000)) return null;
      potential += row.potential_pv_kwh;
      if (conditional) {
        if (!num(row.nominal_soc_pct, 0, 100) || !num(row.captured_pv_kwh, -1e-9, row.potential_pv_kwh + 1e-7)) return null;
        captured += row.captured_pv_kwh;
      } else if (row.nominal_soc_pct !== null || row.captured_pv_kwh !== null) return null;
    }
    if (available && !close(potential, v.potential_pv_24h_kwh) || conditional && !close(captured, v.captured_pv_24h_kwh)) return null;
    return { ...v, expired: nowMs >= until };
  } catch { return null; }
}

const REPORT_FIELDS = 'schema generated_at valid_until cohort_id model_rule by_horizon unique_origin_days last_target_at next_mature_at sampling_basis validation_scope pv_energy_accuracy physical_calibration_qualified causal_benefit_qualified graduated automatic_actuation report_sha256'.split(' ');
export function parseEnergyPerformance(raw, { nowMs = Date.now() } = {}) {
  try {
    const v = decode(raw, nowMs);
    if (!shape(v, REPORT_FIELDS) || v.schema !== 'earthship-household-solar-storage-performance/v1' || !digest(v.cohort_id) || !digest(v.report_sha256)
      || v.model_rule !== 'array_potential_constant_AC_load_nominal_storage_v1' || v.sampling_basis !== 'one_origin_per_utc_hour'
      || v.validation_scope !== 'sealed_producer_endpoint_pairs' || v.pv_energy_accuracy !== 'unavailable_unmatched_meter_scope'
      || ['physical_calibration_qualified', 'causal_benefit_qualified', 'graduated', 'automatic_actuation'].some(k => v[k] !== false)
      || !shape(v.by_horizon, horizons) || !count(v.unique_origin_days) || v.unique_origin_days > 8) return null;
    const generated = time(v.generated_at), until = time(v.valid_until);
    if (generated === null || until === null || generated > nowMs || until - generated !== 30 * 60000) return null;
    let latest = null, maxDays = 0, sumDays = 0;
    for (const row of Object.values(v.by_horizon)) {
      if (!shape(row, ['count', 'attempted_count', 'unique_origin_days', 'mae_soc_pct', 'bias_soc_pct', 'rmse_soc_pct', 'rmse_skill', 'last_target_at'])
        || !count(row.count) || !count(row.attempted_count) || row.count > row.attempted_count || !count(row.unique_origin_days)
        || row.unique_origin_days > Math.min(8, row.count)) return null;
      maxDays = Math.max(maxDays, row.unique_origin_days); sumDays += row.unique_origin_days;
      if (!row.count) {
        if (['mae_soc_pct', 'bias_soc_pct', 'rmse_soc_pct', 'rmse_skill', 'last_target_at'].some(k => row[k] !== null) || row.unique_origin_days !== 0) return null;
        continue;
      }
      const target = time(row.last_target_at);
      if (target === null || target > generated - 5 * 60000 || row.unique_origin_days < 1) return null;
      latest = Math.max(latest ?? target, target);
      for (const [field, low] of [['mae_soc_pct', 0], ['bias_soc_pct', -100], ['rmse_soc_pct', 0]]) {
        if (!shape(row[field], models) || Object.values(row[field]).some(n => !num(n, low, 100))) return null;
      }
      if (!shape(row.rmse_skill, ['constant_power', 'hold_soc'])) return null;
      for (const model of models) if (Math.abs(row.bias_soc_pct[model]) > row.mae_soc_pct[model] + 1e-7 || row.mae_soc_pct[model] > row.rmse_soc_pct[model] + 1e-7) return null;
      for (const model of ['constant_power', 'hold_soc']) {
        const expected = row.rmse_soc_pct[model] === 0 ? null : 1 - row.rmse_soc_pct.pv_load_scenario / row.rmse_soc_pct[model];
        if (expected === null ? row.rmse_skill[model] !== null : !Number.isFinite(row.rmse_skill[model]) || !close(row.rmse_skill[model], expected)) return null;
      }
    }
    if (v.unique_origin_days < maxDays || v.unique_origin_days > sumDays || (v.last_target_at === null ? latest !== null : time(v.last_target_at) !== latest)
      || v.next_mature_at !== null && time(v.next_mature_at) === null) return null;
    return { ...v, expired: nowMs >= until };
  } catch { return null; }
}
