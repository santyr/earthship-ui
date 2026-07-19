import { readFile } from 'node:fs/promises';
import { beforeAll, describe, expect, it } from 'vitest';
import { createRuleHarness } from './rule-harness.js';

const RULE_URL = new URL('../../openhab/rules/night-load-owner.js', import.meta.url);
const MANIFEST_URL = new URL('../../openhab/managed-resources.json', import.meta.url);

const NOON = Date.parse('2026-07-18T12:00:00.000Z');

let ruleSource;

beforeAll(async () => {
  ruleSource = await readFile(RULE_URL, 'utf8');
});

// --- helpers ---------------------------------------------------------------

function baseStates(overrides = {}) {
  return {
    NightLoadOverride_Request: 'NULL',
    NightLoadOverride_Result: 'NULL',
    NightLoadDevice_Request: 'NULL',
    NightLoadDevice_Result: 'NULL',
    OverrideSwitch: 'OFF',
    Dish_Washer_Power: 'ON',
    ShurefloPump_Power: 'ON',
    Goat_Plugs_Outlet1_Switch: 'ON',
    FeederOverride: 'OFF',
    ...overrides,
  };
}

function overrideRequest(requestId, command, requestedAt = '2026-07-18T12:00:00.000Z') {
  return JSON.stringify({ requestId, requestedAt, command });
}

function deviceRequest(requestId, device, command, requestedAt = '2026-07-18T12:00:00.000Z') {
  return JSON.stringify({
    requestId, requestedAt, device, command,
  });
}

function overrideLedger(entries) {
  return JSON.stringify({ version: 'night-load-request-ledger/v1', entries });
}

function results(h, item) {
  return h.events
    .filter((e) => e.type === 'update' && e.item === item)
    .map((e) => JSON.parse(e.value));
}

function overrideResults(h) {
  return results(h, 'NightLoadOverride_Result');
}

function deviceResults(h) {
  return results(h, 'NightLoadDevice_Result');
}

function commandsFor(h, item) {
  return h.events
    .filter((e) => e.type === 'command' && e.item === item)
    .map((e) => e.value);
}

function allDeviceCommands(h) {
  const owned = new Set(['Dish_Washer_Power', 'ShurefloPump_Power', 'Goat_Plugs_Outlet1_Switch']);
  return h.events
    .filter((e) => e.type === 'command' && owned.has(e.item))
    .map((e) => ({ item: e.item, value: e.value }));
}

function overrideLedgerState(h) {
  const raw = h.state('NightLoadOverride_Request');
  return (raw === 'NULL' || raw === 'UNDEF') ? null : JSON.parse(raw);
}

function deviceLedgerState(h) {
  const raw = h.state('NightLoadDevice_Request');
  return (raw === 'NULL' || raw === 'UNDEF') ? null : JSON.parse(raw);
}

function harness(overrides = {}) {
  return createRuleHarness({ source: ruleSource, states: baseStates(overrides) });
}

// --- manifest / capability -------------------------------------------------

describe('[RED:T4A-1] canonical night-load owner resources', () => {
  it('declares the versioned owner, request/result items, capability, and triggers', async () => {
    const [source, manifest] = await Promise.all([
      readFile(RULE_URL, 'utf8'),
      readFile(MANIFEST_URL, 'utf8').then(JSON.parse),
    ]);
    const nightLoad = manifest.subsets?.['night-load'];
    expect(nightLoad?.capability).toBe('night-load-owner-v1');
    expect(nightLoad?.rule).toMatchObject({
      uid: 'hex_night_load_override',
      source: 'openhab/rules/night-load-owner.js',
    });
    expect(source).toContain('EARTHSHIP_NIGHT_LOAD_OWNER_VERSION');
    expect(nightLoad?.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ name: 'NightLoadOverride_Request', type: 'String' }),
      expect.objectContaining({ name: 'NightLoadOverride_Result', type: 'String' }),
      expect.objectContaining({ name: 'NightLoadDevice_Request', type: 'String' }),
      expect.objectContaining({ name: 'NightLoadDevice_Result', type: 'String' }),
    ]));
    expect(nightLoad?.metadata).toEqual(expect.arrayContaining([
      expect.objectContaining({ item: 'NightLoadOverride_Request', namespace: 'autoupdate', value: 'false' }),
      expect.objectContaining({ item: 'NightLoadDevice_Request', namespace: 'autoupdate', value: 'false' }),
      expect.objectContaining({ item: 'OverrideSwitch', namespace: 'autoupdate', value: 'false' }),
    ]));
    expect(nightLoad?.persistence).toMatchObject({
      serviceId: 'jdbc',
      strategy: 'everyChange',
      restoreOnStartup: true,
      items: expect.arrayContaining([
        'NightLoadOverride_Request',
        'NightLoadDevice_Request',
        'OverrideSwitch',
      ]),
    });
    const triggerItems = nightLoad?.rule?.triggers?.map((t) => t.configuration?.itemName);
    expect(triggerItems).toEqual(expect.arrayContaining([
      'NightLoadOverride_Request',
      'NightLoadDevice_Request',
      'OverrideSwitch',
    ]));
  });
});

