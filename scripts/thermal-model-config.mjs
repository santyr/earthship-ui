#!/usr/bin/env node

import { createHash } from 'node:crypto';
import {
  mkdir,
  readFile,
  rename,
  stat,
  writeFile,
} from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export const ITEM_NAME = 'Thermal_Model_JSON';
export const ITEM_PATH = `/rest/items/${encodeURIComponent(ITEM_NAME)}`;
export const STATE_PATH = `${ITEM_PATH}/state`;
export const RECEIPT_FILENAME = 'receipt.json';
export const SNAPSHOT_FILENAME = 'pre-state.json';

export const THERMAL_ITEM = Object.freeze({
  name: ITEM_NAME,
  type: 'String',
  label: 'Thermal model shadow output',
  category: '',
  tags: Object.freeze([]),
  groupNames: Object.freeze([]),
});

const RECEIPT_SCHEMA = 'earthship-thermal-model-config-receipt/v1';
const MAX_STATE_BYTES = 16_384;
const AUTH_FILE = '/home/sat/.config/hex/openhab.env';
const DEFAULT_BASE_URL = 'http://192.168.1.161:8080';
const ITEM_KEYS = Object.freeze([
  'category', 'groupNames', 'label', 'name', 'tags', 'type',
]);
const ALLOWED_REQUESTS = new Set([
  `GET ${ITEM_PATH}`,
  `PUT ${ITEM_PATH}`,
  `DELETE ${ITEM_PATH}`,
  `PUT ${STATE_PATH}`,
]);

function clone(value) {
  return structuredClone(value);
}

function canonicalValue(value) {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(
    Object.keys(value)
      .filter((key) => key !== 'checksum')
      .sort()
      .map((key) => [key, canonicalValue(value[key])]),
  );
}

function digest(value) {
  return createHash('sha256')
    .update(JSON.stringify(canonicalValue(value)))
    .digest('hex');
}

function withChecksum(receipt) {
  const next = clone(receipt);
  delete next.checksum;
  next.checksum = digest(next);
  return next;
}

function equal(left, right) {
  return JSON.stringify(canonicalValue(left)) === JSON.stringify(canonicalValue(right));
}

function stringArray(value, field) {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== 'string')) {
    throw new Error(`Thermal item ${field} must be an array of strings`);
  }
  return [...value];
}

function itemConfiguration(item) {
  if (item === null || item === undefined) return null;
  if (!item || typeof item !== 'object' || Array.isArray(item)) {
    throw new Error('Thermal item configuration must be an object or null');
  }
  if (item.name !== ITEM_NAME) throw new Error('Thermal item name mismatch');
  if (typeof item.type !== 'string' || !item.type) {
    throw new Error('Thermal item type must be a non-empty string');
  }
  for (const field of ['label', 'category']) {
    if (item[field] !== undefined && typeof item[field] !== 'string') {
      throw new Error(`Thermal item ${field} must be a string`);
    }
  }
  return {
    name: ITEM_NAME,
    type: item.type,
    label: item.label ?? '',
    category: item.category ?? '',
    tags: stringArray(item.tags ?? [], 'tags'),
    groupNames: stringArray(item.groupNames ?? [], 'groupNames'),
  };
}

function assertExactItemBody(body) {
  const normalized = itemConfiguration(body);
  const keys = Object.keys(body).sort();
  if (!equal(keys, ITEM_KEYS) || !equal(body, normalized)) {
    throw new Error('Denied OpenHAB item configuration body');
  }
}

function assertShadowStateBody(body) {
  if (typeof body !== 'string' || Buffer.byteLength(body, 'utf8') >= MAX_STATE_BYTES) {
    throw new Error('Denied OpenHAB thermal state body');
  }
  let payload;
  try {
    payload = JSON.parse(body);
  } catch {
    throw new Error('Denied OpenHAB thermal state body');
  }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)
      || payload.version !== 1 || payload.status !== 'shadow') {
    throw new Error('Denied OpenHAB thermal state body');
  }
}

export function assertThermalOutputRequest(method, path, body) {
  const key = `${String(method).toUpperCase()} ${String(path)}`;
  if (!ALLOWED_REQUESTS.has(key)) throw new Error(`Denied OpenHAB request: ${key}`);
  if (arguments.length < 3) return;
  if (key === `PUT ${ITEM_PATH}`) {
    assertExactItemBody(body);
  } else if (key === `PUT ${STATE_PATH}`) {
    assertShadowStateBody(body);
  } else if (body !== undefined) {
    throw new Error(`Denied OpenHAB request body: ${key}`);
  }
}

