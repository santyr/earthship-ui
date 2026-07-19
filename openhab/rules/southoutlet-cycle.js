'use strict';

/*
 * SouthOutlet SOC-gated greywater cycle controller with correlated manual
 * requests (Discover AES lithium bank; South planter greywater circulation
 * pump). Canonical rewrite of the live `hex_southoutlet_cycle` rule in the
 * GraalJS `openhab` idiom so the durable request ledger, readback gate, and
 * result contract are shared verbatim with `openhab/rules/feeder-owner.js`.
 *
 * Spec amendments over the live rule (operator-approved, 2026-07-19):
 * - 5-minute cycle (was 10 min).
 * - 230-minute start-to-start gap (hydrology / pump dry-run protection).
 * - SoC eligibility is sky-conditioned: SkyCondition == 'CLEAR' -> SoC >= 90,
 *   else SoC >= 98. The interim curtailment-only block is removed entirely.
 * - The BMS/voltage fail-closed chain is preserved exactly
 *   (invalid voltage -> comms staleness > 1800s -> invalid SoC -> absolute
 *   low-SoC cutoff -> absurd voltage band).
 * - AFTER-DARK CURFEW (operator, 2026-07-19) preserved exactly: cycles require
 *   Sun elevation > 0; it fails closed on missing astro data and gates BOTH the
 *   automatic and the manual paths. A cycle caught running past sunset is forced
 *   OFF on the next evaluation.
 * - The 24h aerobic fallback only widens *why* a start is considered (gap > 24h);
 *   it never bypasses the SoC eligibility threshold or the curfew.
 *
 * LastCycleStart is the restart-safe 230-minute start-to-start authority
 * (posted at the start of every automatic and manual cycle). LastCycle is the
 * UI truth (posted only after a completed cycle). LastAutoRun stays
 * automatic-only for compatibility. On first evaluation LastCycleStart is
 * seeded logically from LastAutoRun (read fallback) without moving equipment.
 *
 * NOT DEPLOYED by this task — a later attended maintenance transaction applies
 * it. Simulations only.
 */

const { actions, cache, items, time } = require('openhab');

const EARTHSHIP_SOUTHOUTLET_VERSION = 'greywater-request-v1';
const LEDGER_VERSION = 'greywater-request-ledger/v1';

const CFG = {
  voltageItem: 'DCData_Voltage',
  socItem: 'BMS_SOC',
  bmsCommsItem: 'BMS_Comms_Status',
  commsStaleMaxS: 1800,
  lowSocCutoffItem: 'SouthOutlet_LowSocCutoff',
  outletItem: 'SouthOutlet_Outlet2_Switch',
  lastRunItem: 'SouthOutlet_LastAutoRun',
  statusItem: 'SouthOutlet_AutoStatus',
  skyConditionItem: 'SkyCondition',
  sunElevationItem: 'Sun_Position_Elevation',
  requestItem: 'SouthOutlet_ManualRequest',
  resultItem: 'SouthOutlet_ManualResult',
  lastCycleStartItem: 'SouthOutlet_LastCycleStart',
  lastCycleItem: 'SouthOutlet_LastCycle',
  voltageSaneMin: 40.0,
  voltageSaneMax: 60.0,
  defaultLowSocCutoff: 45,
  clearSocMin: 90,
  defaultSocMin: 98,
  requiredGapMs: 230 * 60 * 1000,
  fallbackMaxGapMs: 24 * 60 * 60 * 1000,
  cycleMs: 5 * 60 * 1000,
};

const BUSY_KEY = 'earthship.southoutlet.busy';
const MAX_LEDGER_BYTES = 8192;
const MAX_LEDGER_ENTRIES = 32;
const LEDGER_READBACK_ATTEMPTS = 20;
const LEDGER_READBACK_POLL_MS = 50;
// Request-staleness window, values verbatim from feeder-owner.js.
const MAX_REQUEST_AGE_MS = 2 * 60 * 1000;
const MAX_REQUEST_FUTURE_SKEW_MS = 30 * 1000;
const NULL_STATES = new Set(['NULL', 'UNDEF']);
const TERMINAL_STATUSES = new Set(['completed', 'failed', 'denied']);

// ---- clock / item helpers -------------------------------------------------

function now() {
  return time.ZonedDateTime.now();
}

function nowText() {
  return now().toString();
}

