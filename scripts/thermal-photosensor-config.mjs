#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import {
  chmod, mkdir, mkdtemp, open, readFile, rename, rm, stat, unlink,
} from "node:fs/promises";
import { hostname, tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

export const THING_UID = "zigbee:device:a7351eb531:001788011024c307";
export const THING_PATH = `/rest/things/${encodeURIComponent(THING_UID)}`;
export const JDBC_PATH = "/rest/persistence/jdbc";
export const RECEIPT_FILENAME = "receipt.json";
export const SNAPSHOT_FILENAME = "pre-state.json";
export const LOCK_FILENAME = "transaction.lock";

const RECEIPT_SCHEMA = "earthship-thermal-photosensor-config-receipt/v1";
const LOCK_SCHEMA = "earthship-thermal-photosensor-config-lock/v1";
const AUTH_FILE = "/home/sat/.config/hex/openhab.env";
const DEFAULT_BASE_URL = "http://192.168.1.161:8080";

const item = (name, type, label) => Object.freeze({
  name,
  type,
  label,
  category: "",
  tags: Object.freeze([]),
  groupNames: Object.freeze([]),
});

export const PHOTOSENSOR_ITEMS = Object.freeze([
  item(
    "LivingOffice_Shade_Illuminance",
    "Number",
    "Living/office shade illuminance",
  ),
  item(
    "LivingOffice_Shade_Occupancy",
    "Switch",
    "Living/office shade occupancy",
  ),
  item(
    "LivingOffice_Shade_Temperature",
    "Number:Temperature",
    "Living/office shade sensor temperature",
  ),
]);

const channel = (suffix) => `${THING_UID}:${suffix}`;
export const PHOTOSENSOR_LINKS = Object.freeze([
  Object.freeze({
    itemName: PHOTOSENSOR_ITEMS[0].name,
    channelUID: channel("001788011024C307_2_illuminance"),
    configuration: Object.freeze({}),
  }),
  Object.freeze({
    itemName: PHOTOSENSOR_ITEMS[1].name,
    channelUID: channel("001788011024C307_2_occupancy"),
    configuration: Object.freeze({}),
  }),
  Object.freeze({
    itemName: PHOTOSENSOR_ITEMS[2].name,
    channelUID: channel("001788011024C307_2_temperature"),
    configuration: Object.freeze({}),
  }),
]);

export const JDBC_HISTORY_PATHS = Object.freeze(PHOTOSENSOR_ITEMS.map(({ name }) => (
  `/rest/persistence/items/${encodeURIComponent(name)}?serviceId=jdbc`
)));

const ITEM_KEYS = Object.freeze([
  "category", "groupNames", "label", "name", "tags", "type",
]);
const LINK_KEYS = Object.freeze(["channelUID", "configuration", "itemName"]);

function clone(value) {
  return structuredClone(value);
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.keys(value)
      .sort()
      .map((key) => [key, canonical(value[key])]),
  );
}

function equal(left, right) {
  return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
}

export function canonicalDigest(value) {
  const root = clone(value);
  if (root && typeof root === "object" && !Array.isArray(root)) {
    delete root.checksum;
  }
  return createHash("sha256")
    .update(JSON.stringify(canonical(root)))
    .digest("hex");
}

const digest = canonicalDigest;

function withChecksum(receipt) {
  const next = clone(receipt);
  delete next.checksum;
  next.checksum = digest(next);
  return next;
}

function itemPath(name) {
  return `/rest/items/${encodeURIComponent(name)}`;
}

function linkPath(link) {
  return `/rest/links/${encodeURIComponent(link.itemName)}/${encodeURIComponent(link.channelUID)}`;
}

function stringArray(value, field) {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string")) {
    throw new Error(`Photosensor Item ${field} must be an array of strings`);
  }
  return [...value];
}

export function normalizeItem(value, expectedName) {
  if (value === null || value === undefined) return null;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Photosensor Item must be an object or null");
  }
  if (value.name !== expectedName) throw new Error("Photosensor Item name mismatch");
  if (typeof value.type !== "string" || !value.type) {
    throw new Error("Photosensor Item type must be a non-empty string");
  }
  for (const field of ["label", "category"]) {
    if (value[field] !== undefined && typeof value[field] !== "string") {
      throw new Error(`Photosensor Item ${field} must be a string`);
    }
  }
  return {
    name: expectedName,
    type: value.type,
    label: value.label ?? "",
    category: value.category ?? "",
    tags: stringArray(value.tags ?? [], "tags"),
    groupNames: stringArray(value.groupNames ?? [], "groupNames"),
  };
}

function jsonValue(value, path = "link configuration") {
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error(`${path} must be finite JSON`);
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((entry, index) => jsonValue(entry, `${path}[${index}]`));
  }
  if (!value || typeof value !== "object"
      || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new Error(`${path} must be JSON`);
  }
  return Object.fromEntries(Object.keys(value).sort().map((key) => (
    [key, jsonValue(value[key], `${path}.${key}`)]
  )));
}

export function normalizeLink(value, expected) {
  if (value === null || value === undefined) return null;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Photosensor link must be an object or null");
  }
  if (value.itemName !== expected.itemName || value.channelUID !== expected.channelUID) {
    throw new Error("Photosensor link identity mismatch");
  }
  if (!value.configuration || typeof value.configuration !== "object"
      || Array.isArray(value.configuration)) {
    throw new Error("Photosensor link configuration must be an object");
  }
  return {
    itemName: expected.itemName,
    channelUID: expected.channelUID,
    configuration: jsonValue(value.configuration),
  };
}

