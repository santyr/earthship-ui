import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';
import {
  FEEDER_RULE_UID,
  assertAllowedFeederRequest,
  buildFeederReceipt,
  buildFeederApplyPlan,
  buildFeederRollbackPlan,
  buildFeederRuleDto,
  verifyFeederState,
} from '../../scripts/openhab-config.mjs';
import * as openhabConfig from '../../scripts/openhab-config.mjs';
import { isAllowedProxyRequest } from '../../src/lib/openhab/proxyPolicy.js';

const MANIFEST_URL = new URL('../../openhab/managed-resources.json', import.meta.url);
const RULE_URL = new URL('../../openhab/rules/feeder-owner.js', import.meta.url);

async function desired() {
  const [manifest, source] = await Promise.all([
    readFile(MANIFEST_URL, 'utf8').then(JSON.parse),
    readFile(RULE_URL, 'utf8'),
  ]);
  return { manifest, source, rule: buildFeederRuleDto(manifest, source) };
}

function verifiedFixture(rule) {
  return {
    runtimeInfo: { version: '5.2.0', buildString: 'Release Build' },
    items: {
      GoatFeeder_ManualRequest: { name: 'GoatFeeder_ManualRequest', type: 'String', state: 'NULL' },
      GoatFeeder_ManualResult: { name: 'GoatFeeder_ManualResult', type: 'String', state: 'NULL' },
      Goat_Plugs_Outlet2_Switch: { name: 'Goat_Plugs_Outlet2_Switch', type: 'Switch', state: 'OFF' },
      GoatFeedings: { name: 'GoatFeedings', type: 'Number', state: '47' },
    },
    metadata: {
      GoatFeeder_ManualRequest: {
        autoupdate: { value: 'false', config: {} },
      },
      Goat_Plugs_Outlet2_Switch: {
        expire: { value: '0h0m1s,command=OFF', config: {} },
      },
    },
    links: [],
    persistenceCoverage: {
      serviceId: 'jdbc',
      strategy: 'everyChange',
      restoreOnStartup: true,
      items: ['GoatFeeder_ManualRequest', 'GoatFeeder_ManualResult'],
    },
    requestHistoryCount: 0,
    rule,
    ruleStatus: { status: 'IDLE', statusDetail: 'NONE' },
  };
}

