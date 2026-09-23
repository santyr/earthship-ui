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
  it('reproduces the old getHour exception but clears its unactuated token', () => {
    const h = harness({ script: source.replace('now().hour()', 'now().getHour()') });
    expect(() => h.execute()).toThrow(/getHour/);
    h.advance(1000);
    h.execute();
    expect(ons(h)).toHaveLength(0);
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=cycle_interrupted');
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
  });
  it.each([[0, 'SouthOutlet_Outlet2_Switch'], [3600000, 'East_Bed_Socket_Outlet_2_Power']])(
    'selects local-hour pump and completes the live fifteen-minute cycle', (offset, pump) => {
      const h = harness({ clock: now + offset });
      h.execute();
      expect(ons(h).map(e => e.item)).toEqual([pump]);
      expect(h.pendingTimers()).toBe(1);
      h.runNextTimer();
      expect(h.state(pump)).toBe('OFF');
      expect(h.state('SouthOutlet_LastCycle')).toBe(new Date(now + offset + 900000).toISOString());
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
  it('forces a running pump OFF when its timer token is expired', () => {
    const h = harness({ token: 'auto:2026-09-16T21:00:00Z', overrides: { SouthOutlet_Outlet2_Switch: 'ON' } });
    h.execute(); expect(ons(h)).toHaveLength(0);
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=cycle_timer_expired');
    expect(h.state('SouthOutlet_LastCycle')).toBe('NULL');
  });
  it('keeps a single pump ON while its timer token is still fresh', () => {
    const h = harness({ token: 'auto:2026-09-19T17:55:00Z', overrides: { SouthOutlet_Outlet2_Switch: 'ON' } });
    h.execute();
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('ON');
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=cycle_active');
  });
  it('fails closed on an unparseable timer token with a pump ON', () => {
    const h = harness({ token: 'unparseable', overrides: { SouthOutlet_Outlet2_Switch: 'ON' } });
    h.execute();
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=cycle_timer_invalid');
  });
});

describe('cycle timer ownership after interruption', () => {
  it('invalidates a timer when its pump turns OFF before completion', () => {
    const h = harness(); h.execute();
    h.advance(7 * 60000); h.setState('SouthOutlet_Outlet2_Switch', 'OFF');
    h.execute();
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=cycle_interrupted');
    expect(h.state('SouthOutlet_LastCycle')).toBe('NULL');
    const count = h.events.length;
    h.runNextTimer();
    expect(h.events).toHaveLength(count);
    expect(h.state('SouthOutlet_LastCycle')).toBe('NULL');
  });

  it('does not complete when the pump turns OFF just before its callback', () => {
    const h = harness(); h.execute();
    h.advance(15 * 60000); h.setState('SouthOutlet_Outlet2_Switch', 'OFF');
    h.runNextTimer();
    expect(h.state('SouthOutlet_LastCycle')).toBe('NULL');
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=cycle_interrupted');
  });

  it('fails an interrupted manual request without a completion receipt', () => {
    const h = harness();
    h.execute({ itemName: 'SouthOutlet_ManualRequest', receivedCommand: JSON.stringify({
      requestId: 'manual-early-off-20260919', requestedAt: new Date(now).toISOString(),
    }) });
    h.advance(15 * 60000); h.setState('SouthOutlet_Outlet2_Switch', 'OFF');
    h.runNextTimer();
    expect(h.state('SouthOutlet_LastCycle')).toBe('NULL');
    expect(JSON.parse(h.state('SouthOutlet_ManualRequest')).entries[0]).toMatchObject({
      status: 'failed', reason: 'cycle_interrupted',
    });
    expect(JSON.parse(h.state('SouthOutlet_ManualResult'))).toMatchObject({
      status: 'failed', reason: 'cycle_interrupted',
    });
  });

  it('stops a pump whose timer did not complete by the next cron', () => {
    const h = harness(); h.execute();
    h.advance(16 * 60000); h.execute();
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=cycle_timer_expired');
    expect(h.state('SouthOutlet_LastCycle')).toBe('NULL');
    const count = h.events.length;
    h.runNextTimer();
    expect(h.events).toHaveLength(count);
  });

  it.each([
    ['Sun_Position_Elevation', '-1'],
    ['BMS_SOC', '40'],
    ['DCData_Voltage', 'UNDEF'],
  ])('does not report completion after %s invalidates its owner', (item, value) => {
    const h = harness(); h.execute();
    h.advance(60000); h.setState(item, value); h.execute();
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    const count = h.events.length;
    const status = h.state('SouthOutlet_AutoStatus');
    h.runNextTimer();
    expect(h.events).toHaveLength(count);
    expect(h.state('SouthOutlet_LastCycle')).toBe('NULL');
    expect(h.state('SouthOutlet_AutoStatus')).toBe(status);
  });

  it('cannot command OFF or complete a newer cycle after ownership changes', () => {
    const h = harness(); h.execute();
    h.advance(60000); h.setState('Sun_Position_Elevation', '-1'); h.execute();
    h.advance(60 * 60000); h.setState('Sun_Position_Elevation', '37'); h.execute();
    expect(h.pendingTimers()).toBe(2);
    expect(h.state('East_Bed_Socket_Outlet_2_Power')).toBe('ON');
    const count = h.events.length;
    h.runNextTimer(); // delayed callback for the now-invalid South owner
    expect(h.events).toHaveLength(count);
    expect(h.state('East_Bed_Socket_Outlet_2_Power')).toBe('ON');
    expect(h.state('SouthOutlet_LastCycle')).toBe('NULL');
    h.runNextTimer(); // current owner still completes normally
    expect(h.state('East_Bed_Socket_Outlet_2_Power')).toBe('OFF');
    expect(h.state('SouthOutlet_AutoStatus')).toContain('cycle_completed');
  });

  it('cannot replace a recovered interrupted manual result with completion', () => {
    const h = harness();
    h.execute({ itemName: 'SouthOutlet_ManualRequest', receivedCommand: JSON.stringify({
      requestId: 'manual-curfew-20260919', requestedAt: new Date(now).toISOString(),
    }) });
    expect(JSON.parse(h.state('SouthOutlet_ManualRequest')).entries[0].status).toBe('accepted');
    h.advance(60000); h.setState('Sun_Position_Elevation', '-1'); h.execute();
    h.advance(1000); h.execute(); // normal interrupted-ledger recovery
    expect(JSON.parse(h.state('SouthOutlet_ManualRequest')).entries[0].status).toBe('failed');
    const count = h.events.length;
    const ledger = h.state('SouthOutlet_ManualRequest');
    const result = h.state('SouthOutlet_ManualResult');
    h.runNextTimer();
    expect(h.events).toHaveLength(count);
    expect(h.state('SouthOutlet_ManualRequest')).toBe(ledger);
    expect(h.state('SouthOutlet_ManualResult')).toBe(result);
    expect(h.state('SouthOutlet_LastCycle')).toBe('NULL');
  });
});