function normalizedOriginal(original) {
  if (!original || typeof original !== "object" || Array.isArray(original)
      || !original.items || !original.links) {
    throw new Error("Photosensor pre-state must contain Items and links");
  }
  return {
    items: Object.fromEntries(PHOTOSENSOR_ITEMS.map(({ name }) => [
      name, normalizeItem(original.items[name], name),
    ])),
    links: Object.fromEntries(PHOTOSENSOR_LINKS.map((link) => [
      link.itemName, normalizeLink(original.links[link.itemName], link),
    ])),
  };
}

function normalizeThingEvidence(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)
      || value.uid !== THING_UID || value.status !== "ONLINE"
      || !Array.isArray(value.channels) || value.channels.length !== 3) {
    throw new Error("Philips photosensor Thing evidence mismatch");
  }
  const channels = PHOTOSENSOR_LINKS.map((expected, index) => {
    const actual = value.channels.find(({ uid }) => uid === expected.channelUID);
    if (!actual || actual.kind !== "STATE" || typeof actual.itemType !== "string") {
      throw new Error("Philips photosensor channel evidence mismatch");
    }
    const desiredType = PHOTOSENSOR_ITEMS[index].type;
    const compatible = desiredType === "Switch"
      ? actual.itemType === "Switch"
      : actual.itemType.startsWith("Number");
    if (!compatible) throw new Error("Philips photosensor channel type mismatch");
    return {
      uid: expected.channelUID,
      kind: "STATE",
      itemType: actual.itemType,
    };
  });
  return { uid: THING_UID, status: "ONLINE", channels };
}

function sanitizeThing(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Philips photosensor Thing response must be an object");
  }
  return normalizeThingEvidence({
    uid: value.UID ?? value.uid,
    status: value.statusInfo?.status ?? value.status,
    channels: (value.channels ?? []).map((entry) => ({
      uid: entry.uid ?? entry.UID,
      kind: entry.kind,
      itemType: entry.itemType,
    })),
  });
}

function normalizeJdbcEvidence(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)
      || value.serviceId !== "jdbc" || value.editable !== true
      || !Array.isArray(value.wildcardStrategies)) {
    throw new Error("JDBC wildcard persistence evidence mismatch");
  }
  const strategies = [...new Set(value.wildcardStrategies)].sort();
  if (!strategies.includes("everyChange")
      || !strategies.includes("restoreOnStartup")) {
    throw new Error("JDBC wildcard persistence strategies are incomplete");
  }
  return {
    serviceId: "jdbc",
    editable: true,
    wildcardStrategies: strategies,
  };
}

function sanitizeJdbc(value) {
  if (value?.wildcardStrategies) return normalizeJdbcEvidence(value);
  if (!value || typeof value !== "object" || Array.isArray(value)
      || !Array.isArray(value.configs)) {
    throw new Error("JDBC persistence response must be an object");
  }
  const wildcard = value.configs.find((entry) => (
    Array.isArray(entry.items) && entry.items.includes("*")
  ));
  return normalizeJdbcEvidence({
    serviceId: value.serviceId,
    editable: value.editable,
    wildcardStrategies: wildcard?.strategies,
  });
}

function normalizeSnapshot(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)
      || !equal(Object.keys(value).sort(), ["items", "jdbc", "links", "thing"])) {
    throw new Error("Photosensor snapshot shape mismatch");
  }
  const resources = normalizedOriginal(value);
  return {
    ...resources,
    thing: normalizeThingEvidence(value.thing),
    jdbc: normalizeJdbcEvidence(value.jdbc),
  };
}

export function buildApplyPlan(original) {
  const captured = normalizedOriginal(original);
  return [
    ...PHOTOSENSOR_ITEMS.filter((desired) => (
      !equal(captured.items[desired.name], desired)
    )).map((desired) => ({
      method: "PUT", path: itemPath(desired.name), body: clone(desired),
    })),
    ...PHOTOSENSOR_LINKS.filter((desired) => (
      !equal(captured.links[desired.itemName], desired)
    )).map((desired) => ({
      method: "PUT", path: linkPath(desired), body: clone(desired),
    })),
  ];
}

export function buildRollbackPlan(original) {
  const captured = normalizedOriginal(original);
  const changedLinks = PHOTOSENSOR_LINKS.filter((desired) => (
    !equal(captured.links[desired.itemName], desired)
  ));
  const changedItems = PHOTOSENSOR_ITEMS.filter((desired) => (
    !equal(captured.items[desired.name], desired)
  ));
  return [
    ...changedLinks.toReversed().map((desired) => {
      const prior = captured.links[desired.itemName];
      return prior
        ? { method: "PUT", path: linkPath(desired), body: prior }
        : { method: "DELETE", path: linkPath(desired) };
    }),
    ...changedItems.toReversed().map((desired) => {
      const prior = captured.items[desired.name];
      return prior
        ? { method: "PUT", path: itemPath(desired.name), body: prior }
        : { method: "DELETE", path: itemPath(desired.name) };
    }),
  ];
}

function instant(now) {
  const value = typeof now === "function" ? now() : new Date();
  const parsed = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(parsed.getTime())) throw new Error("Invalid receipt timestamp");
  return parsed.toISOString();
}