describe('feeder OpenHAB REST safety', () => {
  it('denies item commands, state writes, runnow, and every out-of-subset resource', () => {
    for (const [method, path] of [
      ['GET', '/rest/'],
      ['GET', '/rest/items/GoatFeeder_ManualRequest'],
      ['PUT', '/rest/items/GoatFeeder_ManualRequest'],
      ['GET', `/rest/rules/${FEEDER_RULE_UID}`],
      ['PUT', `/rest/rules/${FEEDER_RULE_UID}`],
      ['POST', `/rest/rules/${FEEDER_RULE_UID}/enable`],
    ]) expect(() => assertAllowedFeederRequest(method, path)).not.toThrow();

    for (const [method, path] of [
      ['POST', '/rest/items/Goat_Plugs_Outlet2_Switch'],
      ['POST', '/rest/items/GoatFeeder_ManualRequest'],
      ['PUT', '/rest/items/Goat_Plugs_Outlet2_Switch/state'],
      ['POST', `/rest/rules/${FEEDER_RULE_UID}/runnow`],
      ['DELETE', `/rest/rules/${FEEDER_RULE_UID}`],
      ['PUT', '/rest/items/Unrelated'],
    ]) expect(() => assertAllowedFeederRequest(method, path)).toThrow(/denied/i);
  });

  it('embeds the exact versioned source into the one canonical rule DTO', async () => {
    const { manifest, source, rule } = await desired();
    expect(rule.uid).toBe(FEEDER_RULE_UID);
    expect(rule.triggers).toEqual(manifest.subsets.feeder.rule.triggers);
    expect(rule.actions).toHaveLength(1);
    expect(rule.actions[0].configuration.script).toBe(source);
    expect(rule.actions[0].configuration.type)
      .toBe('application/javascript;version=ECMAScript-2021');
  });

  it('verifies the exact unlinked Items, persistence, metadata, source, and OFF precondition', async () => {
    const { rule } = await desired();
    const fixture = verifiedFixture(rule);
    expect(verifyFeederState(fixture)).toEqual({ ok: true, reasons: [] });

    fixture.items.Goat_Plugs_Outlet2_Switch.state = 'ON';
    fixture.links.push({ itemName: 'GoatFeeder_ManualRequest', channelUID: 'bad:link' });
    fixture.metadata.GoatFeeder_ManualRequest.autoupdate.value = 'true';
    expect(verifyFeederState(fixture)).toMatchObject({
      ok: false,
      reasons: expect.arrayContaining([
        expect.stringMatching(/actuator.*off/i),
        expect.stringMatching(/unlinked/i),
        expect.stringMatching(/autoupdate/i),
      ]),
    });
  });

  it('rejects a restored ledger with duplicate IDs or a non-canonical status', async () => {
    const { rule } = await desired();
    const duplicate = {
      requestId: 'feed-duplicate-deploy',
      status: 'complete',
      reason: 'complete',
      at: '2026-07-18T11:00:00.000Z',
    };
    const fixture = verifiedFixture(rule);
    fixture.items.GoatFeeder_ManualRequest.state = JSON.stringify({
      version: 'feeder-request-ledger/v1',
      entries: [duplicate, duplicate],
    });
    expect(verifyFeederState(fixture)).toMatchObject({
      ok: false,
      reasons: expect.arrayContaining([expect.stringMatching(/ledger.*corrupt/i)]),
    });

    fixture.items.GoatFeeder_ManualRequest.state = JSON.stringify({
      version: 'feeder-request-ledger/v1',
      entries: [{ ...duplicate, requestId: 'feed-invalid-status', status: 'owned' }],
    });
    expect(verifyFeederState(fixture).ok).toBe(false);
  });

  it('requires everyChange and restoreOnStartup in the same structural JDBC config', () => {
    expect(typeof openhabConfig.normalizePersistenceCoverage).toBe('function');
    if (typeof openhabConfig.normalizePersistenceCoverage !== 'function') return;

    expect(openhabConfig.normalizePersistenceCoverage({
      serviceId: 'jdbc',
      configs: [{ items: ['*'], strategies: ['everyChange', 'restoreOnStartup'] }],
    })).toEqual({
      serviceId: 'jdbc',
      strategy: 'everyChange',
      restoreOnStartup: true,
      items: ['GoatFeeder_ManualRequest', 'GoatFeeder_ManualResult'],
    });

    expect(openhabConfig.normalizePersistenceCoverage({
      serviceId: 'jdbc',
      configs: [
        { items: ['*'], strategies: ['everyChange'] },
        { items: ['Unrelated'], strategies: ['restoreOnStartup'] },
      ],
    })).toEqual({
      serviceId: 'jdbc',
      strategy: null,
      restoreOnStartup: false,
      items: [],
    });
  });

  it('builds a token-free, checksum-bound open receipt', async () => {
    const { rule } = await desired();
    const receipt = buildFeederReceipt({
      generation: 'feeder-20260718T160000Z',
      live: verifiedFixture(rule),
      createdAt: '2026-07-18T16:00:00.000Z',
    });
    expect(receipt).toMatchObject({
      schema: 'earthship-ui-openhab-feeder-receipt/v1',
      subset: 'feeder',
      state: 'open',
      generation: 'feeder-20260718T160000Z',
    });
    expect(receipt.checksum).toMatch(/^[a-f0-9]{64}$/);
    expect(JSON.stringify(receipt)).not.toMatch(/authorization|api.?token|password/i);
  });

  it('plans only disabled resource writes and an exact non-actuating rollback', async () => {
    const { manifest, source, rule } = await desired();
    const live = verifiedFixture(rule);
    const apply = buildFeederApplyPlan({ manifest, source, original: live });

    expect(apply.map(({ method, path, body }) => [method, path, body])).toEqual([
      ['POST', `/rest/rules/${FEEDER_RULE_UID}/enable`, 'false'],
      ['PUT', '/rest/items/GoatFeeder_ManualRequest', manifest.subsets.feeder.items[0]],
      ['PUT', '/rest/items/GoatFeeder_ManualResult', manifest.subsets.feeder.items[1]],
      ['PUT', '/rest/items/GoatFeeder_ManualRequest/metadata/autoupdate', {
        value: 'false',
        config: {},
      }],
      ['PUT', `/rest/rules/${FEEDER_RULE_UID}`, buildFeederRuleDto(manifest, source, rule)],
    ]);
    expect(apply.some(({ path }) => /runnow|Goat_Plugs_Outlet2_Switch/.test(path))).toBe(false);

    const absentOriginal = verifiedFixture(rule);
    absentOriginal.items.GoatFeeder_ManualRequest = null;
    absentOriginal.items.GoatFeeder_ManualResult = null;
    absentOriginal.metadata.GoatFeeder_ManualRequest = {};
    const rollback = buildFeederRollbackPlan(absentOriginal);
    expect(rollback.map(({ method, path }) => [method, path])).toEqual([
      ['POST', `/rest/rules/${FEEDER_RULE_UID}/enable`],
      ['PUT', `/rest/rules/${FEEDER_RULE_UID}`],
      ['DELETE', '/rest/items/GoatFeeder_ManualRequest/metadata/autoupdate'],
      ['DELETE', '/rest/items/GoatFeeder_ManualResult'],
      ['DELETE', '/rest/items/GoatFeeder_ManualRequest'],
    ]);
    expect(rollback.some(({ path }) => /runnow|Goat_Plugs_Outlet2_Switch/.test(path))).toBe(false);
  });

  it('accepts a checksum-verified candidate while disabled without mistaking it for IDLE', async () => {
    const { rule } = await desired();
    const fixture = verifiedFixture(rule);
    fixture.ruleEnabled = false;
    fixture.ruleStatus = { status: 'UNINITIALIZED', statusDetail: 'DISABLED' };
    expect(verifyFeederState(fixture, { requireDisabled: true }))
      .toEqual({ ok: true, reasons: [] });
  });

  it('keeps the feeder actuator out of the browser proxy while opening the validated request channel', () => {
    // The actuator is never directly writable from the browser in any mode.
    for (const mode of ['maintenance', 'safe-compat', 'full']) {
      expect(isAllowedProxyRequest(
        'POST',
        '/rest/items/Goat_Plugs_Outlet2_Switch',
        mode,
      )).toBe(false);
    }
    // Task 5 opens the correlated feeder request channel (validated + serialized
    // by the owner rule) for safe-compat/full, and keeps it closed in maintenance.
    expect(isAllowedProxyRequest('POST', '/rest/items/GoatFeeder_ManualRequest', 'full')).toBe(true);
    expect(isAllowedProxyRequest('POST', '/rest/items/GoatFeeder_ManualRequest', 'safe-compat')).toBe(true);
    expect(isAllowedProxyRequest('POST', '/rest/items/GoatFeeder_ManualRequest', 'maintenance')).toBe(false);
    // The result item is never a browser write path.
    expect(isAllowedProxyRequest('POST', '/rest/items/GoatFeeder_ManualResult', 'full')).toBe(false);
  });

  it('classifies feeder activity on the continuous event cursor as unsafe', () => {
    expect(typeof openhabConfig.createFeederEventGuard).toBe('function');
    if (typeof openhabConfig.createFeederEventGuard !== 'function') return;
    const guard = openhabConfig.createFeederEventGuard('2026-07-18T16:00:00.000Z');

    expect(() => guard.assertSafe()).not.toThrow();
    guard.observe({
      topic: 'openhab/items/GoatFeeder_ManualRequest/command',
      type: 'ItemCommandEvent',
      payload: JSON.stringify({ type: 'String', value: '{"requestId":"unexpected"}' }),
    });

    expect(() => guard.assertSafe()).toThrow(/execution.*activity|feeder.*activity/i);
    expect(guard.snapshot()).toMatchObject({ unsafeEventCount: 1, eventCount: 1 });
  });

  it('aborts before the next mutation when activity arrives during a transition', async () => {
    expect(typeof openhabConfig.executeGuardedOperations).toBe('function');
    expect(typeof openhabConfig.createFeederEventGuard).toBe('function');
    if (
      typeof openhabConfig.executeGuardedOperations !== 'function'
      || typeof openhabConfig.createFeederEventGuard !== 'function'
    ) return;
    const guard = openhabConfig.createFeederEventGuard('2026-07-18T16:00:00.000Z');
    const calls = [];
    const request = async (method, path) => {
      calls.push(`${method} ${path}`);
      guard.observe({
        topic: `openhab/rules/${FEEDER_RULE_UID}/state`,
        type: 'RuleStatusInfoEvent',
        payload: JSON.stringify({ status: 'RUNNING', statusDetail: 'NONE' }),
      });
    };

    await expect(openhabConfig.executeGuardedOperations({
      request,
      receipt: { writeCount: 0, transitions: [] },
      operations: [
        { method: 'PUT', path: '/rest/items/GoatFeeder_ManualRequest', body: {} },
        { method: 'PUT', path: '/rest/items/GoatFeeder_ManualResult', body: {} },
      ],
      phase: 'desired-disabled',
      eventGuard: guard,
    })).rejects.toThrow(/execution.*activity|feeder.*activity/i);

    expect(calls).toEqual(['PUT /rest/items/GoatFeeder_ManualRequest']);
  });

  it('enforces command-specific receipt phases for verify, rollback, and close', () => {
    expect(typeof openhabConfig.assertFeederTransactionPhase).toBe('function');
    if (typeof openhabConfig.assertFeederTransactionPhase !== 'function') return;

    for (const phase of ['snapshot', 'desired-disabled', 'desired', 'rolled-back-disabled', 'rolled-back']) {
      expect(() => openhabConfig.assertFeederTransactionPhase('verify', phase)).not.toThrow();
    }
    for (const phase of ['disabling', 'desired-disabled', 'desired', 'rolled-back-disabled']) {
      expect(() => openhabConfig.assertFeederTransactionPhase('rollback', phase)).not.toThrow();
    }
    expect(() => openhabConfig.assertFeederTransactionPhase('rollback', 'snapshot'))
      .toThrow(/phase/i);
    expect(() => openhabConfig.assertFeederTransactionPhase('close:desired', 'desired'))
      .not.toThrow();
    expect(() => openhabConfig.assertFeederTransactionPhase('close:desired', 'snapshot'))
      .toThrow(/phase/i);
  });

  it('accepts only an exact closed receipt when resuming an interrupted close publication', () => {
    expect(typeof openhabConfig.assertClosedReceiptRetry).toBe('function');
    if (typeof openhabConfig.assertClosedReceiptRetry !== 'function') return;
    const closed = {
      state: 'closed',
      phase: 'closed',
      terminal: 'desired',
      verification: { phase: 'desired', writeCount: 5 },
      writeCount: 5,
    };

    expect(() => openhabConfig.assertClosedReceiptRetry(closed, 'desired')).not.toThrow();
    expect(() => openhabConfig.assertClosedReceiptRetry(closed, 'rolled-back'))
      .toThrow(/terminal/i);
    expect(() => openhabConfig.assertClosedReceiptRetry({ ...closed, state: 'open' }, 'desired'))
      .toThrow(/closed/i);
  });
});
