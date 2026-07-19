import { readFile } from 'node:fs/promises';
import { beforeAll, describe, expect, it } from 'vitest';
import { createRuleHarness } from './rule-harness.js';

const RULE_URL = new URL('../../openhab/rules/southoutlet-cycle.js', import.meta.url);
const MANIFEST_URL = new URL('../../openhab/managed-resources.json', import.meta.url);

const NOON = Date.parse('2026-07-18T12:00:00.000Z');
const SIX_HOURS_AGO = new Date(NOON - (6 * 60 * 60 * 1000)).toISOString();

let ruleSource;

beforeAll(async () => {
  ruleSource = await readFile(RULE_URL, 'utf8');
});

function baseStates(overrides = {}) {
  return {
    DCData_Voltage: '53.6',
    BMS_SOC: '95',
    BMS_Comms_Status: 'OK',
    SouthOutlet_LowSocCutoff: '45',
    SouthOutlet_Outlet2_Switch: 'OFF',
    SkyCondition: 'CLEAR',
    Sun_Position_Elevation: '37.3',
    SouthOutlet_LastAutoRun: SIX_HOURS_AGO,
    SouthOutlet_LastCycleStart: SIX_HOURS_AGO,
    SouthOutlet_ManualRequest: 'NULL',
    SouthOutlet_ManualResult: 'NULL',
    SouthOutlet_LastCycle: 'NULL',
    SouthOutlet_AutoStatus: 'NULL',
    ...overrides,
  };
}

function gwRequest(requestId, requestedAt = '2026-07-18T12:00:00.000Z') {
  return JSON.stringify({ requestId, requestedAt });
}

function gwLedger(entries) {
  return JSON.stringify({ version: 'greywater-request-ledger/v1', entries });
}

function results(h) {
  return h.events
    .filter((e) => e.type === 'update' && e.item === 'SouthOutlet_ManualResult')
    .map((e) => JSON.parse(e.value));
}

function outletCommands(h) {
  return h.events
    .filter((e) => e.type === 'command' && e.item === 'SouthOutlet_Outlet2_Switch')
    .map((e) => e.value);
}

function onCount(h) {
  return outletCommands(h).filter((v) => v === 'ON').length;
}

function ledger(h) {
  const raw = h.state('SouthOutlet_ManualRequest');
  return (raw === 'NULL' || raw === 'UNDEF') ? null : JSON.parse(raw);
}

function autoStatus(h) {
  return h.state('SouthOutlet_AutoStatus');
}

function auto(overrides = {}) {
  const h = createRuleHarness({ source: ruleSource, states: baseStates(overrides) });
  h.execute();
  return h;
}

describe('[RED:T15A-1] canonical greywater rule resources', () => {
  it('exposes the versioned owner, items, capability, and request trigger', async () => {
    const [source, manifest] = await Promise.all([
      readFile(RULE_URL, 'utf8'),
      readFile(MANIFEST_URL, 'utf8').then(JSON.parse),
    ]);
    const greywater = manifest.subsets?.greywater;
    expect(greywater?.capability).toBe('greywater-request-v1');
    expect(greywater?.rule).toMatchObject({
      uid: 'hex_southoutlet_cycle',
      source: 'openhab/rules/southoutlet-cycle.js',
    });
    expect(source).toContain('EARTHSHIP_SOUTHOUTLET_VERSION');
    expect(greywater?.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ name: 'SouthOutlet_ManualRequest', type: 'String' }),
      expect.objectContaining({ name: 'SouthOutlet_ManualResult', type: 'String' }),
      expect.objectContaining({ name: 'SouthOutlet_LastCycleStart', type: 'DateTime' }),
      expect.objectContaining({ name: 'SouthOutlet_LastCycle', type: 'String' }),
    ]));
    expect(greywater?.rule?.triggers).toEqual(expect.arrayContaining([
      expect.objectContaining({
        type: 'core.ItemCommandTrigger',
        configuration: { itemName: 'SouthOutlet_ManualRequest' },
      }),
    ]));
    expect(greywater?.persistence).toMatchObject({
      serviceId: 'jdbc',
      strategy: 'everyChange',
      restoreOnStartup: true,
      items: expect.arrayContaining(['SouthOutlet_ManualRequest', 'SouthOutlet_LastCycleStart']),
    });
  });
});

