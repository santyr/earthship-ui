import {
  access,
  mkdtemp,
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
} from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import validShadow from '../fixtures/thermal-shadow-v1-available.json';
import {
  ITEM_PATH,
  LOCK_FILENAME,
  RECEIPT_FILENAME,
  SNAPSHOT_FILENAME,
  STATE_PATH,
  THERMAL_ITEM,
  applyTransaction,
  authorizeThermalOutputRequest,
  buildReceipt,
  createRestClient,
  inspectReceiptLock,
  main,
  rollbackTransaction,
  settleTransaction,
  snapshotTransaction,
  verifyTransaction,
} from '../../scripts/thermal-model-config.mjs';

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
  const directory = await mkdtemp(join(tmpdir(), 'thermal-config-hardening-'));
  temporaryDirectories.push(directory);
  return directory;
}

function response(status = 204, { redirected = false, value = null } = {}) {
  return {
    ok: status >= 200 && status < 300,
    redirected,
    status,
    text: async () => (value === null ? '' : JSON.stringify(value)),
  };
}

function transactionContext(original, operation) {
  const { receipt, snapshot } = buildReceipt(original, {
    createdAt: '2026-08-13T20:00:00.000Z',
  });
  return { operation, receipt, snapshot };
}

function mutableTransport(initial, {
  deleteMode = 'success',
  putMode = 'success',
  onPut,
} = {}) {
  let item = structuredClone(initial);
  const calls = [];
  const request = async (method, path, options = {}) => {
    calls.push({ method, path, options: structuredClone(options) });
    if (method === 'GET') return structuredClone(item);
    if (method === 'PUT') {
      if (onPut) await onPut(options.body);
      if (putMode === 'throw-before-land') throw new Error('write outcome unknown');
      item = structuredClone(options.body);
      if (putMode === 'land-then-throw') throw new Error('write outcome unknown');
      return null;
    }
    if (method === 'DELETE') {
      if (deleteMode === 'throw-before-land') throw new Error('write outcome unknown');
      item = null;
      if (deleteMode === 'land-then-throw') throw new Error('write outcome unknown');
      return null;
    }
    throw new Error(`unexpected fake request ${method} ${path}`);
  };
  return { calls, current: () => structuredClone(item), request };
}

async function storedReceipt(directory) {
  return JSON.parse(await readFile(join(directory, RECEIPT_FILENAME), 'utf8'));
}

async function assertNoLockOrTemps(directory) {
  const names = await readdir(directory);
  expect(names).not.toContain(LOCK_FILENAME);
  expect(names.filter((name) => name.includes('.tmp-'))).toEqual([]);
}

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => (
    rm(path, { recursive: true, force: true })
  )));
});

