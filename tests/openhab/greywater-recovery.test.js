import { readFile } from 'node:fs/promises';
import { beforeAll, describe, expect, it } from 'vitest';
import { createRuleHarness } from './rule-harness.js';

const RULE_URL = new URL('../../openhab/rules/southoutlet-cycle.js', import.meta.url);

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

function onCount(h) {
  return h.events.filter(
    (e) => e.type === 'command' && e.item === 'SouthOutlet_Outlet2_Switch' && e.value === 'ON',
  ).length;
}

function ledger(h) {
  const raw = h.state('SouthOutlet_ManualRequest');
  return (raw === 'NULL' || raw === 'UNDEF') ? null : JSON.parse(raw);
}

describe('greywater restart recovery', () => {
  it('marks a pending accepted request restart-uncertain and never re-actuates it', () => {
    const requestId = 'gw-20260718-interrupted';
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({
        SouthOutlet_ManualRequest: gwLedger([{
          requestId,
          status: 'accepted',
          reason: 'accepted',
          at: '2026-07-18T11:00:00.000Z',
        }]),
      }),
    });

    h.execute({ itemName: 'SouthOutlet_ManualRequest', receivedCommand: gwRequest(requestId) });

    expect(onCount(h)).toBe(0);
    expect(ledger(h).entries[0]).toMatchObject({
      requestId,
      status: 'failed',
      reason: 'restart_uncertain',
    });
    expect(results(h).at(-1)).toMatchObject({ requestId, status: 'denied', reason: 'duplicate' });
  });

  it('recovers an interrupted ledger on the first automatic evaluation without actuation', () => {
    const requestId = 'gw-20260718-auto-recover';
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({
        SouthOutlet_ManualRequest: gwLedger([{
          requestId,
          status: 'accepted',
          reason: 'accepted',
          at: '2026-07-18T11:00:00.000Z',
        }]),
      }),
    });

    h.execute();

    expect(onCount(h)).toBe(0);
    expect(ledger(h).entries[0]).toMatchObject({
      requestId,
      status: 'failed',
      reason: 'restart_uncertain',
    });
    const persisted = h.events.some(
      (e) => e.type === 'persist' && e.item === 'SouthOutlet_ManualRequest',
    );
    expect(persisted).toBe(true);
  });

  it('keeps a completed request idempotent across restart', () => {
    const requestId = 'gw-20260718-completed-durable';
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({
        SouthOutlet_ManualRequest: gwLedger([{
          requestId,
          status: 'completed',
          reason: 'completed',
          at: '2026-07-18T11:00:00.000Z',
        }]),
      }),
    });

    h.execute({ itemName: 'SouthOutlet_ManualRequest', receivedCommand: gwRequest(requestId) });

    expect(onCount(h)).toBe(0);
    expect(results(h).at(-1)).toMatchObject({ requestId, status: 'denied', reason: 'duplicate' });
    expect(ledger(h).entries[0]).toMatchObject({ requestId, status: 'completed' });
  });

  it('fails closed on corrupt restored ledger state before any actuation', () => {
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({ SouthOutlet_ManualRequest: '{not-json' }),
    });

    h.execute({
      itemName: 'SouthOutlet_ManualRequest',
      receivedCommand: gwRequest('gw-20260718-after-corrupt'),
    });

    expect(onCount(h)).toBe(0);
    expect(results(h).at(-1)).toMatchObject({ status: 'denied', reason: 'ledger_invalid' });
  });

  it('forces an orphaned pump OFF in the same evaluation as ledger recovery', () => {
    // Restart with the outlet still ON and an 'accepted' ledger entry: the
    // recovery pass must de-energize the pump in this same evaluation instead
    // of returning early and leaving it ON until the next cron.
    const requestId = 'gw-20260718-orphan-restart';
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({
        SouthOutlet_Outlet2_Switch: 'ON',
        SouthOutlet_ManualRequest: gwLedger([{
          requestId,
          status: 'accepted',
          reason: 'accepted',
          at: '2026-07-18T11:00:00.000Z',
        }]),
      }),
    });
    h.clearVolatileCache(); // no live timer survives the restart
    h.execute(); // automatic evaluation

    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(onCount(h)).toBe(0);
    const offCommands = h.events.filter(
      (e) => e.type === 'command' && e.item === 'SouthOutlet_Outlet2_Switch' && e.value === 'OFF',
    );
    expect(offCommands.length).toBeGreaterThanOrEqual(1);
    // Ledger is still recovered to restart-uncertain in the same pass.
    expect(ledger(h).entries[0]).toMatchObject({
      requestId,
      status: 'failed',
      reason: 'restart_uncertain',
    });
  });
});

describe('greywater persist / readback failure branches', () => {
  it('ends OFF and posts failed/ledger_persist_failed when the accepted persist throws', () => {
    const h = createRuleHarness({ source: ruleSource, states: baseStates() });
    h.setPersistFailure(new Error('jdbc offline'));
    h.execute({
      itemName: 'SouthOutlet_ManualRequest',
      receivedCommand: gwRequest('gw-20260718-persist-fail'),
    });

    expect(onCount(h)).toBe(0);
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(results(h).at(-1)).toMatchObject({ status: 'failed', reason: 'ledger_persist_failed' });
  });

  it('ends OFF and posts failed/ledger_readback_failed when the accept never reads back', () => {
    const h = createRuleHarness({ source: ruleSource, states: baseStates() });
    h.delayNextPersistVisibility(25); // never visible within the bounded readback loop
    h.execute({
      itemName: 'SouthOutlet_ManualRequest',
      receivedCommand: gwRequest('gw-20260718-readback-fail'),
    });

    expect(onCount(h)).toBe(0);
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(results(h).at(-1)).toMatchObject({ status: 'failed', reason: 'ledger_readback_failed' });
  });

  it('denies with ledger_restore_missing when a persisted ledger fails to restore', () => {
    const h = createRuleHarness({
      source: ruleSource,
      states: baseStates({ SouthOutlet_ManualRequest: 'NULL' }),
      histories: {
        SouthOutlet_ManualRequest: [gwLedger([{
          requestId: 'gw-20260718-prior',
          status: 'completed',
          reason: 'completed',
          at: '2026-07-18T10:00:00.000Z',
        }])],
      },
    });
    h.execute({
      itemName: 'SouthOutlet_ManualRequest',
      receivedCommand: gwRequest('gw-20260718-restore-miss'),
    });

    expect(onCount(h)).toBe(0);
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF');
    expect(results(h).at(-1)).toMatchObject({ status: 'denied', reason: 'ledger_restore_missing' });
  });

  it('ends OFF and posts failed/execution_error when the timer-callback OFF throws', () => {
    const h = createRuleHarness({ source: ruleSource, states: baseStates() });
    const requestId = 'gw-20260718-timer-fail';
    h.execute({
      itemName: 'SouthOutlet_ManualRequest',
      receivedCommand: gwRequest(requestId),
    });
    expect(onCount(h)).toBe(1);
    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('ON');

    h.failNextCommand('SouthOutlet_Outlet2_Switch', 'OFF');
    h.runNextTimer();

    expect(h.state('SouthOutlet_Outlet2_Switch')).toBe('OFF'); // safeOff backstop
    expect(results(h).at(-1)).toMatchObject({ requestId, status: 'failed', reason: 'execution_error' });
    expect(ledger(h).entries[0]).toMatchObject({
      requestId,
      status: 'failed',
      reason: 'execution_error',
    });
  });
});