describe('automatic SoC + sky eligibility', () => {
  it('starts a cycle on CLEAR sky at SoC 91 and denies at SoC 89', () => {
    const start = auto({ SkyCondition: 'CLEAR', BMS_SOC: '91' });
    expect(onCount(start)).toBe(1);
    expect(start.state('SouthOutlet_Outlet2_Switch')).toBe('ON');
    expect(start.state('SouthOutlet_LastCycleStart')).not.toBe(SIX_HOURS_AGO);
    expect(autoStatus(start)).toMatch(/reason=cycle_started/);

    const deny = auto({ SkyCondition: 'CLEAR', BMS_SOC: '89' });
    expect(onCount(deny)).toBe(0);
    expect(autoStatus(deny)).toMatch(/reason=low_soc/);
  });

  it('requires SoC >= 98 when the sky is not CLEAR (CLOUDY and NULL)', () => {
    expect(onCount(auto({ SkyCondition: 'CLOUDY', BMS_SOC: '97' }))).toBe(0);
    expect(onCount(auto({ SkyCondition: 'NULL', BMS_SOC: '97' }))).toBe(0);
    expect(onCount(auto({ SkyCondition: 'CLOUDY', BMS_SOC: '98.5' }))).toBe(1);
  });
});

describe('automatic timing', () => {
  it('runs the outlet ON for exactly 5 minutes then OFF', () => {
    const h = auto({ SkyCondition: 'CLEAR', BMS_SOC: '95' });
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('ON');
    const timer = h.events.find((e) => e.type === 'timer');
    expect(timer.at).toBe(NOON + (5 * 60 * 1000));

    h.runNextTimer();
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(outletCommands(h)).toEqual(['ON', 'OFF', 'OFF']); // redundant safe-OFF backstop
    expect(h.state('SouthOutlet_LastCycle')).not.toBe('NULL');
    expect(autoStatus(h)).toMatch(/reason=cycle_completed/);
  });

  it('waits for the 230-minute start-to-start gap', () => {
    const recent = new Date(NOON - (10 * 60 * 1000)).toISOString();
    const h = auto({
      SkyCondition: 'CLEAR',
      BMS_SOC: '95',
      SouthOutlet_LastCycleStart: recent,
      SouthOutlet_LastAutoRun: recent,
    });
    expect(onCount(h)).toBe(0);
    expect(autoStatus(h)).toMatch(/reason=cooldown_wait/);
  });
});

describe('after-dark curfew', () => {
  it('never starts after sunset (elevation <= 0)', () => {
    const h = auto({ Sun_Position_Elevation: '-1' });
    expect(onCount(h)).toBe(0);
    expect(autoStatus(h)).toMatch(/reason=after_dark/);
  });

  it('forces a running cycle OFF once caught past sunset', () => {
    const h = auto({ SkyCondition: 'CLEAR', BMS_SOC: '95' });
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('ON');

    h.setState('Sun_Position_Elevation', '-1');
    h.execute();
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(autoStatus(h)).toMatch(/reason=after_dark/);
  });

  it('fails closed when astro elevation is NULL/UNDEF', () => {
    expect(autoStatus(auto({ Sun_Position_Elevation: 'NULL' }))).toMatch(/reason=after_dark/);
    expect(onCount(auto({ Sun_Position_Elevation: 'UNDEF' }))).toBe(0);
  });
});

