import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { createRuleHarness } from './rule-harness.js';
import { withGreywaterSocEvidence } from './greywater-evidence.js';

const source = readFileSync(new URL('../../openhab/rules/southoutlet-cycle-current.js', import.meta.url), 'utf8');
const now = Date.parse('2026-10-03T18:00:00Z');
const requestId = 'recovery-debt-20261003';
const interrupted = JSON.stringify({ version: 'greywater-request-ledger/v1', entries: [{
  requestId, status: 'accepted', reason: 'accepted', at: '2026-10-03T17:50:00Z',
}] });

function harness(overrides = {}) {
  return withGreywaterSocEvidence(createRuleHarness({ source, now, states: {
    DCData_Voltage: '53.6', BMS_SOC: '99', BMS_Comms_Status: 'OK',
    SouthOutlet_LowSocCutoff: '45', SouthOutlet_Outlet2_Switch: 'OFF',
    East_Bed_Socket_Outlet_2_Power: 'OFF', SkyCondition: 'CLEAR', Sun_Position_Elevation: '37',
    SouthOutlet_LastAutoRun: '2026-10-03T10:00:00Z', SouthOutlet_LastCycleStart: '2026-10-03T10:00:00Z',
    SouthOutlet_ManualRequest: interrupted, SouthOutlet_ManualResult: 'NULL',
    SouthOutlet_LastCycle: 'NULL', SouthOutlet_AutoStatus: 'NULL', ...overrides,
  }, histories: { SouthOutlet_ManualRequest: [interrupted] } }));
}
const onCommands = h => h.events.filter(e => e.type === 'command' && e.value === 'ON');
const nextRequest = h => ({ itemName: 'SouthOutlet_ManualRequest', receivedCommand: JSON.stringify({
  requestId: 'new-manual-20261003', requestedAt: new Date(h.nowMs()).toISOString(),
}) });