// UTC instant string (ends in 'Z'); strict-parseable by real Instant.parse().
// All durable ledger, result, and DateTime-authority timestamps are written in
// this form so a production readback never re-parses a bracketed rendering.
function nowInstantText() {
  return now().toInstant().toString();
}

function nowMillis() {
  return epochMillis(now());
}

// Real time.ZonedDateTime.now().toString() ends in a bracketed zone id
// (e.g. ...-06:00[America/Denver]) and openHAB renders DateTime item states
// with colon-less offsets (confirmed live: 2026-07-19T07:09:25.359-0600); real
// time.toInstant()/Instant.parse() is strict and accepts only 'Z' instants.
// Normalize both non-Z forms — this restores the old live rule's colon-less
// offset handling (`([+-]\d{2})(\d{2})$` -> `$1:$2`) plus bracket stripping —
// so LastCycleStart/LastAutoRun item states and historical ledger timestamps
// still parse. Belt-and-braces to the instant-form writes above.
function normalizeTimestamp(value) {
  return String(value)
    .replace(/\[[^\]]+\]$/, '')
    .replace(/([+-]\d{2})(\d{2})$/, '$1:$2');
}

function epochMillis(value) {
  if (value && typeof value.toInstant === 'function') {
    try {
      return Number(time.toInstant(value).toEpochMilli());
    } catch {
      return Number.NaN;
    }
  }
  const ms = Date.parse(normalizeTimestamp(value));
  return Number.isFinite(ms) ? ms : Number.NaN;
}

function state(name, fallback = 'NULL') {
  try {
    return String(items.getItem(name).state);
  } catch {
    return fallback;
  }
}

function post(name, value) {
  try {
    items.getItem(name).postUpdate(String(value));
  } catch {
    // Telemetry updates are best-effort; the durable ledger is authoritative.
  }
}

function command(name, value) {
  items.getItem(name).sendCommand(String(value));
}

function num(name, fallback = Number.NaN) {
  const raw = state(name, '').trim();
  if (raw === '' || raw === 'NULL' || raw === 'UNDEF') return fallback;
  const cleaned = raw.replace(/[^0-9.+-]/g, '');
  if (['', '+', '-', '.', '+.', '-.'].includes(cleaned)) return fallback;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : fallback;
}

function status(reason, fields = {}) {
  const parts = [`reason=${reason}`];
  for (const [key, value] of Object.entries(fields)) parts.push(`${key}=${value}`);
  post(CFG.statusItem, parts.join(','));
}

function postResult(requestId, resultStatus, reason, at = nowInstantText()) {
  items.getItem(CFG.resultItem).postUpdate(JSON.stringify({
    requestId,
    status: resultStatus,
    reason,
    at,
  }));
}

function safeResult(requestId, resultStatus, reason) {
  try {
    postResult(requestId, resultStatus, reason);
  } catch {
    // The durable request ledger remains the authoritative receipt.
  }
}

function settleItemUpdate(delayMs = LEDGER_READBACK_POLL_MS) {
  if (typeof Java !== 'undefined') {
    Java.type('java.lang.Thread').sleep(delayMs);
  } else if (typeof java !== 'undefined') {
    java.lang.Thread.sleep(delayMs);
  }
}

function utf8Bytes(value) {
  if (typeof Java !== 'undefined') {
    const JavaString = Java.type('java.lang.String');
    const StandardCharsets = Java.type('java.nio.charset.StandardCharsets');
    return new JavaString(String(value)).getBytes(StandardCharsets.UTF_8).length;
  }
  if (typeof java !== 'undefined') {
    return new java.lang.String(String(value))
      .getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
  }
  return new TextEncoder().encode(String(value)).length;
}

// ---- request / ledger (shared contract with feeder-owner.js) --------------

function parseRequest(raw) {
  if (typeof raw !== 'string' || raw.length === 0 || raw.length > 2048) {
    throw new Error('request_invalid');
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error('request_invalid');
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('request_invalid');
  }
  if (
    typeof parsed.requestId !== 'string'
    || !/^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/.test(parsed.requestId)
  ) {
    throw new Error('request_invalid');
  }
  if (typeof parsed.requestedAt !== 'string' || !Number.isFinite(epochMillis(parsed.requestedAt))) {
    throw new Error('request_invalid');
  }
  return {
    requestId: parsed.requestId,
    requestedAt: parsed.requestedAt,
    requestedAtMs: epochMillis(parsed.requestedAt),
  };
}