describe('aerobic fallback never bypasses SoC or curfew', () => {
  const stale = new Date(NOON - (25 * 60 * 60 * 1000)).toISOString();

  it('does NOT start after 24h when SoC is below the sky threshold', () => {
    const h = auto({
      SkyCondition: 'CLOUDY',
      BMS_SOC: '97',
      SouthOutlet_LastCycleStart: stale,
      SouthOutlet_LastAutoRun: stale,
    });
    expect(onCount(h)).toBe(0);
    expect(autoStatus(h)).toMatch(/reason=low_soc/);
  });

  it('starts after 24h when SoC clears the threshold in daylight', () => {
    const h = auto({
      SkyCondition: 'CLOUDY',
      BMS_SOC: '98.5',
      SouthOutlet_LastCycleStart: stale,
      SouthOutlet_LastAutoRun: stale,
    });
    expect(onCount(h)).toBe(1);
    expect(autoStatus(h)).toMatch(/mode=aerobic_fallback_24h/);
  });
});

describe('BMS / voltage fail-closed chain', () => {
  it('forces OFF when BMS comms are stale beyond 1800s', () => {
    const h = auto({ BMS_Comms_Status: 'STALE age=2000s', SouthOutlet_Outlet2_Switch: 'ON' });
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(autoStatus(h)).toMatch(/reason=bms_comms_stale/);
  });

  it('tolerates a fresh STALE reading within the window', () => {
    expect(autoStatus(auto({ BMS_Comms_Status: 'STALE age=100s', SkyCondition: 'CLEAR', BMS_SOC: '95' })))
      .toMatch(/reason=cycle_started/);
  });

  it('forces OFF on invalid SoC and invalid voltage', () => {
    const soc = auto({ BMS_SOC: 'NULL', SouthOutlet_Outlet2_Switch: 'ON' });
    expect(soc.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(autoStatus(soc)).toMatch(/reason=invalid_soc/);

    const volts = auto({ DCData_Voltage: 'NULL', SouthOutlet_Outlet2_Switch: 'ON' });
    expect(volts.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(autoStatus(volts)).toMatch(/reason=invalid_voltage/);
  });

  it('forces OFF on absurd voltage outside the 40-60 V band', () => {
    const h = auto({ DCData_Voltage: '12.0', SouthOutlet_Outlet2_Switch: 'ON' });
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(autoStatus(h)).toMatch(/reason=absurd_voltage/);
  });
});

describe('orphan outlet cleanup', () => {
  it('turns the outlet OFF when reloaded ON with no active timer', () => {
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({ SouthOutlet_Outlet2_Switch: 'ON' }),
    });
    h.clearVolatileCache();
    h.execute();
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(autoStatus(h)).toMatch(/reason=orphan_outlet_off/);
  });
});