describe('known interrupted-ledger durability obligation', () => {
  it.each(['persist', 'readback'])('does not start after %s recovery failure', failure => {
    const h = harness();
    if (failure === 'persist') h.setPersistFailure(new Error('synthetic jdbc offline'));
    else h.delayNextPersistVisibility(25);
    h.execute();
    expect(onCommands(h)).toHaveLength(0);
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=ledger_recovery_failed');
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(h.state('East_Bed_Socket_Outlet_2_Power')).toBe('OFF');
  });

  it('retains the obligation when a failed write changed only the in-memory ledger', () => {
    const h = harness(); h.setPersistFailure(new Error('synthetic jdbc offline'));
    h.execute();
    expect(JSON.parse(h.state('SouthOutlet_ManualRequest')).entries[0].status).toBe('failed');
    for (let tick = 0; tick < 4; tick++) { h.advance(60000); h.execute(); }
    h.execute(nextRequest(h));
    expect(onCommands(h)).toHaveLength(0);
    expect(JSON.parse(h.state('SouthOutlet_ManualResult'))).toMatchObject({
      status: 'denied', reason: 'ledger_recovery_failed',
    });
  });

  it('recovers durability before returning to normal automatic cycles', () => {
    const h = harness(); h.setPersistFailure(new Error('synthetic jdbc offline')); h.execute();
    h.setPersistFailure(null); h.advance(60000); h.execute();
    expect(onCommands(h)).toHaveLength(0);
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=ledger_recovered');
    const persisted = h.events.filter(e => e.type === 'persist').at(-1);
    expect(JSON.parse(persisted.value).entries[0]).toMatchObject({
      requestId, status: 'failed', reason: 'restart_uncertain',
    });
    h.advance(60000); h.execute();
    expect(onCommands(h)).toHaveLength(1);
  });

  it('also retains failed recovery initiated by a new manual request', () => {
    const h = harness(); h.setPersistFailure(new Error('synthetic jdbc offline'));
    h.execute(nextRequest(h)); h.advance(60000); h.execute();
    expect(onCommands(h)).toHaveLength(0);
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=ledger_recovery_failed');
  });

  it('does not clear pending recovery after an unowned ledger replacement', () => {
    const h = harness(); h.setPersistFailure(new Error('synthetic jdbc offline')); h.execute();
    h.setState('SouthOutlet_ManualRequest', JSON.stringify({ version: 'greywater-request-ledger/v1',
      entries: [{ requestId: 'unowned-new-ledger', status: 'completed', reason: 'completed',
        at: '2026-10-03T17:51:00Z' }] }));
    h.setPersistFailure(null); h.advance(60000); h.execute();
    expect(onCommands(h)).toHaveLength(0);
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=ledger_recovery_failed');
  });

  it('rejects unowned terminal changes even when they reuse the interrupted request ID', () => {
    const h = harness(); h.setPersistFailure(new Error('synthetic jdbc offline')); h.execute();
    const replacement = JSON.parse(h.state('SouthOutlet_ManualRequest'));
    replacement.entries[0].status = 'completed'; replacement.entries[0].reason = 'completed';
    h.setState('SouthOutlet_ManualRequest', JSON.stringify(replacement));
    h.setPersistFailure(null); h.advance(60000); h.execute();
    expect(onCommands(h)).toHaveLength(0);
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=ledger_recovery_failed');
  });

  it('retains pending recovery when the registry becomes unreadable', () => {
    const h = harness(); h.setPersistFailure(new Error('synthetic jdbc offline')); h.execute();
    h.setState('SouthOutlet_ManualRequest', 'malformed');
    h.setPersistFailure(null); h.advance(60000); h.execute();
    expect(onCommands(h)).toHaveLength(0);
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=ledger_recovery_failed');
  });

  it('rechecks JDBC if volatile recovery state is lost while the registry is terminal', () => {
    const h = harness(); h.setPersistFailure(new Error('synthetic jdbc offline')); h.execute();
    h.clearVolatileCache(); h.advance(60000); h.execute();
    expect(onCommands(h)).toHaveLength(0);
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=ledger_recovery_failed');
    h.setPersistFailure(null); h.advance(60000); h.execute();
    expect(onCommands(h)).toHaveLength(0);
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=ledger_recovered');
    h.advance(60000); h.execute(); expect(onCommands(h)).toHaveLength(1);
  });

  it('does not let a manual request bypass terminal recovery after volatile state loss', () => {
    const h = harness(); h.setPersistFailure(new Error('synthetic jdbc offline')); h.execute();
    h.clearVolatileCache(); h.advance(60000); h.execute(nextRequest(h));
    expect(onCommands(h)).toHaveLength(0);
    expect(JSON.parse(h.state('SouthOutlet_ManualResult'))).toMatchObject({
      status: 'denied', reason: 'ledger_recovery_failed',
    });
  });

  it('does not change automatic policy for an unreadable ledger with no known recovery debt', () => {
    const h = harness({ SouthOutlet_ManualRequest: 'malformed' });
    h.execute();
    expect(onCommands(h)).toHaveLength(1);
  });

  it('bounds repeated delayed readback failures before a successful retry', () => {
    const h = harness();
    for (let tick = 0; tick < 3; tick++) {
      h.delayNextPersistVisibility(25); h.execute(); h.advance(60000);
      expect(onCommands(h)).toHaveLength(0);
    }
    h.delayNextPersistVisibility(0); h.execute();
    expect(onCommands(h)).toHaveLength(0);
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=ledger_recovered');
    h.advance(60000); h.execute(); expect(onCommands(h)).toHaveLength(1);
  });

  it.each(['SouthOutlet_Outlet2_Switch', 'East_Bed_Socket_Outlet_2_Power'])
    ('stops an orphaned %s even when recovery persistence fails', pump => {
      const h = harness({ [pump]: 'ON' }); h.setPersistFailure(new Error('synthetic jdbc offline'));
      h.execute();
      expect(h.state(pump)).toBe('OFF');
      expect(onCommands(h)).toHaveLength(0);
    });

  it('keeps the original BMS safety refusal ahead of recovery diagnostics', () => {
    const h = harness({ BMS_Comms_Status: 'STALE', SouthOutlet_Outlet2_Switch: 'ON' });
    h.setPersistFailure(new Error('synthetic jdbc offline')); h.execute();
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(h.state('SouthOutlet_AutoStatus')).toContain('reason=bms_comms_stale');
  });
});
