#!/usr/bin/env node

import {
  mkdir,
  readFile,
  rename,
  stat,
  writeFile,
} from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export const SUPPORTED_OPENHAB_VERSION = '5.2.0';
export const AQI_THING_UID = 'openmeteo:air-quality:local:aq';
export const CURRENT_AQI_CHANNEL = `${AQI_THING_UID}:current#us-aqi`;
export const CURRENT_AQI_ITEM = Object.freeze({
  type: 'Number',
  name: 'Current_US_AQI',
  label: 'Current US AQI',
  category: 'airquality',
  tags: ['Measurement'],
  groupNames: [],
});

const FORECAST_ITEM_NAME = 'Forecast_AQI';
const DEFAULT_BASE_URL = 'http://192.168.1.161:8080';
const AUTH_FILE = '/home/sat/.config/hex/openhab.env';
const ACTIVE_RECEIPT = '/tmp/earthship-ui-openhab-active/aqi.json';
const THING_PATH = `/rest/things/${encodeURIComponent(AQI_THING_UID)}`;
const THING_CONFIG_PATH = `${THING_PATH}/config`;
const ITEM_PATH = `/rest/items/${CURRENT_AQI_ITEM.name}`;
const FORECAST_ITEM_PATH = `/rest/items/${FORECAST_ITEM_NAME}`;
const LINK_PATH = `/rest/links/${CURRENT_AQI_ITEM.name}/${encodeURIComponent(CURRENT_AQI_CHANNEL)}`;
const LINKS_PATH = '/rest/links';

const ALLOWED_REQUESTS = new Set([
  'GET /rest/',
  `GET ${THING_PATH}`,
  `PUT ${THING_CONFIG_PATH}`,
  `GET ${ITEM_PATH}`,
  `PUT ${ITEM_PATH}`,
  `DELETE ${ITEM_PATH}`,
  `GET ${FORECAST_ITEM_PATH}`,
  `GET ${LINK_PATH}`,
  `PUT ${LINK_PATH}`,
  `DELETE ${LINK_PATH}`,
  `GET ${LINKS_PATH}`,
]);

export function assertAllowedRequest(method, path) {
  const key = `${String(method).toUpperCase()} ${path}`;
  if (!ALLOWED_REQUESTS.has(key)) {
    throw new Error(`Denied OpenHAB request: ${key}`);
  }
}

export function buildDesiredThingConfig(original = {}) {
  return {
    ...structuredClone(original),
    current: true,
    airQualityIndicatorsAsNumber: true,
    airQualityIndicatorsAsString: true,
    hourlyTimeSeries: true,
  };
}

function itemDto(item) {
  if (!item) return null;
  return {
    type: item.type,
    name: item.name,
    label: item.label ?? '',
    category: item.category ?? '',
    tags: Array.isArray(item.tags) ? item.tags : [],
    groupNames: Array.isArray(item.groupNames) ? item.groupNames : [],
  };
}

function linkDto(link) {
  if (!link) return null;
  return {
    itemName: link.itemName,
    channelUID: link.channelUID,
    configuration: link.configuration ?? {},
  };
}

export function buildReceipt({
  runtimeInfo,
  thing,
  currentItem,
  currentLink,
  forecastItem,
  forecastLink,
  createdAt = new Date().toISOString(),
  backupPath = null,
} = {}) {
  return {
    schema: 'earthship-ui-openhab-aqi-receipt/v1',
    state: 'open',
    createdAt,
    updatedAt: createdAt,
    backupPath,
    runtimeInfo: structuredClone(runtimeInfo),
    resource: {
      thingUID: AQI_THING_UID,
      itemName: CURRENT_AQI_ITEM.name,
      channelUID: CURRENT_AQI_CHANNEL,
    },
    original: {
      thingConfiguration: structuredClone(thing.configuration),
      currentItem: currentItem ? { ...itemDto(currentItem), state: currentItem.state } : null,
      currentLink: linkDto(currentLink),
      forecastItem: forecastItem ? { ...itemDto(forecastItem), state: forecastItem.state } : null,
      forecastLink: linkDto(forecastLink),
    },
    operations: [],
  };
}

