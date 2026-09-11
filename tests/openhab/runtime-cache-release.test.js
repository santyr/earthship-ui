import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { planRuntimeCacheRelease, verifyRuntimeCacheReadback, runtimeRuleEnabledState, RULE_UID } from '../../scripts/runtime-cache-release.mjs';

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
