import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { createRuleHarness } from './rule-harness.js';
import { withGreywaterSocEvidence } from './greywater-evidence.js';

const source = readFileSync(new URL('../../openhab/rules/southoutlet-cycle-current.js', import.meta.url), 'utf8');
const NOW = Date.parse('2026-09-19T18:00:00Z');
const SUN = 'Sun_Position_Elevation';
const PUMPS = ['SouthOutlet_Outlet2_Switch', 'East_Bed_Socket_Outlet_2_Power'];
function harness() {
  const h = withGreywaterSocEvidence(createRuleHarness({ source, now: NOW, states: {
    DCData_Voltage:'53.6', BMS_SOC:'99', BMS_Comms_Status:'OK', SouthOutlet_LowSocCutoff:'45',
    [PUMPS[0]]:'OFF', [PUMPS[1]]:'OFF', SkyCondition:'CLEAR', [SUN]:'25 °',
    Sun_Daylight_Start:'2026-09-19T07:00:00-0600', Sun_Set_Start:'2026-09-19T19:00:00-0600',
    SouthOutlet_LastAutoRun:'2026-09-18T18:00:00Z', SouthOutlet_LastCycleStart:'2026-09-18T18:00:00Z',
    SouthOutlet_ManualRequest:'NULL', SouthOutlet_ManualResult:'NULL', SouthOutlet_LastCycle:'NULL',
  }}));
  h.setThingStatus('astro:sun:local', 'ONLINE'); h.setLastUpdate(SUN, NOW-1000);
  return h;
}
const onCommands = h => h.events.filter(e => e.type==='command' && e.value==='ON');
const request = h => ({itemName:'SouthOutlet_ManualRequest', receivedCommand:JSON.stringify({
  requestId:'astro-freshness-request', requestedAt:new Date(h.nowMs()).toISOString(),
})});
const invalid = [
  ['restored without observation', h=>h.setLastUpdate(SUN,null)],
  ['offline provider', h=>h.setThingStatus('astro:sun:local','OFFLINE')],
  ['unknown provider', h=>h.setThingStatus('astro:sun:local','UNKNOWN')],
  ['stale elevation', h=>h.setLastUpdate(SUN,NOW-120000)],
  ['future observation', h=>h.setLastUpdate(SUN,NOW+1)],
  ['nonphysical elevation', h=>h.setState(SUN,'91 °')],
  ['untyped daylight bound', h=>h.setState('Sun_Set_Start','2026-09-19T19:00:00')],
  ['invalid observation', h=>h.setLastUpdate(SUN,NaN)],
  ['missing sunrise', h=>h.setState('Sun_Daylight_Start','UNDEF')],
  ['missing sunset', h=>h.setState('Sun_Set_Start','NULL')],
  ['previous-day bounds spanning now', h=>{h.setState('Sun_Daylight_Start','2026-09-18T14:00:00-0600');h.setState('Sun_Set_Start','2026-09-19T13:00:00-0600');}],
  ['reversed bounds', h=>h.setState('Sun_Daylight_Start','2026-09-19T20:00:00-0600')],
  ['before daylight', h=>h.setState('Sun_Daylight_Start','2026-09-19T12:00:01-0600')],
  ['at sunset', h=>h.setState('Sun_Set_Start','2026-09-19T12:00:00-0600')],
];
describe('protected greywater native daylight qualification',()=>{
  for(const mode of ['automatic','manual']) {
    it.each(invalid)(`${mode} rejects %s despite positive elevation`,(_name,damage)=>{
      const h=harness(); damage(h); h.execute(mode==='manual'?request(h):undefined);
      expect(onCommands(h)).toHaveLength(0);
      expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=after_dark');
      if(mode==='manual')expect(JSON.parse(h.state('SouthOutlet_ManualResult'))).toMatchObject({status:'denied',reason:'after_dark'});
    });
    it(`${mode} accepts fresh ONLINE daylight with equivalent UTC bounds`,()=>{
      const h=harness(); h.setState('Sun_Daylight_Start','2026-09-19T13:00:00Z');h.setState('Sun_Set_Start','2026-09-20T01:00:00Z');
      h.execute(mode==='manual'?request(h):undefined);expect(onCommands(h)).toHaveLength(1);
    });
  }
  it('stops a running cycle at the bound despite a fresh positive elevation and invalidates completion',()=>{
    const h=harness();h.setState('Sun_Set_Start','2026-09-19T12:01:00-0600');h.execute();expect(onCommands(h)).toHaveLength(1);
    h.advance(60000);h.setLastUpdate(SUN,h.nowMs());h.execute();
    for(const pump of PUMPS)expect(h.state(pump)).toBe('OFF');
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=after_dark');
    h.runNextTimer();expect(h.state('SouthOutlet_LastCycle')).toBe('NULL');expect(onCommands(h)).toHaveLength(1);
  });
  it('stops a running cycle when Astro goes offline',()=>{
    const h=harness();h.execute();h.setThingStatus('astro:sun:local','OFFLINE');h.execute();
    for(const pump of PUMPS)expect(h.state(pump)).toBe('OFF');
    h.runNextTimer();expect(h.state('SouthOutlet_LastCycle')).toBe('NULL');
  });
  it('accepts an observation just within the age limit without using a change timestamp',()=>{
    const h=harness();h.setLastUpdate(SUN,NOW-119999);h.execute();expect(onCommands(h)).toHaveLength(1);
  });
  it.each([
    ['2026-03-08T18:00:00Z','2026-03-08T13:30:00Z','2026-03-09T01:00:00Z'],
    ['2026-11-01T19:00:00Z','2026-11-01T14:00:00Z','2026-11-02T00:00:00Z'],
  ])('uses the household calendar across the DST day at %s',(at,start,end)=>{
    const h=harness();h.advance(Date.parse(at)-NOW);h.setLastUpdate(SUN,h.nowMs()-1000);
    h.setState('Sun_Daylight_Start',start);h.setState('Sun_Set_Start',end);
    h.setState('SouthOutlet_LastCycleStart',new Date(h.nowMs()-86400000).toISOString());
    h.execute();expect(onCommands(h)).toHaveLength(1);
  });

});
