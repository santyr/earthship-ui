import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import manifest from '../../openhab/thermal-model-items.json';
import {
  RECEIPT_FILENAME,
  SNAPSHOT_FILENAME,
  THERMAL_ITEM,
  applyTransaction,
  assertReceiptIntegrity,
  assertThermalOutputRequest,
  buildApplyPlan,
  buildReceipt,
  buildRollbackPlan,
  rollbackTransaction,
  snapshotTransaction,
  verifyTransaction,
} from '../../scripts/thermal-model-config.mjs';

const ITEM_PATH = '/rest/items/Thermal_Model_JSON';
const STATE_PATH = `${ITEM_PATH}/state`;
const ORIGINAL = Object.freeze({
  name: 'Thermal_Model_JSON',
  type: 'String',
  label: 'Previous thermal output',
  category: 'temperature',
  tags: ['Point'],
  groupNames: ['Existing_Group'],
});

const temporaryDirectories = [];

async function receiptDirectory() {
  const directory = await mkdtemp(join(tmpdir(), 'thermal-model-config-test-'));
  temporaryDirectories.push(directory);
  return directory;
}

function mutableItemTransport(initial, { ambiguousPut = false } = {}) {
  let item = structuredClone(initial);
  const calls = [];
  const request = async (method, path, options = {}) => {
    calls.push({ method, path, options: structuredClone(options) });
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
    throw new Error(`unexpected fake request ${method} ${path}`);
  };
  return { calls, current: () => structuredClone(item), request };
}

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => (
    rm(path, { recursive: true, force: true })
  )));
});

