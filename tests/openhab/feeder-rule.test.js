import { readFile } from 'node:fs/promises';
import { beforeAll, describe, expect, it } from 'vitest';
import { createRuleHarness, feederRequest } from './rule-harness.js';

const RULE_URL = new URL('../../openhab/rules/feeder-owner.js', import.meta.url);
const MANIFEST_URL = new URL('../../openhab/managed-resources.json', import.meta.url);

async function canonicalFeederResources() {
  const [ruleSource, manifestSource] = await Promise.all([
    readFile(RULE_URL, 'utf8'),
    readFile(MANIFEST_URL, 'utf8'),
  ]);
  return { ruleSource, manifest: JSON.parse(manifestSource) };
}

let ruleSource;

beforeAll(async () => {
  ({ ruleSource } = await canonicalFeederResources());
});

it('[RED:T14A-1] requires the versioned owner and durable request contract', async () => {
  let resources;
  try {
    resources = await canonicalFeederResources();
  } catch (error) {
    if (error?.code === 'ENOENT') {
      throw new Error('[RED:T14A-1] missing canonical correlated feeder owner');
    }
    throw error;
  }

  const { ruleSource, manifest } = resources;
  const feeder = manifest.subsets?.feeder;
  expect(feeder?.capability).toBe('feeder-request-v1');
  expect(feeder?.rule).toMatchObject({ uid: '88bd9ec4de', source: 'openhab/rules/feeder-owner.js' });
  expect(ruleSource).toContain('EARTHSHIP_FEEDER_OWNER_VERSION');
  expect(feeder?.items).toEqual(expect.arrayContaining([
    expect.objectContaining({ name: 'GoatFeeder_ManualRequest', type: 'String' }),
    expect.objectContaining({ name: 'GoatFeeder_ManualResult', type: 'String' }),
  ]));
  expect(feeder?.metadata).toEqual(expect.arrayContaining([
    expect.objectContaining({
      item: 'GoatFeeder_ManualRequest',
      namespace: 'autoupdate',
      value: 'false',
    }),
    expect.objectContaining({
      item: 'Goat_Plugs_Outlet2_Switch',
      namespace: 'expire',
      value: '0h0m1s,command=OFF',
    }),
  ]));
  expect(feeder?.persistence).toMatchObject({
    serviceId: 'jdbc',
    strategy: 'everyChange',
    restoreOnStartup: true,
    items: expect.arrayContaining(['GoatFeeder_ManualRequest']),
  });
  expect(feeder?.rule?.triggers).toEqual([
    expect.objectContaining({
      type: 'core.ItemCommandTrigger',
      configuration: { itemName: 'GoatFeeder_ManualRequest' },
    }),
  ]);
});