export function buildApplyPlan(original) {
  itemConfiguration(original);
  return [{ method: 'PUT', path: ITEM_PATH, body: clone(THERMAL_ITEM) }];
}

export function buildRollbackPlan(original) {
  const captured = itemConfiguration(original);
  if (captured) return [{ method: 'PUT', path: ITEM_PATH, body: captured }];
  return [{ method: 'DELETE', path: ITEM_PATH }];
}

export function buildReceipt(original, {
  createdAt = new Date().toISOString(),
} = {}) {
  const snapshot = { item: itemConfiguration(original) };
  const receipt = withChecksum({
    schema: RECEIPT_SCHEMA,
    state: 'open',
    phase: 'snapshot',
    itemName: ITEM_NAME,
    createdAt,
    updatedAt: createdAt,
    snapshotDigest: digest(snapshot),
    writeCount: 0,
    transitions: [],
  });
  return { receipt, snapshot };
}

export function assertReceiptIntegrity(receipt, snapshot) {
  if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)) {
    throw new Error('Thermal config receipt is required');
  }
  if (receipt.schema !== RECEIPT_SCHEMA || receipt.state !== 'open'
      || receipt.itemName !== ITEM_NAME) {
    throw new Error('Thermal config receipt identity mismatch');
  }
  if (!/^[a-f0-9]{64}$/.test(receipt.checksum ?? '')) {
    throw new Error('Thermal config receipt checksum is missing');
  }
  if (digest(receipt) !== receipt.checksum) {
    throw new Error('Thermal config receipt checksum mismatch');
  }
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)
      || Object.keys(snapshot).length !== 1 || !Object.hasOwn(snapshot, 'item')) {
    throw new Error('Thermal config snapshot shape mismatch');
  }
  const normalized = { item: itemConfiguration(snapshot.item) };
  if (!equal(snapshot, normalized)) throw new Error('Thermal config snapshot shape mismatch');
  if (!/^[a-f0-9]{64}$/.test(receipt.snapshotDigest ?? '')
      || digest(snapshot) !== receipt.snapshotDigest) {
    throw new Error('Thermal config snapshot digest mismatch');
  }
}

function instant(now) {
  const value = typeof now === 'function' ? now() : new Date();
  const parsed = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(parsed.getTime())) throw new Error('Invalid receipt timestamp');
  return parsed.toISOString();
}

async function exists(path) {
  try {
    await stat(path);
    return true;
  } catch (error) {
    if (error?.code === 'ENOENT') return false;
    throw error;
  }
}