describe('confined OpenHAB destination', () => {
  it.each([
    'ftp://openhab.test',
    'https://user@openhab.test',
    'https://user:pass@openhab.test',
    'https://openhab.test/rest',
    'https://openhab.test/rest/',
    'https://openhab.test/?token=bad',
    'https://openhab.test/#fragment',
  ])('rejects unsafe base URL %s before fetch', (baseUrl) => {
    const fetchCalls = [];
    expect(() => createRestClient({
      baseUrl,
      authorization: 'Basic fixture',
      fetchImpl: (...args) => fetchCalls.push(args),
    })).toThrow(/OpenHAB URL|base URL|destination/i);
    expect(fetchCalls).toEqual([]);
  });

  it.each(['https://openhab.test', 'https://openhab.test/'])(
    'resolves the exact allowed path on a root base and disables redirects: %s',
    async (baseUrl) => {
      const fetchCalls = [];
      const request = createRestClient({
        baseUrl,
        authorization: 'Basic fixture',
        fetchImpl: async (...args) => {
          fetchCalls.push(args);
          return response();
        },
      });

      await request('PUT', ITEM_PATH, {
        body: THERMAL_ITEM,
        transaction: transactionContext(null, 'apply'),
      });

      expect(fetchCalls).toHaveLength(1);
      expect(fetchCalls[0][0]).toBe(`https://openhab.test${ITEM_PATH}`);
      expect(fetchCalls[0][1]).toMatchObject({ method: 'PUT', redirect: 'error' });
    },
  );

  it.each([
    `//evil.invalid${ITEM_PATH}`,
    '/%72est/items/Thermal_Model_JSON',
    `${ITEM_PATH}?redirect=https://evil.invalid`,
    `${ITEM_PATH}#fragment`,
  ])('rejects alternate or destination-changing request path %s', async (path) => {
    const fetchCalls = [];
    const request = createRestClient({
      baseUrl: 'https://openhab.test/',
      authorization: 'Basic fixture',
      fetchImpl: async (...args) => {
        fetchCalls.push(args);
        return response();
      },
    });

    await expect(request('GET', path)).rejects.toThrow(/denied|destination/i);
    expect(fetchCalls).toEqual([]);
  });

  it.each([307, 308])('never forwards a body across HTTP %s', async (status) => {
    const fetchCalls = [];
    const request = createRestClient({
      baseUrl: 'https://openhab.test/',
      authorization: 'Basic fixture',
      fetchImpl: async (...args) => {
        fetchCalls.push(args);
        return response(status);
      },
    });

    await expect(request('PUT', ITEM_PATH, {
      body: THERMAL_ITEM,
      transaction: transactionContext(null, 'apply'),
    })).rejects.toThrow(/307|308|redirect/i);
    expect(fetchCalls).toHaveLength(1);
    expect(fetchCalls[0][1].redirect).toBe('error');
  });

  it('rejects a response reported as redirected even when status is successful', async () => {
    const request = createRestClient({
      baseUrl: 'https://openhab.test/',
      authorization: 'Basic fixture',
      fetchImpl: async () => response(204, { redirected: true }),
    });

    await expect(request('GET', ITEM_PATH)).rejects.toThrow(/redirect/i);
  });
});

describe('transaction-bound request bodies', () => {
  it('allows apply only for the exact desired manifest body', () => {
    const transaction = transactionContext(null, 'apply');
    expect(() => authorizeThermalOutputRequest('PUT', ITEM_PATH, {
      body: THERMAL_ITEM,
      transaction,
    })).not.toThrow();

    for (const body of [
      { ...THERMAL_ITEM, type: 'Switch' },
      { ...THERMAL_ITEM, label: 'Arbitrary' },
      { ...THERMAL_ITEM, groupNames: ['Actuators'] },
      { ...THERMAL_ITEM, state: 'shadow' },
    ]) {
      expect(() => authorizeThermalOutputRequest('PUT', ITEM_PATH, {
        body,
        transaction,
      })).toThrow(/body|desired|denied/i);
    }
  });

  it('allows rollback PUT only for the digest-bound original and DELETE only if absent', () => {
    const restore = transactionContext(ORIGINAL, 'rollback');
    expect(() => authorizeThermalOutputRequest('PUT', ITEM_PATH, {
      body: ORIGINAL,
      transaction: restore,
    })).not.toThrow();
    expect(() => authorizeThermalOutputRequest('PUT', ITEM_PATH, {
      body: THERMAL_ITEM,
      transaction: restore,
    })).toThrow(/original|body|denied/i);
    expect(() => authorizeThermalOutputRequest('DELETE', ITEM_PATH, {
      transaction: restore,
    })).toThrow(/original|delete|denied/i);

    const remove = transactionContext(null, 'rollback');
    expect(() => authorizeThermalOutputRequest('DELETE', ITEM_PATH, {
      transaction: remove,
    })).not.toThrow();
    expect(() => authorizeThermalOutputRequest('DELETE', ITEM_PATH, {
      transaction: transactionContext(null, 'apply'),
    })).toThrow(/rollback|denied/i);
  });

  it('uses the canonical Python validator for one complete available v1 state', () => {
    expect(() => authorizeThermalOutputRequest('PUT', STATE_PATH, {
      body: JSON.stringify(validShadow),
      transaction: { operation: 'publish' },
    })).not.toThrow();
  });

  it.each([
    ['command field', (payload) => { payload.commands = ['OPEN']; }],
    ['unknown nested field', (payload) => { payload.current.unknown = 1; }],
    ['incomplete nested object', (payload) => { delete payload.forecast.intervalLowF; }],
    ['unavailable grade', (payload) => { payload.confidence.grade = 'unavailable'; }],
  ])('rejects deep-invalid state: %s', (_label, mutate) => {
    const payload = structuredClone(validShadow);
    mutate(payload);
    expect(() => authorizeThermalOutputRequest('PUT', STATE_PATH, {
      body: JSON.stringify(payload),
      transaction: { operation: 'publish' },
    })).toThrow(/state body|validator|denied/i);
  });

  it('rejects non-JSON and >=16 KiB state bodies', () => {
    for (const body of ['ON', `${JSON.stringify(validShadow)}${' '.repeat(16 * 1024)}`]) {
      expect(() => authorizeThermalOutputRequest('PUT', STATE_PATH, {
        body,
        transaction: { operation: 'publish' },
      })).toThrow(/state body|16 KiB|denied/i);
    }
  });

  it('cannot replace the canonical state authority validator', async () => {
    const transaction = { operation: 'publish' };
    expect(() => authorizeThermalOutputRequest('PUT', STATE_PATH, {
      body: 'ON',
      transaction,
      stateValidator: () => {},
    })).toThrow(/state body|validator|denied/i);

    const fetchCalls = [];
    const request = createRestClient({
      baseUrl: 'https://openhab.test/',
      authorization: 'Basic fixture',
      fetchImpl: (...args) => {
        fetchCalls.push(args);
        return Promise.resolve(response());
      },
      stateValidator: () => {},
    });
    await expect(request('PUT', STATE_PATH, {
      body: 'ON',
      transaction,
    })).rejects.toThrow(/state body|validator|denied/i);
    expect(fetchCalls).toEqual([]);
  });
});