// --- override matrices -----------------------------------------------------

describe('override ON matrix', () => {
  it('commits OverrideSwitch ON then forces the exact owned OFF matrix and completes', () => {
    const h = harness();
    h.execute({
      itemName: 'NightLoadOverride_Request',
      receivedCommand: overrideRequest('nl-20260718-on', 'ON'),
    });

    // OverrideSwitch is committed ON via postUpdate (owner policy state).
    expect(h.state('OverrideSwitch')).toBe('ON');
    // Exact matrix: all three owned devices commanded OFF.
    expect(allDeviceCommands(h)).toEqual([
      { item: 'Dish_Washer_Power', value: 'OFF' },
      { item: 'ShurefloPump_Power', value: 'OFF' },
      { item: 'Goat_Plugs_Outlet1_Switch', value: 'OFF' },
    ]);
    expect(overrideResults(h).map((r) => r.status)).toEqual(['accepted', 'running']);
    expect(h.pendingTimers()).toBe(1);

    // Downstream coupling (Goat Cam OFF -> FeederOverride ON) fires
    // asynchronously via the preserved GoatCamOff rule before verification.
    h.setState('FeederOverride', 'ON');
    h.runNextTimer();
    expect(overrideResults(h).map((r) => r.status)).toEqual(['accepted', 'running', 'completed']);
    expect(overrideLedgerState(h).entries[0]).toMatchObject({
      requestId: 'nl-20260718-on', status: 'completed',
    });
    // The owner never wrote FeederOverride; it only observed the coupling.
    expect(commandsFor(h, 'FeederOverride')).toEqual([]);
    expect(h.events.some((e) => e.item === 'FeederOverride' && e.type === 'update')).toBe(false);
  });

  it('withholds completion and fails coupling_pending when FeederOverride never flips', () => {
    // Simulates a broken/disabled GoatCamOff coupling rule: the goat cam is
    // commanded OFF by the ON matrix but FeederOverride never becomes ON.
    const h = harness({ FeederOverride: 'OFF' });
    h.execute({
      itemName: 'NightLoadOverride_Request',
      receivedCommand: overrideRequest('nl-20260718-on-nocouple', 'ON'),
    });

    // Provider matrix is satisfied (all three commanded OFF reflect), but the
    // FeederOverride side effect is absent, so completion must be withheld.
    expect(allDeviceCommands(h)).toEqual([
      { item: 'Dish_Washer_Power', value: 'OFF' },
      { item: 'ShurefloPump_Power', value: 'OFF' },
      { item: 'Goat_Plugs_Outlet1_Switch', value: 'OFF' },
    ]);
    h.runNextTimer();

    expect(overrideResults(h).at(-1)).toMatchObject({ status: 'failed', reason: 'coupling_pending' });
    expect(overrideResults(h).some((r) => r.status === 'completed')).toBe(false);
    expect(overrideLedgerState(h).entries[0]).toMatchObject({
      requestId: 'nl-20260718-on-nocouple', status: 'failed', reason: 'coupling_pending',
    });
    // The owner still never writes FeederOverride, even on the failure path.
    expect(commandsFor(h, 'FeederOverride')).toEqual([]);
    expect(h.events.some((e) => e.item === 'FeederOverride' && e.type === 'update')).toBe(false);
  });

  it('persists the accepted ledger and commits OverrideSwitch before any load command', () => {
    const h = harness();
    h.execute({
      itemName: 'NightLoadOverride_Request',
      receivedCommand: overrideRequest('nl-20260718-order', 'ON'),
    });

    const acceptedPersist = h.events.findIndex(
      (e) => e.type === 'persist' && e.item === 'NightLoadOverride_Request',
    );
    const switchUpdate = h.events.findIndex(
      (e) => e.type === 'update' && e.item === 'OverrideSwitch' && e.value === 'ON',
    );
    const firstLoad = h.events.findIndex(
      (e) => e.type === 'command'
        && ['Dish_Washer_Power', 'ShurefloPump_Power', 'Goat_Plugs_Outlet1_Switch'].includes(e.item),
    );
    expect(acceptedPersist).toBeGreaterThanOrEqual(0);
    expect(switchUpdate).toBeGreaterThan(acceptedPersist);
    expect(firstLoad).toBeGreaterThan(switchUpdate);
  });

  it('never commands OverrideSwitch (owner uses postUpdate for visible policy state)', () => {
    const h = harness();
    h.execute({
      itemName: 'NightLoadOverride_Request',
      receivedCommand: overrideRequest('nl-20260718-nocmd', 'ON'),
    });
    expect(commandsFor(h, 'OverrideSwitch')).toEqual([]);
  });
});