export function buildReceipt(original, {
  createdAt = new Date().toISOString(),
} = {}) {
  const snapshot = normalizeSnapshot(original);
  const receipt = withChecksum({
    schema: RECEIPT_SCHEMA,
    state: "open",
    phase: "snapshot",
    createdAt,
    updatedAt: createdAt,
    snapshotDigest: digest(snapshot),
    nextOperation: 0,
    pendingOperation: null,
    writeCount: 0,
    transitions: [],
    closures: [],
  });
  return { receipt, snapshot };
}

export function assertReceiptIntegrity(receipt, snapshot) {
  if (!receipt || typeof receipt !== "object" || Array.isArray(receipt)
      || receipt.schema !== RECEIPT_SCHEMA
      || !["open", "closed"].includes(receipt.state)
      || !/^[a-f0-9]{64}$/.test(receipt.checksum ?? "")
      || digest(receipt) !== receipt.checksum) {
    throw new Error("Photosensor config receipt identity or checksum mismatch");
  }
  const normalized = normalizeSnapshot(snapshot);
  if (!equal(snapshot, normalized)
      || receipt.snapshotDigest !== digest(normalized)) {
    throw new Error("Photosensor config snapshot digest mismatch");
  }
  const openKeys = [
    "checksum", "closures", "createdAt", "nextOperation", "pendingOperation",
    "phase", "schema", "snapshotDigest", "state", "transitions", "updatedAt",
    "writeCount",
  ];
  const expectedKeys = receipt.state === "closed"
    ? [...openKeys, "closedAt", "closedPhase"].sort() : openKeys.sort();
  if (!equal(Object.keys(receipt).sort(), expectedKeys)) {
    throw new Error("Photosensor config receipt fields mismatch");
  }
  const phases = [
    "snapshot", "applying", "desired", "rolling-back", "rolled-back",
  ];
  if (!phases.includes(receipt.phase)
      || !Number.isInteger(receipt.nextOperation) || receipt.nextOperation < 0
      || !(receipt.pendingOperation === null
        || (Number.isInteger(receipt.pendingOperation)
          && receipt.pendingOperation >= 0))
      || !Number.isInteger(receipt.writeCount) || receipt.writeCount < 0
      || !Array.isArray(receipt.transitions) || !Array.isArray(receipt.closures)) {
    throw new Error("Photosensor config receipt state mismatch");
  }
  const timestamp = (value) => (
    typeof value === "string"
      && Number.isFinite(Date.parse(value))
      && new Date(value).toISOString() === value
  );
  if (!timestamp(receipt.createdAt) || !timestamp(receipt.updatedAt)
      || receipt.transitions.some((entry) => (
        !entry || typeof entry !== "object" || Array.isArray(entry)
        || !equal(Object.keys(entry).sort(), ["at", "phase"])
        || !timestamp(entry.at) || typeof entry.phase !== "string"
      ))
      || receipt.closures.some((entry) => (
        !entry || typeof entry !== "object" || Array.isArray(entry)
        || !equal(Object.keys(entry).sort(), ["at", "phase"])
        || !timestamp(entry.at) || !["desired", "rolled-back"].includes(entry.phase)
      ))) {
    throw new Error("Photosensor config receipt chronology mismatch");
  }
  const applyCount = buildApplyPlan(normalized).length;
  const rollbackCount = buildRollbackPlan(normalized).length;
  const expectedWriteCount = receipt.phase === "snapshot" ? 0
    : receipt.phase === "applying" ? receipt.nextOperation
      : receipt.phase === "desired" ? applyCount
        : receipt.phase === "rolling-back" ? applyCount + receipt.nextOperation
          : applyCount + rollbackCount;
  const operationCount = ["rolling-back", "rolled-back"].includes(receipt.phase)
    ? rollbackCount : applyCount;
  if (receipt.nextOperation > operationCount
      || receipt.writeCount !== expectedWriteCount
      || (receipt.pendingOperation !== null
        && receipt.pendingOperation !== receipt.nextOperation)
      || (receipt.pendingOperation !== null
        && receipt.pendingOperation >= operationCount)
      || (["snapshot", "desired", "rolled-back"].includes(receipt.phase)
        && receipt.pendingOperation !== null)
      || (receipt.phase === "snapshot" && receipt.nextOperation !== 0)
      || (receipt.phase === "desired" && receipt.nextOperation !== applyCount)
      || (receipt.phase === "rolled-back" && receipt.nextOperation !== rollbackCount)) {
    throw new Error("Photosensor config receipt operation accounting mismatch");
  }
  if (receipt.state === "closed") {
    const last = receipt.closures.at(-1);
    if (!last || receipt.closedAt !== last.at || receipt.closedPhase !== last.phase
        || receipt.phase !== receipt.closedPhase
        || !["desired", "rolled-back"].includes(receipt.phase)) {
      throw new Error("Photosensor config closed receipt mismatch");
    }
  } else if (Object.hasOwn(receipt, "closedAt")
      || Object.hasOwn(receipt, "closedPhase")) {
    throw new Error("Photosensor config open receipt has closed fields");
  }
}

const GET_PATHS = new Set([
  THING_PATH,
  JDBC_PATH,
  ...PHOTOSENSOR_ITEMS.map(({ name }) => itemPath(name)),
  ...PHOTOSENSOR_LINKS.map(linkPath),
  ...JDBC_HISTORY_PATHS,
]);
const MUTATION_PATHS = new Set([
  ...PHOTOSENSOR_ITEMS.map(({ name }) => itemPath(name)),
  ...PHOTOSENSOR_LINKS.map(linkPath),
]);

