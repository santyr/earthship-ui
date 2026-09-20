import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { createRuleHarness } from './rule-harness.js';

const source = readFileSync(new URL('../../openhab/rules/southoutlet-cycle-current.js', import.meta.url), 'utf8');
const now = Date.parse('2026-09-19T18:00:00Z'); // local noon, South
const states = {
  DCData_Voltage: '53.6', BMS_SOC: '99', BMS_Comms_Status: 'OK',
  SouthOutlet_LowSocCutoff: '45', SouthOutlet_Outlet2_Switch: 'OFF',
  East_Bed_Socket_Outlet_2_Power: 'OFF', SkyCondition: 'CLEAR',
  Sun_Position_Elevation: '37', SouthOutlet_LastAutoRun: '2026-09-16T21:10:58Z',
  SouthOutlet_LastCycleStart: '2026-09-16T21:10:58Z',
  SouthOutlet_ManualRequest: 'NULL', SouthOutlet_ManualResult: 'NULL',
  SouthOutlet_LastCycle: 'NULL', SouthOutlet_AutoStatus: 'NULL',
};
const ons = h => h.events.filter(e => e.type === 'command' && e.value === 'ON');
function harness({ token, overrides = {}, clock = now, script = source } = {}) {
  if (token !== undefined) script = script.replace('runSouthOutlet(typeof event',
    `cache.shared.put(BUSY_KEY, ${JSON.stringify(token)});\nrunSouthOutlet(typeof event`);
  return createRuleHarness({ source: script, now: clock, states: { ...states, ...overrides } });
}

describe('September 19 live greywater clock and expired-busy repair', () => {
  it('reproduces the old getHour exception and subsequent busy latch', () => {
    const h = harness({ script: source.replace('now().hour()', 'now().getHour()') });
    expect(() => h.execute()).toThrow(/getHour/);
    h.advance(1000);
    h.execute();
    expect(ons(h)).toHaveLength(0);
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=busy');
  });
  it.each([[0, 'SouthOutlet_Outlet2_Switch'], [3600000, 'East_Bed_Socket_Outlet_2_Power']])(
    'selects local-hour pump and completes the unchanged ten-minute cycle', (offset, pump) => {
      const h = harness({ clock: now + offset });
      h.execute();
      expect(ons(h).map(e => e.item)).toEqual([pump]);
      expect(h.pendingTimers()).toBe(1);
      h.runNextTimer();
      expect(h.state(pump)).toBe('OFF');
      expect(h.state('SouthOutlet_LastCycle')).toBe(new Date(now + offset + 600000).toISOString());
    });
  it('recovers an expired token only with both pumps explicitly OFF', () => {
    const h = harness({ token: 'auto:2026-09-16T15:10:58-06:00[America/Denver]' });
    h.execute();
    expect(ons(h)).toHaveLength(1);
  });
  it.each(['auto:2026-09-19T17:59:00Z', 'auto:2026-09-19T19:00:00Z', 'unparseable'])
    ('retains the interlock for token %s', token => {
      const h = harness({ token }); h.execute(); expect(ons(h)).toHaveLength(0);
    });
  it.each([
    { BMS_SOC: '40' }, { BMS_SOC: 'UNDEF' }, { DCData_Voltage: 'UNDEF' },
    { Sun_Position_Elevation: '-1' }, { Sun_Position_Elevation: 'UNDEF' },
    { SouthOutlet_LastCycleStart: '2026-09-19T17:30:00Z' },
  ])('preserves safety and cooldown with %j', overrides => {
    const h = harness({ token: 'auto:2026-09-16T21:00:00Z', overrides });
    h.execute(); expect(ons(h)).toHaveLength(0);
  });
  it('does not bypass a running pump with an old token', () => {
    const h = harness({ token: 'auto:2026-09-16T21:00:00Z', overrides: { SouthOutlet_Outlet2_Switch: 'ON' } });
    h.execute(); expect(ons(h)).toHaveLength(0);
    expect(h.state('SouthOutlet_AutoStatus')).toContain('cycle_active');
  });
});