export function verifyDesiredState({ runtimeInfo, thing, currentItem, currentLink } = {}) {
  const reasons = [];
  if (runtimeInfo?.version !== SUPPORTED_OPENHAB_VERSION) {
    reasons.push(`OpenHAB runtime must be ${SUPPORTED_OPENHAB_VERSION}`);
  }
  if (thing?.UID !== AQI_THING_UID) reasons.push('AQI Thing UID mismatch');
  if (thing?.statusInfo?.status !== 'ONLINE') reasons.push('AQI Thing is not ONLINE');
  for (const key of [
    'current',
    'airQualityIndicatorsAsNumber',
    'airQualityIndicatorsAsString',
    'hourlyTimeSeries',
  ]) {
    if (thing?.configuration?.[key] !== true) reasons.push(`AQI Thing ${key} is not enabled`);
  }
  if (!thing?.channels?.some((channel) => channel.uid === CURRENT_AQI_CHANNEL)) {
    reasons.push('Current numeric US AQI channel is unavailable');
  }
  if (currentItem?.name !== CURRENT_AQI_ITEM.name || currentItem?.type !== 'Number') {
    reasons.push('Current AQI Number item is unavailable');
  }
  if (
    currentLink?.itemName !== CURRENT_AQI_ITEM.name
    || currentLink?.channelUID !== CURRENT_AQI_CHANNEL
  ) {
    reasons.push('Current AQI link is unavailable');
  }
  const numericState = Number(currentItem?.state);
  if (!Number.isFinite(numericState) || numericState < 0) {
    reasons.push('Current AQI provider state is not numeric');
  }
  return { ok: reasons.length === 0, reasons, numericState };
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
    if (
      (value.startsWith('"') && value.endsWith('"'))
      || (value.startsWith("'") && value.endsWith("'"))
    ) value = value.slice(1, -1);
    values[key] = value;
  }
  return values;
}

async function loadAuth() {
  const fileValues = parseEnv(await readFile(AUTH_FILE, 'utf8'));
  const token = fileValues.OPENHAB_TOKEN;
  if (!token) throw new Error(`OPENHAB_TOKEN is missing from ${AUTH_FILE}`);
  if (process.env.OPENHAB_TOKEN && process.env.OPENHAB_TOKEN !== token) {
    throw new Error('Ambient OPENHAB_TOKEN conflicts with the protected token file');
  }
  return {
    baseUrl: (fileValues.OPENHAB_URL || DEFAULT_BASE_URL).replace(/\/$/, ''),
    authorization: `Basic ${Buffer.from(`${token}:`).toString('base64')}`,
  };
}