async function atomicWriteJson(path, value) {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  const temporary = `${path}.${process.pid}.${Date.now()}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  await rename(temporary, path);
}

function transactionPaths(receiptDir) {
  if (typeof receiptDir !== 'string' || !receiptDir) {
    throw new Error('A receipt directory is required');
  }
  return {
    receiptPath: join(receiptDir, RECEIPT_FILENAME),
    snapshotPath: join(receiptDir, SNAPSHOT_FILENAME),
  };
}

async function readTransaction(receiptDir) {
  const { receiptPath, snapshotPath } = transactionPaths(receiptDir);
  let receipt;
  let snapshot;
  try {
    [receipt, snapshot] = await Promise.all([
      readFile(receiptPath, 'utf8').then(JSON.parse),
      readFile(snapshotPath, 'utf8').then(JSON.parse),
    ]);
  } catch (error) {
    throw new Error(`Thermal config receipt or snapshot unavailable: ${error.message}`);
  }
  assertReceiptIntegrity(receipt, snapshot);
  return { receipt, receiptPath, snapshot, snapshotPath };
}

async function writeReceipt(receiptPath, receipt, { now, phase, writeCount } = {}) {
  const at = instant(now);
  const next = withChecksum({
    ...clone(receipt),
    phase: phase ?? receipt.phase,
    updatedAt: at,
    writeCount: writeCount ?? receipt.writeCount,
    transitions: phase === undefined
      ? clone(receipt.transitions)
      : [...receipt.transitions, { at, phase }],
  });
  await atomicWriteJson(receiptPath, next);
  return next;
}

async function readLiveItem(request) {
  return itemConfiguration(await request('GET', ITEM_PATH, { allowMissing: true }));
}

async function executeOperation(request, operation) {
  const options = {};
  if (Object.hasOwn(operation, 'body')) options.body = clone(operation.body);
  if (operation.method === 'DELETE') options.allowMissing = true;
  assertThermalOutputRequest(operation.method, operation.path, options.body);
  return request(operation.method, operation.path, options);
}

export async function snapshotTransaction({ request, receiptDir, now } = {}) {
  if (typeof request !== 'function') throw new Error('OpenHAB request transport is required');
  const { receiptPath, snapshotPath } = transactionPaths(receiptDir);
  if (await exists(receiptPath) || await exists(snapshotPath)) {
    throw new Error('Thermal config receipt directory is not empty');
  }
  const original = await readLiveItem(request);
  const createdAt = instant(now);
  const transaction = buildReceipt(original, { createdAt });
  await atomicWriteJson(snapshotPath, transaction.snapshot);
  await atomicWriteJson(receiptPath, transaction.receipt);
  return transaction;
}

export async function planTransaction({ receiptDir } = {}) {
  const { receipt, snapshot } = await readTransaction(receiptDir);
  return {
    receipt: clone(receipt),
    apply: buildApplyPlan(snapshot.item),
    rollback: buildRollbackPlan(snapshot.item),
  };
}

function assertOpenPhase(receipt, command, allowed) {
  if (!allowed.includes(receipt.phase)) {
    throw new Error(`Cannot ${command} thermal item from receipt phase ${receipt.phase}`);
  }
}

export async function applyTransaction({ request, receiptDir, now } = {}) {
  if (typeof request !== 'function') throw new Error('OpenHAB request transport is required');
  const transaction = await readTransaction(receiptDir);
  let { receipt } = transaction;
  assertOpenPhase(receipt, 'apply', ['snapshot']);

  const live = await readLiveItem(request);
  if (digest({ item: live }) !== receipt.snapshotDigest) {
    throw new Error('Live Thermal_Model_JSON configuration drifted from the captured pre-state');
  }

  receipt = await writeReceipt(transaction.receiptPath, receipt, { now, phase: 'applying' });
  const [operation] = buildApplyPlan(transaction.snapshot.item);
  await executeOperation(request, operation);
  receipt = await writeReceipt(transaction.receiptPath, receipt, {
    now,
    phase: 'applied',
    writeCount: receipt.writeCount + 1,
  });

  const verified = await readLiveItem(request);
  if (!equal(verified, THERMAL_ITEM)) {
    throw new Error('Thermal_Model_JSON desired configuration verification failed');
  }
  return writeReceipt(transaction.receiptPath, receipt, { now, phase: 'desired' });
}

export async function verifyTransaction({ request, receiptDir } = {}) {
  if (typeof request !== 'function') throw new Error('OpenHAB request transport is required');
  const { receipt, snapshot } = await readTransaction(receiptDir);
  const live = await readLiveItem(request);
  if (['snapshot', 'rolled-back'].includes(receipt.phase)) {
    return {
      ok: equal(live, snapshot.item),
      expected: 'original',
      phase: receipt.phase,
    };
  }
  if (['applied', 'desired'].includes(receipt.phase)) {
    return {
      ok: equal(live, THERMAL_ITEM),
      expected: 'desired',
      phase: receipt.phase,
    };
  }
  if (['applying', 'rolling-back'].includes(receipt.phase)) {
    return {
      ok: equal(live, snapshot.item) || equal(live, THERMAL_ITEM),
      expected: 'original-or-desired',
      phase: receipt.phase,
    };
  }
  throw new Error(`Cannot verify thermal item from receipt phase ${receipt.phase}`);
}

export async function rollbackTransaction({ request, receiptDir, now } = {}) {
  if (typeof request !== 'function') throw new Error('OpenHAB request transport is required');
  const transaction = await readTransaction(receiptDir);
  let { receipt } = transaction;
  assertOpenPhase(receipt, 'rollback', [
    'snapshot', 'applying', 'applied', 'desired', 'rolling-back', 'rolled-back',
  ]);

  const live = await readLiveItem(request);
  if (equal(live, transaction.snapshot.item)) {
    if (receipt.phase === 'rolled-back') return receipt;
    return writeReceipt(transaction.receiptPath, receipt, { now, phase: 'rolled-back' });
  }
  if (!equal(live, THERMAL_ITEM)) {
    throw new Error('Live Thermal_Model_JSON configuration drifted from receipt-owned states');
  }

  if (receipt.phase !== 'rolling-back') {
    receipt = await writeReceipt(transaction.receiptPath, receipt, {
      now,
      phase: 'rolling-back',
    });
  }
  const [operation] = buildRollbackPlan(transaction.snapshot.item);
  await executeOperation(request, operation);
  receipt = await writeReceipt(transaction.receiptPath, receipt, {
    now,
    writeCount: receipt.writeCount + 1,
  });
  const restored = await readLiveItem(request);
  if (!equal(restored, transaction.snapshot.item)) {
    throw new Error('Thermal_Model_JSON rollback verification failed');
  }
  return writeReceipt(transaction.receiptPath, receipt, { now, phase: 'rolled-back' });
}

function parseEnv(text) {
  const values = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const index = line.indexOf('=');
    if (index < 1) continue;
    const key = line.slice(0, index).trim().replace(/^export\s+/, '');
    let value = line.slice(index + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"'))
        || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}

async function loadAuth() {
  const values = parseEnv(await readFile(AUTH_FILE, 'utf8'));
  const token = values.OPENHAB_TOKEN;
  if (!token) throw new Error(`OPENHAB_TOKEN is missing from ${AUTH_FILE}`);
  if (process.env.OPENHAB_TOKEN && process.env.OPENHAB_TOKEN !== token) {
    throw new Error('Ambient OPENHAB_TOKEN conflicts with the protected token file');
  }
  return {
    baseUrl: (values.OPENHAB_URL || DEFAULT_BASE_URL).replace(/\/$/, ''),
    authorization: `Basic ${Buffer.from(`${token}:`).toString('base64')}`,
  };
}

export function createRestClient({ baseUrl, authorization, fetchImpl = fetch }) {
  return async function request(method, path, options = {}) {
    const hasBody = Object.hasOwn(options, 'body');
    assertThermalOutputRequest(method, path, hasBody ? options.body : undefined);
    const headers = { Accept: 'application/json', Authorization: authorization };
    let body;
    if (hasBody) {
      if (path === STATE_PATH) {
        headers['Content-Type'] = 'text/plain';
        body = options.body;
      } else {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify(options.body);
      }
    }
    const response = await fetchImpl(`${baseUrl}${path}`, {
      method,
      headers,
      body,
      signal: AbortSignal.timeout(15_000),
    });
    if (options.allowMissing && response.status === 404) return null;
    if (!response.ok) {
      throw new Error(`OpenHAB ${method} ${path} failed with HTTP ${response.status}`);
    }
    if (response.status === 204) return null;
    const text = await response.text();
    return text ? JSON.parse(text) : null;
  };
}

function usage() {
  return 'Usage: thermal-model-config.mjs snapshot|plan|apply|verify|rollback --receipt-dir PATH';
}

function parseCli(argv) {
  if (argv.includes('--help') || argv.includes('-h')) return { help: true };
  const command = argv[0];
  if (!['snapshot', 'plan', 'apply', 'verify', 'rollback'].includes(command)) {
    throw new Error(usage());
  }
  const receiptIndex = argv.indexOf('--receipt-dir');
  if (receiptIndex < 0 || !argv[receiptIndex + 1] || argv[receiptIndex + 1].startsWith('--')) {
    throw new Error('--receipt-dir PATH is required');
  }
  if (argv.length !== 3 || receiptIndex !== 1) throw new Error(usage());
  return { command, receiptDir: resolve(argv[receiptIndex + 1]) };
}

export async function main(argv = process.argv.slice(2), dependencies = {}) {
  const args = parseCli(argv);
  if (args.help) return { help: usage() };
  if (args.command === 'plan') return planTransaction(args);
  const request = dependencies.request
    ?? createRestClient({ ...(await loadAuth()), fetchImpl: dependencies.fetchImpl });
  if (args.command === 'snapshot') return snapshotTransaction({ ...args, request });
  if (args.command === 'apply') return applyTransaction({ ...args, request });
  if (args.command === 'verify') return verifyTransaction({ ...args, request });
  return rollbackTransaction({ ...args, request });
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().then((result) => {
    if (result.help) process.stdout.write(`${result.help}\n`);
    else process.stdout.write(`${JSON.stringify(result)}\n`);
    if (Object.hasOwn(result, 'ok') && !result.ok) process.exitCode = 1;
  }).catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