function assertExactBody(path, body) {
  const desiredItem = PHOTOSENSOR_ITEMS.find(({ name }) => itemPath(name) === path);
  if (desiredItem) {
    const normalized = normalizeItem(body, desiredItem.name);
    if (!equal(Object.keys(body).sort(), ITEM_KEYS) || !equal(body, normalized)) {
      throw new Error("Denied OpenHAB photosensor Item body");
    }
    return;
  }
  const desiredLink = PHOTOSENSOR_LINKS.find((link) => linkPath(link) === path);
  const normalized = normalizeLink(body, desiredLink);
  if (!equal(Object.keys(body).sort(), LINK_KEYS) || !equal(body, normalized)) {
    throw new Error("Denied OpenHAB photosensor link body");
  }
}

export function authorizePhotosensorRequest(method, path, {
  body,
  transaction,
} = {}) {
  const normalizedMethod = String(method).toUpperCase();
  if (normalizedMethod === "GET" && GET_PATHS.has(String(path))) {
    if (body !== undefined) throw new Error("Denied OpenHAB photosensor GET body");
    return;
  }
  if (!["PUT", "DELETE"].includes(normalizedMethod)
      || !MUTATION_PATHS.has(String(path))) {
    throw new Error(`Denied OpenHAB photosensor request: ${normalizedMethod} ${path}`);
  }
  if (!transaction || !["apply", "rollback"].includes(transaction.operation)) {
    throw new Error("Denied OpenHAB photosensor mutation without receipt context");
  }
  assertReceiptIntegrity(transaction.receipt, transaction.snapshot);
  if (transaction.receipt.state !== "open") {
    throw new Error("Denied OpenHAB photosensor mutation from closed receipt");
  }
  const plan = transaction.operation === "apply"
    ? buildApplyPlan(transaction.snapshot)
    : buildRollbackPlan(transaction.snapshot);
  const authorized = plan.some((operation) => (
    operation.method === normalizedMethod
      && operation.path === String(path)
      && (normalizedMethod === "DELETE" || equal(operation.body, body))
  ));
  if (!authorized) throw new Error("Denied OpenHAB photosensor operation outside receipt plan");
  if (normalizedMethod === "PUT") assertExactBody(String(path), body);
  if (normalizedMethod === "DELETE" && body !== undefined) {
    throw new Error("Denied OpenHAB photosensor DELETE body");
  }
}

