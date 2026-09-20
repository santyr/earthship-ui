import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { planRuntimeCacheRelease, verifyRuntimeCacheReadback, runtimeRuleEnabledState, executeRuntimeCacheRelease, RULE_UID } from '../../scripts/runtime-cache-release.mjs';

const source = readFileSync(new URL('../../openhab/rules/bms-runtime-estimator.js', import.meta.url), 'utf8');
const oldFunction = `function overnightW() {
  const today = time.toZDT().toLocalDate().toString();
  let night = cache.private.get("p_night");
  if (!night || night.day !== today) {
    let w = NaN;
    try {
      const start = time.toZDT().minusDays(1).withHour(20).withMinute(30).withSecond(0);
      const end = time.toZDT().withHour(6).withMinute(0).withSecond(0);
      const a = items.getItem("ConextGateway_ACPowerValue").persistence.averageBetween(start, end);
      w = (a == null) ? NaN : (typeof a === "number" ? a : parseFloat(a.numericState ?? a.state));
    } catch (e) { /* fallback below */ }
    night = { day: today, w: Number.isFinite(w) ? w : NIGHT_FALLBACK_W };
    cache.private.put("p_night", night);
  }
  return night.w;
}

`;
const originalSource = source.slice(0, source.indexOf('function overnightW()')) + oldFunction + source.slice(source.indexOf('// projection(forceEvening)'));
function options(enabled = true) {
  return { source, enabled, version: '5.2.1', rule: { uid: RULE_UID, name: 'original name',
    description: 'original description', tags: ['Battery'], visibility: 'VISIBLE', configuration: {},
    conditions: [], triggers: [{ id: '1', configuration: { itemName: 'BMS_TimeToDischarge_Min' }, type: 'core.ItemStateUpdateTrigger' }],
    actions: [{ inputs: {}, id: '2', type: 'script.ScriptAction', configuration: { type: 'application/javascript', script: originalSource } }],
    editable: true, configDescriptions: [], templateState: 'no-template',
    status: enabled ? { status: 'IDLE', statusDetail: 'NONE' } : { status: 'UNINITIALIZED', statusDetail: 'DISABLED' } } };
}

describe('exact runtime-cache release planner', () => {
  it('derives enable state only from explicit known OpenHAB statuses', () => {
    expect(runtimeRuleEnabledState(options().rule)).toBe(true);
    expect(runtimeRuleEnabledState(options(false).rule)).toBe(false);
    expect(() => runtimeRuleEnabledState({status:{status:'UNINITIALIZED',statusDetail:'HANDLER_INITIALIZING_ERROR'}})).toThrow();
    expect(() => runtimeRuleEnabledState({})).toThrow();
  });
  it.each([true, false])('preserves metadata/enable=%s and changes only source', enabled => {
    const input = options(enabled), before = structuredClone(input);
    const plan = planRuntimeCacheRelease(input);
    const changed = structuredClone(plan.desired);
    changed.actions[0].configuration.script = originalSource;
    expect(changed).toEqual(plan.original); expect(input).toEqual(before);
    expect(plan.operations.map(o => `${o.method} ${o.path}`)).toEqual(enabled ? [
      `POST /rest/rules/${RULE_UID}/enable`, `PUT /rest/rules/${RULE_UID}`, `POST /rest/rules/${RULE_UID}/enable`,
    ] : [`PUT /rest/rules/${RULE_UID}`]);
    expect(verifyRuntimeCacheReadback({ plan, rule: { ...input.rule, ...plan.desired }, enabled }).verified).toBe(true);
  });
  it.each(['version', 'source', 'uid', 'running', 'trigger', 'extraAction', 'extraField', 'originalSource'])('rejects %s drift', kind => {
    const input = options();
    if (kind === 'version') input.version = '5.2.0';
    if (kind === 'source') input.source += ' ';
    if (kind === 'uid') input.rule.uid = 'another-rule';
    if (kind === 'running') input.rule.status.status = 'RUNNING';
    if (kind === 'trigger') input.rule.triggers[0].configuration.itemName = 'Other';
    if (kind === 'extraAction') input.rule.actions.push(input.rule.actions[0]);
    if (kind === 'extraField') input.rule.unrecognized = true;
    if (kind === 'originalSource') input.rule.actions[0].configuration.script += ' ';
    expect(() => planRuntimeCacheRelease(input)).toThrow();
  });
  it('readback refuses metadata drift and incorrect enabled state', () => {
    const input = options(), plan = planRuntimeCacheRelease(input);
    const rule = { ...input.rule, ...plan.desired };
    expect(() => verifyRuntimeCacheReadback({ plan, rule, enabled: false })).toThrow();
    rule.tags = [];
    expect(() => verifyRuntimeCacheReadback({ plan, rule, enabled: true })).toThrow();
  });
});