describe('exact canonical feeder owner', () => {
  it('persists the accepted request before the exact ON -> timer -> OFF/counter/complete sequence', () => {
    const harness = createRuleHarness({ source: ruleSource });
    const requestId = 'feed-20260718-success';

    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest(requestId),
    });

    expect(harness.resultPayloads().map(({ status }) => status)).toEqual(['accepted', 'running']);
    expect(harness.actuatorCommands().map(({ value }) => value)).toEqual(['ON']);
    expect(harness.pendingTimers()).toBe(1);

    const acceptedUpdate = harness.events.findIndex(({ type, item }) => (
      type === 'update' && item === 'GoatFeeder_ManualRequest'
    ));
    const acceptedPersist = harness.events.findIndex(({ type, item }) => (
      type === 'persist' && item === 'GoatFeeder_ManualRequest'
    ));
    const pulseOn = harness.events.findIndex(({ type, item, value }) => (
      type === 'command' && item === 'Goat_Plugs_Outlet2_Switch' && value === 'ON'
    ));
    expect(acceptedUpdate).toBeGreaterThanOrEqual(0);
    expect(acceptedPersist).toBeGreaterThan(acceptedUpdate);
    expect(pulseOn).toBeGreaterThan(acceptedPersist);

    harness.runNextTimer();

    expect(harness.actuatorCommands().map(({ value }) => value)).toEqual(['ON', 'OFF', 'OFF']);
    expect(harness.state('GoatFeedings')).toBe('8');
    expect(harness.resultPayloads().map(({ status }) => status)).toEqual([
      'accepted',
      'running',
      'complete',
    ]);
    expect(harness.ledger().entries[0]).toMatchObject({ requestId, status: 'complete' });
  });

  it('serializes concurrent IDs and enforces the five-second start cooldown', () => {
    const harness = createRuleHarness({ source: ruleSource });
    const first = 'feed-20260718-first';
    const busy = 'feed-20260718-busy';
    const cooldown = 'feed-20260718-cooldown';

    harness.execute({ itemName: 'GoatFeeder_ManualRequest', receivedCommand: feederRequest(first) });
    harness.execute({ itemName: 'GoatFeeder_ManualRequest', receivedCommand: feederRequest(busy) });
    expect(harness.resultPayloads().at(-1)).toMatchObject({
      requestId: busy,
      status: 'denied',
      reason: 'busy',
    });
    expect(harness.actuatorCommands().filter(({ value }) => value === 'ON')).toHaveLength(1);

    harness.runNextTimer();
    harness.advance(1000);
    harness.execute({ itemName: 'GoatFeeder_ManualRequest', receivedCommand: feederRequest(cooldown) });
    expect(harness.resultPayloads().at(-1)).toMatchObject({
      requestId: cooldown,
      status: 'denied',
      reason: 'cooldown',
    });
    expect(harness.actuatorCommands().filter(({ value }) => value === 'ON')).toHaveLength(1);
  });

  it('rejects a completed request ID after rule reload without a second pulse', () => {
    const harness = createRuleHarness({ source: ruleSource });
    const requestId = 'feed-20260718-durable-duplicate';
    const command = feederRequest(requestId);

    harness.execute({ itemName: 'GoatFeeder_ManualRequest', receivedCommand: command });
    harness.runNextTimer();
    harness.clearVolatileCache();
    harness.advance(6000);
    harness.execute({ itemName: 'GoatFeeder_ManualRequest', receivedCommand: command });

    expect(harness.resultPayloads().at(-1)).toMatchObject({
      requestId,
      status: 'denied',
      reason: 'duplicate',
    });
    expect(harness.actuatorCommands().filter(({ value }) => value === 'ON')).toHaveLength(1);
  });

  it('forces OFF, records failure, and clears busy when timer creation throws', () => {
    const harness = createRuleHarness({ source: ruleSource });
    const requestId = 'feed-20260718-timer-failure';
    harness.setTimerFailure(new Error('injected timer failure'));

    expect(() => harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest(requestId),
    })).not.toThrow();

    expect(harness.actuatorCommands().map(({ value }) => value)).toEqual(['ON', 'OFF']);
    expect(harness.resultPayloads().at(-1)).toMatchObject({
      requestId,
      status: 'failed',
      reason: 'execution_error',
    });
    expect(harness.ledger().entries[0]).toMatchObject({ requestId, status: 'failed' });
  });

  it('fails closed when ON throws and does not leave the owner busy', () => {
    const harness = createRuleHarness({ source: ruleSource });
    harness.failNextCommand('Goat_Plugs_Outlet2_Switch', 'ON');
    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest('feed-20260718-on-failure'),
    });

    expect(harness.actuatorCommands().map(({ value }) => value)).toEqual(['OFF']);
    expect(harness.pendingTimers()).toBe(0);
    expect(harness.resultPayloads().at(-1)).toMatchObject({
      status: 'failed',
      reason: 'execution_error',
    });

    harness.advance(6000);
    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest('feed-20260718-after-on-failure'),
    });
    expect(harness.actuatorCommands().filter(({ value }) => value === 'ON')).toHaveLength(1);
  });

  it('uses the redundant OFF path and clears busy when the callback OFF throws', () => {
    const harness = createRuleHarness({ source: ruleSource });
    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest('feed-20260718-off-failure'),
    });
    harness.failNextCommand('Goat_Plugs_Outlet2_Switch', 'OFF');
    harness.runNextTimer();

    expect(harness.actuatorCommands().map(({ value }) => value)).toEqual(['ON', 'OFF']);
    expect(harness.state('Goat_Plugs_Outlet2_Switch')).toBe('OFF');
    expect(harness.resultPayloads().at(-1)).toMatchObject({
      status: 'failed',
      reason: 'execution_error',
    });
  });

  it('does not absorb an unrelated counter update during the pulse', () => {
    const harness = createRuleHarness({ source: ruleSource, states: { GoatFeedings: '20' } });
    const requestId = 'feed-20260718-counter-race';

    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: feederRequest(requestId),
    });
    harness.setState('GoatFeedings', '21');
    harness.runNextTimer();

    expect(harness.state('GoatFeedings')).toBe('21');
    expect(harness.resultPayloads().at(-1)).toMatchObject({
      requestId,
      status: 'failed',
      reason: 'execution_error',
    });
    expect(harness.ledger().entries[0]).toMatchObject({ requestId, status: 'failed' });
  });
});