describe('override OFF matrix', () => {
  it('restores only Shureflo ON, commits OverrideSwitch OFF, and leaves dishwasher/goat-cam alone', () => {
    const h = harness({
      OverrideSwitch: 'ON',
      Dish_Washer_Power: 'OFF',
      ShurefloPump_Power: 'OFF',
      Goat_Plugs_Outlet1_Switch: 'OFF',
    });
    h.execute({
      itemName: 'NightLoadOverride_Request',
      receivedCommand: overrideRequest('nl-20260718-off', 'OFF'),
    });

    // Only Shureflo is commanded, and only ON; OverrideSwitch still ON pre-verify.
    expect(allDeviceCommands(h)).toEqual([{ item: 'ShurefloPump_Power', value: 'ON' }]);
    expect(h.state('OverrideSwitch')).toBe('ON');

    h.runNextTimer();
    // release-ready running checkpoint precedes the committed OFF and completion.
    expect(overrideResults(h).map((r) => r.status)).toEqual([
      'accepted', 'running', 'running', 'completed',
    ]);
    expect(overrideResults(h).map((r) => r.reason)).toContain('release-ready');
    expect(h.state('OverrideSwitch')).toBe('OFF');
    expect(commandsFor(h, 'Dish_Washer_Power')).toEqual([]);
    expect(commandsFor(h, 'Goat_Plugs_Outlet1_Switch')).toEqual([]);
    expect(overrideLedgerState(h).entries[0]).toMatchObject({
      requestId: 'nl-20260718-off', status: 'completed',
    });
  });

  it('leaves ownership ON and fails when Shureflo never confirms ON', () => {
    const h = harness({
      OverrideSwitch: 'ON',
      ShurefloPump_Power: 'OFF',
    });
    h.holdProvider('ShurefloPump_Power'); // command issued but provider never follows
    h.execute({
      itemName: 'NightLoadOverride_Request',
      receivedCommand: overrideRequest('nl-20260718-off-fail', 'OFF'),
    });
    h.runNextTimer();

    expect(overrideResults(h).at(-1)).toMatchObject({ status: 'failed', reason: 'provider_mismatch' });
    expect(h.state('OverrideSwitch')).toBe('ON'); // ownership retained
  });
});

// --- serialization ---------------------------------------------------------

describe('serialized owner', () => {
  it('denies a concurrent second request as busy while one is in flight', () => {
    const h = harness();
    h.execute({
      itemName: 'NightLoadOverride_Request',
      receivedCommand: overrideRequest('nl-20260718-first', 'ON'),
    });
    // Second request arrives before the first completes.
    h.execute({
      itemName: 'NightLoadDevice_Request',
      receivedCommand: deviceRequest('nl-20260718-second', 'dishwasher', 'ON'),
    });
    expect(deviceResults(h).at(-1)).toMatchObject({ status: 'denied', reason: 'busy' });
    // Only the first transition actuated.
    expect(allDeviceCommands(h).map((c) => c.value)).toEqual(['OFF', 'OFF', 'OFF']);
  });

  it('denies a concurrent second override request as busy', () => {
    const h = harness();
    h.execute({
      itemName: 'NightLoadOverride_Request',
      receivedCommand: overrideRequest('nl-20260718-a', 'ON'),
    });
    h.execute({
      itemName: 'NightLoadOverride_Request',
      receivedCommand: overrideRequest('nl-20260718-b', 'OFF'),
    });
    expect(overrideResults(h).at(-1)).toMatchObject({ status: 'denied', reason: 'busy' });
  });
});

