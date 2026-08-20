import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import manifest from '../openhab/energy-analytics-item.json';
import {
  ENERGY_ANALYTICS_ITEM,
  ITEM_PATH,
  RECEIPT_FILENAME,
  SNAPSHOT_FILENAME,
  applyTransaction,
  assertAnalyticsConfigRequest,
  assertReceiptIntegrity,
  buildApplyPlan,
  buildReceipt,
  buildRollbackPlan,
  closeTransaction,
  rehearseTransaction,
  rollbackTransaction,
  snapshotTransaction,
  verifyTransaction,
} from '../scripts/energy-analytics-config.mjs';

const ORIGINAL = Object.freeze({
  name: 'Energy_Analytics_JSON', type: 'String', label: 'Previous label',
  category: 'energy', tags: ['Point'], groupNames: ['Existing_Group'],
});
const temporaryDirectories = [];

async function receiptDirectory() {
  const directory = await mkdtemp(join(tmpdir(), 'energy-analytics-config-test-'));
  temporaryDirectories.push(directory);
  return directory;
}

function mutableItemTransport(initial, { ambiguousPut = false } = {}) {
  let item = structuredClone(initial);
  const calls = [];
  const request = async (method, path, options = {}) => {
    const recorded = structuredClone(options);
    delete recorded.transaction;
    calls.push({ method, path, options: recorded });
    expect(path).toBe(ITEM_PATH);
    if (method === 'GET') return structuredClone(item);
    if (method === 'PUT') {
      item = structuredClone(options.body);
      if (ambiguousPut) throw new Error('connection closed after write');
      return null;
    }
    if (method === 'DELETE') {
      item = null;
      return null;
    }
    throw new Error(`unexpected request ${method} ${path}`);
  };
  return { calls, current: () => structuredClone(item), request };
}

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => (
    rm(path, { recursive: true, force: true })
  )));
});

