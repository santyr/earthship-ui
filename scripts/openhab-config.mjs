#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { readFile, stat } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import {
  assertReceiptChecksum as assertIngressChecksum,
  durableAtomicWriteJson,
  verifyQuiescent as verifyIngressQuiescent,
} from './feeder-ingress.mjs';

export const SUPPORTED_OPENHAB_VERSION = '5.2.0';
export const FEEDER_RULE_UID = '88bd9ec4de';
export const FEEDER_REQUEST_ITEM = 'GoatFeeder_ManualRequest';
export const FEEDER_RESULT_ITEM = 'GoatFeeder_ManualResult';
export const FEEDER_ACTUATOR_ITEM = 'Goat_Plugs_Outlet2_Switch';
export const FEEDER_COUNTER_ITEM = 'GoatFeedings';
const AUTH_FILE = '/home/sat/.config/hex/openhab.env';
const DEFAULT_BASE_URL = 'http://192.168.1.161:8080';
const ACTIVE_RECEIPT = '/tmp/earthship-ui-openhab-active/feeder.json';

const exactPaths = new Set([
  'GET /rest/',
  'GET /rest/events',
  'GET /rest/links',
  'GET /rest/persistence',
  'GET /rest/persistence/jdbc',
  `GET /rest/persistence/items/${FEEDER_REQUEST_ITEM}`,
  ...[FEEDER_REQUEST_ITEM, FEEDER_RESULT_ITEM, FEEDER_ACTUATOR_ITEM, FEEDER_COUNTER_ITEM]
    .map((name) => `GET /rest/items/${name}`),
  `GET /rest/items/${FEEDER_REQUEST_ITEM}/metadata/autoupdate`,
  `GET /rest/items/${FEEDER_ACTUATOR_ITEM}/metadata/expire`,
  `GET /rest/rules/${FEEDER_RULE_UID}`,
  `PUT /rest/items/${FEEDER_REQUEST_ITEM}`,
  `PUT /rest/items/${FEEDER_RESULT_ITEM}`,
  `PUT /rest/items/${FEEDER_REQUEST_ITEM}/metadata/autoupdate`,
  `PUT /rest/items/${FEEDER_ACTUATOR_ITEM}/metadata/expire`,
  `PUT /rest/rules/${FEEDER_RULE_UID}`,
  `POST /rest/rules/${FEEDER_RULE_UID}/enable`,
  `DELETE /rest/items/${FEEDER_REQUEST_ITEM}`,
  `DELETE /rest/items/${FEEDER_RESULT_ITEM}`,
  `DELETE /rest/items/${FEEDER_REQUEST_ITEM}/metadata/autoupdate`,
]);

export function assertAllowedFeederRequest(method, rawPath) {
  const path = String(rawPath).split('?')[0];
  const key = `${String(method).toUpperCase()} ${path}`;
  if (!exactPaths.has(key)) throw new Error(`Denied OpenHAB request: ${key}`);
}

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

function checksum(value) {
  return createHash('sha256')
    .update(JSON.stringify(canonicalValue(value)))
    .digest('hex');
}

function withChecksum(value) {
  const next = clone(value);
  delete next.checksum;
  next.checksum = checksum(next);
  return next;
}

export function assertFeederReceiptChecksum(receipt) {
  if (!receipt || typeof receipt !== 'object') throw new Error('feeder receipt is required');
  if (!/^[a-f0-9]{64}$/.test(receipt.checksum ?? '')) {
    throw new Error('feeder receipt checksum is missing');
  }
  if (checksum(receipt) !== receipt.checksum) throw new Error('feeder receipt checksum mismatch');
}

function eventPayload(event) {
  try {
    return typeof event?.payload === 'string' ? JSON.parse(event.payload) : event?.payload;
  } catch {
    return null;
  }
}

function unsafeFeederEvent(event) {
  const topic = String(event?.topic ?? '');
  const type = String(event?.type ?? '');
  const itemMatch = /^openhab\/items\/([^/]+)\//.exec(topic);
  if (itemMatch && [
    FEEDER_REQUEST_ITEM,
    FEEDER_RESULT_ITEM,
    FEEDER_ACTUATOR_ITEM,
    FEEDER_COUNTER_ITEM,
  ].includes(itemMatch[1])) {
    return /Item(Command|State|StateChanged|StatePredicted)Event/.test(type);
  }
  if (topic.startsWith(`openhab/rules/${FEEDER_RULE_UID}/`)) {
    const payload = eventPayload(event);
    return payload?.status === 'RUNNING' || payload?.statusDetail === 'RUNNING';
  }
  return false;
}

export function createFeederEventGuard(startedAt = new Date().toISOString()) {
  let eventCount = 0;
  let unsafeEventCount = 0;
  let digest = createHash('sha256').update('').digest('hex');
  let lastEventAt = null;
  let failure = null;
  return {
    observe(event) {
      if (!unsafeFeederEvent(event)) return;
      eventCount += 1;
      unsafeEventCount += 1;
      lastEventAt = new Date().toISOString();
      digest = createHash('sha256').update(`${digest}:${JSON.stringify(canonicalValue({
        topic: event.topic,
        type: event.type,
        payload: eventPayload(event),
      }))}`).digest('hex');
    },
    fail(error) {
      failure = error instanceof Error ? error : new Error(String(error));
    },
    assertSafe() {
      if (failure) throw new Error(`feeder event monitor failed: ${failure.message}`);
      if (unsafeEventCount > 0) {
        throw new Error('feeder execution activity appeared on the continuous event cursor');
      }
    },
    snapshot() {
      return { startedAt, eventCount, unsafeEventCount, lastEventAt, digest };
    },
  };
}

function sseEvents(buffer) {
  const events = [];
  let boundary;
  while ((boundary = buffer.indexOf('\n\n')) >= 0) {
    const block = buffer.slice(0, boundary);
    buffer = buffer.slice(boundary + 2);
    const data = block.split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n');
    if (data) events.push(JSON.parse(data));
  }
  return { events, buffer };
}