// --- device requests -------------------------------------------------------

describe('device requests', () => {
  it('completes a dishwasher ON request only when override is OFF and provider confirms', () => {
    const h = harness({ Dish_Washer_Power: 'OFF' });
    h.execute({
      itemName: 'NightLoadDevice_Request',
      receivedCommand: deviceRequest('nl-20260718-dish-on', 'dishwasher', 'ON'),
    });
    expect(commandsFor(h, 'Dish_Washer_Power')).toEqual(['ON']);
    expect(deviceResults(h).map((r) => r.status)).toEqual(['accepted', 'running']);

    h.runNextTimer();
    expect(deviceResults(h).at(-1)).toMatchObject({ status: 'completed' });
    expect(deviceLedgerState(h).entries[0]).toMatchObject({
      requestId: 'nl-20260718-dish-on', status: 'completed',
    });
  });

  it('denies a device request while the override owns the loads', () => {
    const h = harness({ OverrideSwitch: 'ON' });
    h.execute({
      itemName: 'NightLoadDevice_Request',
      receivedCommand: deviceRequest('nl-20260718-owned', 'shureflo', 'ON'),
    });
    expect(commandsFor(h, 'ShurefloPump_Power')).toEqual([]);
    expect(deviceResults(h).at(-1)).toMatchObject({ status: 'denied', reason: 'override_active' });
  });

  it('fails a device request when the provider readback does not match the command', () => {
    const h = harness({ ShurefloPump_Power: 'OFF' });
    h.holdProvider('ShurefloPump_Power');
    h.execute({
      itemName: 'NightLoadDevice_Request',
      receivedCommand: deviceRequest('nl-20260718-mismatch', 'shureflo', 'ON'),
    });
    h.runNextTimer();
    expect(deviceResults(h).at(-1)).toMatchObject({ status: 'failed', reason: 'provider_mismatch' });
  });
});

// --- goat cam coupling -----------------------------------------------------

describe('goat cam coupling preserved', () => {
  it('never writes FeederOverride and completes goat-cam only after the coupling side effect', () => {
    const h = harness({ Goat_Plugs_Outlet1_Switch: 'OFF', FeederOverride: 'ON' });
    h.execute({
      itemName: 'NightLoadDevice_Request',
      receivedCommand: deviceRequest('nl-20260718-cam-on', 'goat-cam', 'ON'),
    });
    // Owner commands only the goat cam plug, never FeederOverride.
    expect(commandsFor(h, 'Goat_Plugs_Outlet1_Switch')).toEqual(['ON']);
    expect(commandsFor(h, 'FeederOverride')).toEqual([]);
    expect(h.events.some((e) => e.item === 'FeederOverride' && e.type === 'update')).toBe(false);

    // Downstream coupling (Goat Cam ON -> FeederOverride OFF) fires asynchronously.
    h.setState('FeederOverride', 'OFF');
    h.runNextTimer();
    expect(deviceResults(h).at(-1)).toMatchObject({ status: 'completed' });
  });

  it('fails goat-cam when the downstream FeederOverride coupling is not observed', () => {
    const h = harness({ Goat_Plugs_Outlet1_Switch: 'OFF', FeederOverride: 'ON' });
    h.execute({
      itemName: 'NightLoadDevice_Request',
      receivedCommand: deviceRequest('nl-20260718-cam-nocouple', 'goat-cam', 'ON'),
    });
    // FeederOverride stays ON (coupling never fired) -> completion is withheld.
    h.runNextTimer();
    expect(deviceResults(h).at(-1)).toMatchObject({ status: 'failed', reason: 'coupling_pending' });
    expect(commandsFor(h, 'FeederOverride')).toEqual([]);
  });
});

// --- malformed / duplicate / stale (feeder contract) -----------------------