describe('manual correlated requests', () => {
  it('accepts then completes an eligible daylight request and updates cycle items', () => {
    const h = createRuleHarness({ source: ruleSource, states: baseStates() });
    const requestId = 'gw-20260718-success';
    h.execute({ itemName: 'SouthOutlet_ManualRequest', receivedCommand: gwRequest(requestId) });

    expect(results(h).map((r) => r.status)).toEqual(['accepted']);
    expect(onCount(h)).toBe(1);
    expect(ledger(h).entries[0]).toMatchObject({ requestId, status: 'accepted' });

    const acceptedPersist = h.events.findIndex(
      (e) => e.type === 'persist' && e.item === 'SouthOutlet_ManualRequest',
    );
    const pulseOn = h.events.findIndex(
      (e) => e.type === 'command' && e.item === 'SouthOutlet_Outlet2_Switch' && e.value === 'ON',
    );
    expect(acceptedPersist).toBeGreaterThanOrEqual(0);
    expect(pulseOn).toBeGreaterThan(acceptedPersist);

    h.runNextTimer();
    expect(results(h).map((r) => r.status)).toEqual(['accepted', 'completed']);
    expect(outletCommands(h)).toEqual(['ON', 'OFF', 'OFF']); // redundant safe-OFF backstop
    expect(h.state('SouthOutlet_LastCycleStart')).not.toBe(SIX_HOURS_AGO);
    expect(h.state('SouthOutlet_LastCycle')).not.toBe('NULL');
    expect(ledger(h).entries[0]).toMatchObject({ requestId, status: 'completed' });
  });

  it('keeps only the newest 32 canonical ledger entries', () => {
    const oldEntries = Array.from({ length: 32 }, (_, index) => ({
      requestId: `gw-old-${String(index).padStart(2, '0')}`,
      status: 'completed',
      reason: 'completed',
      at: new Date(Date.parse('2026-07-17T12:00:00.000Z') - (index * 1000)).toISOString(),
    }));
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({ SouthOutlet_ManualRequest: gwLedger(oldEntries) }),
    });
    const requestId = 'gw-20260718-newest';
    h.execute({ itemName: 'SouthOutlet_ManualRequest', receivedCommand: gwRequest(requestId) });

    expect(ledger(h).entries).toHaveLength(32);
    expect(ledger(h).entries[0]).toMatchObject({ requestId, status: 'accepted' });
    expect(ledger(h).entries.at(-1).requestId).toBe('gw-old-30');
  });

  it('runs one cycle per requestId and denies the duplicate after reload', () => {
    const h = createRuleHarness({ source: ruleSource, states: baseStates() });
    const requestId = 'gw-20260718-durable-duplicate';
    h.execute({ itemName: 'SouthOutlet_ManualRequest', receivedCommand: gwRequest(requestId) });
    h.runNextTimer();
    h.clearVolatileCache();

    h.execute({
      itemName: 'SouthOutlet_ManualRequest',
      receivedCommand: gwRequest(requestId, '2026-07-18T12:05:00.000Z'),
    });
    expect(results(h).at(-1)).toMatchObject({ requestId, status: 'denied', reason: 'duplicate' });
    expect(onCount(h)).toBe(1);
  });

  it('fails malformed and incomplete requests as request_invalid without actuation', () => {
    const bad = createRuleHarness({ source: ruleSource, states: baseStates() });
    bad.execute({ itemName: 'SouthOutlet_ManualRequest', receivedCommand: '{not-json' });
    expect(onCount(bad)).toBe(0);
    expect(results(bad).at(-1)).toMatchObject({ status: 'failed', reason: 'request_invalid' });

    const noTime = createRuleHarness({ source: ruleSource, states: baseStates() });
    noTime.execute({
      itemName: 'SouthOutlet_ManualRequest',
      receivedCommand: JSON.stringify({ requestId: 'gw-20260718-no-time' }),
    });
    expect(onCount(noTime)).toBe(0);
    expect(results(noTime).at(-1)).toMatchObject({ status: 'failed', reason: 'request_invalid' });
  });

  it('denies a manual request during the 230-minute gap', () => {
    const recent = new Date(NOON - (10 * 60 * 1000)).toISOString();
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({ SouthOutlet_LastCycleStart: recent, SouthOutlet_LastAutoRun: recent }),
    });
    h.execute({
      itemName: 'SouthOutlet_ManualRequest',
      receivedCommand: gwRequest('gw-20260718-cooldown'),
    });
    expect(onCount(h)).toBe(0);
    expect(results(h).at(-1)).toMatchObject({ status: 'denied', reason: 'cooldown' });
  });

  it('denies a manual request after dark', () => {
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({ Sun_Position_Elevation: '-1' }),
    });
    h.execute({
      itemName: 'SouthOutlet_ManualRequest',
      receivedCommand: gwRequest('gw-20260718-night'),
    });
    expect(onCount(h)).toBe(0);
    expect(results(h).at(-1)).toMatchObject({ status: 'denied', reason: 'after_dark' });
  });

  it('denies a manual request below the SoC eligibility threshold', () => {
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({ SkyCondition: 'CLEAR', BMS_SOC: '89' }),
    });
    h.execute({
      itemName: 'SouthOutlet_ManualRequest',
      receivedCommand: gwRequest('gw-20260718-low'),
    });
    expect(onCount(h)).toBe(0);
    expect(results(h).at(-1)).toMatchObject({ status: 'denied', reason: 'low_soc' });
  });
});