function validLedgerEntry(entry) {
  return Boolean(
    entry
    && typeof entry === 'object'
    && !Array.isArray(entry)
    && typeof entry.requestId === 'string'
    && /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/.test(entry.requestId)
    && typeof entry.status === 'string'
    && ['accepted', ...TERMINAL_STATUSES].includes(entry.status)
    && typeof entry.reason === 'string'
    && typeof entry.at === 'string'
    && Number.isFinite(epochMillis(entry.at))
    && (entry.updatedAt === undefined || (
      typeof entry.updatedAt === 'string' && Number.isFinite(epochMillis(entry.updatedAt))
    )),
  );
}

function parseLedger(requestItem) {
  const raw = requestItem.state.toString();
  if (NULL_STATES.has(raw)) {
    if (requestItem.persistence.previousState(false, 'jdbc') !== null) {
      throw new Error('ledger_restore_missing');
    }
    return { version: LEDGER_VERSION, entries: [] };
  }
  if (raw.length === 0 || utf8Bytes(raw) > MAX_LEDGER_BYTES) {
    throw new Error('ledger_invalid');
  }
  let ledger;
  try {
    ledger = JSON.parse(raw);
  } catch {
    throw new Error('ledger_invalid');
  }
  const uniqueIds = new Set(ledger?.entries?.map((entry) => entry?.requestId));
  if (
    !ledger
    || typeof ledger !== 'object'
    || Array.isArray(ledger)
    || ledger.version !== LEDGER_VERSION
    || !Array.isArray(ledger.entries)
    || ledger.entries.length > MAX_LEDGER_ENTRIES
    || uniqueIds.size !== ledger.entries.length
    || !ledger.entries.every(validLedgerEntry)
  ) {
    throw new Error('ledger_invalid');
  }
  return ledger;
}

function writeLedger(requestItem, ledger, requestId, expectedStatus) {
  const encoded = JSON.stringify({
    version: LEDGER_VERSION,
    entries: ledger.entries.slice(0, MAX_LEDGER_ENTRIES),
  });
  if (utf8Bytes(encoded) > MAX_LEDGER_BYTES) throw new Error('ledger_invalid');
  requestItem.postUpdate(encoded);
  settleItemUpdate();
  requestItem.persistence.persist('jdbc');

  for (let attempt = 0; attempt < LEDGER_READBACK_ATTEMPTS; attempt += 1) {
    try {
      const readback = JSON.parse(requestItem.state.toString());
      const previous = requestItem.persistence.previousState(false, 'jdbc');
      const persistedReadback = previous === null
        ? null
        : JSON.parse(previous.state.toString());
      if (
        readback?.version === LEDGER_VERSION
        && readback.entries?.[0]?.requestId === requestId
        && readback.entries?.[0]?.status === expectedStatus
        && persistedReadback?.version === LEDGER_VERSION
        && persistedReadback.entries?.[0]?.requestId === requestId
        && persistedReadback.entries?.[0]?.status === expectedStatus
        && JSON.stringify(readback) === encoded
        && JSON.stringify(persistedReadback) === encoded
      ) return;
    } catch {
      // Persistence is asynchronous; retry only until the bounded deadline.
    }
    if (attempt + 1 < LEDGER_READBACK_ATTEMPTS) settleItemUpdate();
  }
  throw new Error('ledger_readback_failed');
}

function acceptedLedger(ledger, requestId, at) {
  return {
    version: LEDGER_VERSION,
    entries: [{
      requestId,
      status: 'accepted',
      reason: 'accepted',
      at,
    }, ...ledger.entries.filter((entry) => entry.requestId !== requestId)]
      .slice(0, MAX_LEDGER_ENTRIES),
  };
}

function terminalLedger(ledger, requestId, terminalStatus, reason, updatedAt) {
  return {
    version: LEDGER_VERSION,
    entries: ledger.entries.map((entry) => (
      entry.requestId === requestId
        ? { ...entry, status: terminalStatus, reason, updatedAt }
        : entry
    )).slice(0, MAX_LEDGER_ENTRIES),
  };
}

function recoverInterruptedLedger(ledger, updatedAt) {
  return {
    version: LEDGER_VERSION,
    entries: ledger.entries.map((entry) => (
      entry.status === 'accepted'
        ? { ...entry, status: 'failed', reason: 'restart_uncertain', updatedAt }
        : entry
    )),
  };
}