describe('malformed, duplicate, and stale requests', () => {
  it('fails malformed and incomplete device requests as request_invalid without actuation', () => {
    const bad = harness();
    bad.execute({ itemName: 'NightLoadDevice_Request', receivedCommand: '{not-json' });
    expect(allDeviceCommands(bad)).toEqual([]);
    expect(deviceResults(bad).at(-1)).toMatchObject({ status: 'failed', reason: 'request_invalid' });

    const noDevice = harness();
    noDevice.execute({
      itemName: 'NightLoadDevice_Request',
      receivedCommand: JSON.stringify({ requestId: 'nl-20260718-nodev', requestedAt: '2026-07-18T12:00:00.000Z', command: 'ON' }),
    });
    expect(deviceResults(noDevice).at(-1)).toMatchObject({ status: 'failed', reason: 'request_invalid' });

    const badCmd = harness();
    badCmd.execute({
      itemName: 'NightLoadDevice_Request',
      receivedCommand: deviceRequest('nl-20260718-badcmd', 'shureflo', 'TOGGLE'),
    });
    expect(deviceResults(badCmd).at(-1)).toMatchObject({ status: 'failed', reason: 'request_invalid' });
  });

  it('denies a duplicate override requestId after reload without re-actuating', () => {
    const h = harness();
    h.execute({
      itemName: 'NightLoadOverride_Request',
      receivedCommand: overrideRequest('nl-20260718-dup', 'ON'),
    });
    h.runNextTimer();
    h.clearVolatileCache();
    h.execute({
      itemName: 'NightLoadOverride_Request',
      receivedCommand: overrideRequest('nl-20260718-dup', 'ON', '2026-07-18T12:00:01.000Z'),
    });
    expect(overrideResults(h).at(-1)).toMatchObject({ status: 'denied', reason: 'duplicate' });
    expect(allDeviceCommands(h).map((c) => c.value)).toEqual(['OFF', 'OFF', 'OFF']);
  });

  it('denies a stale queued request with request_stale before actuation', () => {
    const staleAt = new Date(NOON - (10 * 60 * 1000)).toISOString();
    const h = harness();
    h.execute({
      itemName: 'NightLoadDevice_Request',
      receivedCommand: deviceRequest('nl-20260718-stale', 'shureflo', 'ON', staleAt),
    });
    expect(allDeviceCommands(h)).toEqual([]);
    expect(deviceResults(h).at(-1)).toMatchObject({ status: 'denied', reason: 'request_stale' });
  });

  it('keeps only the newest 32 canonical override ledger entries', () => {
    const oldEntries = Array.from({ length: 32 }, (_, index) => ({
      requestId: `nl-old-${String(index).padStart(2, '0')}`,
      status: 'completed',
      reason: 'completed',
      at: new Date(Date.parse('2026-07-17T12:00:00.000Z') - (index * 1000)).toISOString(),
    }));
    const h = harness({ NightLoadOverride_Request: overrideLedger(oldEntries) });
    h.execute({
      itemName: 'NightLoadOverride_Request',
      receivedCommand: overrideRequest('nl-20260718-newest', 'ON'),
    });
    expect(overrideLedgerState(h).entries).toHaveLength(32);
    expect(overrideLedgerState(h).entries[0]).toMatchObject({
      requestId: 'nl-20260718-newest', status: 'accepted',
    });
    expect(overrideLedgerState(h).entries.at(-1).requestId).toBe('nl-old-30');
  });
});

// --- schedule interactions -------------------------------------------------

describe('schedule / external OverrideSwitch commands', () => {
  it('carries a synthetic id through the override ledger for a schedule ON command', () => {
    const h = harness();
    h.execute({ itemName: 'OverrideSwitch', receivedCommand: 'ON' });

    expect(h.state('OverrideSwitch')).toBe('ON');
    expect(allDeviceCommands(h).map((c) => c.value)).toEqual(['OFF', 'OFF', 'OFF']);
    const entry = overrideLedgerState(h).entries[0];
    expect(entry.requestId).toMatch(/^override-switch:ON:/);
    expect(entry.status).toBe('accepted');

    // Preserved GoatCamOff coupling drives FeederOverride ON after the cam OFF.
    h.setState('FeederOverride', 'ON');
    h.runNextTimer();
    expect(overrideLedgerState(h).entries[0]).toMatchObject({ status: 'completed' });
    // Owner never echoes a command back to OverrideSwitch.
    expect(commandsFor(h, 'OverrideSwitch')).toEqual([]);
  });
});
