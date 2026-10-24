import { parseQualification } from './qualification.js';
import { parsePolicyComparison } from './policyComparison.js';
import { parseSourceTimestamp } from '../openhab/timestamp.js';

export const OBSERVATION_MAX_BYTES = 32768;
const FIELDS = 'schema receipt_sha256 snapshot_id snapshot_as_of decision_at verified_at valid_until planner_mode planner_version authority automatic_actuation plan_status model_identities candidate_generation proposals source_quality confidence effects_qualified policy_comparison'.split(' ');
const CONFIDENCE = ['unavailable', 'low', 'medium', 'high'];
const DOMAINS = ['energy', 'thermal', 'water', 'weather', 'authority'];
const TYPES = ['NO_ACTION', 'RUN_GREYWATER_CYCLE', 'RUN_FEEDER_CYCLE', 'SET_NIGHT_LOAD_OVERRIDE', 'SET_NIGHT_LOAD_DEVICE'];
const EFFECT_UNITS = { batteryKwh: 'kWh', socPct: 'percentage_points', thermalF: 'degF', water: 'litre', wearCost: 'normalized_cycle_cost' };
const LIMITS = { batteryKwh: 1000, socPct: 100, thermalF: 100, water: 1000000, wearCost: 1000000 };
const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const shape = (value, fields) => isObject(value) && Object.keys(value).length === fields.length && fields.every(key => Object.hasOwn(value, key));
const token = value => typeof value === 'string' && /^[a-z][a-z0-9_]{0,63}$/.test(value);
const reason = value => value === null || token(value);
const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const nullableDigest = value => value === null || digest(value);
const list = (value, limit) => Array.isArray(value) && value.length <= limit;
function time(value) {
  return typeof value === 'string' && value.length <= 64 && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    ? parseSourceTimestamp(value, Number.MAX_SAFE_INTEGER) : null;
}

// JSON.parse alone collapses duplicate keys, leaving overridden private bytes
// in the original transport body. Scan validated JSON with decoded key names.
export function uniqueObjectKeys(raw) {
  let offset = 0;
  const space = () => { while (/\s/.test(raw[offset] ?? '') && offset < raw.length) offset++; };
  function string() {
    const start = offset++;
    while (offset < raw.length) {
      if (raw[offset] === '\\') { offset += 2; continue; }
      if (raw[offset++] === '"') return JSON.parse(raw.slice(start, offset));
    }
    throw new Error('Invalid string');
  }
  function value(depth) {
    if (depth > 16) throw new Error('Observation nesting exceeds bound');
    space();
    if (raw[offset] === '"') { string(); return; }
    if (raw[offset] === '{') {
      offset++; space(); const keys = new Set();
      if (raw[offset] === '}') { offset++; return; }
      for (;;) {
        space(); const key = string();
        if (keys.has(key)) throw new Error('Duplicate observation key');
        keys.add(key); space(); offset++; value(depth + 1); space();
        if (raw[offset++] === '}') return;
      }
    }
    if (raw[offset] === '[') {
      offset++; space();
      if (raw[offset] === ']') { offset++; return; }
      for (;;) { value(depth + 1); space(); if (raw[offset++] === ']') return; }
    }
    while (offset < raw.length && !/[\s,}\]]/.test(raw[offset])) offset++;
  }
  value(0);
}

