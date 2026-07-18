import { readFile } from 'node:fs/promises';
import { beforeAll, describe, expect, it } from 'vitest';
import { createRuleHarness, feederLedger, feederRequest } from './rule-harness.js';

const RULE_URL = new URL('../../openhab/rules/feeder-owner.js', import.meta.url);
const MANIFEST_URL = new URL('../../openhab/managed-resources.json', import.meta.url);
let ruleSource;
let feeder;

beforeAll(async () => {
  const [source, manifest] = await Promise.all([
    readFile(RULE_URL, 'utf8'),
    readFile(MANIFEST_URL, 'utf8').then(JSON.parse),
  ]);
  ruleSource = source;
  feeder = manifest.subsets.feeder;
});

describe('durable feeder request ledger', () => {
  it.each([
    ['corrupt', '{not-json'],
    ['oversize', 'x'.repeat(9000)],
  ])('fails closed on %s restored state before actuation', (_label, state) => {
    const harness = createRuleHarness({
      source: ruleSource,
      states: { GoatFeeder_ManualRequest: state },
    });

    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest('feed-20260718-invalid-ledger'),
    });

    expect(harness.actuatorCommands()).toEqual([]);
    expect(harness.resultPayloads().at(-1)).toMatchObject({
      status: 'denied',
      reason: 'ledger_invalid',
    });
  });

  it('enforces the 8 KiB ledger bound in UTF-8 bytes rather than JavaScript characters', () => {
    const state = feederLedger([{
      requestId: 'feed-unicode-oversize',
      status: 'complete',
      reason: '🔥'.repeat(2100),
      at: '2026-07-18T11:00:00.000Z',
    }]);
    expect(state.length).toBeLessThan(8192);
    const harness = createRuleHarness({
      source: ruleSource,
      states: { GoatFeeder_ManualRequest: state },
    });

    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest('feed-20260718-after-unicode'),
    });

    expect(harness.actuatorCommands()).toEqual([]);
    expect(harness.resultPayloads().at(-1)).toMatchObject({
      status: 'denied',
      reason: 'ledger_invalid',
    });
  });

  it('treats NULL as empty only when JDBC proves no prior ledger history', () => {
    const harness = createRuleHarness({
      source: ruleSource,
      histories: {
        GoatFeeder_ManualRequest: [feederLedger([{
          requestId: 'feed-old-history',
          status: 'complete',
          reason: 'complete',
          at: '2026-07-18T11:00:00.000Z',
        }])],
      },
    });

    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest('feed-20260718-missing-restore'),
    });

    expect(harness.actuatorCommands()).toEqual([]);
    expect(harness.resultPayloads().at(-1)).toMatchObject({
      status: 'denied',
      reason: 'ledger_restore_missing',
    });
  });

  it('keeps only the newest 32 canonical entries', () => {
    const oldEntries = Array.from({ length: 32 }, (_, index) => ({
      requestId: `feed-old-${String(index).padStart(2, '0')}`,
      status: 'complete',
      reason: 'complete',
      at: new Date(Date.parse('2026-07-17T12:00:00.000Z') - (index * 1000)).toISOString(),
    }));
    const harness = createRuleHarness({
      source: ruleSource,
      states: { GoatFeeder_ManualRequest: feederLedger(oldEntries) },
    });
    const requestId = 'feed-20260718-newest';

    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest(requestId),
    });

    expect(harness.ledger().entries).toHaveLength(32);
    expect(harness.ledger().entries[0]).toMatchObject({ requestId, status: 'accepted' });
    expect(harness.ledger().entries.at(-1).requestId).toBe('feed-old-30');
  });

  it('aborts before ON when accepted-ledger readback does not match', () => {
    const harness = createRuleHarness({ source: ruleSource });
    harness.suppressRequestReadback();

    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest('feed-20260718-readback'),
    });

    expect(harness.actuatorCommands()).toEqual([]);
    expect(harness.resultPayloads().at(-1)).toMatchObject({
      status: 'failed',
      reason: 'ledger_readback_failed',
    });
  });

  it('waits for the exact accepted ledger to become visible in asynchronous JDBC history', () => {
    const harness = createRuleHarness({ source: ruleSource });
    harness.delayNextPersistVisibility(2);

    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest('feed-20260718-delayed-jdbc'),
    });

    expect(harness.actuatorCommands().map(({ value }) => value)).toEqual(['ON']);
    expect(harness.resultPayloads().map(({ status }) => status)).toEqual(['accepted', 'running']);
    expect(harness.events.filter(({ type }) => type === 'history').length).toBeGreaterThan(2);
  });

  it('uses GraalJS capital-Java interop for bounded persistence polling', () => {
    const harness = createRuleHarness({ source: ruleSource, javaInterop: true });
    harness.delayNextPersistVisibility(1);

    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest('feed-20260718-graal-java'),
    });

    expect(harness.actuatorCommands().map(({ value }) => value)).toEqual(['ON']);
    expect(harness.events.filter(({ type }) => type === 'sleep').length).toBeGreaterThan(0);
  });

  it('uses the request item as the only ledger and keeps operational metadata immutable', () => {
    expect(feeder.items.map(({ name }) => name)).toEqual([
      'GoatFeeder_ManualRequest',
      'GoatFeeder_ManualResult',
    ]);
    expect(feeder.metadata).toEqual([
      {
        item: 'GoatFeeder_ManualRequest',
        namespace: 'autoupdate',
        value: 'false',
        config: {},
      },
      {
        item: 'Goat_Plugs_Outlet2_Switch',
        namespace: 'expire',
        value: '0h0m1s,command=OFF',
        config: {},
      },
    ]);
  });

  it('rejects duplicate IDs inside restored ledger state as non-canonical', () => {
    const duplicate = {
      requestId: 'feed-duplicate-ledger',
      status: 'complete',
      reason: 'complete',
      at: '2026-07-18T11:00:00.000Z',
    };
    const harness = createRuleHarness({
      source: ruleSource,
      states: { GoatFeeder_ManualRequest: feederLedger([duplicate, duplicate]) },
    });
    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest('feed-20260718-new-after-corrupt'),
    });

    expect(harness.actuatorCommands()).toEqual([]);
    expect(harness.resultPayloads().at(-1)).toMatchObject({
      status: 'denied',
      reason: 'ledger_invalid',
    });
  });

  it('marks interrupted accepted work restart-uncertain and never replays it', () => {
    const requestId = 'feed-20260718-interrupted';
    const harness = createRuleHarness({
      source: ruleSource,
      states: {
        GoatFeeder_ManualRequest: feederLedger([{
          requestId,
          status: 'accepted',
          reason: 'accepted',
          at: '2026-07-18T11:00:00.000Z',
        }]),
      },
    });

    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest(requestId),
    });

    expect(harness.actuatorCommands()).toEqual([]);
    expect(harness.ledger().entries[0]).toMatchObject({
      requestId,
      status: 'failed',
      reason: 'restart_uncertain',
    });
    expect(harness.resultPayloads().at(-1)).toMatchObject({
      requestId,
      status: 'denied',
      reason: 'duplicate',
    });
  });

  it('denies stale correlated requests before ledger mutation or actuation', () => {
    const harness = createRuleHarness({ source: ruleSource });
    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest('feed-20260718-stale', '2026-07-18T11:55:00.000Z'),
    });

    expect(harness.actuatorCommands()).toEqual([]);
    expect(harness.ledger()).toBeNull();
    expect(harness.resultPayloads().at(-1)).toMatchObject({
      status: 'denied',
      reason: 'request_stale',
    });
  });

  it('requires requestedAt on every correlated manual request', () => {
    const harness = createRuleHarness({ source: ruleSource });
    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: JSON.stringify({ requestId: 'feed-20260718-no-time' }),
    });

    expect(harness.actuatorCommands()).toEqual([]);
    expect(harness.ledger()).toBeNull();
    expect(harness.resultPayloads().at(-1)).toMatchObject({
      status: 'denied',
      reason: 'request_invalid',
    });
  });
});
