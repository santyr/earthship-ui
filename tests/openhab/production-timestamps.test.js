import { readFile } from 'node:fs/promises';
import { beforeAll, describe, expect, it } from 'vitest';
import { createRuleHarness, openhabDateTimeState } from './rule-harness.js';

// Regression suite for the final-review Criticals. The harness now emulates
// production semantics: ZonedDateTime.toString() renders a bracketed zone id,
// string time.toInstant()/Instant.parse() is strict (only 'Z' instants), and
// openhabDateTimeState() renders DateTime item states with a colon-less offset.
// These tests fail if the owner rules regress to writing bracketed ledger
// timestamps or to feeding non-'Z' strings straight into time.toInstant().

const FEEDER_URL = new URL('../../openhab/rules/feeder-owner.js', import.meta.url);
const GREYWATER_URL = new URL('../../openhab/rules/southoutlet-cycle.js', import.meta.url);
const NIGHT_URL = new URL('../../openhab/rules/night-load-owner.js', import.meta.url);

const LEDGER_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/;
const NOON = Date.parse('2026-07-18T12:00:00.000Z');

let feederSource;
let greywaterSource;
let nightSource;

beforeAll(async () => {
  [feederSource, greywaterSource, nightSource] = await Promise.all([
    readFile(FEEDER_URL, 'utf8'),
    readFile(GREYWATER_URL, 'utf8'),
    readFile(NIGHT_URL, 'utf8'),
  ]);
});

function feederReq(requestId, requestedAt = '2026-07-18T12:00:00.000Z') {
  return JSON.stringify({ requestId, requestedAt });
}

// --- C1: ledger written then re-read across evaluations stays valid --------

describe('C1 production-form ledger timestamps', () => {
  it('re-reads a feeder ledger written across evaluations (instant-form at survives readback)', () => {
    const h = createRuleHarness({ source: feederSource, filename: 'openhab/rules/feeder-owner.js' });

    h.execute({ itemName: 'GoatFeeder_ManualRequest', receivedCommand: feederReq('feed-c1-0001') });
    h.runNextTimer();

    const first = JSON.parse(h.state('GoatFeeder_ManualRequest'));
    expect(first.entries[0]).toMatchObject({ requestId: 'feed-c1-0001', status: 'complete' });
    // Timestamps are written as UTC instant strings (ending in 'Z'), never the
    // bracketed ZonedDateTime rendering that strict Instant.parse would reject.
    expect(first.entries[0].at.endsWith('Z')).toBe(true);
    expect(first.entries[0].updatedAt.endsWith('Z')).toBe(true);

    // A second request one cooldown later must parse the stored ledger. With
    // bracketed timestamps epochMillis() would be NaN and the channel would be
    // permanently denied 'ledger_invalid' after the first accepted request.
    h.advance(6000);
    h.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederReq('feed-c1-0002', new Date(NOON + 6000).toISOString()),
    });
    h.runNextTimer();

    const results = h.resultPayloads();
    expect(results.some((r) => r.reason === 'ledger_invalid')).toBe(false);
    expect(results.at(-1)).toMatchObject({ requestId: 'feed-c1-0002', status: 'complete' });

    const ledger = JSON.parse(h.state('GoatFeeder_ManualRequest'));
    expect(ledger.entries).toHaveLength(2);
    expect(ledger.entries.every((e) => e.at.endsWith('Z'))).toBe(true);
  });

  it('tolerantly parses a pre-existing ledger whose timestamps use the bracketed zone form', () => {
    const bracketAt = '2026-07-18T05:59:00.000-06:00[America/Denver]';
    const h = createRuleHarness({
      source: feederSource,
      filename: 'openhab/rules/feeder-owner.js',
      states: {
        GoatFeeder_ManualRequest: JSON.stringify({
          version: 'feeder-request-ledger/v1',
          entries: [{
            requestId: 'feed-old-0001',
            status: 'complete',
            reason: 'complete',
            at: bracketAt,
            updatedAt: bracketAt,
          }],
        }),
      },
    });

    h.advance(6000);
    h.execute({ itemName: 'GoatFeeder_ManualRequest', receivedCommand: feederReq('feed-new-0001') });

    const results = h.resultPayloads();
    expect(results.some((r) => r.reason === 'ledger_invalid')).toBe(false);
    expect(results.at(-1)).toMatchObject({ requestId: 'feed-new-0001', status: 'running' });
  });
});

// --- C2: greywater LastCycleStart colon-less-offset item-state round-trip --

