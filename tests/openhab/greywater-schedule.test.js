import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { createRuleHarness } from './rule-harness.js';

const source = readFileSync(new URL('../../openhab/rules/southoutlet-cycle-current.js', import.meta.url), 'utf8');
const noon = Date.parse('2026-09-20T18:24:00Z');
const states = {
  DCData_Voltage: '53.6', BMS_SOC: '99', BMS_Comms_Status: 'OK',
  SouthOutlet_LowSocCutoff: '45', SouthOutlet_Outlet2_Switch: 'OFF',
  East_Bed_Socket_Outlet_2_Power: 'OFF', SkyCondition: 'CLEAR',
  Sun_Position_Elevation: '37', SouthOutlet_LastAutoRun: '2026-09-19T18:00:00Z',
  SouthOutlet_LastCycleStart: '2026-09-19T18:00:00Z',
  SouthOutlet_ManualRequest: 'NULL', SouthOutlet_ManualResult: 'NULL',
  SouthOutlet_LastCycle: 'NULL', SouthOutlet_AutoStatus: 'NULL',
};
const fields = h => Object.fromEntries(h.state('SouthOutlet_AutoStatus').split(',').map(s => {
  const i = s.indexOf('='); return [s.slice(0, i), s.slice(i + 1)];
}));

describe('owner-authored next greywater eligibility', () => {
  it.each([[0, 'east'], [3600000, 'south']])('publishes the next local-hour candidate at %s', (offset, pump) => {
    const h = createRuleHarness({ source, now: noon + offset, states });
    h.execute();
    expect(fields(h)).toMatchObject({ scheduleVersion: '1', scheduling: 'conditional', nextPump: pump,
      nextEligibleAt: new Date(noon + offset + 3600000).toISOString() });
    expect(h.pendingTimers()).toBe(1);
  });
  it('keeps the same earliest time through cooldown and completed cycle', () => {
    const h = createRuleHarness({ source, now: noon, states });
    h.execute(); const first = fields(h).nextEligibleAt;
    h.runNextTimer(); expect(fields(h).nextEligibleAt).toBe(first);
    h.execute(); expect(fields(h)).toMatchObject({ reason: 'cooldown_wait', nextEligibleAt: first });
  });
  it.each([{ Sun_Position_Elevation: '-1' }, { BMS_SOC: '80' }, { BMS_Comms_Status: 'NO-DATA' }])(
    'does not invent a start time behind a safety/daylight gate %j', overrides => {
      const h = createRuleHarness({ source, now: noon, states: { ...states, ...overrides } });
      h.execute(); expect(fields(h).scheduling).toBe('blocked');
      expect(fields(h).nextEligibleAt).toBeUndefined();
      expect(fields(h).nextPump).toBeUndefined();
      expect(h.events.filter(e => e.type === 'command' && e.value === 'ON')).toHaveLength(0);
    });
  it('does not project from a future start clock', () => {
    const h = createRuleHarness({ source, now: noon, states: { ...states,
      SouthOutlet_LastCycleStart: new Date(noon + 3600000).toISOString() } });
    h.execute(); expect(fields(h).scheduling).toBe('unavailable');
    expect(fields(h).nextPump).toBeUndefined();
  });
  it('uses the captured start even before asynchronous Item state catches up', () => {
    const delayed = source.replace('post(CFG.lastCycleStartItem, startAt);', '// delayed registry update');
    const h = createRuleHarness({ source: delayed, now: noon, states });
    h.execute();
    expect(Date.parse(fields(h).nextEligibleAt)).toBe(noon + 3600000);
    expect(fields(h).nextPump).toBe('east');
  });
  it('a display projection failure cannot prevent the stop timer', () => {
    const broken = source.replace('evaluated.plusNanos(Math.round((earliest - evaluatedMs) * 1e6))',
      '(() => { throw new Error("display failure"); })()');
    const h = createRuleHarness({ source: broken, now: noon, states });
    h.execute(); expect(h.pendingTimers()).toBe(1);
    h.runNextTimer(); expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
  });
});
