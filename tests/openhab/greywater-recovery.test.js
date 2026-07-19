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
});