describe('staged runtime-cache release execution', () => {
  function harness(enabled = true, hooks = {}) {
    let rule = options(enabled).rule;
    let reads = 0;
    const events = [];
    const input = {
      source, version: '5.2.1',
      readRule: async () => {
        events.push('read');
        hooks.read?.(rule, ++reads);
        return structuredClone(rule);
      },
      backup: async snapshot => {
        events.push('backup');
        if (hooks.backup) return hooks.backup(snapshot);
        const text = JSON.stringify(snapshot, (_key, v) => v && typeof v === 'object' && !Array.isArray(v)
          ? Object.fromEntries(Object.keys(v).sort().map(k => [k, v[k]])) : v);
        return { verified: true, sha256: createHash('sha256').update(text).digest('hex') };
      },
      write: async operation => {
        events.push(operation.method === 'PUT' ? 'replace' : `enable=${operation.body}`);
        hooks.write?.(operation);
        if (operation.method === 'PUT') rule = { ...rule, ...structuredClone(operation.body) };
        else rule.status = operation.body === 'true'
          ? { status: 'IDLE', statusDetail: 'NONE' }
          : { status: 'UNINITIALIZED', statusDetail: 'DISABLED' };
      },
    };
    return { input, events };
  }
  it.each([true, false])('verifies every stage and preserves original enable=%s', async enabled => {
    const h = harness(enabled);
    expect(await executeRuntimeCacheRelease(h.input)).toMatchObject({ verified: true, enabled });
    expect(h.events).toEqual(['read', 'backup', 'read', ...(enabled ? ['enable=false'] : []),
      'read', 'replace', 'read', ...(enabled ? ['enable=true'] : []), 'read']);
  });
  it.each([{}, { verified: true, sha256: 'wrong' }])('refuses an unverified backup', async receipt => {
    const h = harness(true, { backup: () => receipt });
    await expect(executeRuntimeCacheRelease(h.input)).rejects.toThrow('stopped at backup');
    expect(h.events).toEqual(['read', 'backup']);
  });
  it.each([2, 3, 4])('stops on concurrent metadata drift at read %s', async at => {
    const h = harness(true, { read: (rule, count) => { if (count === at) rule.tags.push('concurrent-edit'); } });
    await expect(executeRuntimeCacheRelease(h.input)).rejects.toThrow('inspect live state');
    expect(h.events).not.toContain('enable=true');
    if (at < 4) expect(h.events).not.toContain('replace');
  });
  it('does not write while disable readback remains running', async () => {
    const h = harness(true, { read: (rule, count) => {
      if (count === 3) rule.status = { status: 'RUNNING', statusDetail: 'NONE' };
    } });
    await expect(executeRuntimeCacheRelease(h.input)).rejects.toThrow('disabled-original-readback');
    expect(h.events).not.toContain('replace');
  });
  it('does not reenable a replacement whose script readback differs', async () => {
    const h = harness(true, { read: (rule, count) => {
      if (count === 4) rule.actions[0].configuration.script += '\n// unexpected';
    } });
    await expect(executeRuntimeCacheRelease(h.input)).rejects.toThrow('disabled-replacement-readback');
    expect(h.events).not.toContain('enable=true');
  });
  it('refuses an unreviewed initial script without backing up or writing', async () => {
    const h = harness(true, { read: rule => { rule.actions[0].configuration.script += ' '; } });
    await expect(executeRuntimeCacheRelease(h.input)).rejects.toThrow('stopped at snapshot');
    expect(h.events).toEqual(['read']);
  });
  it.each(['false', 'PUT', 'true'])('does not retry or leak an ambiguous %s failure', async failure => {
    const h = harness(true, { write: op => {
      if (op.method === failure || op.body === failure) throw new Error('SECRET transport payload');
    } });
    let error;
    try { await executeRuntimeCacheRelease(h.input); } catch (e) { error = e; }
    expect(error.message).toMatch(/stopped at (disable|replace|enable);/);
    expect(error.message).not.toContain('SECRET');
    const writes = h.events.filter(e => e !== 'read' && e !== 'backup');
    expect(writes).toEqual(failure === 'false' ? ['enable=false']
      : failure === 'PUT' ? ['enable=false', 'replace'] : ['enable=false', 'replace', 'enable=true']);
  });
  it('rejects a final error status instead of reporting completion', async () => {
    const h = harness(true, { read: (rule, count) => {
      if (count === 5) rule.status = { status: 'UNINITIALIZED', statusDetail: 'HANDLER_INITIALIZING_ERROR' };
    } });
    await expect(executeRuntimeCacheRelease(h.input)).rejects.toThrow('final-readback');
  });
});
