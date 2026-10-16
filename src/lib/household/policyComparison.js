import { parseSourceTimestamp } from '../openhab/timestamp.js';
const fields = 'schema status reason owner owner_reason owner_scheduling evaluated_at valid_until source_sha256 rule_sha256 gate comparisons performance_status performance_reason physical_permission automatic_actuation'.split(' ');
const gates = { after_dark:'curfew_allowed', cooldown_wait:'cooldown_ready', cooldown_initialized:'cooldown_ready', cycle_started:'owner_idle', cycle_active:'owner_idle', busy:'owner_idle' };
const predictable = ['cooldown_wait','cooldown_initialized','cycle_active','cycle_started','cycle_completed'];
const gateReasons = { curfew_allowed:'after_dark', cooldown_ready:'cooldown', owner_idle:'busy' };
const shape = (v, keys) => v !== null && typeof v === 'object' && !Array.isArray(v)
  && Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v,k));
const digest = v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const token = v => typeof v === 'string' && /^[a-z_]{1,64}$/.test(v);
const time = v => typeof v === 'string' && v.length<=64 && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v)
  ? parseSourceTimestamp(v,Number.MAX_SAFE_INTEGER) : null;

/** Original gate comparison only. Expiry never becomes a physical permission. */
export function parsePolicyComparison(v,{decisionMs,nowMs,proposals}) {
  if (!shape(v,fields) || v.schema!=='earthship-household-policy-block-comparison/v1' || v.owner!=='hex_southoutlet_cycle'
    || v.performance_status!=='unavailable' || v.performance_reason!=='unqualified_effect'
    || v.physical_permission!==false || v.automatic_actuation!==false) return null;
  const metadata=['owner_reason','owner_scheduling','evaluated_at','valid_until','source_sha256','rule_sha256'];
  const at=time(v.evaluated_at),until=time(v.valid_until);
  let status='unavailable',reason='source_unavailable',gate=null;
  if (v.evaluated_at===null) {
    if (metadata.some(k=>v[k]!==null)) return null;
  } else {
    if (at===null || until===null || at>decisionMs || until-at!==120000
      || !digest(v.source_sha256) || !digest(v.rule_sha256) || !token(v.owner_reason)
      || !['blocked','conditional','unavailable'].includes(v.owner_scheduling)) return null;
    if (v.owner_scheduling==='conditional' ? !predictable.includes(v.owner_reason)
      : predictable.includes(v.owner_reason)!==(v.owner_scheduling==='unavailable')) return null;
    if (decisionMs>=until) reason='source_stale';
    else if (Object.hasOwn(gates,v.owner_reason)) {status='observed_block';reason=null;gate=gates[v.owner_reason];}
    else reason=v.owner_scheduling==='conditional'?'eligibility_not_permission':'owner_reason_not_comparable';
  }
  if (v.status!==status || v.reason!==reason || v.gate!==gate || !Array.isArray(v.comparisons)) return null;
  const expected=proposals.filter(p=>p.type==='RUN_GREYWATER_CYCLE');
  if (v.comparisons.length!==expected.length || new Set(v.comparisons.map(r=>r?.intent_id)).size!==v.comparisons.length) return null;
  for (const row of v.comparisons) {
    if (!shape(row,['intent_id','status','shadow_status'])) return null;
    const proposal=expected.find(p=>p.intent_id===row.intent_id);
    if (!proposal) return null;
    const checks=gate===null?[]:proposal.hard_checks.filter(c=>c.rule===gate);
    const check=checks.length===1?checks[0]:null;
    const result=check && check.status!=='unknown'
      ? check.status==='rejected' && check.reason===gateReasons[gate]?'matching_block':'different_gate_result' : 'unknown';
    if (row.status!==result || row.shadow_status!==(check?.status??null)) return null;
  }
  return {...v,expired:until!==null && nowMs>=until};
}
