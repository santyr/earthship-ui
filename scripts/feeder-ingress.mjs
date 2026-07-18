#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { execFile as execFileCallback } from 'node:child_process';
import { mkdir, open, readFile, readdir, readlink, rename, stat } from 'node:fs/promises';
import { basename, dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { promisify } from 'node:util';

const execFile = promisify(execFileCallback);
const OPENHAB_PORT = 8080;
const KNOWN_LISTENER_PORTS = new Set([3002, 8090]);
const KNOWN_FEEDER_SCRIPT_PATHS = Object.freeze([
  '/home/sat/bin/middleware/main.py',
  '/home/sat/bin/fastapi_ap.py',
]);
const KNOWN_FEEDER_SCRIPT_NAMES = new Set(
  KNOWN_FEEDER_SCRIPT_PATHS.map((path) => basename(path)),
);
const KNOWN_FEEDER_EXECUTABLES = new Set(['lightning_goats']);
const EXEMPT_OPENHAB_CONNECTION_PATHS = Object.freeze([
  '/home/sat/earthship-ui/node_modules/.bin/vite',
]);
const READINESS_URLS = Object.freeze({
  'lnbits.service': 'http://127.0.0.1:3002/',
  'lightning_goats.service': 'http://127.0.0.1:8090/health',
});

export const KNOWN_FEEDER_UNITS = Object.freeze([
  'lnbits.service',
  'lightning_goats.service',
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

export function receiptChecksum(value) {
  return createHash('sha256')
    .update(JSON.stringify(canonicalValue(value)))
    .digest('hex');
}

export function withReceiptChecksum(value) {
  const next = clone(value);
  delete next.checksum;
  next.checksum = receiptChecksum(next);
  return next;
}

export function assertReceiptChecksum(receipt) {
  if (!receipt || typeof receipt !== 'object') throw new Error('receipt is required');
  if (!/^[a-f0-9]{64}$/.test(receipt.checksum ?? '')) {
    throw new Error('receipt checksum is missing');
  }
  if (receiptChecksum(receipt) !== receipt.checksum) {
    throw new Error('receipt checksum mismatch');
  }
}

function captureChecksum(receipt) {
  return createHash('sha256').update(JSON.stringify(canonicalValue({
    schema: receipt.schema,
    generation: receipt.generation,
    createdAt: receipt.createdAt,
    units: receipt.units,
    dependencyOrder: receipt.dependencyOrder,
    unknownProcesses: receipt.unknownProcesses,
    exemptProcesses: receipt.exemptProcesses,
  }))).digest('hex');
}

function unitMap(units) {
  const map = new Map();
  for (const unit of units ?? []) {
    if (!unit?.id) throw new Error('captured unit ID is required');
    if (map.has(unit.id)) throw new Error(`duplicate captured unit: ${unit.id}`);
    if (!KNOWN_FEEDER_UNITS.includes(unit.id)) throw new Error(`unknown feeder unit: ${unit.id}`);
    map.set(unit.id, unit);
  }
  return map;
}

export function topologicalOrder(units) {
  const map = unitMap(units);
  const visiting = new Set();
  const visited = new Set();
  const order = [];

  function visit(id) {
    if (visited.has(id)) return;
    if (visiting.has(id)) throw new Error(`dependency cycle includes ${id}`);
    const unit = map.get(id);
    if (!unit) throw new Error(`missing captured dependency: ${id}`);
    visiting.add(id);
    for (const dependency of unit.dependsOn ?? []) {
      if (!map.has(dependency)) throw new Error(`missing captured dependency: ${dependency}`);
      visit(dependency);
    }
    visiting.delete(id);
    visited.add(id);
    order.push(id);
  }

  for (const id of map.keys()) visit(id);
  return order;
}

function validateUnit(unit) {
  if (!['system', 'user', 'absent'].includes(unit.scope)) {
    throw new Error(`ambiguous unit scope: ${unit.id}`);
  }
  if (unit.exists !== true && unit.exists !== false) {
    throw new Error(`known unit existence was not captured: ${unit.id}`);
  }
  if (!unit.exists && unit.scope !== 'absent') throw new Error(`absent unit scope mismatch: ${unit.id}`);
  if (unit.exists && unit.scope === 'absent') throw new Error(`loaded unit scope mismatch: ${unit.id}`);
  if (!['active', 'inactive'].includes(unit.activeState)) {
    throw new Error(`ambiguous ActiveState for ${unit.id}`);
  }
  if (!Number.isInteger(unit.mainPid) || unit.mainPid < 0) {
    throw new Error(`invalid MainPID for ${unit.id}`);
  }
  if (!/^[a-f0-9]{64}$/.test(unit.commandHash ?? '')) {
    throw new Error(`invalid command hash for ${unit.id}`);
  }
  if (!Array.isArray(unit.listeners) || !unit.listeners.every(Number.isInteger)) {
    throw new Error(`invalid listener capture for ${unit.id}`);
  }
  if (!Number.isInteger(unit.openhabConnections) || unit.openhabConnections < 0) {
    throw new Error(`invalid OpenHAB connection capture for ${unit.id}`);
  }
  if (
    unit.pids !== undefined
    && (!Array.isArray(unit.pids) || !unit.pids.every((pid) => Number.isInteger(pid) && pid > 0))
  ) throw new Error(`invalid cgroup PID capture for ${unit.id}`);
  if (
    unit.processes !== undefined
    && (!Array.isArray(unit.processes) || !unit.processes.every((process) => (
      Number.isInteger(process.pid)
      && process.pid > 0
      && Number.isInteger(process.startTicks)
      && process.startTicks > 0
      && /^[a-f0-9]{64}$/.test(process.commandHash ?? '')
    )))
  ) throw new Error(`invalid process identity capture for ${unit.id}`);
  if (unit.readinessUrl !== undefined && unit.readinessUrl !== READINESS_URLS[unit.id]) {
    throw new Error(`invalid readiness endpoint for ${unit.id}`);
  }
}

function validateExemptProcess(process) {
  if (!Number.isInteger(process?.pid) || process.pid <= 0) {
    throw new Error('invalid exempt process PID');
  }
  if (!Number.isInteger(process.startTicks) || process.startTicks <= 0) {
    throw new Error(`invalid exempt process start time for PID ${process.pid}`);
  }
  if (!/^[a-f0-9]{64}$/.test(process.commandHash ?? '')) {
    throw new Error(`invalid exempt process command hash for PID ${process.pid}`);
  }
  if (process.reason !== 'earthship-ui-vite-proxy') {
    throw new Error(`invalid exempt process reason for PID ${process.pid}`);
  }
}

export function buildIngressReceipt({
  generation,
  units,
  unknownProcesses = [],
  exemptProcesses = [],
  createdAt = new Date().toISOString(),
} = {}) {
  if (typeof generation !== 'string' || !generation) throw new Error('ingress generation is required');
  if (!Array.isArray(unknownProcesses)) throw new Error('unknown process inventory is required');
  if (unknownProcesses.length > 0) throw new Error('unmapped feeder caller is present');
  if (!Array.isArray(exemptProcesses)) throw new Error('exempt process inventory is required');
  for (const process of exemptProcesses) validateExemptProcess(process);
  if (new Set(exemptProcesses.map(({ pid }) => pid)).size !== exemptProcesses.length) {
    throw new Error('duplicate exempt process PID');
  }
  const map = unitMap(units);
  if (map.size === 0) throw new Error('no known feeder units were captured');
  for (const unit of map.values()) validateUnit(unit);
  const dependencyOrder = topologicalOrder([...map.values()]);
  const receipt = {
    schema: 'earthship-ui-feeder-ingress-receipt/v1',
    state: 'open',
    phase: 'captured',
    generation,
    createdAt,
    updatedAt: createdAt,
    units: clone([...map.values()]),
    dependencyOrder,
    unknownProcesses: [],
    exemptProcesses: clone(exemptProcesses),
    transitions: [],
    openhabBinding: null,
    openhabTerminal: null,
  };
  receipt.captureChecksum = captureChecksum(receipt);
  return withReceiptChecksum(receipt);
}

function validatedIngress(receipt) {
  assertReceiptChecksum(receipt);
  if (receipt.schema !== 'earthship-ui-feeder-ingress-receipt/v1') {
    throw new Error('unexpected ingress receipt schema');
  }
  if (receipt.state !== 'open') throw new Error('ingress receipt is not open');
  if (
    receipt.openhabTerminal !== null
    && !['absent', 'desired', 'rolled-back', 'unmutated'].includes(receipt.openhabTerminal)
  ) throw new Error('invalid authorized OpenHAB terminal');
  if (captureChecksum(receipt) !== receipt.captureChecksum) {
    throw new Error('ingress immutable capture checksum mismatch');
  }
  if (!Array.isArray(receipt.unknownProcesses) || receipt.unknownProcesses.length > 0) {
    throw new Error('ingress receipt contains an unmapped feeder caller');
  }
  if (!Array.isArray(receipt.exemptProcesses)) {
    throw new Error('ingress receipt lacks exempt process inventory');
  }
  for (const process of receipt.exemptProcesses) validateExemptProcess(process);
  if (new Set(receipt.exemptProcesses.map(({ pid }) => pid)).size !== receipt.exemptProcesses.length) {
    throw new Error('ingress receipt contains duplicate exempt process PIDs');
  }
  const order = topologicalOrder(receipt.units);
  if (JSON.stringify(order) !== JSON.stringify(receipt.dependencyOrder)) {
    throw new Error('ingress dependency order mismatch');
  }
  return clone(receipt);
}

function activeAtCapture(unit) {
  return unit.exists && unit.activeState === 'active';
}

async function checkpoint(working, onTransition) {
  working.updatedAt = new Date().toISOString();
  const checksummed = withReceiptChecksum(working);
  Object.assign(working, checksummed);
  await onTransition(checksummed);
}

async function compensateStopped(working, adapter, stoppedIds, onTransition) {
  const map = unitMap(working.units);
  for (const id of working.dependencyOrder) {
    if (!stoppedIds.has(id)) continue;
    const unit = map.get(id);
    working.transitions.push({ action: 'compensating-start-pending', unit: id });
    await checkpoint(working, onTransition);
    await adapter.start(unit);
    working.transitions.push({ action: 'compensating-start', unit: id });
    await checkpoint(working, onTransition);
    await adapter.verifyReady(unit);
    working.transitions.push({ action: 'compensating-ready', unit: id });
    await checkpoint(working, onTransition);
  }
}

export async function quiesceServices(receipt, adapter, {
  allowStopKnownServices = false,
  onTransition = async () => {},
  shouldStop = (unit) => activeAtCapture(unit),
  compensateOnFailure = true,
} = {}) {
  const working = validatedIngress(receipt);
  if (!allowStopKnownServices) throw new Error('quiesce requires --allow-stop-known-services');
  if (working.openhabBinding) throw new Error('bound receipt requires re-quiesce recovery');
  if (working.phase === 'quiescent') return working;
  if (working.phase !== 'captured') throw new Error(`cannot quiesce phase ${working.phase}`);

  const map = unitMap(working.units);
  const stoppedIds = new Set();
  try {
    for (const id of [...working.dependencyOrder].reverse()) {
      const unit = map.get(id);
      if (!await shouldStop(unit)) continue;
      stoppedIds.add(id);
      working.transitions.push({ action: 'stop-pending', unit: id });
      await checkpoint(working, onTransition);
      await adapter.stop(unit);
      working.transitions.push({ action: 'stop', unit: id });
      await checkpoint(working, onTransition);
      await adapter.verifyQuiescent(unit);
      working.transitions.push({ action: 'verify-quiescent', unit: id });
      await checkpoint(working, onTransition);
    }
    if (typeof adapter.verifyAllQuiescent === 'function') {
      await adapter.verifyAllQuiescent(working);
    }
  } catch (error) {
    if (!compensateOnFailure) throw error;
    try {
      await compensateStopped(working, adapter, stoppedIds, onTransition);
    } catch (restoreError) {
      throw new Error(
        `quiesce failed (${error.message}); compensating restore failed (${restoreError.message})`,
      );
    }
    throw new Error(`quiesce failed (${error.message}); compensating restore completed`);
  }
  working.phase = 'quiescent';
  await checkpoint(working, onTransition);
  return working;
}

export async function restoreServices(receipt, adapter, { onTransition = async () => {} } = {}) {
  const working = validatedIngress(receipt);
  const map = unitMap(working.units);
  for (const id of working.dependencyOrder) {
    const unit = map.get(id);
    if (!activeAtCapture(unit)) {
      await adapter.verifyInactive(unit);
      working.transitions.push({ action: 'verify-captured-inactive', unit: id });
      await checkpoint(working, onTransition);
      continue;
    }
    for (const dependency of unit.dependsOn ?? []) {
      const dependencyUnit = map.get(dependency);
      if (activeAtCapture(dependencyUnit)) await adapter.verifyReady(dependencyUnit);
    }
    working.transitions.push({ action: 'start-pending', unit: id });
    await checkpoint(working, onTransition);
    await adapter.start(unit);
    working.transitions.push({ action: 'start', unit: id });
    await checkpoint(working, onTransition);
    await adapter.verifyReady(unit);
    working.transitions.push({ action: 'verify-ready', unit: id });
    await checkpoint(working, onTransition);
  }
  working.phase = 'restored';
  await checkpoint(working, onTransition);
  return working;
}

export function bindOpenhabReceipt(ingressReceipt, openhabReceipt) {
  const working = validatedIngress(ingressReceipt);
  assertReceiptChecksum(openhabReceipt);
  const bindingStateAllowed = openhabReceipt.state === 'open'
    || (working.openhabBinding && openhabReceipt.state === 'closed');
  if (
    openhabReceipt.schema !== 'earthship-ui-openhab-feeder-receipt/v1'
    || openhabReceipt.subset !== 'feeder'
    || !bindingStateAllowed
    || openhabReceipt.ingressGeneration !== working.generation
    || openhabReceipt.ingressBinding?.generation !== working.generation
    || openhabReceipt.ingressBinding?.checksum !== working.captureChecksum
  ) throw new Error('OpenHAB feeder receipt binding mismatch');

  const binding = {
    generation: openhabReceipt.generation,
    checksum: openhabReceipt.snapshotChecksum ?? openhabReceipt.checksum,
  };
  if (working.openhabBinding) {
    if (JSON.stringify(working.openhabBinding) !== JSON.stringify(binding)) {
      throw new Error('ingress receipt is bound to a different OpenHAB receipt');
    }
    return working;
  }
  working.openhabBinding = binding;
  working.updatedAt = new Date().toISOString();
  return withReceiptChecksum(working);
}

export function assertRestoreReceiptPair(ingressReceipt, openhabReceipt) {
  const working = validatedIngress(ingressReceipt);
  assertReceiptChecksum(openhabReceipt);
  if (working.phase !== 'quiescent') {
    throw new Error('caller restoration requires quiescent ingress');
  }
  if (openhabReceipt.state !== 'closed' || openhabReceipt.phase !== 'closed') {
    throw new Error('caller restoration requires a closed OpenHAB receipt');
  }
  if (!new Set(['desired', 'rolled-back', 'unmutated']).has(openhabReceipt.terminal)) {
    throw new Error('caller restoration requires an allowed OpenHAB terminal');
  }
  if (!/^[a-f0-9]{64}$/.test(openhabReceipt.snapshotChecksum ?? '')) {
    throw new Error('caller restoration requires an immutable OpenHAB snapshot checksum');
  }
  return bindOpenhabReceipt(working, openhabReceipt);
}

export function assertIngressCloseTerminal(receipt, terminal) {
  if (receipt?.state !== 'open') throw new Error('ingress close requires an open receipt');
  if (receipt.phase !== 'restored') throw new Error('ingress close requires restored phase');
  const allowedOpenhabTerminals = {
    restored: new Set(['desired', 'rolled-back']),
    'restored-unmutated': new Set(['unmutated']),
    'restored-no-openhab': new Set(['absent']),
  }[terminal];
  if (!allowedOpenhabTerminals?.has(receipt.openhabTerminal)) {
    throw new Error('ingress close terminal does not match the authorized OpenHAB terminal');
  }
}

function parseProperties(text) {
  return Object.fromEntries(String(text).split(/\r?\n/).filter(Boolean).map((line) => {
    const index = line.indexOf('=');
    return index < 0 ? [line, ''] : [line.slice(0, index), line.slice(index + 1)];
  }));
}

async function systemctl(scope, ...args) {
  const prefix = scope === 'user' ? ['--user'] : [];
  return execFile('systemctl', [...prefix, ...args], { timeout: 20_000, maxBuffer: 1024 * 1024 });
}

async function probeScope(id, scope) {
  let output;
  try {
    output = await systemctl(
      scope,
      'show',
      id,
      '--no-pager',
      '--property=LoadState,UnitFileState,ActiveState,SubState,MainPID,ExecStart,ControlGroup',
    );
  } catch (error) {
    if (/not found|could not be found|no medium found/i.test(`${error.stderr ?? ''} ${error.message}`)) {
      return null;
    }
    throw error;
  }
  const values = parseProperties(output.stdout);
  if (!values.LoadState || values.LoadState === 'not-found') return null;
  return {
    id,
    scope,
    exists: true,
    enabled: values.UnitFileState || 'unknown',
    activeState: values.ActiveState,
    subState: values.SubState,
    mainPid: Number(values.MainPID || 0),
    commandHash: createHash('sha256').update(values.ExecStart || '').digest('hex'),
    controlGroup: values.ControlGroup || '',
  };
}

async function processArgv(pid) {
  try {
    return (await readFile(`/proc/${pid}/cmdline`))
      .toString('utf8')
      .split('\0')
      .filter(Boolean);
  } catch (error) {
    if (error?.code === 'ENOENT') return [];
    throw error;
  }
}

async function processCwd(pid) {
  try {
    return await readlink(`/proc/${pid}/cwd`);
  } catch (error) {
    if (['ENOENT', 'EACCES', 'EPERM'].includes(error?.code)) return null;
    throw error;
  }
}

function resolvedArgv(argv, cwd) {
  return argv.map((arg) => (arg.startsWith('/') ? resolve(arg) : cwd ? resolve(cwd, arg) : null));
}

export function isKnownFeederCaller(argv, cwd) {
  const canonicalArgs = new Set(resolvedArgv(argv, cwd).filter(Boolean));
  return KNOWN_FEEDER_SCRIPT_PATHS.some((path) => canonicalArgs.has(path))
    || (cwd === null && argv.some((arg) => KNOWN_FEEDER_SCRIPT_NAMES.has(basename(arg))))
    || argv.some((arg) => KNOWN_FEEDER_EXECUTABLES.has(basename(arg)));
}

async function processStartTicks(pid) {
  try {
    const stat = await readFile(`/proc/${pid}/stat`, 'utf8');
    const closingParen = stat.lastIndexOf(')');
    if (closingParen < 0) return null;
    const fieldsAfterCommand = stat.slice(closingParen + 2).trim().split(/\s+/);
    const startTicks = Number(fieldsAfterCommand[19]);
    return Number.isInteger(startTicks) && startTicks > 0 ? startTicks : null;
  } catch (error) {
    if (error?.code === 'ENOENT') return null;
    throw error;
  }
}

async function processIdentity(pid) {
  const startBefore = await processStartTicks(pid);
  const cwdBefore = await processCwd(pid);
  const argv = await processArgv(pid);
  const cwdAfter = await processCwd(pid);
  const startAfter = await processStartTicks(pid);
  const stable = startBefore === startAfter && cwdBefore === cwdAfter;
  const cwd = stable ? cwdAfter : null;
  return {
    pid,
    startTicks: stable ? startAfter : null,
    commandHash: createHash('sha256').update(JSON.stringify({ argv, cwd })).digest('hex'),
    isKnownFeederCaller: stable && isKnownFeederCaller(argv, cwd),
    exemptReason: stable && EXEMPT_OPENHAB_CONNECTION_PATHS.some((path) => (
      resolvedArgv(argv, cwd).includes(path)
    ))
      ? 'earthship-ui-vite-proxy'
      : null,
  };
}

async function cgroupPids(unit) {
  if (!unit.exists || !unit.controlGroup) return unit.mainPid > 0 ? [unit.mainPid] : [];
  try {
    const raw = await readFile(`/sys/fs/cgroup${unit.controlGroup}/cgroup.procs`, 'utf8');
    return [...new Set(raw.split(/\s+/).filter(Boolean).map(Number).filter((pid) => pid > 0))];
  } catch (error) {
    if (error?.code === 'ENOENT') return unit.mainPid > 0 ? [unit.mainPid] : [];
    throw error;
  }
}

function socketPids(line) {
  return [...String(line).matchAll(/pid=(\d+)/g)].map((match) => Number(match[1]));
}

function remotePort(line) {
  const endpoints = String(line).trim().split(/\s+/).filter((field) => /:\d+$/.test(field));
  const peer = endpoints.at(-1) ?? '';
  const match = /:(\d+)$/.exec(peer);
  return match ? Number(match[1]) : null;
}

function localPort(line) {
  const local = String(line).trim().split(/\s+/).find((field) => /:\d+$/.test(field)) ?? '';
  const match = /:(\d+)$/.exec(local);
  return match ? Number(match[1]) : null;
}

function socketOwners(line) {
  const pids = socketPids(line);
  return pids.length > 0 ? pids : [null];
}

export function socketInventoryFromText(listeners, connections) {
  return {
    listeners: String(listeners).split(/\r?\n/).filter(Boolean).flatMap((line) => (
      socketOwners(line).map((pid) => ({ pid, port: localPort(line), line }))
    )),
    connections: String(connections).split(/\r?\n/).filter(Boolean).flatMap((line) => (
      socketOwners(line).map((pid) => ({ pid, remotePort: remotePort(line), line }))
    )),
  };
}

async function scanSockets() {
  const [{ stdout: listeners }, { stdout: connections }] = await Promise.all([
    execFile('ss', ['-H', '-ltnp'], { timeout: 10_000, maxBuffer: 4 * 1024 * 1024 }),
    execFile('ss', ['-H', '-tnp', 'state', 'established'], {
      timeout: 10_000,
      maxBuffer: 4 * 1024 * 1024,
    }),
  ]);
  return socketInventoryFromText(listeners, connections);
}

async function scanProcessIdentities() {
  const entries = await readdir('/proc', { withFileTypes: true });
  return (await Promise.all(entries
    .filter((entry) => entry.isDirectory() && /^\d+$/.test(entry.name))
    .map((entry) => processIdentity(Number(entry.name)))))
    .filter(({ startTicks }) => startTicks !== null);
}

export function classifyIngressObservation({ units, sockets, processes }) {
  const knownPids = new Set(units.flatMap(({ pids = [] }) => pids));
  const identities = new Map(processes.map((process) => [process.pid, process]));
  const unknownProcesses = [];
  const exemptProcesses = [];
  const unknownKeys = new Set();
  const exemptPids = new Set();
  const addUnknown = (pid, reason) => {
    const key = `${pid ?? 'ownerless'}:${reason}`;
    if (unknownKeys.has(key)) return;
    unknownKeys.add(key);
    unknownProcesses.push({ pid, reason });
  };

  for (const { pid, port } of sockets.listeners.filter(({ port }) => (
    KNOWN_LISTENER_PORTS.has(port)
  ))) {
    if (pid === null) addUnknown(null, `ownerless relevant listener on ${port}`);
    else if (!knownPids.has(pid)) addUnknown(pid, `unmapped listener on ${port}`);
  }

  for (const { pid } of sockets.connections.filter(({ remotePort: port }) => (
    port === OPENHAB_PORT
  ))) {
    if (pid === null) {
      addUnknown(null, `ownerless OpenHAB connection on ${OPENHAB_PORT}`);
      continue;
    }
    if (knownPids.has(pid)) continue;
    const identity = identities.get(pid);
    if (
      identity?.exemptReason === 'earthship-ui-vite-proxy'
      && !identity.isKnownFeederCaller
      && identity.startTicks !== null
    ) {
      if (!exemptPids.has(pid)) {
        exemptPids.add(pid);
        exemptProcesses.push({
          pid,
          startTicks: identity.startTicks,
          commandHash: identity.commandHash,
          reason: identity.exemptReason,
        });
      }
    } else {
      addUnknown(pid, identity?.isKnownFeederCaller
        ? 'unmapped known feeder caller'
        : `unmapped OpenHAB connection on ${OPENHAB_PORT}`);
    }
  }

  for (const identity of processes) {
    if (identity.isKnownFeederCaller && !knownPids.has(identity.pid)) {
      addUnknown(identity.pid, 'unmapped known feeder caller');
    }
  }
  return { unknownProcesses, exemptProcesses };
}

function processCommandHashes(processes = []) {
  return processes.map(({ commandHash }) => commandHash).sort();
}

export function restoredUnitMatchesCapture(captured, current) {
  return current.activeState === captured.activeState
    && current.subState === captured.subState
    && current.enabled === captured.enabled
    && current.mainPid > 0
    && current.commandHash === captured.commandHash
    && captured.listeners.every((port) => current.listeners.includes(port))
    && (captured.openhabConnections === 0 || current.openhabConnections > 0)
    && (!Array.isArray(captured.processes) || (
      current.processes.every(({ startTicks }) => Number.isInteger(startTicks) && startTicks > 0)
      && JSON.stringify(processCommandHashes(current.processes))
        === JSON.stringify(processCommandHashes(captured.processes))
    ));
}

export async function captureKnownIngress({
  generation = `ingress-${new Date().toISOString().replace(/[-:.]/g, '')}`,
  createdAt = new Date().toISOString(),
} = {}) {
  const units = [];
  for (const id of KNOWN_FEEDER_UNITS) {
    const candidates = (await Promise.all([
      probeScope(id, 'system'),
      probeScope(id, 'user'),
    ])).filter(Boolean);
    if (candidates.length > 1) throw new Error(`ambiguous unit scope for ${id}`);
    units.push(candidates[0] ?? {
      id,
      scope: 'absent',
      exists: false,
      enabled: 'not-found',
      activeState: 'inactive',
      subState: 'dead',
      mainPid: 0,
      commandHash: createHash('sha256').update('').digest('hex'),
      controlGroup: '',
    });
  }

  const byId = new Map(units.map((unit) => [unit.id, unit]));
  byId.get('lightning_goats.service').dependsOn = ['lnbits.service'];
  byId.get('lnbits.service').dependsOn = [];
  const sockets = await scanSockets();
  for (const unit of units) {
    unit.pids = await cgroupPids(unit);
    unit.listeners = sockets.listeners
      .filter(({ pid, port }) => unit.pids.includes(pid) && KNOWN_LISTENER_PORTS.has(port))
      .map(({ port }) => port);
    unit.openhabConnections = sockets.connections.filter(({ pid, remotePort: port }) => (
      unit.pids.includes(pid) && port === OPENHAB_PORT
    )).length;
  }
  const processes = await scanProcessIdentities();
  const identities = new Map(processes.map((process) => [process.pid, process]));
  for (const unit of units) {
    unit.processes = unit.pids.map((pid) => identities.get(pid)).filter(Boolean).map((process) => ({
      pid: process.pid,
      startTicks: process.startTicks,
      commandHash: process.commandHash,
    }));
    unit.readinessUrl = READINESS_URLS[unit.id];
  }
  const { unknownProcesses, exemptProcesses } = classifyIngressObservation({
    units,
    sockets,
    processes,
  });
  return buildIngressReceipt({
    generation,
    units,
    unknownProcesses,
    exemptProcesses,
    createdAt,
  });
}

async function probeCapturedUnit(unit) {
  if (!unit.exists) return { ...unit };
  const current = await probeScope(unit.id, unit.scope);
  if (!current) throw new Error(`captured unit disappeared: ${unit.id}`);
  const sockets = await scanSockets();
  const pids = await cgroupPids(current);
  const processes = (await Promise.all(pids.map((pid) => processIdentity(pid))))
    .filter(({ startTicks }) => startTicks !== null)
    .map(({ pid, startTicks, commandHash }) => ({ pid, startTicks, commandHash }));
  return {
    ...unit,
    ...current,
    pids,
    processes,
    listeners: sockets.listeners
      .filter(({ pid, port }) => pids.includes(pid) && KNOWN_LISTENER_PORTS.has(port))
      .map(({ port }) => port),
    openhabConnections: sockets.connections.filter(({ pid, remotePort: port }) => (
      pids.includes(pid) && port === OPENHAB_PORT
    )).length,
  };
}

async function waitFor(description, predicate, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  let latest;
  while (Date.now() < deadline) {
    latest = await predicate();
    if (latest) return latest;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`timed out waiting for ${description}`);
}

export function createSystemdAdapter() {
  return {
    async stop(unit) {
      if (unit.exists) await systemctl(unit.scope, 'stop', unit.id);
    },
    async start(unit) {
      if (unit.exists) await systemctl(unit.scope, 'start', unit.id);
    },
    async verifyQuiescent(unit) {
      if (!unit.exists) return;
      await waitFor(`${unit.id} quiescence`, async () => {
        const current = await probeCapturedUnit(unit);
        return current.activeState === 'inactive'
          && current.mainPid === 0
          && current.listeners.length === 0
          && current.openhabConnections === 0;
      });
    },
    async verifyReady(unit) {
      if (!unit.exists) return;
      await waitFor(`${unit.id} readiness`, async () => {
        const current = await probeCapturedUnit(unit);
        if (!restoredUnitMatchesCapture(unit, current)) return false;
        try {
          const response = await fetch(unit.readinessUrl, {
            signal: AbortSignal.timeout(5000),
          });
          return response.ok;
        } catch {
          return false;
        }
      });
    },
    async verifyInactive(unit) {
      if (!unit.exists) return;
      const current = await probeCapturedUnit(unit);
      if (
        current.activeState !== 'inactive'
        || current.mainPid !== 0
        || current.commandHash !== unit.commandHash
        || current.pids.length !== 0
        || current.processes.length !== 0
        || current.listeners.length !== 0
        || current.openhabConnections !== 0
      ) {
        throw new Error(`captured-inactive unit became active: ${unit.id}`);
      }
    },
    async isActive(unit) {
      if (!unit.exists) return false;
      const current = await probeCapturedUnit(unit);
      return current.activeState === 'active';
    },
    async verifyAllQuiescent(receipt = { units: [], exemptProcesses: [] }) {
      for (const unit of receipt.units) await this.verifyQuiescent(unit);
      const sockets = await scanSockets();
      const processes = await scanProcessIdentities();
      const observed = classifyIngressObservation({ units: receipt.units, sockets, processes });
      const exemptionDrift = observed.exemptProcesses.some((current) => {
        const captured = receipt.exemptProcesses.find(({ pid }) => pid === current.pid);
        return !captured
          || captured.startTicks !== current.startTicks
          || captured.commandHash !== current.commandHash;
      });
      if (observed.unknownProcesses.length > 0 || exemptionDrift) {
        throw new Error('feeder ingress remains live through an unmapped listener or connection');
      }
    },
  };
}

export async function verifyQuiescent(receipt) {
  const working = validatedIngress(receipt);
  const adapter = createSystemdAdapter();
  for (const unit of working.units) await adapter.verifyQuiescent(unit);
  await adapter.verifyAllQuiescent(working);
  return working;
}

export async function verifyRestored(receipt) {
  const working = validatedIngress(receipt);
  const adapter = createSystemdAdapter();
  for (const unit of working.units) {
    if (activeAtCapture(unit)) await adapter.verifyReady(unit);
    else await adapter.verifyInactive(unit);
  }
  return working;
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

export async function durableAtomicWriteJson(path, value, {
  makeDirectory = mkdir,
  openFile = open,
  renameFile = rename,
} = {}) {
  const directory = dirname(path);
  await makeDirectory(directory, { recursive: true, mode: 0o700 });
  const temp = `${path}.${process.pid}.tmp`;
  const file = await openFile(temp, 'w', 0o600);
  try {
    await file.writeFile(`${JSON.stringify(value, null, 2)}\n`);
    await file.sync();
  } finally {
    await file.close();
  }
  await renameFile(temp, path);
  const parent = await openFile(directory, 'r');
  try {
    await parent.sync();
  } finally {
    await parent.close();
  }
}

async function readReceipt(path) {
  return JSON.parse(await readFile(path, 'utf8'));
}

function options(argv) {
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

async function runCli(command, args) {
  const receiptPath = args.receipt;
  if (!receiptPath) throw new Error('--receipt is required');
  if (command === 'capture') {
    if (await exists(receiptPath)) throw new Error('an open ingress receipt already exists');
    const captured = await captureKnownIngress();
    await durableAtomicWriteJson(receiptPath, captured);
    return captured;
  }
  const current = await readReceipt(receiptPath);
  const adapter = createSystemdAdapter();
  if (command === 'quiesce' || command === 're-quiesce') {
    const source = command === 're-quiesce'
      ? withReceiptChecksum({ ...current, phase: 'captured', openhabBinding: null })
      : current;
    const next = await quiesceServices(source, adapter, {
      allowStopKnownServices: args['allow-stop-known-services'] === true,
      shouldStop: command === 're-quiesce'
        ? (unit) => adapter.isActive(unit)
        : (unit) => activeAtCapture(unit),
      compensateOnFailure: command !== 're-quiesce',
      onTransition: async (transitionReceipt) => {
        const durable = command === 're-quiesce'
          ? withReceiptChecksum({
              ...transitionReceipt,
              openhabBinding: current.openhabBinding,
            })
          : transitionReceipt;
        await durableAtomicWriteJson(receiptPath, durable);
      },
    });
    const rebound = command === 're-quiesce'
      ? withReceiptChecksum({ ...next, openhabBinding: current.openhabBinding })
      : next;
    await durableAtomicWriteJson(receiptPath, rebound);
    return rebound;
  }
  if (command === 'verify-quiescent') return verifyQuiescent(current);
  if (command === 'bind-openhab') {
    if (!args['openhab-receipt']) throw new Error('--openhab-receipt is required');
    const openhab = await readReceipt(args['openhab-receipt']);
    assertReceiptChecksum(openhab);
    const reciprocal = withReceiptChecksum({
      ...openhab,
      ingressBinding: { generation: current.generation, checksum: current.captureChecksum },
      updatedAt: new Date().toISOString(),
    });
    const bound = bindOpenhabReceipt(current, reciprocal);
    await durableAtomicWriteJson(args['openhab-receipt'], reciprocal);
    await durableAtomicWriteJson(receiptPath, bound);
    return bound;
  }
  if (command === 'restore-pre-openhab') {
    const asserted = args['assert-openhab-receipt-absent'];
    if (!asserted || await exists(asserted)) throw new Error('OpenHAB receipt must be explicitly absent');
    if (current.openhabBinding) throw new Error('bound ingress cannot use pre-OpenHAB restore');
    const authorized = withReceiptChecksum({
      ...current,
      openhabTerminal: 'absent',
      updatedAt: new Date().toISOString(),
    });
    await durableAtomicWriteJson(receiptPath, authorized);
    const restored = await restoreServices(authorized, adapter, {
      onTransition: (transitionReceipt) => durableAtomicWriteJson(receiptPath, transitionReceipt),
    });
    await durableAtomicWriteJson(receiptPath, restored);
    return restored;
  }
  if (command === 'restore') {
    if (!args['openhab-receipt']) throw new Error('--openhab-receipt is required');
    const openhab = await readReceipt(args['openhab-receipt']);
    assertRestoreReceiptPair(current, openhab);
    const authorized = withReceiptChecksum({
      ...current,
      openhabTerminal: openhab.terminal,
      updatedAt: new Date().toISOString(),
    });
    await durableAtomicWriteJson(receiptPath, authorized);
    const restored = await restoreServices(authorized, adapter, {
      onTransition: (transitionReceipt) => durableAtomicWriteJson(receiptPath, transitionReceipt),
    });
    await durableAtomicWriteJson(receiptPath, restored);
    return restored;
  }
  if (command === 'verify-restored') return verifyRestored(current);
  if (command === 'close') {
    const allowedTerminals = new Set(['restored', 'restored-unmutated', 'restored-no-openhab']);
    if (!allowedTerminals.has(args.terminal)) throw new Error('unsupported --terminal value');
    assertIngressCloseTerminal(current, args.terminal);
    await verifyRestored(current);
    const closed = withReceiptChecksum({
      ...current,
      state: 'closed',
      phase: 'closed',
      terminal: args.terminal,
      updatedAt: new Date().toISOString(),
    });
    await durableAtomicWriteJson(receiptPath, closed);
    return closed;
  }
  throw new Error(`unknown command: ${command}`);
}

function usage() {
  return [
    'Usage: node scripts/feeder-ingress.mjs <command> --receipt <path>',
    'Commands: capture, quiesce, verify-quiescent, bind-openhab, re-quiesce,',
    '          restore-pre-openhab, restore, verify-restored, close',
    'This tool fails closed unless its command-specific receipt checks pass.',
  ].join('\n');
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  const command = process.argv[2];
  if (!command || ['-h', '--help', 'help'].includes(command)) {
    console.log(usage());
  } else {
    runCli(command, options(process.argv.slice(3)))
      .then((receipt) => console.log(JSON.stringify({
        ok: true,
        command,
        generation: receipt.generation,
        phase: receipt.phase,
      })))
      .catch((error) => {
        console.error(`feeder-ingress: ${error.message}`);
        process.exitCode = 1;
      });
  }
}