function createRestClient({ baseUrl, authorization }) {
  return async function request(method, path, { body, allowMissing = false } = {}) {
    assertAllowedRequest(method, path);
    const headers = { Accept: 'application/json', Authorization: authorization };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetch(`${baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(15_000),
    });
    if (allowMissing && response.status === 404) return null;
    if (!response.ok) {
      throw new Error(`OpenHAB ${method} ${path} failed with HTTP ${response.status}`);
    }
    if (response.status === 204) return null;
    const text = await response.text();
    return text ? JSON.parse(text) : null;
  };
}

async function liveState(request) {
  const [root, thing, currentItem, forecastItem, links] = await Promise.all([
    request('GET', '/rest/'),
    request('GET', THING_PATH),
    request('GET', ITEM_PATH, { allowMissing: true }),
    request('GET', FORECAST_ITEM_PATH, { allowMissing: true }),
    request('GET', LINKS_PATH),
  ]);
  const currentLink = links.find((link) => (
    link.itemName === CURRENT_AQI_ITEM.name && link.channelUID === CURRENT_AQI_CHANNEL
  )) ?? null;
  const forecastLink = links.find((link) => link.itemName === FORECAST_ITEM_NAME) ?? null;
  return {
    runtimeInfo: root.runtimeInfo,
    thing,
    currentItem,
    currentLink,
    forecastItem,
    forecastLink,
  };
}

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

async function waitFor(request, predicate, description, timeoutMs = 90_000) {
  const deadline = Date.now() + timeoutMs;
  let latest;
  while (Date.now() < deadline) {
    latest = await liveState(request);
    if (predicate(latest)) return latest;
    await sleep(2_000);
  }
  throw new Error(`Timed out waiting for ${description}`);
}

async function pathExists(path) {
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
  const temp = `${path}.${process.pid}.tmp`;
  await writeFile(temp, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  await rename(temp, path);
}

async function readReceipt() {
  const receipt = JSON.parse(await readFile(ACTIVE_RECEIPT, 'utf8'));
  if (receipt.schema !== 'earthship-ui-openhab-aqi-receipt/v1') {
    throw new Error('Unsupported AQI receipt schema');
  }
  if (receipt.state !== 'open') throw new Error(`AQI receipt is ${receipt.state}`);
  return receipt;
}

async function updateReceipt(receipt, operation) {
  const next = structuredClone(receipt);
  next.updatedAt = new Date().toISOString();
  next.operations.push({ at: next.updatedAt, operation });
  await atomicWriteJson(ACTIVE_RECEIPT, next);
  if (next.backupPath) await atomicWriteJson(next.backupPath, next);
  return next;
}

async function snapshot(request) {
  if (await pathExists(ACTIVE_RECEIPT)) {
    const existing = JSON.parse(await readFile(ACTIVE_RECEIPT, 'utf8'));
    throw new Error(`AQI receipt already exists in state ${existing.state}`);
  }
  const state = await liveState(request);
  if (state.runtimeInfo?.version !== SUPPORTED_OPENHAB_VERSION) {
    throw new Error(
      `Unsupported OpenHAB ${state.runtimeInfo?.version}; expected ${SUPPORTED_OPENHAB_VERSION}`,
    );
  }
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const backupPath = `/tmp/earthship-ui-openhab-aqi-${stamp}/receipt.json`;
  const receipt = buildReceipt({ ...state, backupPath });
  await atomicWriteJson(backupPath, receipt);
  await atomicWriteJson(ACTIVE_RECEIPT, receipt);
  return receipt;
}

async function applyDesired(request, operation = 'apply') {
  let receipt = await readReceipt();
  const before = await liveState(request);
  await request('PUT', THING_CONFIG_PATH, {
    body: buildDesiredThingConfig(before.thing.configuration),
  });
  receipt = await updateReceipt(receipt, `${operation}:thing-config`);

  await waitFor(
    request,
    (state) => state.thing.statusInfo?.status === 'ONLINE'
      && state.thing.channels?.some((channel) => channel.uid === CURRENT_AQI_CHANNEL),
    'ONLINE AQI Thing and current numeric channel',
  );

  await request('PUT', ITEM_PATH, { body: CURRENT_AQI_ITEM });
  receipt = await updateReceipt(receipt, `${operation}:current-item`);
  await request('PUT', LINK_PATH, {
    body: {
      itemName: CURRENT_AQI_ITEM.name,
      channelUID: CURRENT_AQI_CHANNEL,
      configuration: {},
    },
  });
  receipt = await updateReceipt(receipt, `${operation}:current-link`);

  const desired = await waitFor(
    request,
    (state) => verifyDesiredState(state).ok,
    'numeric provider-produced Current_US_AQI state',
  );
  await updateReceipt(receipt, `${operation}:verified`);
  return verifyDesiredState(desired);
}

async function rollback(request) {
  let receipt = await readReceipt();
  const original = receipt.original;

  if (original.currentLink) {
    await request('PUT', LINK_PATH, { body: original.currentLink });
  } else {
    await request('DELETE', LINK_PATH, { allowMissing: true });
  }
  receipt = await updateReceipt(receipt, 'rollback:current-link');

  if (original.currentItem) {
    await request('PUT', ITEM_PATH, { body: itemDto(original.currentItem) });
  } else {
    await request('DELETE', ITEM_PATH, { allowMissing: true });
  }
  receipt = await updateReceipt(receipt, 'rollback:current-item');

  await request('PUT', THING_CONFIG_PATH, { body: original.thingConfiguration });
  receipt = await updateReceipt(receipt, 'rollback:thing-config');
  const restored = await waitFor(
    request,
    (state) => state.thing.statusInfo?.status === 'ONLINE'
      && JSON.stringify(state.thing.configuration) === JSON.stringify(original.thingConfiguration)
      && Boolean(state.currentItem) === Boolean(original.currentItem)
      && Boolean(state.currentLink) === Boolean(original.currentLink),
    'exact original AQI configuration',
  );
  await updateReceipt(receipt, 'rollback:verified');
  return restored;
}

async function verify(request) {
  await readReceipt();
  return verifyDesiredState(await liveState(request));
}

async function closeDesired(request) {
  const receipt = await readReceipt();
  const result = verifyDesiredState(await liveState(request));
  if (!result.ok) throw new Error(`Cannot close AQI receipt: ${result.reasons.join('; ')}`);
  const closed = structuredClone(receipt);
  closed.state = 'closed-desired';
  closed.updatedAt = new Date().toISOString();
  closed.operations.push({ at: closed.updatedAt, operation: 'close:desired' });
  await atomicWriteJson(ACTIVE_RECEIPT, closed);
  if (closed.backupPath) await atomicWriteJson(closed.backupPath, closed);
  return result;
}

function printResult(label, result) {
  const safe = {
    label,
    ok: result?.ok ?? true,
    numericState: result?.numericState,
    reasons: result?.reasons ?? [],
    receipt: ACTIVE_RECEIPT,
  };
  process.stdout.write(`${JSON.stringify(safe)}\n`);
}

async function main() {
  const command = process.argv[2];
  if (!['snapshot', 'apply', 'verify', 'rollback', 'reapply', 'close'].includes(command)) {
    throw new Error('Usage: openhab-aqi.mjs snapshot|apply|verify|rollback|reapply|close');
  }
  const request = createRestClient(await loadAuth());
  if (command === 'snapshot') {
    await snapshot(request);
    printResult('snapshot', { ok: true });
  } else if (command === 'apply') {
    printResult('apply', await applyDesired(request));
  } else if (command === 'verify') {
    const result = await verify(request);
    printResult('verify', result);
    if (!result.ok) process.exitCode = 1;
  } else if (command === 'rollback') {
    await rollback(request);
    printResult('rollback', { ok: true });
  } else if (command === 'reapply') {
    printResult('reapply', await applyDesired(request, 'reapply'));
  } else {
    printResult('close', await closeDesired(request));
  }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.stderr.write(`Recovery: node scripts/openhab-aqi.mjs rollback\n`);
    process.exitCode = 1;
  });
}
