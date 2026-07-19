import { readFile } from 'node:fs/promises';
import { beforeAll, describe, expect, it } from 'vitest';
import { createRuleHarness } from './rule-harness.js';

const RULE_URL = new URL('../../openhab/rules/night-load-owner.js', import.meta.url);

let ruleSource;

beforeAll(async () => {
  ruleSource = await readFile(RULE_URL, 'utf8');
});

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

function ledger(entries) {
  return JSON.stringify({ version: 'night-load-request-ledger/v1', entries });
}

function results(h, item) {
  return h.events
    .filter((e) => e.type === 'update' && e.item === item)
    .map((e) => JSON.parse(e.value));
}

function ledgerState(h, item) {
  const raw = h.state(item);
  return (raw === 'NULL' || raw === 'UNDEF') ? null : JSON.parse(raw);
}

function anyLoadCommands(h) {
  const owned = new Set([
    'Dish_Washer_Power', 'ShurefloPump_Power', 'Goat_Plugs_Outlet1_Switch',
  ]);
  return h.events.filter((e) => e.type === 'command' && owned.has(e.item));
}

describe('night-load restart recovery', () => {
  it('marks a pending accepted override entry restart-uncertain and never re-actuates', () => {
    const requestId = 'nl-20260718-interrupted-override';
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({
        NightLoadOverride_Request: ledger([{
          requestId, status: 'accepted', reason: 'accepted', at: '2026-07-18T11:00:00.000Z',
        }]),
      }),
    });
    h.clearVolatileCache();
    h.execute({ itemName: 'NightLoadOverride_Request', receivedCommand: overrideRequest(requestId, 'ON') });

    expect(anyLoadCommands(h)).toEqual([]);
    // OverrideSwitch is not re-committed during recovery.
    expect(h.events.some((e) => e.type === 'update' && e.item === 'OverrideSwitch')).toBe(false);
    expect(ledgerState(h, 'NightLoadOverride_Request').entries[0]).toMatchObject({
      requestId, status: 'failed', reason: 'restart_uncertain',
    });
    expect(results(h, 'NightLoadOverride_Result').at(-1)).toMatchObject({
      requestId, status: 'denied', reason: 'duplicate',
    });
  });

  it('recovers an interrupted device ledger on a reconciliation pass without actuation', () => {
    const requestId = 'nl-20260718-interrupted-device';
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({
        NightLoadDevice_Request: ledger([{
          requestId, status: 'running', reason: 'release-ready', at: '2026-07-18T11:00:00.000Z',
        }]),
      }),
    });
    h.clearVolatileCache();
    h.execute(); // cron reconciliation (no event)

    expect(anyLoadCommands(h)).toEqual([]);
    expect(ledgerState(h, 'NightLoadDevice_Request').entries[0]).toMatchObject({
      requestId, status: 'failed', reason: 'restart_uncertain',
    });
    expect(h.events.some(
      (e) => e.type === 'persist' && e.item === 'NightLoadDevice_Request',
    )).toBe(true);
  });

  it('keeps a completed request idempotent across restart', () => {
    const requestId = 'nl-20260718-completed-durable';
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({
        NightLoadDevice_Request: ledger([{
          requestId, status: 'completed', reason: 'completed', at: '2026-07-18T11:00:00.000Z',
        }]),
        Dish_Washer_Power: 'OFF',
      }),
    });
    h.execute({
      itemName: 'NightLoadDevice_Request',
      receivedCommand: deviceRequest(requestId, 'dishwasher', 'ON'),
    });
    expect(anyLoadCommands(h)).toEqual([]);
    expect(results(h, 'NightLoadDevice_Result').at(-1)).toMatchObject({
      requestId, status: 'denied', reason: 'duplicate',
    });
  });

  it('fails closed on corrupt restored ledger state before actuation', () => {
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({ NightLoadDevice_Request: '{not-json' }),
    });
    h.execute({
      itemName: 'NightLoadDevice_Request',
      receivedCommand: deviceRequest('nl-20260718-after-corrupt', 'shureflo', 'ON'),
    });
    expect(anyLoadCommands(h)).toEqual([]);
    expect(results(h, 'NightLoadDevice_Result').at(-1)).toMatchObject({
      status: 'denied', reason: 'ledger_invalid',
    });
  });

  it('fails closed on oversize restored ledger state', () => {
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({ NightLoadOverride_Request: 'x'.repeat(9000) }),
    });
    h.execute({
      itemName: 'NightLoadOverride_Request',
      receivedCommand: overrideRequest('nl-20260718-oversize', 'ON'),
    });
    expect(anyLoadCommands(h)).toEqual([]);
    expect(results(h, 'NightLoadOverride_Result').at(-1)).toMatchObject({
      status: 'denied', reason: 'ledger_invalid',
    });
  });

  it('denies with ledger_restore_missing when a persisted ledger fails to restore', () => {
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({ NightLoadDevice_Request: 'NULL' }),
      histories: {
        NightLoadDevice_Request: [ledger([{
          requestId: 'nl-20260718-prior', status: 'completed', reason: 'completed', at: '2026-07-18T10:00:00.000Z',
        }])],
      },
    });
    h.execute({
      itemName: 'NightLoadDevice_Request',
      receivedCommand: deviceRequest('nl-20260718-restore-miss', 'shureflo', 'ON'),
    });
    expect(anyLoadCommands(h)).toEqual([]);
    expect(results(h, 'NightLoadDevice_Result').at(-1)).toMatchObject({
      status: 'denied', reason: 'ledger_restore_missing',
    });
  });

  it('ends without actuation and posts ledger_persist_failed when the accept persist throws', () => {
    const h = createRuleHarness({ source: ruleSource, states: baseStates({ Dish_Washer_Power: 'OFF' }) });
    h.setPersistFailure(new Error('jdbc offline'));
    h.execute({
      itemName: 'NightLoadDevice_Request',
      receivedCommand: deviceRequest('nl-20260718-persist-fail', 'dishwasher', 'ON'),
    });
    expect(anyLoadCommands(h)).toEqual([]);
    expect(results(h, 'NightLoadDevice_Result').at(-1)).toMatchObject({
      status: 'failed', reason: 'ledger_persist_failed',
    });
  });

  it('ends without actuation and posts ledger_readback_failed when the accept never reads back', () => {
    const h = createRuleHarness({ source: ruleSource, states: baseStates({ Dish_Washer_Power: 'OFF' }) });
    h.delayNextPersistVisibility(25); // never visible within the bounded readback loop
    h.execute({
      itemName: 'NightLoadDevice_Request',
      receivedCommand: deviceRequest('nl-20260718-readback-fail', 'dishwasher', 'ON'),
    });
    expect(anyLoadCommands(h)).toEqual([]);
    expect(results(h, 'NightLoadDevice_Result').at(-1)).toMatchObject({
      status: 'failed', reason: 'ledger_readback_failed',
    });
  });
});