function releaseBusy(token) {
  if (cache.shared.get(BUSY_KEY) === token) cache.shared.remove(BUSY_KEY);
}

function safeOff(actuator) {
  if (!actuator) return;
  try {
    actuator.sendCommand('OFF');
  } catch {
    // Best-effort redundant OFF; the next evaluation re-forces OFF on faults.
  }
}

// ---- gates ----------------------------------------------------------------

function lowSocCutoff() {
  const raw = num(CFG.lowSocCutoffItem, CFG.defaultLowSocCutoff);
  return Number.isFinite(raw) ? raw : CFG.defaultLowSocCutoff;
}

// Fail-closed safety chain preserved from the live rule. Returns the first
// failing gate as { reason, fields } (a force-OFF condition) or null.
function safetyReason() {
  const voltage = num(CFG.voltageItem);
  if (!Number.isFinite(voltage)) {
    return { reason: 'invalid_voltage', fields: { voltage: state(CFG.voltageItem) } };
  }
  const comms = state(CFG.bmsCommsItem, 'NO-DATA');
  const staleM = comms.match(/^STALE age=(\d+)s/);
  if (comms !== 'OK' && (!staleM || parseInt(staleM[1], 10) > CFG.commsStaleMaxS)) {
    return { reason: 'bms_comms_stale', fields: { comms, voltage: voltage.toFixed(2) } };
  }
  const soc = num(CFG.socItem);
  if (!Number.isFinite(soc)) {
    return { reason: 'invalid_soc', fields: { soc: state(CFG.socItem), voltage: voltage.toFixed(2) } };
  }
  const cutoff = lowSocCutoff();
  if (soc <= cutoff) {
    return { reason: 'low_soc', fields: { soc: soc.toFixed(1), lowSocCutoff: cutoff.toFixed(1) } };
  }
  if (voltage < CFG.voltageSaneMin || voltage > CFG.voltageSaneMax) {
    return { reason: 'absurd_voltage', fields: { voltage: voltage.toFixed(2), soc: soc.toFixed(1) } };
  }
  // After-dark curfew: fail closed on missing astro data; gates auto + manual.
  const elev = num(CFG.sunElevationItem);
  if (!Number.isFinite(elev) || elev <= 0) {
    return {
      reason: 'after_dark',
      fields: {
        sunElev: Number.isFinite(elev) ? elev.toFixed(1) : state(CFG.sunElevationItem),
        soc: soc.toFixed(1),
      },
    };
  }
  return null;
}

function socEligible(soc) {
  const sky = state(CFG.skyConditionItem);
  const threshold = sky === 'CLEAR' ? CFG.clearSocMin : CFG.defaultSocMin;
  return { eligible: soc >= threshold, threshold, sky };
}

function lastStartMs() {
  const primary = epochMillis(state(CFG.lastCycleStartItem));
  if (Number.isFinite(primary)) return primary;
  const seed = epochMillis(state(CFG.lastRunItem)); // migration seed from LastAutoRun
  return Number.isFinite(seed) ? seed : Number.NaN;
}

function forceOff(reason, fields = {}) {
  cache.shared.remove(BUSY_KEY);
  try {
    if (state(CFG.outletItem) !== 'OFF') command(CFG.outletItem, 'OFF');
  } catch {
    // Redundant OFF backstop lives in the next evaluation and expire metadata.
  }
  status(reason, fields);
}

// ---- cycle actuation ------------------------------------------------------

function beginCycle({ isManual, request, ledger, voltage, soc, mode, invocationToken }) {
  const startAt = nowInstantText();
  post(CFG.lastCycleStartItem, startAt);
  if (!isManual) post(CFG.lastRunItem, startAt); // automatic-only compatibility
  command(CFG.outletItem, 'ON');
  status('cycle_started', {
    voltage: voltage.toFixed(2),
    soc: soc.toFixed(1),
    mode: mode || 'normal',
    origin: isManual ? 'manual' : 'auto',
  });

  actions.ScriptExecution.createTimer(now().plusSeconds(CFG.cycleMs / 1000), () => {
    const actuator = items.getItem(CFG.outletItem);
    try {
      actuator.sendCommand('OFF');
      post(CFG.lastCycleItem, nowInstantText());
      status('cycle_completed', { origin: isManual ? 'manual' : 'auto' });
      if (isManual) {
        const done = terminalLedger(ledger, request.requestId, 'completed', 'completed', nowInstantText());
        writeLedger(items.getItem(CFG.requestItem), done, request.requestId, 'completed');
        postResult(request.requestId, 'completed', 'completed');
      }
    } catch {
      if (isManual) {
        try {
          const failed = terminalLedger(
            ledger, request.requestId, 'failed', 'execution_error', nowInstantText(),
          );
          writeLedger(items.getItem(CFG.requestItem), failed, request.requestId, 'failed');
        } catch {
          // The failed result remains the only safe receipt without persistence.
        }
        safeResult(request.requestId, 'failed', 'execution_error');
      }
    } finally {
      safeOff(actuator);
      releaseBusy(invocationToken);
    }
  });
}

