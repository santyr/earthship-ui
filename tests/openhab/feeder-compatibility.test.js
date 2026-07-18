import { readFile } from 'node:fs/promises';
import { beforeAll, describe, expect, it } from 'vitest';
import { createRuleHarness } from './rule-harness.js';

const RULE_URL = new URL('../../openhab/rules/feeder-owner.js', import.meta.url);
let ruleSource;

beforeAll(async () => {
  ruleSource = await readFile(RULE_URL, 'utf8');
});

describe('legacy feeder callers', () => {
  it('keeps triggerless runnow/payment invocations on the same pulse owner without correlated results', () => {
    const harness = createRuleHarness({ source: ruleSource, states: { GoatFeedings: '12' } });

    harness.execute(undefined);
    expect(harness.actuatorCommands().map(({ value }) => value)).toEqual(['ON']);
    expect(harness.resultPayloads()).toEqual([]);

    harness.runNextTimer();
    expect(harness.actuatorCommands().map(({ value }) => value)).toEqual(['ON', 'OFF', 'OFF']);
    expect(harness.state('GoatFeedings')).toBe('13');
    expect(harness.resultPayloads()).toEqual([]);
  });

  it('shares busy and cooldown serialization with manual requests', () => {
    const harness = createRuleHarness({ source: ruleSource });

    harness.execute({});
    harness.execute({});
    expect(harness.actuatorCommands().filter(({ value }) => value === 'ON')).toHaveLength(1);
    harness.runNextTimer();
    harness.advance(1000);
    harness.execute({});
    expect(harness.actuatorCommands().filter(({ value }) => value === 'ON')).toHaveLength(1);
  });

  it('fails closed when a legacy invocation follows a restart-interrupted manual pulse', () => {
    const harness = createRuleHarness({ source: ruleSource });

    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: JSON.stringify({
        requestId: 'feed-20260718-restart-legacy',
        requestedAt: '2026-07-18T12:00:00.000Z',
      }),
    });
    harness.clearVolatileCache();
    harness.advance(6000);
    harness.execute(undefined);

    expect(harness.actuatorCommands().filter(({ value }) => value === 'ON')).toHaveLength(1);
    expect(harness.pendingTimers()).toBe(1);
    expect(harness.ledger().entries[0]).toMatchObject({
      requestId: 'feed-20260718-restart-legacy',
      status: 'failed',
      reason: 'restart_uncertain',
    });
  });

  it('applies the durable manual-start cooldown to a legacy invocation after reload', () => {
    const harness = createRuleHarness({ source: ruleSource });

    harness.execute({
      itemName: 'GoatFeeder_ManualRequest',
      receivedCommand: JSON.stringify({
        requestId: 'feed-20260718-cooldown-legacy',
        requestedAt: '2026-07-18T12:00:00.000Z',
      }),
    });
    harness.runNextTimer();
    harness.clearVolatileCache();
    harness.advance(1000);
    harness.execute(undefined);

    expect(harness.actuatorCommands().filter(({ value }) => value === 'ON')).toHaveLength(1);
    expect(harness.pendingTimers()).toBe(0);
  });
});