describe('explicit ambiguity settlement', () => {
  it('keeps landed apply unresolved until settle reads back exact desired state', async () => {
    const directory = await receiptDirectory();
    await snapshotTransaction({
      request: mutableTransport(null).request,
      receiptDir: directory,
    });
    const ambiguous = mutableTransport(null, { putMode: 'land-then-throw' });

    await expect(applyTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    })).rejects.toThrow(/unknown/i);
    await expect(verifyTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    })).resolves.toMatchObject({ ok: false, phase: 'applying' });

    const settled = await settleTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    });
    expect(settled.phase).toBe('applied');
    await expect(verifyTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    })).resolves.toMatchObject({ ok: true, expected: 'desired' });
  });

  it('never treats a nonlanded apply as verified or settled', async () => {
    const directory = await receiptDirectory();
    await snapshotTransaction({
      request: mutableTransport(null).request,
      receiptDir: directory,
    });
    const ambiguous = mutableTransport(null, { putMode: 'throw-before-land' });

    await expect(applyTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    })).rejects.toThrow(/unknown/i);
    await expect(verifyTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    })).resolves.toMatchObject({ ok: false, phase: 'applying' });
    await expect(settleTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    })).rejects.toThrow(/not land|unresolved|cannot settle/i);
    expect((await storedReceipt(directory)).phase).toBe('applying');
  });

  it('settles rollback only after exact original readback', async () => {
    const directory = await receiptDirectory();
    const applied = mutableTransport(ORIGINAL);
    await snapshotTransaction({ request: applied.request, receiptDir: directory });
    await applyTransaction({ request: applied.request, receiptDir: directory });
    const ambiguous = mutableTransport(THERMAL_ITEM, { putMode: 'land-then-throw' });

    await expect(rollbackTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    })).rejects.toThrow(/unknown/i);
    await expect(verifyTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    })).resolves.toMatchObject({ ok: false, phase: 'rolling-back' });
    const putsBeforeRecovery = ambiguous.calls.filter(({ method }) => method === 'PUT').length;
    await expect(rollbackTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    })).rejects.toThrow(/settle|phase rolling-back/i);
    expect(ambiguous.calls.filter(({ method }) => method === 'PUT'))
      .toHaveLength(putsBeforeRecovery);
    expect((await settleTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    })).phase).toBe('rolled-back');
  });

  it('does not retry an ambiguous rollback DELETE after an originally absent snapshot', async () => {
    const directory = await receiptDirectory();
    const applied = mutableTransport(null);
    await snapshotTransaction({ request: applied.request, receiptDir: directory });
    await applyTransaction({ request: applied.request, receiptDir: directory });
    const ambiguous = mutableTransport(THERMAL_ITEM, { deleteMode: 'land-then-throw' });

    await expect(rollbackTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    })).rejects.toThrow(/unknown/i);
    expect(ambiguous.calls.filter(({ method }) => method === 'DELETE')).toHaveLength(1);
    await expect(rollbackTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    })).rejects.toThrow(/settle|phase rolling-back/i);
    expect(ambiguous.calls.filter(({ method }) => method === 'DELETE')).toHaveLength(1);
    expect((await settleTransaction({
      request: ambiguous.request,
      receiptDir: directory,
    })).phase).toBe('rolled-back');
  });
});