export async function startFeederEventMonitor({ baseUrl, authorization, fetchImpl = fetch }) {
  assertAllowedFeederRequest('GET', '/rest/events');
  const guard = createFeederEventGuard();
  const controller = new AbortController();
  let closed = false;
  const timeout = setTimeout(() => controller.abort(), 10_000);
  let response;
  try {
    response = await fetchImpl(`${baseUrl}/rest/events`, {
      headers: { Accept: 'text/event-stream', Authorization: authorization },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
  if (!response.ok || !response.body) {
    controller.abort();
    throw new Error(`OpenHAB event monitor failed with HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const task = (async () => {
    let buffer = '';
    while (!closed) {
      const { done, value } = await reader.read();
      if (done) {
        if (!closed) guard.fail(new Error('event stream ended'));
        return;
      }
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      const parsed = sseEvents(buffer);
      buffer = parsed.buffer;
      for (const event of parsed.events) guard.observe(event);
    }
  })().catch((error) => {
    if (!closed) guard.fail(error);
  });
  return {
    guard,
    async close() {
      closed = true;
      controller.abort();
      try { await reader.cancel(); } catch { /* already closed */ }
      await task;
    },
  };
}

export function buildFeederRuleDto(manifest, ruleSource, originalRule = {}) {
  const feeder = manifest?.subsets?.feeder;
  if (feeder?.capability !== 'feeder-request-v1') {
    throw new Error('feeder-request-v1 manifest is required');
  }
  if (feeder.rule?.uid !== FEEDER_RULE_UID) throw new Error('canonical feeder UID mismatch');
  if (typeof ruleSource !== 'string' || !ruleSource.includes('EARTHSHIP_FEEDER_OWNER_VERSION')) {
    throw new Error('versioned feeder owner source is required');
  }
  return {
    uid: FEEDER_RULE_UID,
    name: feeder.rule.name,
    description: originalRule.description ?? 'Canonical correlated feeder owner',
    tags: Array.isArray(originalRule.tags) ? clone(originalRule.tags) : [],
    visibility: originalRule.visibility ?? 'VISIBLE',
    configuration: clone(originalRule.configuration ?? {}),
    triggers: clone(feeder.rule.triggers),
    conditions: clone(originalRule.conditions ?? []),
    actions: [{
      // openHAB GET always renders `inputs: {}` on actions; include it so the
      // built DTO compares canonically equal to the applied rule.
      inputs: {},
      id: feeder.rule.action.id,
      type: feeder.rule.action.type,
      configuration: {
        ...clone(feeder.rule.action.configuration),
        script: ruleSource,
      },
    }],
  };
}

function itemPutDto(item) {
  if (!item) return null;
  return {
    type: item.type,
    name: item.name,
    label: item.label ?? '',
    category: item.category ?? '',
    tags: clone(item.tags ?? []),
    groupNames: clone(item.groupNames ?? []),
  };
}

function rulePutDto(rule) {
  return {
    uid: rule.uid,
    name: rule.name,
    description: rule.description ?? '',
    tags: clone(rule.tags ?? []),
    visibility: rule.visibility ?? 'VISIBLE',
    configuration: clone(rule.configuration ?? {}),
    triggers: clone(rule.triggers ?? []),
    conditions: clone(rule.conditions ?? []),
    actions: clone(rule.actions ?? []),
  };
}

export function buildFeederApplyPlan({ manifest, source, original }) {
  const feeder = manifest?.subsets?.feeder;
  if (!original?.rule) throw new Error('captured original feeder rule is required');
  return [
    { method: 'POST', path: `/rest/rules/${FEEDER_RULE_UID}/enable`, body: 'false' },
    {
      method: 'PUT',
      path: `/rest/items/${FEEDER_REQUEST_ITEM}`,
      body: clone(feeder.items.find(({ name }) => name === FEEDER_REQUEST_ITEM)),
    },
    {
      method: 'PUT',
      path: `/rest/items/${FEEDER_RESULT_ITEM}`,
      body: clone(feeder.items.find(({ name }) => name === FEEDER_RESULT_ITEM)),
    },
    {
      method: 'PUT',
      path: `/rest/items/${FEEDER_REQUEST_ITEM}/metadata/autoupdate`,
      body: { value: 'false', config: {} },
    },
    {
      method: 'PUT',
      path: `/rest/rules/${FEEDER_RULE_UID}`,
      body: buildFeederRuleDto(manifest, source, original.rule),
    },
  ];
}

export function buildFeederRollbackPlan(original) {
  if (!original?.rule) throw new Error('captured original feeder rule is required');
  const operations = [
    { method: 'POST', path: `/rest/rules/${FEEDER_RULE_UID}/enable`, body: 'false' },
    { method: 'PUT', path: `/rest/rules/${FEEDER_RULE_UID}`, body: rulePutDto(original.rule) },
  ];
  const originalAutoupdate = original.metadata?.[FEEDER_REQUEST_ITEM]?.autoupdate;
  operations.push(originalAutoupdate
    ? {
        method: 'PUT',
        path: `/rest/items/${FEEDER_REQUEST_ITEM}/metadata/autoupdate`,
        body: clone(originalAutoupdate),
      }
    : {
        method: 'DELETE',
        path: `/rest/items/${FEEDER_REQUEST_ITEM}/metadata/autoupdate`,
      });
  for (const name of [FEEDER_RESULT_ITEM, FEEDER_REQUEST_ITEM]) {
    const item = original.items?.[name];
    operations.push(item
      ? { method: 'PUT', path: `/rest/items/${name}`, body: itemPutDto(item) }
      : { method: 'DELETE', path: `/rest/items/${name}` });
  }
  return operations;
}

// ---------------------------------------------------------------------------
// Manifest-driven planning for any subset (feeder, greywater, night-load).
//
// These are PURE functions over openhab/managed-resources.json — no live REST
// calls. They generalize the feeder-specific builders so the same transaction
// machinery can (a) create String AND DateTime Items with metadata and declare
// their persistence coverage, (b) replace an existing rule's script by UID,
// (c) create a brand-new rule, (d) retire duplicate child rules by DISABLE (with
// a receipt-bound backup for reversal — never DELETE), and (e) leave schedules /
// coupling rules untouched while verifying their hashes are unchanged.
// ---------------------------------------------------------------------------

export const SUBSET_VERSION_TOKENS = Object.freeze({
  feeder: 'EARTHSHIP_FEEDER_OWNER_VERSION',
  greywater: 'EARTHSHIP_SOUTHOUTLET_VERSION',
  'night-load': 'EARTHSHIP_NIGHT_LOAD_OWNER_VERSION',
});

export function getSubset(manifest, subsetName) {
  const subset = manifest?.subsets?.[subsetName];
  if (!subset) throw new Error(`unknown managed-resources subset: ${subsetName}`);
  return subset;
}

// Full rule DTO for a subset. When originalRule is supplied it is a
// replace-in-place (existing UID); when it is empty it is a fresh create. The
// versioned owner source must carry the subset's version token.
export function buildSubsetRuleDto({ subset, subsetName, source, originalRule = {} }) {
  if (!subset?.rule?.uid) throw new Error(`subset ${subsetName} declares no rule uid`);
  const token = SUBSET_VERSION_TOKENS[subsetName];
  if (!token || typeof source !== 'string' || !source.includes(token)) {
    throw new Error(`versioned ${subsetName} owner source is required`);
  }
  return {
    uid: subset.rule.uid,
    name: subset.rule.name,
    description: originalRule.description ?? `Canonical ${subsetName} owner`,
    tags: Array.isArray(originalRule.tags) ? clone(originalRule.tags) : [],
    visibility: originalRule.visibility ?? 'VISIBLE',
    configuration: clone(originalRule.configuration ?? {}),
    triggers: clone(subset.rule.triggers),
    conditions: clone(originalRule.conditions ?? []),
    actions: [{
      // Same canonical-compare contract as buildFeederRuleDto: openHAB GET
      // renders `inputs: {}` on every action.
      inputs: {},
      id: subset.rule.action.id,
      type: subset.rule.action.type,
      configuration: {
        ...clone(subset.rule.action.configuration),
        script: source,
      },
    }],
  };
}

function metadataPath(item, namespace) {
  return `/rest/items/${item}/metadata/${namespace}`;
}

// Retirement is DISABLE, never DELETE. Each retired child rule is disabled so
// the transaction is reversible from the receipt-bound backup.
export function buildRetirementPlan(subset) {
  return (subset.graph?.retiredRules ?? []).map((retired) => ({
    method: 'POST',
    path: `/rest/rules/${retired.uid}/enable`,
    body: 'false',
    kind: 'retire-disable',
    uid: retired.uid,
  }));
}

export function buildRetirementRollback(subset, retiredBackup = {}) {
  // Reverse a retirement only for rules that were enabled before we disabled
  // them (recorded in the receipt-bound backup). Default to re-enable.
  return (subset.graph?.retiredRules ?? []).map((retired) => ({
    method: 'POST',
    path: `/rest/rules/${retired.uid}/enable`,
    body: retiredBackup?.[retired.uid]?.enabled === false ? 'false' : 'true',
    kind: 'retire-reverse',
    uid: retired.uid,
  }));
}

export function buildSubsetApplyPlan({
  manifest, subsetName, source, original = {},
}) {
  const subset = getSubset(manifest, subsetName);
  const ruleUid = subset.rule.uid;
  const isNewRule = !original.rule; // create (c) vs replace-in-place (b)
  const operations = [];

  // (d) Retire duplicate child rules first (DISABLE, receipt-backed).
  operations.push(...buildRetirementPlan(subset));

  // (b) Disable the target rule before replacing its script; a brand-new rule
  // has nothing to disable.
  if (!isNewRule) {
    operations.push({
      method: 'POST', path: `/rest/rules/${ruleUid}/enable`, body: 'false', kind: 'disable-target',
    });
  }

  // (a) Items — String AND DateTime, from the manifest declaration.
  for (const item of subset.items ?? []) {
    operations.push({
      method: 'PUT', path: `/rest/items/${item.name}`, body: itemPutDto(item), kind: 'item',
    });
  }

  // (a) Item metadata — autoupdate=false, expire backstops, etc.
  for (const meta of subset.metadata ?? []) {
    operations.push({
      method: 'PUT',
      path: metadataPath(meta.item, meta.namespace),
      body: { value: meta.value, config: clone(meta.config ?? {}) },
      kind: 'metadata',
    });
  }

  // (b)/(c) Replace or create the owner rule. openHAB creates rules with
  // POST /rest/rules (PUT on a missing UID is 404, learned live 2026-07-19);
  // replace-in-place stays a PUT on the existing UID.
  operations.push({
    method: isNewRule ? 'POST' : 'PUT',
    path: isNewRule ? '/rest/rules' : `/rest/rules/${ruleUid}`,
    body: buildSubsetRuleDto({
      subset, subsetName, source, originalRule: original.rule ?? {},
    }),
    kind: isNewRule ? 'rule-create' : 'rule-replace',
  });

  return operations;
}

export function buildSubsetRollbackPlan({ manifest, subsetName, original = {} }) {
  const subset = getSubset(manifest, subsetName);
  const ruleUid = subset.rule.uid;
  const isNewRule = !original.rule;
  const operations = [
    { method: 'POST', path: `/rest/rules/${ruleUid}/enable`, body: 'false', kind: 'disable-target' },
  ];

  // Restore the prior rule DTO, or delete a rule that this transaction created.
  operations.push(isNewRule
    ? { method: 'DELETE', path: `/rest/rules/${ruleUid}`, kind: 'rule-delete' }
    : { method: 'PUT', path: `/rest/rules/${ruleUid}`, body: rulePutDto(original.rule), kind: 'rule-restore' });

  // Restore each metadata namespace to its captured value, or delete if it did
  // not exist before.
  for (const meta of subset.metadata ?? []) {
    const captured = original.metadata?.[meta.item]?.[meta.namespace];
    operations.push(captured
      ? {
          method: 'PUT', path: metadataPath(meta.item, meta.namespace), body: clone(captured), kind: 'metadata-restore',
        }
      : { method: 'DELETE', path: metadataPath(meta.item, meta.namespace), kind: 'metadata-delete' });
  }

  // Restore or delete each managed Item (reverse declaration order).
  for (const item of [...(subset.items ?? [])].reverse()) {
    const captured = original.items?.[item.name];
    operations.push(captured
      ? { method: 'PUT', path: `/rest/items/${item.name}`, body: itemPutDto(captured), kind: 'item-restore' }
      : { method: 'DELETE', path: `/rest/items/${item.name}`, kind: 'item-delete' });
  }

  // (d) Reverse retirement — re-enable the retired child rules.
  operations.push(...buildRetirementRollback(subset, original.retiredRules));

  return operations;
}

// (a) The persistence coverage the subset declares. Persistence is provisioned
// out of band (the jdbc .persist config), exactly as the feeder path verifies
// rather than writes; this is the coverage the verify step must confirm.
export function expectedPersistenceCoverage(subset) {
  const persistence = subset.persistence ?? {};
  return {
    serviceId: persistence.serviceId ?? null,
    strategy: persistence.strategy ?? null,
    restoreOnStartup: persistence.restoreOnStartup === true,
    items: clone(persistence.items ?? []),
  };
}

// (e) The UIDs of rules the transaction must leave byte-for-byte untouched:
// preserved coupling rules and schedules.
export function graphImmutableUids(subset) {
  const graph = subset.graph ?? {};
  return [
    ...(graph.couplingDependencies ?? []).map((rule) => rule.uid),
    ...(graph.schedules ?? []).map((rule) => rule.uid),
  ];
}

export function ruleHash(rule) {
  return checksum(canonicalValue(rule));
}

// (e) Verify every untouched schedule/coupling rule's hash is unchanged between
// the captured snapshot and the current live state.
export function assertUnchangedGraphHashes(subset, capturedHashes, liveHashes) {
  const reasons = [];
  for (const uid of graphImmutableUids(subset)) {
    const before = capturedHashes?.[uid];
    const after = liveHashes?.[uid];
    if (before === undefined || after === undefined) {
      reasons.push(`missing hash for untouched rule ${uid}`);
    } else if (before !== after) {
      reasons.push(`untouched rule ${uid} was modified`);
    }
  }
  return { ok: reasons.length === 0, reasons };
}

function metadataValue(metadata, item, namespace) {
  return metadata?.[item]?.[namespace]?.value;
}

function validRestoredLedger(raw) {
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > 8192) return false;
  try {
    const ledger = JSON.parse(raw);
    const entries = ledger?.entries;
    const uniqueIds = new Set(entries?.map((entry) => entry?.requestId));
    return ledger?.version === 'feeder-request-ledger/v1'
      && Array.isArray(entries)
      && entries.length <= 32
      && uniqueIds.size === entries.length
      && entries.every((entry) => (
        typeof entry?.requestId === 'string'
        && /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/.test(entry.requestId)
        && ['accepted', 'running', 'complete', 'failed', 'denied'].includes(entry.status)
        && typeof entry?.reason === 'string'
        && Number.isFinite(Date.parse(String(entry?.at).replace(/\[[^\]]+\]$/, '')))
        && (entry.updatedAt === undefined || (
          typeof entry.updatedAt === 'string'
          && Number.isFinite(Date.parse(entry.updatedAt.replace(/\[[^\]]+\]$/, '')))
        ))
      ));
  } catch {
    return false;
  }
}

export function verifyFeederState(live, { requireDisabled = false, expectedRule = null } = {}) {
  const reasons = [];
  if (live?.runtimeInfo?.version !== SUPPORTED_OPENHAB_VERSION) {
    reasons.push(`OpenHAB runtime must be ${SUPPORTED_OPENHAB_VERSION}`);
  }
  for (const name of [FEEDER_REQUEST_ITEM, FEEDER_RESULT_ITEM]) {
    if (live?.items?.[name]?.type !== 'String') reasons.push(`${name} must be a String Item`);
  }
  if (live?.items?.[FEEDER_ACTUATOR_ITEM]?.state !== 'OFF') {
    reasons.push('feeder actuator must be OFF');
  }
  if (live?.items?.[FEEDER_COUNTER_ITEM]?.type !== 'Number') {
    reasons.push('GoatFeedings counter must be a Number Item');
  }
  if (metadataValue(live?.metadata, FEEDER_REQUEST_ITEM, 'autoupdate') !== 'false') {
    reasons.push('request autoupdate must be false');
  }
  if (
    metadataValue(live?.metadata, FEEDER_ACTUATOR_ITEM, 'expire')
    !== '0h0m1s,command=OFF'
  ) reasons.push('actuator expire metadata mismatch');

  const linked = (live?.links ?? []).filter(({ itemName }) => (
    itemName === FEEDER_REQUEST_ITEM || itemName === FEEDER_RESULT_ITEM
  ));
  if (linked.length > 0) reasons.push('manual request and result Items must remain unlinked');

  const persistence = live?.persistenceCoverage;
  if (
    persistence?.serviceId !== 'jdbc'
    || persistence?.strategy !== 'everyChange'
    || persistence?.restoreOnStartup !== true
    || ![FEEDER_REQUEST_ITEM, FEEDER_RESULT_ITEM]
      .every((name) => persistence?.items?.includes(name))
  ) reasons.push('JDBC everyChange/restoreOnStartup coverage is incomplete');

  const requestState = live?.items?.[FEEDER_REQUEST_ITEM]?.state;
  if (['NULL', 'UNDEF'].includes(requestState)) {
    if (live?.requestHistoryCount !== 0) reasons.push('request ledger restore is missing');
  } else if (!validRestoredLedger(requestState)) {
    reasons.push('request ledger is corrupt or unbounded');
  }

  const rule = live?.rule;
  if (rule?.uid !== FEEDER_RULE_UID) reasons.push('canonical feeder rule UID mismatch');
  if (rule?.triggers?.length !== 1 || (
    rule.triggers[0]?.type !== 'core.ItemCommandTrigger'
    || rule.triggers[0]?.configuration?.itemName !== FEEDER_REQUEST_ITEM
  )) reasons.push('canonical feeder received-command trigger mismatch');
  const script = rule?.actions?.[0]?.configuration?.script;
  if (typeof script !== 'string' || !script.includes("'feeder-request-v1'")) {
    reasons.push('versioned feeder rule source mismatch');
  }
  if (
    expectedRule
    && JSON.stringify(canonicalValue(rule)) !== JSON.stringify(canonicalValue(expectedRule))
  ) reasons.push('canonical feeder rule hash mismatch');
  if (requireDisabled) {
    if (
      live?.ruleEnabled !== false
      || live?.ruleStatus?.status !== 'UNINITIALIZED'
      || live?.ruleStatus?.statusDetail !== 'DISABLED'
    ) reasons.push('canonical feeder rule must be disabled');
  } else if (live?.ruleStatus?.status !== 'IDLE') {
    reasons.push('canonical feeder rule must be IDLE');
  }
  return { ok: reasons.length === 0, reasons };
}

function assertNoSecretKeys(value, path = []) {
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    if (/(authorization|api.?token|password|secret|private.?key)/i.test(key)) {
      throw new Error(`secret-like field cannot enter receipt: ${[...path, key].join('.')}`);
    }
    assertNoSecretKeys(child, [...path, key]);
  }
}

export function buildFeederReceipt({
  generation,
  live,
  createdAt = new Date().toISOString(),
  ingressGeneration = null,
} = {}) {
  if (typeof generation !== 'string' || !generation) throw new Error('feeder generation is required');
  assertNoSecretKeys(live);
  const snapshot = {
    schema: 'earthship-ui-openhab-feeder-receipt/v1',
    subset: 'feeder',
    state: 'open',
    phase: 'snapshot',
    generation,
    ingressGeneration,
    createdAt,
    updatedAt: createdAt,
    writeCount: 0,
    original: clone(live),
    transitions: [],
  };
  snapshot.snapshotChecksum = createHash('sha256')
    .update(JSON.stringify(canonicalValue({
      generation,
      ingressGeneration,
      original: snapshot.original,
    })))
    .digest('hex');
  return withChecksum(snapshot);
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
  const values = parseEnv(await readFile(AUTH_FILE, 'utf8'));
  const token = values.OPENHAB_TOKEN;
  if (!token) throw new Error(`OPENHAB_TOKEN is missing from ${AUTH_FILE}`);
  if (process.env.OPENHAB_TOKEN && process.env.OPENHAB_TOKEN !== token) {
    throw new Error('ambient OPENHAB_TOKEN conflicts with the protected token file');
  }
  return {
    baseUrl: (values.OPENHAB_URL || DEFAULT_BASE_URL).replace(/\/$/, ''),
    authorization: `Basic ${Buffer.from(`${token}:`).toString('base64')}`,
  };
}

function createRestClient({ baseUrl, authorization }) {
  return async function request(method, path, { body, allowMissing = false } = {}) {
    assertAllowedFeederRequest(method, path);
    const headers = { Accept: 'application/json', Authorization: authorization };
    if (body !== undefined) {
      headers['Content-Type'] = typeof body === 'string' ? 'text/plain' : 'application/json';
    }
    const response = await fetch(`${baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : (typeof body === 'string' ? body : JSON.stringify(body)),
      signal: AbortSignal.timeout(20_000),
    });
    if (allowMissing && response.status === 404) return null;
    if (!response.ok) {
      throw new Error(`OpenHAB ${method} ${path} failed with HTTP ${response.status}`);
    }
    if (response.status === 204) return null;
    const text = await response.text();
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  };
}

export function normalizePersistenceCoverage(configuration) {
  const requiredItems = [FEEDER_REQUEST_ITEM, FEEDER_RESULT_ITEM];
  const covered = new Set();
  for (const config of Array.isArray(configuration?.configs) ? configuration.configs : []) {
    const strategies = new Set(Array.isArray(config?.strategies) ? config.strategies : []);
    if (!strategies.has('everyChange') || !strategies.has('restoreOnStartup')) continue;
    const configuredItems = new Set(Array.isArray(config?.items) ? config.items : []);
    for (const item of requiredItems) {
      if (configuredItems.has('*') || configuredItems.has(item)) covered.add(item);
    }
  }
  const complete = requiredItems.every((item) => covered.has(item));
  return {
    serviceId: configuration?.serviceId === 'jdbc' ? 'jdbc' : null,
    strategy: complete ? 'everyChange' : null,
    restoreOnStartup: complete,
    items: complete ? requiredItems : [],
  };
}

function historyCount(response) {
  if (Number.isInteger(response?.totalRecords)) return response.totalRecords;
  if (Number.isInteger(response?.totalrecords)) return response.totalrecords;
  if (Array.isArray(response?.data)) return response.data.length;
  return 0;
}

async function liveFeederState(request) {
  const itemNames = [
    FEEDER_REQUEST_ITEM,
    FEEDER_RESULT_ITEM,
    FEEDER_ACTUATOR_ITEM,
    FEEDER_COUNTER_ITEM,
  ];
  const [root, itemDtos, requestItemMeta, actuatorItemMeta, links, jdbc, history, rule] = await Promise.all([
    request('GET', '/rest/'),
    Promise.all(itemNames.map((name) => request('GET', `/rest/items/${name}`, {
      allowMissing: [FEEDER_REQUEST_ITEM, FEEDER_RESULT_ITEM].includes(name),
    }))),
    // openHAB 5.2 has no GET on /metadata/{namespace} (405) — read namespaces
    // through the item DTO instead.
    request('GET', `/rest/items/${FEEDER_REQUEST_ITEM}?metadata=autoupdate`, { allowMissing: true }),
    request('GET', `/rest/items/${FEEDER_ACTUATOR_ITEM}?metadata=expire`),
    request('GET', '/rest/links'),
    request('GET', '/rest/persistence/jdbc'),
    request(
      'GET',
      `/rest/persistence/items/${FEEDER_REQUEST_ITEM}?serviceId=jdbc&page=0&pageSize=1`,
      { allowMissing: true },
    ),
    request('GET', `/rest/rules/${FEEDER_RULE_UID}`),
  ]);
  const itemsByName = Object.fromEntries(itemNames.map((name, index) => [name, itemDtos[index]]));
  const ruleStatus = clone(rule.status ?? { status: 'UNKNOWN', statusDetail: 'NONE' });
  const namespaceOf = (dto, namespace) => {
    const entry = dto?.metadata?.[namespace];
    if (!entry) return null;
    return { value: entry.value, config: clone(entry.config ?? {}) };
  };
  return {
    runtimeInfo: clone(root.runtimeInfo),
    items: itemsByName,
    metadata: {
      [FEEDER_REQUEST_ITEM]: { autoupdate: namespaceOf(requestItemMeta, 'autoupdate') },
      [FEEDER_ACTUATOR_ITEM]: { expire: namespaceOf(actuatorItemMeta, 'expire') },
    },
    links: clone(links.filter(({ itemName }) => [
      FEEDER_REQUEST_ITEM,
      FEEDER_RESULT_ITEM,
      FEEDER_ACTUATOR_ITEM,
      FEEDER_COUNTER_ITEM,
    ].includes(itemName))),
    persistenceCoverage: normalizePersistenceCoverage(jdbc),
    requestHistoryCount: historyCount(history),
    rule: rulePutDto(rule),
    ruleStatus,
    ruleEnabled: !/DISABLED/i.test(`${ruleStatus.status} ${ruleStatus.statusDetail}`),
  };
}

function assertSnapshotPreconditions(live) {
  const reasons = [];
  if (live.runtimeInfo?.version !== SUPPORTED_OPENHAB_VERSION) reasons.push('unsupported OpenHAB runtime');
  if (live.items?.[FEEDER_ACTUATOR_ITEM]?.state !== 'OFF') reasons.push('feeder actuator must be OFF');
  if (live.items?.[FEEDER_COUNTER_ITEM]?.type !== 'Number') reasons.push('feeder counter is unavailable');
  if (live.rule?.uid !== FEEDER_RULE_UID || live.ruleStatus?.status !== 'IDLE') {
    reasons.push('legacy feeder owner must be IDLE');
  }
  if (
    metadataValue(live.metadata, FEEDER_ACTUATOR_ITEM, 'expire')
    !== '0h0m1s,command=OFF'
  ) reasons.push('feeder OFF backstop mismatch');
  if (live.items?.[FEEDER_REQUEST_ITEM] || live.items?.[FEEDER_RESULT_ITEM]) {
    reasons.push('correlated feeder resources already exist and require inventory resolution');
  }
  if (reasons.length > 0) throw new Error(reasons.join('; '));
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

async function readJson(path) {
  return JSON.parse(await readFile(path, 'utf8'));
}

async function desiredResources() {
  const root = new URL('../', import.meta.url);
  const [manifest, source] = await Promise.all([
    readFile(new URL('openhab/managed-resources.json', root), 'utf8').then(JSON.parse),
    readFile(new URL('openhab/rules/feeder-owner.js', root), 'utf8'),
  ]);
  return { manifest, source };
}

function cliOptions(argv) {
  const parsed = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (!value.startsWith('--')) {
      parsed._.push(value);
      continue;
    }
    const key = value.slice(2);
    if (index + 1 < argv.length && !argv[index + 1].startsWith('--')) {
      parsed[key] = argv[index + 1];
      index += 1;
    } else parsed[key] = true;
  }
  return parsed;
}

function activeReceiptPath(args) {
  if (args['from-active'] !== true) throw new Error('--from-active is required');
  return ACTIVE_RECEIPT;
}

function assertBoundPair(receipt, ingress) {
  assertFeederReceiptChecksum(receipt);
  assertIngressChecksum(ingress);
  if (ingress.phase !== 'quiescent') throw new Error('feeder ingress is not quiescent');
  if (
    ingress.openhabBinding?.generation !== receipt.generation
    || ingress.openhabBinding?.checksum !== receipt.snapshotChecksum
    || receipt.ingressBinding?.generation !== ingress.generation
    || receipt.ingressBinding?.checksum !== ingress.captureChecksum
  ) throw new Error('feeder ingress/OpenHAB receipt binding mismatch');
}

export function assertFeederTransactionPhase(command, phase) {
  const allowed = {
    verify: new Set(['snapshot', 'desired-disabled', 'desired', 'rolled-back-disabled', 'rolled-back']),
    apply: new Set(['snapshot', 'rolled-back-disabled']),
    rollback: new Set(['disabling', 'desired-disabled', 'desired', 'rolled-back-disabled']),
    'close:desired': new Set(['desired']),
    'close:unmutated': new Set(['snapshot']),
    'close:rolled-back': new Set(['rolled-back', 'rolled-back-disabled']),
  }[command];
  if (!allowed?.has(phase)) throw new Error(`cannot ${command} feeder from phase ${phase}`);
}

export function assertClosedReceiptRetry(receipt, terminal) {
  if (receipt?.state !== 'closed' || receipt?.phase !== 'closed') {
    throw new Error('close retry requires an already closed receipt');
  }
  if (receipt.terminal !== terminal) throw new Error('close retry terminal mismatch');
  const allowedVerificationPhases = {
    desired: new Set(['desired']),
    unmutated: new Set(['snapshot']),
    'rolled-back': new Set(['rolled-back', 'rolled-back-disabled']),
  }[terminal];
  if (
    !allowedVerificationPhases?.has(receipt.verification?.phase)
    || receipt.verification?.writeCount !== receipt.writeCount
  ) throw new Error('closed receipt verification mismatch');
}

async function assertBoundQuiescent(receipt, ingress, eventGuard) {
  eventGuard?.assertSafe();
  assertBoundPair(receipt, ingress);
  await verifyIngressQuiescent(ingress);
  eventGuard?.assertSafe();
}

async function verifyReceiptLiveState(receipt, live) {
  if (receipt.writeCount === 0 || receipt.phase.startsWith('rolled-back')) {
    if (JSON.stringify(stableLive(live)) !== JSON.stringify(stableLive(receipt.original))) {
      throw new Error('live feeder resources drifted from the captured snapshot');
    }
    return;
  }
  const { manifest, source } = await desiredResources();
  const verification = verifyFeederState(live, {
    requireDisabled: receipt.phase.endsWith('disabled'),
    expectedRule: buildFeederRuleDto(manifest, source, receipt.original.rule),
  });
  if (!verification.ok) throw new Error(verification.reasons.join('; '));
}

async function assertMutationGuards(request, receipt, ingressPath, counterState) {
  if (!ingressPath) throw new Error('--ingress-receipt is required for mutation');
  const ingress = await readJson(ingressPath);
  assertBoundPair(receipt, ingress);
  await verifyIngressQuiescent(ingress);
  const live = await liveFeederState(request);
  if (
    live.items[FEEDER_ACTUATOR_ITEM]?.state !== 'OFF'
    || live.items[FEEDER_COUNTER_ITEM]?.state !== counterState
  ) throw new Error('feeder actuator or counter drifted during mutation');
}

export async function executeGuardedOperations({
  request,
  receipt,
  operations,
  phase,
  eventGuard,
  assertSafe = async () => {},
  checkpoint = async () => {},
}) {
  let working = clone(receipt);
  for (const operation of operations) {
    eventGuard?.assertSafe();
    await assertSafe(working);
    eventGuard?.assertSafe();
    await request(operation.method, operation.path, {
      body: operation.body,
      allowMissing: operation.method === 'DELETE',
    });
    working.writeCount += 1;
    working.transitions.push({
      method: operation.method,
      path: operation.path,
      at: new Date().toISOString(),
    });
    working.phase = phase;
    working.updatedAt = new Date().toISOString();
    if (eventGuard) working.executionGuard = eventGuard.snapshot();
    working = withChecksum(working);
    await checkpoint(working);
    eventGuard?.assertSafe();
    await assertSafe(working);
    eventGuard?.assertSafe();
  }
  return working;
}

async function executeOperations(
  request,
  receiptPath,
  receipt,
  operations,
  phase,
  { ingressPath, counterState, eventGuard } = {},
) {
  return executeGuardedOperations({
    request,
    receipt,
    operations,
    phase,
    eventGuard,
    assertSafe: (working) => assertMutationGuards(
      request,
      working,
      ingressPath,
      counterState,
    ),
    checkpoint: (working) => durableAtomicWriteJson(receiptPath, working),
  });
}

function stableLive(value) {
  // Compare only intentionally-managed fields: a live system continuously
  // refreshes item state timestamps (lastStateUpdate/lastStateChange), so a
  // raw deep-compare of GET DTOs false-drifts on every binding poll.
  return canonicalValue({
    runtimeInfo: value.runtimeInfo,
    items: Object.fromEntries(Object.entries(value.items ?? {}).map(([name, dto]) => [
      name,
      dto ? { ...itemPutDto(dto), state: dto.state } : null,
    ])),
    metadata: value.metadata,
    links: value.links,
    persistenceCoverage: value.persistenceCoverage,
    requestHistoryCount: value.requestHistoryCount,
    rule: value.rule,
    ruleEnabled: value.ruleEnabled,
  });
}

async function waitForDisabledSafety(request, counterState) {
  await new Promise((resolve) => setTimeout(resolve, 2200));
  const current = await liveFeederState(request);
  if (
    current.items[FEEDER_ACTUATOR_ITEM]?.state !== 'OFF'
    || current.items[FEEDER_COUNTER_ITEM]?.state !== counterState
    || current.ruleEnabled !== false
  ) throw new Error('disabled feeder precondition drifted');
  return current;
}

async function runSnapshot(args, request) {
  if (args.subset !== 'feeder') throw new Error('--subset feeder is required');
  if (args['activate-backup'] !== true) throw new Error('--activate-backup is required');
  if (!args['ingress-receipt']) throw new Error('--ingress-receipt is required');
  if (await pathExists(ACTIVE_RECEIPT)) throw new Error('an active feeder OpenHAB receipt already exists');
  const ingress = await readJson(args['ingress-receipt']);
  assertIngressChecksum(ingress);
  if (ingress.phase !== 'quiescent' || ingress.openhabBinding) {
    throw new Error('unbound quiescent ingress receipt is required');
  }
  const live = await liveFeederState(request);
  assertSnapshotPreconditions(live);
  const generation = `feeder-${new Date().toISOString().replace(/[-:.]/g, '')}`;
  const backupPath = join(args['out-root'] || '/tmp', 'earthship-ui-openhab-backups', generation, 'feeder.json');
  const receipt = buildFeederReceipt({
    generation,
    live,
    ingressGeneration: ingress.generation,
  });
  receipt.backupPath = backupPath;
  const checksummed = withChecksum(receipt);
  await durableAtomicWriteJson(backupPath, checksummed);
  await durableAtomicWriteJson(ACTIVE_RECEIPT, checksummed);
  return checksummed;
}

async function runVerify(args, request, eventGuard) {
  if (args.subset !== 'feeder' || args['read-only'] !== true) {
    throw new Error('verify requires --subset feeder --read-only');
  }
  const receiptPath = activeReceiptPath(args);
  const receipt = await readJson(receiptPath);
  if (!args['ingress-receipt']) throw new Error('--ingress-receipt is required for verify');
  const ingress = await readJson(args['ingress-receipt']);
  assertFeederTransactionPhase('verify', receipt.phase);
  await assertBoundQuiescent(receipt, ingress, eventGuard);
  const live = await liveFeederState(request);
  await verifyReceiptLiveState(receipt, live);
  eventGuard?.assertSafe();
  const verified = withChecksum({
    ...receipt,
    verification: {
      phase: receipt.phase,
      writeCount: receipt.writeCount,
      at: new Date().toISOString(),
      liveChecksum: createHash('sha256')
        .update(JSON.stringify(stableLive(live)))
        .digest('hex'),
      executionGuard: eventGuard?.snapshot() ?? null,
    },
    updatedAt: new Date().toISOString(),
  });
  await durableAtomicWriteJson(receiptPath, verified);
  return verified;
}

async function runApply(args, request, eventGuard) {
  if (args.subset !== 'feeder' || args.mode !== 'maintenance') {
    throw new Error('apply requires --subset feeder --mode maintenance');
  }
  const receiptPath = activeReceiptPath(args);
  const receipt = await readJson(receiptPath);
  const ingress = await readJson(args['ingress-receipt']);
  assertBoundPair(receipt, ingress);
  assertFeederTransactionPhase('apply', receipt.phase);
  const before = await liveFeederState(request);
  assertSnapshotPreconditions(before);
  const { manifest, source } = await desiredResources();
  const plan = buildFeederApplyPlan({ manifest, source, original: receipt.original });
  const guards = {
    ingressPath: args['ingress-receipt'],
    counterState: before.items[FEEDER_COUNTER_ITEM].state,
    eventGuard,
  };
  let working = await executeOperations(
    request,
    receiptPath,
    receipt,
    [plan[0]],
    'disabling',
    guards,
  );
  await waitForDisabledSafety(request, before.items[FEEDER_COUNTER_ITEM].state);
  working = await executeOperations(
    request,
    receiptPath,
    working,
    plan.slice(1),
    'desired-disabled',
    guards,
  );
  const desired = await liveFeederState(request);
  const verified = verifyFeederState(desired, {
    requireDisabled: true,
    expectedRule: buildFeederRuleDto(manifest, source, receipt.original.rule),
  });
  if (!verified.ok) throw new Error(verified.reasons.join('; '));
  return working;
}

async function runRollback(args, request, eventGuard, { rehearsal = false } = {}) {
  if (args.subset !== 'feeder' || args.mode !== 'maintenance') {
    throw new Error('rollback requires --subset feeder --mode maintenance');
  }
  const receiptPath = activeReceiptPath(args);
  const receipt = await readJson(receiptPath);
  const ingress = await readJson(args['ingress-receipt']);
  assertBoundPair(receipt, ingress);
  assertFeederTransactionPhase('rollback', receipt.phase);
  await assertBoundQuiescent(receipt, ingress, eventGuard);
  const current = await liveFeederState(request);
  if (current.items[FEEDER_ACTUATOR_ITEM]?.state !== 'OFF') throw new Error('feeder actuator must be OFF');
  const plan = buildFeederRollbackPlan(receipt.original);
  const guards = {
    ingressPath: args['ingress-receipt'],
    counterState: receipt.original.items[FEEDER_COUNTER_ITEM].state,
    eventGuard,
  };
  let working = await executeOperations(
    request,
    receiptPath,
    receipt,
    plan,
    'rolled-back-disabled',
    guards,
  );
  if (!rehearsal && receipt.original.ruleEnabled !== false) {
    working = await executeOperations(request, receiptPath, working, [{
      method: 'POST',
      path: `/rest/rules/${FEEDER_RULE_UID}/enable`,
      body: 'true',
    }], 'rolled-back', guards);
  }
  return working;
}

async function runRehearse(args, request, eventGuard) {
  if (args.subset !== 'feeder' || args.mode !== 'maintenance') {
    throw new Error('rehearse requires --subset feeder --mode maintenance');
  }
  const rolledBack = await runRollback(args, request, eventGuard, { rehearsal: true });
  const receiptPath = activeReceiptPath(args);
  const { manifest, source } = await desiredResources();
  const plan = buildFeederApplyPlan({ manifest, source, original: rolledBack.original });
  const guards = {
    ingressPath: args['ingress-receipt'],
    counterState: rolledBack.original.items[FEEDER_COUNTER_ITEM].state,
    eventGuard,
  };
  let working = await executeOperations(
    request,
    receiptPath,
    rolledBack,
    plan,
    'desired-disabled',
    guards,
  );
  const disabled = await liveFeederState(request);
  const expectedRule = buildFeederRuleDto(manifest, source, rolledBack.original.rule);
  const disabledVerification = verifyFeederState(disabled, {
    requireDisabled: true,
    expectedRule,
  });
  if (!disabledVerification.ok) throw new Error(disabledVerification.reasons.join('; '));
  if (rolledBack.original.ruleEnabled !== false) {
    working = await executeOperations(request, receiptPath, working, [{
      method: 'POST',
      path: `/rest/rules/${FEEDER_RULE_UID}/enable`,
      body: 'true',
    }], 'desired', guards);
  }
  await new Promise((resolve) => setTimeout(resolve, 500));
  const final = await liveFeederState(request);
  const verification = verifyFeederState(final, { expectedRule });
  if (!verification.ok) throw new Error(verification.reasons.join('; '));
  return working;
}

async function runClose(args, request, eventGuard) {
  if (args.subset !== 'feeder' || !args.terminal) {
    throw new Error('close-backup requires --subset feeder --terminal');
  }
  const receiptPath = activeReceiptPath(args);
  const receipt = await readJson(receiptPath);
  const ingress = await readJson(args['ingress-receipt']);
  if (receipt.state === 'closed') {
    assertFeederReceiptChecksum(receipt);
    assertClosedReceiptRetry(receipt, args.terminal);
    await assertBoundQuiescent(receipt, ingress, eventGuard);
    await durableAtomicWriteJson(receipt.backupPath, receipt);
    return receipt;
  }
  assertFeederTransactionPhase(`close:${args.terminal}`, receipt.phase);
  await assertBoundQuiescent(receipt, ingress, eventGuard);
  if (
    receipt.verification?.phase !== receipt.phase
    || receipt.verification?.writeCount !== receipt.writeCount
  ) throw new Error('current feeder receipt phase has not passed final read-only verification');
  const live = await liveFeederState(request);
  await verifyReceiptLiveState(receipt, live);
  eventGuard?.assertSafe();
  const closed = withChecksum({
    ...receipt,
    verification: {
      phase: receipt.phase,
      writeCount: receipt.writeCount,
      at: new Date().toISOString(),
      liveChecksum: createHash('sha256')
        .update(JSON.stringify(stableLive(live)))
        .digest('hex'),
      executionGuard: eventGuard?.snapshot() ?? null,
    },
    state: 'closed',
    phase: 'closed',
    terminal: args.terminal,
    updatedAt: new Date().toISOString(),
  });
  await durableAtomicWriteJson(receipt.backupPath, closed);
  await durableAtomicWriteJson(receiptPath, closed);
  return closed;
}

async function runCli(command, args) {
  const auth = await loadAuth();
  const request = createRestClient(auth);
  const monitored = new Set(['verify', 'apply', 'rollback', 'rehearse', 'close-backup']);
  const monitor = monitored.has(command) ? await startFeederEventMonitor(auth) : null;
  try {
    if (command === 'snapshot') return runSnapshot(args, request);
    if (command === 'verify') return runVerify(args, request, monitor.guard);
    if (command === 'apply') return runApply(args, request, monitor.guard);
    if (command === 'rollback') return runRollback(args, request, monitor.guard);
    if (command === 'rehearse') return runRehearse(args, request, monitor.guard);
    if (command === 'close-backup') return runClose(args, request, monitor.guard);
    throw new Error(`unknown command: ${command}`);
  } finally {
    if (monitor) await monitor.close();
  }
}

function usage() {
  return [
    'Usage: node scripts/openhab-config.mjs <command> --subset feeder [options]',
    'Commands: snapshot, verify, apply, rehearse, rollback, close-backup',
    'Mutation commands require an exact checksum-bound ingress receipt.',
  ].join('\n');
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  const command = process.argv[2];
  if (!command || ['-h', '--help', 'help'].includes(command)) {
    console.log(usage());
  } else {
    runCli(command, cliOptions(process.argv.slice(3)))
      .then((receipt) => console.log(JSON.stringify({
        ok: true,
        command,
        generation: receipt.generation,
        phase: receipt.phase,
        writes: receipt.writeCount,
      })))
      .catch((error) => {
        console.error(`openhab-config: ${error.message}`);
        process.exitCode = 1;
      });
  }
}