describe('Energy analytics observational Item transaction', () => {
  it('declares one String Item and no command, rule, state, or actuator', () => {
    expect(manifest).toEqual({
      schema: 'earthship-energy-analytics-observation/v1',
      items: [{
        name: 'Energy_Analytics_JSON', type: 'String',
        label: 'Energy analytics summary', category: '', tags: [], groupNames: [],
      }],
    });
    expect(JSON.stringify(manifest)).not.toMatch(/Switch|command|rule|actuator/i);
    expect(ENERGY_ANALYTICS_ITEM).toEqual(manifest.items[0]);
  });

  it('allows only exact Item configuration paths and denies every state write', () => {
    for (const method of ['GET', 'PUT', 'DELETE']) {
      expect(() => assertAnalyticsConfigRequest(method, ITEM_PATH)).not.toThrow();
    }
    for (const [method, path] of [
      ['PUT', `${ITEM_PATH}/state`], ['POST', ITEM_PATH],
      ['GET', `${ITEM_PATH}?x=1`], ['GET', `${ITEM_PATH}/`],
      ['PUT', '/rest/items/SouthOutlet_Outlet2_Switch'],
      ['PUT', '/rest/rules/example'],
    ]) expect(() => assertAnalyticsConfigRequest(method, path)).toThrow(/denied/i);
  });

  it('builds one exact apply and exact restore-or-delete rollback', () => {
    expect(buildApplyPlan(null)).toEqual([
      { method: 'PUT', path: ITEM_PATH, body: ENERGY_ANALYTICS_ITEM },
    ]);
    expect(buildRollbackPlan(ORIGINAL)).toEqual([
      { method: 'PUT', path: ITEM_PATH, body: ORIGINAL },
    ]);
    expect(buildRollbackPlan(null)).toEqual([
      { method: 'DELETE', path: ITEM_PATH },
    ]);
  });

  it('binds a token-free exact snapshot to checksum and digest', () => {
    const { receipt, snapshot } = buildReceipt(ORIGINAL, {
      createdAt: '2026-08-20T18:00:00.000Z',
    });
    expect(snapshot).toEqual({ item: ORIGINAL });
    expect(receipt).toMatchObject({
      schema: 'earthship-energy-analytics-config-receipt/v1',
      state: 'open', phase: 'snapshot', itemName: 'Energy_Analytics_JSON',
      writeCount: 0,
    });
    expect(receipt.snapshotDigest).toMatch(/^[a-f0-9]{64}$/);
    expect(receipt.checksum).toMatch(/^[a-f0-9]{64}$/);
    expect(JSON.stringify({ receipt, snapshot })).not.toMatch(/token|password|secret/i);
    expect(() => assertReceiptIntegrity(receipt, snapshot)).not.toThrow();
    expect(() => assertReceiptIntegrity(receipt, { item: null })).toThrow(/digest/i);
  });

  it('snapshots privately, rehearses without changing receipt bytes, applies once, verifies, and closes', async () => {
    const directory = await receiptDirectory();
    const transport = mutableItemTransport(null);
    await snapshotTransaction({ request: transport.request, receiptDir: directory });
    expect((await stat(directory)).mode & 0o777).toBe(0o700);
    expect((await stat(join(directory, RECEIPT_FILENAME))).mode & 0o777).toBe(0o600);
    const beforeReceipt = await readFile(join(directory, RECEIPT_FILENAME));
    const beforeSnapshot = await readFile(join(directory, SNAPSHOT_FILENAME));
    await rehearseTransaction({ receiptDir: directory });
    expect(await readFile(join(directory, RECEIPT_FILENAME))).toEqual(beforeReceipt);
    expect(await readFile(join(directory, SNAPSHOT_FILENAME))).toEqual(beforeSnapshot);

    transport.calls.length = 0;
    const applied = await applyTransaction({ request: transport.request, receiptDir: directory });
    expect(applied.phase).toBe('desired');
    expect(applied.writeCount).toBe(1);
    expect(transport.calls.map(({ method }) => method)).toEqual(['GET', 'PUT', 'GET']);
    await expect(verifyTransaction({ request: transport.request, receiptDir: directory }))
      .resolves.toMatchObject({ ok: true, expected: 'desired' });
    await expect(closeTransaction({ request: transport.request, receiptDir: directory }))
      .resolves.toMatchObject({ state: 'closed', phase: 'desired' });
  });

  it('refuses missing/tampered receipts and pre-state drift before writes', async () => {
    const missing = await receiptDirectory();
    const missingTransport = mutableItemTransport(null);
    await expect(applyTransaction({ request: missingTransport.request, receiptDir: missing }))
      .rejects.toThrow(/receipt|snapshot/i);
    expect(missingTransport.calls).toEqual([]);

    const tampered = await receiptDirectory();
    const initial = mutableItemTransport(null);
    await snapshotTransaction({ request: initial.request, receiptDir: tampered });
    await writeFile(join(tampered, SNAPSHOT_FILENAME), `${JSON.stringify({ item: ORIGINAL })}\n`);
    initial.calls.length = 0;
    await expect(applyTransaction({ request: initial.request, receiptDir: tampered }))
      .rejects.toThrow(/digest/i);
    expect(initial.calls).toEqual([]);

    const drift = await receiptDirectory();
    await snapshotTransaction({ request: mutableItemTransport(ORIGINAL).request, receiptDir: drift });
    const drifted = mutableItemTransport({ ...ORIGINAL, label: 'outside drift' });
    await expect(applyTransaction({ request: drifted.request, receiptDir: drift }))
      .rejects.toThrow(/drift/i);
    expect(drifted.calls.map(({ method }) => method)).toEqual(['GET']);
  });

  it('never retries an ambiguous write and remains rollback-capable', async () => {
    const directory = await receiptDirectory();
    await snapshotTransaction({ request: mutableItemTransport(null).request, receiptDir: directory });
    const ambiguous = mutableItemTransport(null, { ambiguousPut: true });
    await expect(applyTransaction({ request: ambiguous.request, receiptDir: directory }))
      .rejects.toThrow(/connection closed/i);
    expect(ambiguous.calls.filter(({ method }) => method === 'PUT')).toHaveLength(1);
    const receipt = JSON.parse(await readFile(join(directory, RECEIPT_FILENAME), 'utf8'));
    expect(receipt.phase).toBe('applying');
  });

  it.each([['restores exact original', ORIGINAL], ['deletes created Item', null]])(
    '%s', async (_label, original) => {
      const directory = await receiptDirectory();
      const transport = mutableItemTransport(original);
      await snapshotTransaction({ request: transport.request, receiptDir: directory });
      await applyTransaction({ request: transport.request, receiptDir: directory });
      await rollbackTransaction({ request: transport.request, receiptDir: directory });
      expect(transport.current()).toEqual(original);
    },
  );
});