describe('durable exclusive receipts', () => {
  it('serializes concurrent snapshots before either can capture a pre-state', async () => {
    const directory = await receiptDirectory();
    let releaseRead;
    let announceRead;
    const readStarted = new Promise((resolve) => { announceRead = resolve; });
    const readReleased = new Promise((resolve) => { releaseRead = resolve; });
    let reads = 0;
    const request = async () => {
      reads += 1;
      announceRead();
      await readReleased;
      return null;
    };

    const first = snapshotTransaction({ request, receiptDir: directory });
    await readStarted;
    await expect(snapshotTransaction({ request, receiptDir: directory }))
      .rejects.toThrow(/busy|lock/i);
    releaseRead();
    await first;

    expect(reads).toBe(1);
    await assertNoLockOrTemps(directory);
  });

  it('serializes concurrent apply attempts so at most one PUT occurs', async () => {
    const directory = await receiptDirectory();
    await snapshotTransaction({
      request: mutableTransport(null).request,
      receiptDir: directory,
    });
    let releasePut;
    let announcePut;
    const putStarted = new Promise((resolve) => { announcePut = resolve; });
    const putReleased = new Promise((resolve) => { releasePut = resolve; });
    const transport = mutableTransport(null, {
      onPut: async () => {
        announcePut();
        await putReleased;
      },
    });

    const first = applyTransaction({ request: transport.request, receiptDir: directory });
    await putStarted;
    await expect(applyTransaction({
      request: transport.request,
      receiptDir: directory,
    })).rejects.toThrow(/busy|lock/i);
    releasePut();
    await first;

    expect(transport.calls.filter(({ method }) => method === 'PUT')).toHaveLength(1);
    await assertNoLockOrTemps(directory);
  });

  it('writes 0600 receipt files durably and cleans locks/temps after success and failure', async () => {
    const directory = await receiptDirectory();
    await snapshotTransaction({
      request: mutableTransport(null).request,
      receiptDir: directory,
    });
    for (const name of [RECEIPT_FILENAME, SNAPSHOT_FILENAME]) {
      expect((await stat(join(directory, name))).mode & 0o777).toBe(0o600);
    }
    await assertNoLockOrTemps(directory);

    await expect(applyTransaction({
      request: mutableTransport(null, { putMode: 'land-then-throw' }).request,
      receiptDir: directory,
    })).rejects.toThrow(/unknown/i);
    await assertNoLockOrTemps(directory);
  });

  it('reports an existing lock for explicit inspection and never deletes it blindly', async () => {
    const directory = await receiptDirectory();
    const lockPath = join(directory, LOCK_FILENAME);
    const lock = {
      schema: 'earthship-thermal-model-config-lock/v1',
      pid: 999999,
      hostname: 'another-host',
      createdAt: '2026-08-13T20:00:00.000Z',
      nonce: 'fixture-lock',
    };
    await writeFile(lockPath, `${JSON.stringify(lock)}\n`, { mode: 0o600 });
    const transport = mutableTransport(null);

    await expect(applyTransaction({
      request: transport.request,
      receiptDir: directory,
    })).rejects.toThrow(/busy|lock/i);
    expect(transport.calls).toEqual([]);
    expect(await inspectReceiptLock(directory)).toMatchObject({
      lock,
      digest: expect.stringMatching(/^[a-f0-9]{64}$/),
    });
    await expect(main(['inspect-lock', '--receipt-dir', directory]))
      .resolves.toMatchObject({ lock });
    await expect(access(lockPath)).resolves.toBeUndefined();
  });
});