/** Validate only the curated observer contract; never interpret a producer receipt. */
export function parseHouseholdObservation(raw, { nowMs = Date.now() } = {}) {
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > OBSERVATION_MAX_BYTES || !Number.isFinite(nowMs)) return null;
  try {
    const row = JSON.parse(raw);
    uniqueObjectKeys(raw);
    if (!shape(row, ['earthship-household-observation/v3','earthship-household-observation/v4'].includes(row?.schema)?[...FIELDS,'qualification_report']:FIELDS) || !['earthship-household-observation/v1','earthship-household-observation/v2','earthship-household-observation/v3','earthship-household-observation/v4'].includes(row.schema)
      || !digest(row.receipt_sha256) || !digest(row.snapshot_id)
      || row.authority !== 'none' || row.automatic_actuation !== false || row.effects_qualified !== false
      || row.confidence !== 'unavailable' || !['bounded_exhaustive_v1','bounded_exhaustive_v2'].includes(row.planner_version)
      || !['shadow', 'unavailable'].includes(row.planner_mode)
      || !['selected_shadow_candidates', 'input_incomplete', 'baseline_outside_reserve', 'no_optional_action_preferred'].includes(row.plan_status)) return null;
    // A changed planning scope must travel with its current qualification
    // contract; retained historical versions keep their original meaning.
    const currentPlanner = row.planner_version === 'bounded_exhaustive_v2';
    if (currentPlanner && ['earthship-household-observation/v3','earthship-household-observation/v4'].includes(row.schema)
      && row.qualification_report?.schema !== 'earthship-household-intent-qualification/v3') return null;
    const snapshot = time(row.snapshot_as_of), decision = time(row.decision_at), verified = time(row.verified_at), until = time(row.valid_until);
    if ([snapshot, decision, verified, until].includes(null) || snapshot > decision || decision > verified || verified > nowMs) return null;
    if (!list(row.model_identities, 2) || new Set(row.model_identities.map(model => model?.domain)).size !== row.model_identities.length) return null;
    for (const model of row.model_identities) {
      if (!shape(model, ['domain', 'artifact_sha256', 'runtime_sha256', 'projection_sha256', 'confidence', 'qualification'])
        || !['energy', 'thermal'].includes(model.domain) || !nullableDigest(model.artifact_sha256)
        || !nullableDigest(model.runtime_sha256) || !digest(model.projection_sha256)
        || !CONFIDENCE.includes(model.confidence)
        || !(['not_assessed', 'not_graduated'].includes(model.qualification)
          || (model.domain === 'energy' && model.qualification === 'conditional_uncalibrated_scenario'))) return null;
    }
    const originalMode = verified < until && row.model_identities.length ? 'shadow' : 'unavailable';
    if (row.planner_mode !== originalMode) return null;
    const generation = row.candidate_generation;
    if (!shape(generation, ['status', 'reason', 'input_qualification'])
      || !['generated_shadow_only', 'unavailable'].includes(generation.status)
      || !reason(generation.reason) || generation.input_qualification !== 'not_assessed') return null;
    if (row.schema==='earthship-household-observation/v1' && (!shape(row.policy_comparison, ['status', 'reason']) || row.policy_comparison.status !== 'unavailable' || !reason(row.policy_comparison.reason))) return null;
    if (!list(row.proposals, 8) || new Set(row.proposals.map(item => item?.intent_id)).size !== row.proposals.length) return null;
    if (currentPlanner && row.proposals.some(item => !['NO_ACTION','SET_NIGHT_LOAD_DEVICE'].includes(item?.type))) return null;
    for (const item of row.proposals) {
      const actionFields=row.schema==='earthship-household-observation/v4'?['parameters','created_at','expires_at']:[];
      if (!shape(item, [...actionFields,'intent_id', 'type', 'selected', 'confidence', 'reasons', 'expected_effects', 'effect_units', 'decision_status', 'decision_reason', 'hard_checks'])
        || !digest(item.intent_id) || !TYPES.includes(item.type) || typeof item.selected !== 'boolean'
        || !CONFIDENCE.includes(item.confidence) || !list(item.reasons, 16) || !item.reasons.length || !item.reasons.every(token)
        || new Set(item.reasons).size !== item.reasons.length || !reason(item.decision_reason)
        || !['accepted', 'rejected', 'unknown', 'superseded', 'deferred'].includes(item.decision_status)
        || !shape(item.expected_effects, Object.keys(EFFECT_UNITS)) || !shape(item.effect_units, Object.keys(EFFECT_UNITS))
        || !list(item.hard_checks, 32)) return null;
      if(row.schema==='earthship-household-observation/v4'){
        const created=time(item.created_at),expires=time(item.expires_at),p=item.parameters;
        if(created!==decision||expires===null||expires<=created||expires-created>300000)return null;
        if(['NO_ACTION','RUN_GREYWATER_CYCLE','RUN_FEEDER_CYCLE'].includes(item.type)){if(!shape(p,[]))return null;}
        else if(item.type==='SET_NIGHT_LOAD_OVERRIDE'){if(!shape(p,['command'])||!['ON','OFF'].includes(p.command))return null;}
        else if(!shape(p,['device','command'])||!['dishwasher','shureflo','goat-cam'].includes(p.device)||!['ON','OFF'].includes(p.command))return null;
      }
      for (const key of Object.keys(EFFECT_UNITS)) {
        const value = item.expected_effects[key];
        if (item.effect_units[key] !== EFFECT_UNITS[key] || (value !== null && (typeof value !== 'number' || !Number.isFinite(value)
          || Math.abs(value) > LIMITS[key] || (key === 'wearCost' && value < 0)))) return null;
      }
      for (const check of item.hard_checks) {
        if (!shape(check, ['rule', 'status', 'reason']) || !token(check.rule) || !reason(check.reason)
          || !['pass', 'rejected', 'unknown'].includes(check.status)) return null;
      }
      if (item.selected && (item.decision_status !== 'accepted' || item.hard_checks.some(check => check.status !== 'pass'))) return null;
    }
    if (!list(row.source_quality, 64) || new Set(row.source_quality.map(source => `${source?.domain}:${source?.role}`)).size !== row.source_quality.length) return null;
    const sources = [];
    for (const source of row.source_quality) {
      if (!shape(source, ['domain', 'role', 'quality_at_issue', 'current_quality', 'reason', 'received_at', 'valid_until'])
        || !DOMAINS.includes(source.domain) || !token(source.role) || !reason(source.reason)
        || !['qualified', 'unavailable'].includes(source.quality_at_issue)
        || !['qualified', 'expired', 'unavailable'].includes(source.current_quality)) return null;
      const received = source.received_at === null ? null : time(source.received_at);
      const expiry = source.valid_until === null ? null : time(source.valid_until);
      if ((source.received_at !== null && received === null) || (source.valid_until !== null && expiry === null)
        || (received !== null && received > verified)) return null;
      const qualified = source.quality_at_issue === 'qualified';
      if (qualified && (received === null || expiry === null || received > snapshot || expiry <= snapshot || source.reason !== null || until > expiry)) return null;
      const atVerification = qualified ? (verified >= expiry ? 'expired' : 'qualified') : 'unavailable';
      if (source.current_quality !== atVerification) return null;
      sources.push({ ...source, current_quality: qualified ? (nowMs >= expiry ? 'expired' : 'qualified') : 'unavailable' });
    }
    const policy = row.schema!=='earthship-household-observation/v1' ? parsePolicyComparison(row.policy_comparison,{decisionMs:decision,nowMs,proposals:row.proposals}) : null;
    if (row.schema!=='earthship-household-observation/v1' && policy===null) return null;
    if (['earthship-household-observation/v3','earthship-household-observation/v4'].includes(row.schema) && parseQualification(row.qualification_report,row)===null) return null;
    return { ...row, ...(policy===null?{}:{policyComparison:policy}), source_quality: sources, expired: nowMs >= until,
      effectiveMode: nowMs < until ? row.planner_mode : 'unavailable', snapshotAgeSeconds: Math.floor((nowMs - snapshot) / 1000) };
  } catch { return null; }
}