describe('thermal observational resources', () => {
  it('contains one String item and no rule, command, or actuator', () => {
    expect(manifest).toEqual({
      schema: 'earthship-thermal-observations/v1',
      items: [{
        name: 'Thermal_Model_JSON', type: 'String',
        label: 'Thermal model shadow output', category: '', tags: [], groupNames: [],
      }],
    });
    expect(JSON.stringify(manifest)).not.toMatch(/Switch|command|rule|actuator/i);
  });

  it('separates exact item configuration and runtime state PUTs and denies every command/path', () => {
    expect(() => assertThermalOutputRequest('GET', ITEM_PATH)).not.toThrow();
    expect(() => assertThermalOutputRequest('PUT', ITEM_PATH, THERMAL_ITEM)).not.toThrow();
    expect(() => assertThermalOutputRequest('DELETE', ITEM_PATH)).not.toThrow();
    expect(() => assertThermalOutputRequest('PUT', STATE_PATH)).not.toThrow();
    expect(() => assertThermalOutputRequest(
      'PUT', STATE_PATH, '{"version":1,"status":"shadow"}',
    )).not.toThrow();

    expect(() => assertThermalOutputRequest('POST', ITEM_PATH)).toThrow(/denied/i);
    expect(() => assertThermalOutputRequest('POST', STATE_PATH, 'ON')).toThrow(/denied/i);
    expect(() => assertThermalOutputRequest(
      'PUT', '/rest/items/SouthOutlet_Outlet2_Switch/state', 'ON',
    )).toThrow(/denied/i);
    expect(() => assertThermalOutputRequest('PUT', `${ITEM_PATH}?x=1`, THERMAL_ITEM))
      .toThrow(/denied/i);
    expect(() => assertThermalOutputRequest('PUT', '/rest/items/%54hermal_Model_JSON', THERMAL_ITEM))
      .toThrow(/denied/i);
    expect(() => assertThermalOutputRequest('PUT', ITEM_PATH, {
      ...THERMAL_ITEM,
      state: 'forbidden-runtime-state',
    })).toThrow(/body/i);
    expect(() => assertThermalOutputRequest('PUT', STATE_PATH, { status: 'shadow' }))
      .toThrow(/body/i);
    expect(() => assertThermalOutputRequest('PUT', STATE_PATH, 'ON')).toThrow(/body/i);
    expect(() => assertThermalOutputRequest('DELETE', ITEM_PATH, 'unexpected'))
      .toThrow(/body/i);
  });

  it('builds one-item apply and exact restore-or-delete rollback plans', () => {
    expect(buildApplyPlan(null)).toEqual([
      { method: 'PUT', path: ITEM_PATH, body: THERMAL_ITEM },
    ]);
    expect(buildApplyPlan(ORIGINAL)).toEqual([
      { method: 'PUT', path: ITEM_PATH, body: THERMAL_ITEM },
    ]);
    expect(buildRollbackPlan(ORIGINAL)).toEqual([
      { method: 'PUT', path: ITEM_PATH, body: ORIGINAL },
    ]);
    expect(buildRollbackPlan(null)).toEqual([
      { method: 'DELETE', path: ITEM_PATH },
    ]);
  });

  it('binds an exact, token-free pre-state snapshot to both digests', () => {
    const { receipt, snapshot } = buildReceipt(ORIGINAL, {
      createdAt: '2026-08-13T20:00:00.000Z',
    });

    expect(snapshot).toEqual({ item: ORIGINAL });
    expect(receipt).toMatchObject({
      schema: 'earthship-thermal-model-config-receipt/v1',
      state: 'open',
      phase: 'snapshot',
      itemName: 'Thermal_Model_JSON',
      writeCount: 0,
      createdAt: '2026-08-13T20:00:00.000Z',
    });
    expect(receipt.snapshotDigest).toMatch(/^[a-f0-9]{64}$/);
    expect(receipt.checksum).toMatch(/^[a-f0-9]{64}$/);
    expect(JSON.stringify({ receipt, snapshot })).not.toMatch(/authorization|token|password|secret/i);
    expect(() => assertReceiptIntegrity(receipt, snapshot)).not.toThrow();

    expect(() => assertReceiptIntegrity(receipt, { item: null })).toThrow(/digest/i);
    expect(() => assertReceiptIntegrity({ ...receipt, phase: 'desired' }, snapshot))
      .toThrow(/checksum/i);
  });

  it('snapshots only the exact item and writes a receipt directory before any mutation', async () => {
    const directory = await receiptDirectory();
    const transport = mutableItemTransport(ORIGINAL);

    const result = await snapshotTransaction({
      request: transport.request,
      receiptDir: directory,
      now: () => new Date('2026-08-13T20:00:00.000Z'),
    });

    expect(result.snapshot).toEqual({ item: ORIGINAL });
    expect(transport.calls).toEqual([{
      method: 'GET', path: ITEM_PATH, options: { allowMissing: true },
    }]);
    const storedReceipt = JSON.parse(await readFile(join(directory, RECEIPT_FILENAME), 'utf8'));
    const storedSnapshot = JSON.parse(await readFile(join(directory, SNAPSHOT_FILENAME), 'utf8'));
    expect(() => assertReceiptIntegrity(storedReceipt, storedSnapshot)).not.toThrow();
  });

  it('refuses apply before contact when the receipt is missing or its snapshot is tampered', async () => {
    const missing = await receiptDirectory();
    const missingTransport = mutableItemTransport(null);
    await expect(applyTransaction({
      request: missingTransport.request,
      receiptDir: missing,
    })).rejects.toThrow(/receipt|snapshot/i);
    expect(missingTransport.calls).toEqual([]);

    const tampered = await receiptDirectory();
    const transport = mutableItemTransport(null);
    await snapshotTransaction({ request: transport.request, receiptDir: tampered });
    await writeFile(
      join(tampered, SNAPSHOT_FILENAME),
      `${JSON.stringify({ item: ORIGINAL })}\n`,
      'utf8',
    );
    transport.calls.length = 0;
    await expect(applyTransaction({
      request: transport.request,
      receiptDir: tampered,
    })).rejects.toThrow(/digest/i);
    expect(transport.calls).toEqual([]);
  });

  it('refuses apply on live pre-state drift and performs no write', async () => {
    const directory = await receiptDirectory();
    const snapshotTransport = mutableItemTransport(ORIGINAL);
    await snapshotTransaction({ request: snapshotTransport.request, receiptDir: directory });
    const drifted = mutableItemTransport({ ...ORIGINAL, label: 'Changed elsewhere' });

    await expect(applyTransaction({
      request: drifted.request,
      receiptDir: directory,
    })).rejects.toThrow(/drift/i);
    expect(drifted.calls.map(({ method }) => method)).toEqual(['GET']);
  });

  it('applies exactly one configuration PUT, verifies it, and records the write', async () => {
    const directory = await receiptDirectory();
    const transport = mutableItemTransport(null);
    await snapshotTransaction({ request: transport.request, receiptDir: directory });
    transport.calls.length = 0;

    const applied = await applyTransaction({
      request: transport.request,
      receiptDir: directory,
      now: () => new Date('2026-08-13T20:01:00.000Z'),
    });

    expect(applied.phase).toBe('desired');
    expect(applied.writeCount).toBe(1);
    expect(transport.calls).toEqual([
      { method: 'GET', path: ITEM_PATH, options: { allowMissing: true } },
      { method: 'PUT', path: ITEM_PATH, options: { body: THERMAL_ITEM } },
      { method: 'GET', path: ITEM_PATH, options: { allowMissing: true } },
    ]);
    await expect(verifyTransaction({
      request: transport.request,
      receiptDir: directory,
    })).resolves.toMatchObject({ ok: true, expected: 'desired' });
  });

  it('never retries an ambiguous apply write and leaves a rollback-capable receipt', async () => {
    const directory = await receiptDirectory();
    const initial = mutableItemTransport(null);
    await snapshotTransaction({ request: initial.request, receiptDir: directory });
    const ambiguous = mutableItemTransport(null, { ambiguousPut: true });

    await expect(applyTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    })).rejects.toThrow(/connection closed/i);
    expect(ambiguous.calls.filter(({ method }) => method === 'PUT')).toHaveLength(1);
    const receipt = JSON.parse(await readFile(join(directory, RECEIPT_FILENAME), 'utf8'));
    expect(receipt.phase).toBe('applying');
    expect(receipt.writeCount).toBe(0);
  });

  it.each([
    ['restores an existing item exactly', ORIGINAL],
    ['deletes an item created by apply', null],
  ])('%s', async (_label, original) => {
    const directory = await receiptDirectory();
    const transport = mutableItemTransport(original);
    await snapshotTransaction({ request: transport.request, receiptDir: directory });
    await applyTransaction({ request: transport.request, receiptDir: directory });
    transport.calls.length = 0;

    const rolledBack = await rollbackTransaction({
      request: transport.request,
      receiptDir: directory,
      now: () => new Date('2026-08-13T20:02:00.000Z'),
    });

    expect(rolledBack.phase).toBe('rolled-back');
    expect(transport.current()).toEqual(original);
    expect(transport.calls.filter(({ method }) => ['PUT', 'DELETE'].includes(method)))
      .toEqual(original
        ? [{ method: 'PUT', path: ITEM_PATH, options: { body: ORIGINAL } }]
        : [{ method: 'DELETE', path: ITEM_PATH, options: { allowMissing: true } }]);
  });

  it('refuses rollback when live state is neither captured original nor exact desired', async () => {
    const directory = await receiptDirectory();
    const transport = mutableItemTransport(null);
    await snapshotTransaction({ request: transport.request, receiptDir: directory });
    await applyTransaction({ request: transport.request, receiptDir: directory });
    const drifted = mutableItemTransport({ ...THERMAL_ITEM, label: 'Unexpected drift' });

    await expect(rollbackTransaction({
      request: drifted.request,
      receiptDir: directory,
    })).rejects.toThrow(/drift/i);
    expect(drifted.calls.map(({ method }) => method)).toEqual(['GET']);
  });
});
