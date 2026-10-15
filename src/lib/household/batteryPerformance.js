import { parseSourceTimestamp } from '../openhab/timestamp.js';
import { OBSERVATION_MAX_BYTES, uniqueObjectKeys } from './observation.js';
const FIELDS = 'schema generated_at valid_until cohort_id model_rule by_horizon unique_origin_days last_target_at next_mature_at sampling_basis validation_scope physical_calibration_qualified causal_benefit_qualified graduated automatic_actuation report_sha256'.split(' ');
const shape = (row, fields) => row !== null && typeof row === 'object' && !Array.isArray(row)
  && Object.keys(row).length === fields.length && fields.every(k => Object.hasOwn(row, k));
const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const count = value => Number.isInteger(value) && value >= 0 && value <= 192;
const number = (value, min, max) => typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max;
function time(value) {
  return typeof value === 'string' && value.length <= 64 && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    ? parseSourceTimestamp(value, Number.MAX_SAFE_INTEGER) : null;
}
export function parseBatteryPerformance(raw, { nowMs = Date.now() } = {}) {
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > OBSERVATION_MAX_BYTES || !Number.isFinite(nowMs)) return null;
  try {
    const row = JSON.parse(raw); uniqueObjectKeys(raw);
    if (!shape(row, FIELDS) || row.schema !== 'earthship-household-battery-performance/v1'
      || !digest(row.cohort_id) || !digest(row.report_sha256) || row.model_rule !== 'constant_net_dc_power_nominal_capacity_v1'
      || row.sampling_basis !== 'one_origin_per_utc_hour' || row.validation_scope !== 'sealed_producer_endpoint_pairs'
      || ['physical_calibration_qualified', 'causal_benefit_qualified', 'graduated', 'automatic_actuation'].some(k => row[k] !== false)) return null;
    const generated = time(row.generated_at), until = time(row.valid_until);
    if (generated === null || until === null || generated > nowMs || until - generated !== 30 * 60_000
      || !shape(row.by_horizon, ['1', '6', '12', '24']) || !count(row.unique_origin_days) || row.unique_origin_days > 8) return null;
    let latest = null, maxDays = 0, sumDays = 0;
    for (const data of Object.values(row.by_horizon)) {
      if (!shape(data, ['count', 'attempted_count', 'unique_origin_days', 'mae_soc_pct', 'bias_soc_pct', 'last_target_at'])
        || !count(data.count) || !count(data.attempted_count) || !count(data.unique_origin_days)
        || data.count > data.attempted_count || data.unique_origin_days > Math.min(data.count, 8)) return null;
      maxDays = Math.max(maxDays, data.unique_origin_days); sumDays += data.unique_origin_days;
      if (!data.count) {
        if (data.mae_soc_pct !== null || data.bias_soc_pct !== null || data.last_target_at !== null || data.unique_origin_days !== 0) return null;
      } else {
        const at = time(data.last_target_at);
        if (at === null || at > generated - 5 * 60_000 || data.unique_origin_days < 1) return null;
        latest = Math.max(latest ?? at, at);
        for (const [name, low] of [['mae_soc_pct', 0], ['bias_soc_pct', -100]]) {
          if (!shape(data[name], ['constant_power', 'hold_soc']) || Object.values(data[name]).some(v => !number(v, low, 100))) return null;
        }
        for (const name of ['constant_power', 'hold_soc']) if (Math.abs(data.bias_soc_pct[name]) > data.mae_soc_pct[name] + 1e-10) return null;
      }
    }
    if (row.unique_origin_days < maxDays || row.unique_origin_days > sumDays
      || (row.last_target_at === null ? latest !== null : time(row.last_target_at) !== latest)
      || (row.next_mature_at !== null && time(row.next_mature_at) === null)) return null;
    return { ...row, expired: nowMs >= until };
  } catch { return null; }
}
