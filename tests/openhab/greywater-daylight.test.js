import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { buildGreywaterDaylightRule, DAYLIGHT_TRIGGERS } from '../../scripts/greywater-daylight.mjs';
import { buildSubsetRuleDto } from '../../scripts/openhab-config.mjs';
import { createRuleHarness } from './rule-harness.js';

const source = readFileSync(new URL('../../openhab/rules/southoutlet-cycle-current.js', import.meta.url), 'utf8');
const manifest = JSON.parse(readFileSync(new URL('../../openhab/managed-resources.json', import.meta.url), 'utf8'));
const rule = {
  uid: 'hex_southoutlet_cycle', name: 'Greywater Pumps SOC-Gated Cycle', tags: ['SouthOutlet'],
  triggers: [{ id: '1', type: 'core.ItemStateChangeTrigger', configuration: { itemName: 'DCData_Voltage' } }],
  conditions: [{ id: '3', type: 'core.TimeOfDayCondition', configuration: { startTime: '08:00', endTime: '20:00' } }],
  actions: [{ id: 'owner', type: 'script.ScriptAction', configuration: { type: 'application/javascript', script: source } }],
};
const states = {
  DCData_Voltage: '53.6', BMS_SOC: '99', BMS_Comms_Status: 'OK',
  SouthOutlet_LowSocCutoff: '45', SouthOutlet_Outlet2_Switch: 'OFF',
  East_Bed_Socket_Outlet_2_Power: 'OFF', SkyCondition: 'CLEAR', Sun_Position_Elevation: '1',
  SouthOutlet_LastAutoRun: '2026-09-16T21:10:58Z', SouthOutlet_LastCycleStart: '2026-09-16T21:10:58Z',
  SouthOutlet_ManualRequest: 'NULL', SouthOutlet_ManualResult: 'NULL', SouthOutlet_LastCycle: 'NULL',
};
const ons = h => h.events.filter(e => e.type === 'command' && e.value === 'ON');

describe('greywater daylight schedule transformation', () => {
  it('removes only the fixed window and leaves live source, triggers and other conditions intact', () => {
    const original = structuredClone(rule);
    original.conditions.push({ id: 'other', type: 'unrelated', configuration: {} });
    const result = buildGreywaterDaylightRule(original, source);
    expect(result.actions).toEqual(original.actions);
    expect(result.triggers.slice(0, original.triggers.length)).toEqual(original.triggers);
    expect(result.conditions).toEqual([original.conditions[1]]);
    expect(original.conditions).toHaveLength(2);
    expect(result.tags).toEqual(original.tags);
    expect(result.triggers.slice(1)).toEqual(DAYLIGHT_TRIGGERS);
    expect(buildGreywaterDaylightRule(result, source)).toEqual(result);
  });
  it('refuses unknown time gates, trigger collisions and source drift', () => {
    const changed = structuredClone(rule);
    changed.conditions[0].configuration.startTime = '09:00';
    expect(() => buildGreywaterDaylightRule(changed, source)).toThrow(/unreviewed/);
    expect(() => buildGreywaterDaylightRule(rule, source + '\n')).toThrow(/reviewed/);
    const conflict = structuredClone(rule);
    conflict.triggers.push({ id: 'cron', type: 'unknown', configuration: {} });
    expect(() => buildGreywaterDaylightRule(conflict, source)).toThrow(/conflicting/);
  });
  it('keeps future managed deployments on daylight policy', () => {
    const subset = manifest.subsets.greywater;
    const result = buildSubsetRuleDto({ subset, subsetName: 'greywater', source, originalRule: rule });
    expect(result.conditions).toEqual([]);
    for (const trigger of DAYLIGHT_TRIGGERS) expect(result.triggers).toContainEqual(trigger);
  });
});

describe('daylight control with unchanged voltage and SoC', () => {
  it.each(['2026-09-20T13:00:00Z', '2026-06-20T02:15:00Z'])(
    'allows an eligible sun-above-horizon cycle outside the old window at %s', clock => {
      const h = createRuleHarness({ source, now: Date.parse(clock), states: {
        ...states, SouthOutlet_LastCycleStart: new Date(Date.parse(clock) - 86400000).toISOString(),
      } });
      h.execute();
      expect(ons(h)).toHaveLength(1);
    });
  it('starts on the sunrise change, stops at zero elevation, and invalidates the completion timer', () => {
    const h = createRuleHarness({ source, now: Date.parse('2026-09-20T13:00:00Z'),
      states: { ...states, Sun_Position_Elevation: '-0.1' } });
    h.execute(); expect(ons(h)).toHaveLength(0);
    h.setState('Sun_Position_Elevation', '0.1'); h.execute();
    expect(ons(h)).toHaveLength(1);
    h.advance(60000); h.setState('Sun_Position_Elevation', '0'); h.execute();
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(h.state('East_Bed_Socket_Outlet_2_Power')).toBe('OFF');
    const count = h.events.length;
    h.runNextTimer(); expect(h.events).toHaveLength(count);
    expect(h.state('SouthOutlet_LastCycle')).toBe('NULL');
  });
  it.each([{ Sun_Position_Elevation: 'UNDEF' }, { BMS_SOC: '40' },
    { BMS_Comms_Status: 'NO-DATA' }, { DCData_Voltage: 'UNDEF' },
    { SkyCondition: 'CLOUDY', BMS_SOC: '95' }])('preserves safety gates: %j', overrides => {
    const h = createRuleHarness({ source, now: Date.parse('2026-09-20T13:00:00Z'), states: { ...states, ...overrides } });
    h.execute(); expect(ons(h)).toHaveLength(0);
  });
});