// ---- automatic path -------------------------------------------------------

function runAutomatic() {
  // Best-effort ledger recovery: a restart between accept and completion leaves
  // an 'accepted' entry that must never be replayed. Non-fatal so ledger
  // corruption can never block the safety force-off chain below. Recovery does
  // NOT short-circuit the orphan-outlet force-off: an evaluation that both
  // recovers the ledger AND observes the pump still energized with no live timer
  // must de-energize it in this same evaluation, never wait for the next cron.
  let recoveredRequestId = null;
  try {
    const requestItem = items.getItem(CFG.requestItem);
    const ledger = parseLedger(requestItem);
    if (
      cache.shared.get(BUSY_KEY) === null
      && ledger.entries.some((entry) => entry.status === 'accepted')
    ) {
      const recovered = recoverInterruptedLedger(ledger, nowInstantText());
      writeLedger(requestItem, recovered, recovered.entries[0].requestId, recovered.entries[0].status);
      recoveredRequestId = recovered.entries[0].requestId;
    }
  } catch {
    // Ledger unreadable on the automatic path: fall through to the safety chain.
  }

  const gate = safetyReason();
  if (gate) {
    forceOff(gate.reason, gate.fields);
    return;
  }

  const voltage = num(CFG.voltageItem);
  const soc = num(CFG.socItem);
  const outlet = state(CFG.outletItem);

  if (outlet === 'ON') {
    if (cache.shared.get(BUSY_KEY) !== null) {
      status('cycle_active', { voltage: voltage.toFixed(2), soc: soc.toFixed(1) });
      return;
    }
    // Orphaned pump with no live timer -> force OFF in this same evaluation,
    // including the ledger-recovery path (recoveredRequestId set above).
    forceOff('orphan_outlet_off', { voltage: voltage.toFixed(2), soc: soc.toFixed(1) });
    return;
  }

  if (recoveredRequestId !== null) {
    status('ledger_recovered', { requestId: recoveredRequestId });
    return; // spent this evaluation on recovery; never start in the same pass
  }

  const elig = socEligible(soc);
  if (!elig.eligible) {
    status('low_soc', { soc: soc.toFixed(1), threshold: elig.threshold, sky: elig.sky });
    return;
  }

  const last = lastStartMs();
  if (!Number.isFinite(last)) {
    post(CFG.lastCycleStartItem, nowInstantText());
    status('cooldown_initialized', { voltage: voltage.toFixed(2), soc: soc.toFixed(1) });
    return;
  }
  const elapsed = nowMillis() - last;
  if (!Number.isFinite(elapsed) || elapsed < CFG.requiredGapMs) {
    const waitMs = Number.isFinite(elapsed) ? Math.max(0, CFG.requiredGapMs - elapsed) : CFG.requiredGapMs;
    status('cooldown_wait', {
      voltage: voltage.toFixed(2),
      soc: soc.toFixed(1),
      waitMin: Math.ceil(waitMs / 60000),
    });
    return;
  }

  const mode = elapsed >= CFG.fallbackMaxGapMs ? 'aerobic_fallback_24h' : 'normal';
  const token = `auto:${nowText()}`;
  if (cache.shared.get(BUSY_KEY, () => token) !== token) {
    status('busy', { soc: soc.toFixed(1) });
    return;
  }
  beginCycle({ isManual: false, voltage, soc, mode, invocationToken: token });
}

// ---- manual path ----------------------------------------------------------