describe('C2 greywater LastCycleStart item-state round-trip', () => {
  function gwStates(overrides = {}) {
    return {
      DCData_Voltage: '53.6',
      BMS_SOC: '95',
      BMS_Comms_Status: 'OK',
      SouthOutlet_LowSocCutoff: '45',
      SouthOutlet_Outlet2_Switch: 'OFF',
      SkyCondition: 'CLEAR',
      Sun_Position_Elevation: '37.3',
      SouthOutlet_ManualRequest: 'NULL',
      SouthOutlet_ManualResult: 'NULL',
      SouthOutlet_LastCycle: 'NULL',
      SouthOutlet_AutoStatus: 'NULL',
      ...overrides,
    };
  }

  function autoStatus(h) {
    const updates = h.events.filter((e) => e.type === 'update' && e.item === 'SouthOutlet_AutoStatus');
    return updates.at(-1)?.value ?? '';
  }

  function onCount(h) {
    return h.events.filter(
      (e) => e.type === 'command' && e.item === 'SouthOutlet_Outlet2_Switch' && e.value === 'ON',
    ).length;
  }

  it('parses a -0600-form LastCycleStart and holds the 230-min gate (gap not yet met)', () => {
    // 229 minutes ago, rendered exactly as openHAB renders a DateTime state.
    const lastStart = openhabDateTimeState(NOON - (229 * 60 * 1000));
    expect(lastStart).toMatch(/[+-]\d{4}$/); // colon-less offset, no 'Z'
    const h = createRuleHarness({
      source: greywaterSource,
      filename: 'openhab/rules/southoutlet-cycle.js',
      states: gwStates({ SouthOutlet_LastCycleStart: lastStart }),
    });

    h.execute(); // automatic evaluation

    expect(onCount(h)).toBe(0);
    // Proves the state parsed: a NaN parse would take the cooldown_initialized
    // branch instead of cooldown_wait with a computed remaining minute.
    expect(autoStatus(h)).toContain('reason=cooldown_wait');
    expect(autoStatus(h)).toContain('waitMin=1');
    expect(autoStatus(h)).not.toContain('cooldown_initialized');
  });

  it('parses a -0600-form LastCycleStart and starts a cycle once the 230-min gap is met', () => {
    const lastStart = openhabDateTimeState(NOON - (231 * 60 * 1000));
    const h = createRuleHarness({
      source: greywaterSource,
      filename: 'openhab/rules/southoutlet-cycle.js',
      states: gwStates({ SouthOutlet_LastCycleStart: lastStart }),
    });

    h.execute(); // automatic evaluation

    expect(onCount(h)).toBe(1);
    expect(autoStatus(h)).toContain('reason=cycle_started');
  });
});

// --- C3: scheduled-override synthetic id is regex-safe ----------------------

describe('C3 scheduled-override synthetic id', () => {
  function nlStates(overrides = {}) {
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

  function overrideResults(h) {
    return h.events
      .filter((e) => e.type === 'update' && e.item === 'NightLoadOverride_Result')
      .map((e) => JSON.parse(e.value));
  }

  it('mints a ledger-regex-safe synthetic id and re-parses the ledger on a second scheduled run', () => {
    const h = createRuleHarness({
      source: nightSource,
      filename: 'openhab/rules/night-load-owner.js',
      states: nlStates(),
    });

    // First scheduled OverrideSwitch ON command -> synthetic id ledger entry.
    h.execute({ itemName: 'OverrideSwitch', receivedCommand: 'ON' });

    const entry = JSON.parse(h.state('NightLoadOverride_Request')).entries[0];
    expect(entry.requestId).toMatch(/^override-switch:ON:/);
    expect(entry.requestId).toMatch(LEDGER_ID_RE); // passes the owner's own ledger regex
    expect(entry.requestId).not.toMatch(/[[\]/]/); // no bracket/slash from a ZDT rendering
    expect(entry.at.endsWith('Z')).toBe(true);

    // Complete the ON transition (preserved GoatCamOff coupling sets FeederOverride ON).
    h.setState('FeederOverride', 'ON');
    h.runNextTimer();
    expect(JSON.parse(h.state('NightLoadOverride_Request')).entries[0]).toMatchObject({ status: 'completed' });

    // A second scheduled command must re-parse the ledger. A bracketed/slashed
    // synthetic id would have poisoned it -> parseLedger throws ledger_invalid.
    h.execute({ itemName: 'OverrideSwitch', receivedCommand: 'OFF' });

    const results = overrideResults(h);
    expect(results.some((r) => r.reason === 'ledger_invalid')).toBe(false);
    expect(results.at(-1).status).not.toBe('denied');
    expect(results.at(-1)).toMatchObject({ status: 'running' });
  });
});