async function exists(path) {
  try {
    await stat(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function fsyncDirectory(path) {
  const handle = await open(path, "r");
  try {
    await handle.sync();
  } finally {
    await handle.close();
  }
}

async function atomicWriteJson(path, value) {
  const parent = dirname(path);
  await mkdir(parent, { recursive: true, mode: 0o700 });
  await chmod(parent, 0o700);
  const temporary = `${path}.tmp-${process.pid}-${randomUUID()}`;
  let handle;
  let renamed = false;
  try {
    handle = await open(temporary, "wx", 0o600);
    await handle.writeFile(`${JSON.stringify(value, null, 2)}\n`, "utf8");
    await handle.chmod(0o600);
    await handle.sync();
    await handle.close();
    handle = null;
    await rename(temporary, path);
    renamed = true;
    await fsyncDirectory(parent);
  } finally {
    if (handle) await handle.close().catch(() => {});
    if (!renamed) await unlink(temporary).catch((error) => {
      if (error?.code !== "ENOENT") throw error;
    });
  }
}

function transactionPaths(receiptDir) {
  if (typeof receiptDir !== "string" || !receiptDir) {
    throw new Error("A photosensor receipt directory is required");
  }
  return {
    lockPath: join(receiptDir, LOCK_FILENAME),
    receiptPath: join(receiptDir, RECEIPT_FILENAME),
    snapshotPath: join(receiptDir, SNAPSHOT_FILENAME),
  };
}

async function acquireReceiptLock(receiptDir, operation, now) {
  const { lockPath } = transactionPaths(receiptDir);
  await mkdir(receiptDir, { recursive: true, mode: 0o700 });
  await chmod(receiptDir, 0o700);
  let handle;
  try {
    handle = await open(lockPath, "wx", 0o600);
  } catch (error) {
    if (error?.code === "EEXIST") {
      throw new Error("Photosensor config receipt is busy; inspect the transaction lock");
    }
    throw error;
  }
  const lock = {
    schema: LOCK_SCHEMA,
    pid: process.pid,
    hostname: hostname(),
    createdAt: instant(now),
    operation,
    nonce: randomUUID(),
  };
  try {
    await handle.writeFile(`${JSON.stringify(lock)}\n`, "utf8");
    await handle.chmod(0o600);
    await handle.sync();
    await handle.close();
    handle = null;
    await fsyncDirectory(receiptDir);
  } catch (error) {
    if (handle) await handle.close().catch(() => {});
    await unlink(lockPath).catch(() => {});
    throw error;
  }
  return async () => {
    const current = JSON.parse(await readFile(lockPath, "utf8"));
    if (current.schema !== LOCK_SCHEMA || current.nonce !== lock.nonce) {
      throw new Error("Photosensor config lock ownership changed");
    }
    await unlink(lockPath);
    await fsyncDirectory(receiptDir);
  };
}

async function withReceiptLock(receiptDir, operation, now, callback) {
  const release = await acquireReceiptLock(receiptDir, operation, now);
  try {
    return await callback();
  } finally {
    await release();
  }
}

async function readTransaction(receiptDir) {
  const paths = transactionPaths(receiptDir);
  let receipt;
  let snapshot;
  try {
    [receipt, snapshot] = await Promise.all([
      readFile(paths.receiptPath, "utf8").then(JSON.parse),
      readFile(paths.snapshotPath, "utf8").then(JSON.parse),
    ]);
  } catch (error) {
    throw new Error(`Photosensor config receipt or snapshot unavailable: ${error.message}`);
  }
  assertReceiptIntegrity(receipt, snapshot);
  return { ...paths, receipt, snapshot };
}

export async function inspectReceiptLock(receiptDir) {
  const { lockPath } = transactionPaths(receiptDir);
  const encoded = await readFile(lockPath, "utf8");
  return {
    lock: JSON.parse(encoded),
    digest: createHash("sha256").update(encoded).digest("hex"),
  };
}

async function writeReceipt(path, receipt, {
  now, phase, nextOperation, pendingOperation, state,
  writeCount,
} = {}) {
  const at = instant(now);
  const base = clone(receipt);
  if (state === "open") {
    delete base.closedAt;
    delete base.closedPhase;
  }
  const next = withChecksum({
    ...base,
    state: state ?? receipt.state,
    phase: phase ?? receipt.phase,
    nextOperation: nextOperation ?? receipt.nextOperation,
    pendingOperation: pendingOperation === undefined
      ? receipt.pendingOperation : pendingOperation,
    writeCount: writeCount ?? receipt.writeCount,
    updatedAt: at,
    transitions: phase === undefined
      ? clone(receipt.transitions)
      : [...receipt.transitions, { at, phase }],
  });
  await atomicWriteJson(path, next);
  return next;
}

async function writeClosedReceipt(path, receipt, now) {
  const at = instant(now);
  const next = withChecksum({
    ...clone(receipt),
    state: "closed",
    closedAt: at,
    closedPhase: receipt.phase,
    updatedAt: at,
    closures: [...receipt.closures, { at, phase: receipt.phase }],
  });
  await atomicWriteJson(path, next);
  return next;
}

async function requestGet(request, path, options = {}) {
  authorizePhotosensorRequest("GET", path);
  return request("GET", path, options);
}

async function readLiveSnapshot(request) {
  const thing = sanitizeThing(await requestGet(request, THING_PATH));
  const jdbc = sanitizeJdbc(await requestGet(request, JDBC_PATH));
  const items = {};
  const links = {};
  for (const desired of PHOTOSENSOR_ITEMS) {
    items[desired.name] = normalizeItem(
      await requestGet(request, itemPath(desired.name), { allowMissing: true }),
      desired.name,
    );
  }
  for (const desired of PHOTOSENSOR_LINKS) {
    links[desired.itemName] = normalizeLink(
      await requestGet(request, linkPath(desired), { allowMissing: true }),
      desired,
    );
  }
  return { items, links, thing, jdbc };
}

function assignOperation(state, operation) {
  const next = clone(state);
  const desiredItem = PHOTOSENSOR_ITEMS.find(({ name }) => itemPath(name) === operation.path);
  if (desiredItem) {
    next.items[desiredItem.name] = operation.method === "DELETE"
      ? null : normalizeItem(operation.body, desiredItem.name);
    return next;
  }
  const desiredLink = PHOTOSENSOR_LINKS.find((link) => linkPath(link) === operation.path);
  next.links[desiredLink.itemName] = operation.method === "DELETE"
    ? null : normalizeLink(operation.body, desiredLink);
  return next;
}

function stateAfter(initial, plan, count) {
  let state = clone(initial);
  for (const operation of plan.slice(0, count)) state = assignOperation(state, operation);
  return state;
}

function desiredSnapshot(snapshot) {
  const plan = buildApplyPlan(snapshot);
  return stateAfter(snapshot, plan, plan.length);
}

async function executeOperation(request, operation, transaction) {
  const options = { transaction };
  if (Object.hasOwn(operation, "body")) options.body = clone(operation.body);
  if (operation.method === "DELETE") options.allowMissing = true;
  authorizePhotosensorRequest(operation.method, operation.path, {
    body: options.body,
    transaction,
  });
  return request(operation.method, operation.path, options);
}

async function executePlan({
  request, transaction, receipt, receiptPath, plan, initial, snapshot, terminal, now,
}) {
  let current = receipt;
  const live = await readLiveSnapshot(request);
  const expected = stateAfter(initial, plan, current.nextOperation);
  if (!equal(live, expected)) {
    throw new Error("Live photosensor configuration drifted from receipt progress");
  }
  for (let index = current.nextOperation; index < plan.length; index += 1) {
    current = await writeReceipt(receiptPath, current, {
      now, pendingOperation: index,
    });
    const operation = plan[index];
    await executeOperation(request, operation, {
      operation: transaction,
      receipt: current,
      snapshot,
    });
    const landed = await requestGet(request, operation.path, { allowMissing: true });
    const expectedValue = operation.method === "DELETE" ? null : operation.body;
    const normalized = PHOTOSENSOR_ITEMS.some(({ name }) => itemPath(name) === operation.path)
      ? normalizeItem(
        landed,
        PHOTOSENSOR_ITEMS.find(({ name }) => itemPath(name) === operation.path).name,
      )
      : normalizeLink(
        landed,
        PHOTOSENSOR_LINKS.find((link) => linkPath(link) === operation.path),
      );
    if (!equal(normalized, expectedValue)) {
      throw new Error("Photosensor configuration write verification failed");
    }
    current = await writeReceipt(receiptPath, current, {
      now,
      nextOperation: index + 1,
      pendingOperation: null,
      writeCount: current.writeCount + 1,
    });
  }
  return writeReceipt(receiptPath, current, {
    now, phase: terminal, pendingOperation: null,
  });
}

async function snapshotTransactionUnlocked({ request, receiptDir, now } = {}) {
  if (typeof request !== "function") throw new Error("OpenHAB request transport is required");
  const paths = transactionPaths(receiptDir);
  if (await exists(paths.receiptPath) || await exists(paths.snapshotPath)) {
    throw new Error("Photosensor config receipt directory is not empty");
  }
  const live = await readLiveSnapshot(request);
  const transaction = buildReceipt(live, { createdAt: instant(now) });
  await atomicWriteJson(paths.snapshotPath, transaction.snapshot);
  await atomicWriteJson(paths.receiptPath, transaction.receipt);
  return transaction;
}

async function planTransactionUnlocked({ receiptDir } = {}) {
  const { receipt, snapshot } = await readTransaction(receiptDir);
  return {
    receipt: clone(receipt),
    apply: buildApplyPlan(snapshot),
    rollback: buildRollbackPlan(snapshot),
  };
}

async function applyTransactionUnlocked({ request, receiptDir, now } = {}) {
  if (typeof request !== "function") throw new Error("OpenHAB request transport is required");
  const transaction = await readTransaction(receiptDir);
  let { receipt } = transaction;
  if (receipt.state !== "open" || !["snapshot", "applying"].includes(receipt.phase)) {
    throw new Error(`Cannot apply photosensor config from ${receipt.state}/${receipt.phase}`);
  }
  if (receipt.phase === "applying" && receipt.pendingOperation !== null) {
    throw new Error("Cannot resume ambiguous photosensor write before settle");
  }
  const plan = buildApplyPlan(transaction.snapshot);
  if (receipt.phase === "snapshot") {
    const live = await readLiveSnapshot(request);
    if (!equal(live, transaction.snapshot)) {
      throw new Error("Live photosensor configuration drifted from captured pre-state");
    }
    receipt = await writeReceipt(transaction.receiptPath, receipt, {
      now, phase: "applying", nextOperation: 0, pendingOperation: null,
    });
  }
  return executePlan({
    request,
    transaction: "apply",
    receipt,
    receiptPath: transaction.receiptPath,
    plan,
    initial: transaction.snapshot,
    snapshot: transaction.snapshot,
    terminal: "desired",
    now,
  });
}

async function verifyTransactionUnlocked({ request, receiptDir } = {}) {
  if (typeof request !== "function") throw new Error("OpenHAB request transport is required");
  const { receipt, snapshot } = await readTransaction(receiptDir);
  const live = await readLiveSnapshot(request);
  if (receipt.phase === "desired") {
    return { ok: equal(live, desiredSnapshot(snapshot)), expected: "desired", phase: receipt.phase };
  }
  if (["snapshot", "rolled-back"].includes(receipt.phase)) {
    return { ok: equal(live, snapshot), expected: "original", phase: receipt.phase };
  }
  return {
    ok: false,
    expected: "unresolved; run settle after exact readback",
    phase: receipt.phase,
  };
}

async function rollbackTransactionUnlocked({ request, receiptDir, now } = {}) {
  if (typeof request !== "function") throw new Error("OpenHAB request transport is required");
  const transaction = await readTransaction(receiptDir);
  let { receipt } = transaction;
  if (receipt.state === "closed") {
    if (receipt.phase !== "desired") {
      throw new Error(`Cannot rollback closed photosensor receipt from ${receipt.phase}`);
    }
    const live = await readLiveSnapshot(request);
    if (!equal(live, desiredSnapshot(transaction.snapshot))) {
      throw new Error("Live photosensor configuration drifted from closed desired state");
    }
    receipt = await writeReceipt(transaction.receiptPath, receipt, {
      now, state: "open", phase: "rolling-back",
      nextOperation: 0, pendingOperation: null,
    });
  } else if (receipt.phase === "desired") {
    receipt = await writeReceipt(transaction.receiptPath, receipt, {
      now, phase: "rolling-back", nextOperation: 0, pendingOperation: null,
    });
  } else if (receipt.phase === "rolled-back") {
    return receipt;
  } else if (receipt.phase !== "rolling-back") {
    throw new Error(`Cannot rollback photosensor config from ${receipt.phase}`);
  }
  if (receipt.pendingOperation !== null) {
    throw new Error("Cannot resume ambiguous photosensor rollback before settle");
  }
  return executePlan({
    request,
    transaction: "rollback",
    receipt,
    receiptPath: transaction.receiptPath,
    plan: buildRollbackPlan(transaction.snapshot),
    initial: desiredSnapshot(transaction.snapshot),
    snapshot: transaction.snapshot,
    terminal: "rolled-back",
    now,
  });
}

function exactProgress(live, initial, plan) {
  const matches = [];
  for (let count = 0; count <= plan.length; count += 1) {
    if (equal(live, stateAfter(initial, plan, count))) matches.push(count);
  }
  if (matches.length !== 1) {
    throw new Error("Cannot settle photosensor transaction: live state is ambiguous or drifted");
  }
  return matches[0];
}

async function settleTransactionUnlocked({ request, receiptDir, now } = {}) {
  if (typeof request !== "function") throw new Error("OpenHAB request transport is required");
  const transaction = await readTransaction(receiptDir);
  const { receipt, snapshot } = transaction;
  if (receipt.state !== "open" || !["applying", "rolling-back"].includes(receipt.phase)
      || receipt.pendingOperation === null) {
    throw new Error("Photosensor transaction has no ambiguous write to settle");
  }
  const applying = receipt.phase === "applying";
  const plan = applying ? buildApplyPlan(snapshot) : buildRollbackPlan(snapshot);
  const initial = applying ? snapshot : desiredSnapshot(snapshot);
  const live = await readLiveSnapshot(request);
  const progress = exactProgress(live, initial, plan);
  if (![receipt.nextOperation, receipt.nextOperation + 1].includes(progress)) {
    throw new Error("Cannot settle photosensor transaction beyond the pending write");
  }
  const landed = progress === receipt.nextOperation + 1;
  return writeReceipt(transaction.receiptPath, receipt, {
    now,
    phase: progress === plan.length
      ? (applying ? "desired" : "rolled-back") : receipt.phase,
    nextOperation: progress,
    pendingOperation: null,
    writeCount: receipt.writeCount + (landed ? 1 : 0),
  });
}

async function closeTransactionUnlocked({ request, receiptDir, now } = {}) {
  if (typeof request !== "function") throw new Error("OpenHAB request transport is required");
  const transaction = await readTransaction(receiptDir);
  const { receipt, snapshot } = transaction;
  if (!["desired", "rolled-back"].includes(receipt.phase)) {
    throw new Error(`Cannot close photosensor receipt from ${receipt.phase}`);
  }
  const live = await readLiveSnapshot(request);
  const expected = receipt.phase === "desired" ? desiredSnapshot(snapshot) : snapshot;
  if (!equal(live, expected)) {
    throw new Error("Cannot close photosensor receipt: exact terminal readback mismatch");
  }
  if (receipt.state === "closed") return receipt;
  return writeClosedReceipt(transaction.receiptPath, receipt, now);
}

async function rehearseTransactionUnlocked({ receiptDir, now } = {}) {
  const realPaths = transactionPaths(receiptDir);
  const beforeReceipt = await readFile(realPaths.receiptPath);
  const beforeSnapshot = await readFile(realPaths.snapshotPath);
  const transaction = await readTransaction(receiptDir);
  if (transaction.receipt.state !== "open" || transaction.receipt.phase !== "snapshot") {
    throw new Error("Photosensor rehearsal requires an open snapshot receipt");
  }
  const isolated = await mkdtemp(join(tmpdir(), "thermal-photosensor-rehearse-"));
  await chmod(isolated, 0o700);
  let state = clone(transaction.snapshot);
  const operations = [];
  const request = async (method, path, options = {}) => {
    operations.push({
      method,
      path,
      bodyDigest: Object.hasOwn(options, "body") ? digest(options.body) : null,
    });
    if (method === "GET" && path === THING_PATH) return clone(state.thing);
    if (method === "GET" && path === JDBC_PATH) return clone(state.jdbc);
    const desiredItem = PHOTOSENSOR_ITEMS.find(({ name }) => itemPath(name) === path);
    const desiredLink = PHOTOSENSOR_LINKS.find((link) => linkPath(link) === path);
    const collection = desiredItem ? state.items : state.links;
    const key = desiredItem?.name ?? desiredLink?.itemName;
    if (method === "GET") return clone(collection[key]);
    const operation = {
      method,
      path,
      ...(Object.hasOwn(options, "body") ? { body: options.body } : {}),
    };
    state = assignOperation(state, operation);
    return null;
  };
  try {
    const isolatedPaths = transactionPaths(isolated);
    await atomicWriteJson(isolatedPaths.snapshotPath, transaction.snapshot);
    await atomicWriteJson(isolatedPaths.receiptPath, transaction.receipt);
    await applyTransactionUnlocked({ request, receiptDir: isolated, now });
    const desired = await verifyTransactionUnlocked({ request, receiptDir: isolated });
    if (!desired.ok) throw new Error("Photosensor rehearsal desired verification failed");
    await rollbackTransactionUnlocked({ request, receiptDir: isolated, now });
    const original = await verifyTransactionUnlocked({ request, receiptDir: isolated });
    if (!original.ok) throw new Error("Photosensor rehearsal rollback verification failed");
    const closed = await closeTransactionUnlocked({ request, receiptDir: isolated, now });
    const writes = operations.filter(({ method }) => ["PUT", "DELETE"].includes(method));
    if (!(await readFile(realPaths.receiptPath)).equals(beforeReceipt)
        || !(await readFile(realPaths.snapshotPath)).equals(beforeSnapshot)) {
      throw new Error("Photosensor rehearsal changed the real receipt");
    }
    return {
      receiptChecksum: transaction.receipt.checksum,
      snapshotDigest: transaction.receipt.snapshotDigest,
      operations,
      writeCounts: {
        put: writes.filter(({ method }) => method === "PUT").length,
        delete: writes.filter(({ method }) => method === "DELETE").length,
        total: writes.length,
      },
      terminal: { state: closed.state, phase: closed.phase },
    };
  } finally {
    await rm(isolated, { recursive: true, force: true });
  }
}

export function snapshotTransaction(args = {}) {
  return withReceiptLock(args.receiptDir, "snapshot", args.now, () => (
    snapshotTransactionUnlocked(args)
  ));
}

export function applyTransaction(args = {}) {
  return withReceiptLock(args.receiptDir, "apply", args.now, () => (
    applyTransactionUnlocked(args)
  ));
}

export function planTransaction(args = {}) {
  return withReceiptLock(args.receiptDir, "plan", args.now, () => (
    planTransactionUnlocked(args)
  ));
}

export function verifyTransaction(args = {}) {
  return withReceiptLock(args.receiptDir, "verify", args.now, () => (
    verifyTransactionUnlocked(args)
  ));
}

export function rollbackTransaction(args = {}) {
  return withReceiptLock(args.receiptDir, "rollback", args.now, () => (
    rollbackTransactionUnlocked(args)
  ));
}

export function settleTransaction(args = {}) {
  return withReceiptLock(args.receiptDir, "settle", args.now, () => (
    settleTransactionUnlocked(args)
  ));
}

export function closeTransaction(args = {}) {
  return withReceiptLock(args.receiptDir, "close", args.now, () => (
    closeTransactionUnlocked(args)
  ));
}

export function rehearseTransaction(args = {}) {
  return withReceiptLock(args.receiptDir, "rehearse", args.now, () => (
    rehearseTransactionUnlocked(args)
  ));
}

function parseEnv(text) {
  const values = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const separator = line.indexOf("=");
    if (separator < 1) continue;
    const key = line.slice(0, separator).trim().replace(/^export\s+/, "");
    let value = line.slice(separator + 1).trim();
    if ((value.startsWith("\"") && value.endsWith("\""))
        || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}

async function loadAuth() {
  const values = parseEnv(await readFile(AUTH_FILE, "utf8"));
  const token = values.OPENHAB_TOKEN;
  if (!token) throw new Error(`OPENHAB_TOKEN is missing from ${AUTH_FILE}`);
  if (process.env.OPENHAB_TOKEN && process.env.OPENHAB_TOKEN !== token) {
    throw new Error("Ambient OPENHAB_TOKEN conflicts with the protected token file");
  }
  return {
    baseUrl: values.OPENHAB_URL || DEFAULT_BASE_URL,
    authorization: `Basic ${Buffer.from(`${token}:`).toString("base64")}`,
  };
}

function confinedBaseUrl(baseUrl) {
  const raw = String(baseUrl ?? "");
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error("Invalid OpenHAB base URL");
  }
  if (!["http:", "https:"].includes(parsed.protocol)
      || parsed.username || parsed.password
      || parsed.pathname !== "/" || parsed.search || parsed.hash) {
    throw new Error("Denied OpenHAB base URL destination");
  }
  const root = `${parsed.protocol}//${parsed.host}`;
  if (raw !== root && raw !== `${root}/`) {
    throw new Error("Denied non-root OpenHAB base URL");
  }
  return new URL(`${root}/`);
}

function confinedRequestUrl(base, path) {
  const destination = new URL(path, base);
  if (destination.origin !== base.origin
      || `${destination.pathname}${destination.search}` !== path
      || destination.hash) {
    throw new Error("Denied OpenHAB photosensor request destination");
  }
  return destination.href;
}

export function createRestClient({
  baseUrl,
  authorization,
  fetchImpl = fetch,
}) {
  const base = confinedBaseUrl(baseUrl);
  return async function request(method, path, options = {}) {
    const hasBody = Object.hasOwn(options, "body");
    authorizePhotosensorRequest(method, path, {
      body: hasBody ? options.body : undefined,
      transaction: options.transaction,
    });
    const url = confinedRequestUrl(base, path);
    const headers = { Accept: "application/json", Authorization: authorization };
    let body;
    if (hasBody) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(options.body);
    }
    const response = await fetchImpl(url, {
      method,
      headers,
      body,
      redirect: "error",
      signal: AbortSignal.timeout(15_000),
    });
    if (response.redirected) throw new Error("OpenHAB redirect denied");
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
  return "Usage: thermal-photosensor-config.mjs snapshot|plan|rehearse|apply|verify|rollback|settle|close|inspect-lock --receipt-dir PATH";
}

function parseCli(argv) {
  if (argv.includes("--help") || argv.includes("-h")) return { help: true };
  const command = argv[0];
  const commands = [
    "snapshot", "plan", "rehearse", "apply", "verify",
    "rollback", "settle", "close", "inspect-lock",
  ];
  if (!commands.includes(command)) throw new Error(usage());
  const receiptIndex = argv.indexOf("--receipt-dir");
  if (receiptIndex !== 1 || !argv[2] || argv[2].startsWith("--")
      || argv.length !== 3) {
    throw new Error("--receipt-dir PATH is required");
  }
  return { command, receiptDir: resolve(argv[2]) };
}

export async function main(argv = process.argv.slice(2), dependencies = {}) {
  const args = parseCli(argv);
  if (args.help) return { help: usage() };
  if (args.command === "inspect-lock") return inspectReceiptLock(args.receiptDir);
  if (args.command === "plan") return planTransaction(args);
  if (args.command === "rehearse") return rehearseTransaction(args);
  const request = dependencies.request
    ?? createRestClient({ ...(await loadAuth()), fetchImpl: dependencies.fetchImpl });
  if (args.command === "snapshot") return snapshotTransaction({ ...args, request });
  if (args.command === "apply") return applyTransaction({ ...args, request });
  if (args.command === "verify") return verifyTransaction({ ...args, request });
  if (args.command === "rollback") return rollbackTransaction({ ...args, request });
  if (args.command === "settle") return settleTransaction({ ...args, request });
  return closeTransaction({ ...args, request });
}

if (process.argv[1]
    && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().then((result) => {
    if (result.help) process.stdout.write(`${result.help}\n`);
    else process.stdout.write(`${JSON.stringify(result)}\n`);
    if (Object.hasOwn(result, "ok") && !result.ok) process.exitCode = 1;
  }).catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