function runManual(triggerEvent) {
  const requestItem = items.getItem(CFG.requestItem);
  const currentMs = nowMillis();
  if (!Number.isFinite(currentMs)) {
    safeResult('unknown', 'failed', 'clock_invalid');
    return;
  }

  let request;
  try {
    request = parseRequest(triggerEvent.receivedCommand);
  } catch (error) {
    safeResult('unknown', 'failed', error.message); // malformed/incomplete -> failed
    return;
  }

  // Bounded request-staleness gate (mirrors feeder-owner.js, same window values):
  // a queued request from a reconnecting tablet that is older than the staleness
  // window — or implausibly far in the future — must not actuate the pump even
  // with a fresh requestId.
  if (
    Number.isFinite(request.requestedAtMs)
    && (
      currentMs - request.requestedAtMs > MAX_REQUEST_AGE_MS
      || request.requestedAtMs - currentMs > MAX_REQUEST_FUTURE_SKEW_MS
    )
  ) {
    safeResult(request.requestId, 'denied', 'request_stale');
    return;
  }

  let ledger;
  try {
    ledger = parseLedger(requestItem);
  } catch (error) {
    safeResult(request.requestId, 'denied', error.message);
    return;
  }

  if (
    cache.shared.get(BUSY_KEY) === null
    && ledger.entries.some((entry) => entry.status === 'accepted')
  ) {
    ledger = recoverInterruptedLedger(ledger, nowInstantText());
    try {
      writeLedger(requestItem, ledger, ledger.entries[0].requestId, ledger.entries[0].status);
    } catch {
      safeResult(request.requestId, 'denied', 'ledger_recovery_failed');
      return;
    }
  }

  if (ledger.entries.some((entry) => entry.requestId === request.requestId)) {
    safeResult(request.requestId, 'denied', 'duplicate');
    return;
  }

  const gate = safetyReason();
  if (gate) {
    forceOff(gate.reason, gate.fields);
    safeResult(request.requestId, 'denied', gate.reason);
    return;
  }

  const soc = num(CFG.socItem);
  const voltage = num(CFG.voltageItem);
  const elig = socEligible(soc);
  if (!elig.eligible) {
    safeResult(request.requestId, 'denied', 'low_soc');
    return;
  }

  const token = `${request.requestId}:${nowText()}`;
  if (cache.shared.get(BUSY_KEY, () => token) !== token) {
    safeResult(request.requestId, 'denied', 'busy');
    return;
  }

  const last = lastStartMs();
  if (!Number.isFinite(last)) {
    // Virgin system (no LastCycleStart, no LastAutoRun): align with the auto
    // path — seed the cooldown clock and deny rather than starting immediately.
    post(CFG.lastCycleStartItem, nowInstantText());
    releaseBusy(token);
    safeResult(request.requestId, 'denied', 'cooldown_initializing');
    return;
  }
  const elapsed = currentMs - last;
  if (elapsed < CFG.requiredGapMs) {
    releaseBusy(token);
    safeResult(request.requestId, 'denied', 'cooldown');
    return;
  }

  ledger = acceptedLedger(ledger, request.requestId, nowInstantText());
  try {
    writeLedger(requestItem, ledger, request.requestId, 'accepted');
  } catch (error) {
    releaseBusy(token);
    safeResult(
      request.requestId,
      'failed',
      error.message === 'ledger_readback_failed' ? 'ledger_readback_failed' : 'ledger_persist_failed',
    );
    return;
  }

  try {
    postResult(request.requestId, 'accepted', 'accepted');
    const mode = (Number.isFinite(last) && elapsed >= CFG.fallbackMaxGapMs)
      ? 'aerobic_fallback_24h'
      : 'normal';
    beginCycle({ isManual: true, request, ledger, voltage, soc, mode, invocationToken: token });
  } catch {
    safeOff(items.getItem(CFG.outletItem));
    try {
      const failed = terminalLedger(ledger, request.requestId, 'failed', 'execution_error', nowInstantText());
      writeLedger(requestItem, failed, request.requestId, 'failed');
    } catch {
      // The failed result remains the only safe receipt without persistence.
    }
    safeResult(request.requestId, 'failed', 'execution_error');
    releaseBusy(token);
  }
}

// ---- entry ----------------------------------------------------------------

function runSouthOutlet(triggerEvent) {
  const isManual = Boolean(
    triggerEvent
    && triggerEvent.itemName === CFG.requestItem
    && typeof triggerEvent.receivedCommand === 'string',
  );
  if (isManual) runManual(triggerEvent);
  else runAutomatic();
}

runSouthOutlet(typeof event === 'undefined' ? null : event);
