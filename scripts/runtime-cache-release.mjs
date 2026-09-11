// Pure, exact-rule release planning. No network, credentials or execution API.
import { createHash } from 'node:crypto';

export const RULE_UID = 'hex_bms_ttd_smooth';
export const ORIGINAL_SHA256 = 'b5b80aa90ca0dbea4b03cd4c7b62eb73d2ee938d7df2b7940a21a29ba5d543a2';
export const REPLACEMENT_SHA256 = '8698b16a5e07a5fde653c6e74219886f78c2b6ec7740e5a8a8608c32c205a794';
const fields = ['uid', 'name', 'description', 'tags', 'visibility', 'configuration', 'triggers', 'conditions', 'actions'];
const readOnlyFields = ['status', 'editable', 'configDescriptions', 'templateState'];
const digest = value => createHash('sha256').update(value).digest('hex');
const canonical = value => JSON.stringify(value, (_key, v) => v && typeof v === 'object' && !Array.isArray(v)
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, v[k]])) : v);
const dto = rule => Object.fromEntries(fields.map(key => [key, structuredClone(rule[key])]));

export function runtimeRuleEnabledState(rule) {
  const s = rule?.status;
  if (['IDLE', 'RUNNING'].includes(s?.status) && s?.statusDetail === 'NONE') return true;
  if (s?.status === 'UNINITIALIZED' && s?.statusDetail === 'DISABLED') return false;
  throw new Error('runtime enable state unknown');
}

export function planRuntimeCacheRelease({ rule, enabled, version, source }) {
  if (version !== '5.2.1' || typeof enabled !== 'boolean' || rule?.uid !== RULE_UID || rule.editable !== true) {
    throw new Error('runtime release identity/version mismatch');
  }
  if (Object.keys(rule).some(k => !fields.includes(k) && !readOnlyFields.includes(k))
      || fields.some(k => !Object.hasOwn(rule, k))) throw new Error('unexpected runtime rule DTO');
  const status = rule.status;
  if (enabled ? status?.status !== 'IDLE' || status?.statusDetail !== 'NONE'
    : status?.status !== 'UNINITIALIZED' || status?.statusDetail !== 'DISABLED') {
    throw new Error('runtime rule must be quiescent with known enable state');
  }
  if (canonical(rule.triggers) !== canonical([{ id: '1', configuration: { itemName: 'BMS_TimeToDischarge_Min' }, type: 'core.ItemStateUpdateTrigger' }])
      || canonical(rule.conditions) !== '[]' || rule.actions?.length !== 1) {
    throw new Error('runtime trigger/action contract drift');
  }
  const action = rule.actions[0];
  if (action.id !== '2' || action.type !== 'script.ScriptAction'
      || action.configuration?.type !== 'application/javascript'
      || typeof action.configuration.script !== 'string'
      || digest(action.configuration.script) !== ORIGINAL_SHA256
      || typeof source !== 'string' || digest(source) !== REPLACEMENT_SHA256) {
    throw new Error('runtime source drift');
  }
  const original = dto(rule), desired = dto(rule);
  desired.actions[0].configuration.script = source;
  const path = `/rest/rules/${RULE_UID}`;
  const operations = [];
  if (enabled) operations.push({ method: 'POST', path: `${path}/enable`, body: 'false' });
  operations.push({ method: 'PUT', path, body: structuredClone(desired) });
  if (enabled) operations.push({ method: 'POST', path: `${path}/enable`, body: 'true' });
  return { schema: 'runtime-cache-release/v1', original, desired, enabled,
    originalSha256: ORIGINAL_SHA256, replacementSha256: REPLACEMENT_SHA256, operations };
}

export function verifyRuntimeCacheReadback({ plan, rule, enabled }) {
  if (plan?.schema !== 'runtime-cache-release/v1' || enabled !== plan.enabled
      || canonical(dto(rule)) !== canonical(plan.desired)) {
    throw new Error('runtime release readback mismatch');
  }
  const s = rule.status;
  if (enabled ? !['IDLE', 'RUNNING'].includes(s?.status) || s?.statusDetail !== 'NONE'
    : s?.status !== 'UNINITIALIZED' || s?.statusDetail !== 'DISABLED') {
    throw new Error('runtime release status mismatch');
  }
  return { verified: true, uid: RULE_UID, sha256: digest(rule.actions[0].configuration.script), enabled };
}

// Injected transport only: callers own attended approval, exclusive edit ownership,
// durable backup/readback and bounded I/O. No retries, /runnow or Item writes.
// On any uncertainty stop; never blindly restore enable state or overwrite drift.
export async function executeRuntimeCacheRelease({ source, version, readRule, backup, write }) {
  let stage = 'snapshot';
  try {
    const snapshot = await readRule();
    const plan = planRuntimeCacheRelease({ rule: snapshot,
      enabled: runtimeRuleEnabledState(snapshot), version, source });
    stage = 'backup';
    const expectedBackupDigest = digest(canonical(snapshot));
    const receipt = await backup(structuredClone(snapshot));
    if (receipt?.verified !== true || receipt.sha256 !== expectedBackupDigest) {
      throw new Error('verified snapshot backup required');
    }
    stage = 'prewrite-recheck';
    const fresh = await readRule();
    if (canonical(fresh) !== canonical(snapshot)) throw new Error('snapshot changed');
    const path = `/rest/rules/${RULE_UID}`;
    if (plan.enabled) {
      stage = 'disable';
      await write({ method: 'POST', path: `${path}/enable`, body: 'false' });
    }
    stage = 'disabled-original-readback';
    verifyRuntimeCacheReadback({ plan: { ...plan, enabled: false, desired: plan.original },
      rule: await readRule(), enabled: false });
    stage = 'replace';
    await write({ method: 'PUT', path, body: structuredClone(plan.desired) });
    stage = 'disabled-replacement-readback';
    verifyRuntimeCacheReadback({ plan: { ...plan, enabled: false },
      rule: await readRule(), enabled: false });
    if (plan.enabled) {
      stage = 'enable';
      await write({ method: 'POST', path: `${path}/enable`, body: 'true' });
    }
    stage = 'final-readback';
    return verifyRuntimeCacheReadback({ plan, rule: await readRule(), enabled: plan.enabled });
  } catch {
    // Do not leak transport errors (which may contain credentials or payloads).
    throw new Error(`runtime cache release stopped at ${stage}; inspect live state before any further write`);
  }
}
