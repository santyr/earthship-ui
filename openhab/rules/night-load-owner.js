'use strict';

/*
 * Serialized Night Load Override owner. ONE canonical GraalJS `openhab` rule
 * that owns the Night Load Override policy (OverrideSwitch) and its three owned
 * loads:
 *   - Dishwasher   Dish_Washer_Power
 *   - Shureflo     ShurefloPump_Power
 *   - Goat Cam     Goat_Plugs_Outlet1_Switch
 *
 * This consolidates the live duplicate child rules into a single serialized
 * reducer that shares the durable request ledger, readback gate, and result
 * contract verbatim with `openhab/rules/feeder-owner.js` and
 * `openhab/rules/southoutlet-cycle.js`:
 *   - retires  ab8a59e1da (Dishwasher Off), 4e234eabea (Shureflo OFF),
 *              e647476610 (Shureflo ON)  -- their matrices move into this owner;
 *   - preserves the Goat Cam <-> FeederOverride coupling rules 3e8f265498
 *     (Goat Cam ON -> FeederOverride OFF) and GoatCamOff (Goat Cam OFF ->
 *     FeederOverride ON) EXACTLY. This owner never commands or updates
 *     FeederOverride; it only observes the downstream coupling side effect;
 *   - preserves schedules 1f692c798b (20:00 ON) and b1501047a9 (09:00 OFF),
 *     which command OverrideSwitch; the owner treats each schedule/external
 *     OverrideSwitch command as a source-agnostic request with a synthetic id.
 *
 * Contract:
 *   NightLoadOverride_Request : { requestId, requestedAt, command: ON|OFF }
 *   NightLoadDevice_Request   : { requestId, requestedAt,
 *                                 device: dishwasher|shureflo|goat-cam,
 *                                 command: ON|OFF }
 *   *_Result : { requestId, status, reason, at, ... }
 *   status in { accepted, running, completed, denied, failed }.
 *
 * Exact matrices (canonical Task 16 contract; goat cam decoupled from the
 * override by operator instruction 2026-07-22 — the override transitions
 * never command Goat_Plugs_Outlet1_Switch; manual goat-cam requests via
 * NightLoadDevice_Request are unchanged):
 *   override ON  -> Dish_Washer_Power OFF, ShurefloPump_Power OFF
 *   override OFF -> ShurefloPump_Power ON   (dishwasher & goat cam untouched)
 *
 * Serialized: one in-flight request at a time via a single cache.shared lock;
 * a second concurrent request is denied `busy`. Commit-before-command: the
 * accepted ledger checkpoint is persisted and read-verified before any physical
 * command, and OverrideSwitch policy is committed (postUpdate + persist +
 * read-verify) before the owned loads are commanded. Provider-generation
 * matching: a transition is `completed` only once every commanded provider Item
 * reflects the commanded state (a MANUAL goat-cam device request additionally
 * requires the downstream FeederOverride coupling side effect; the override
 * path does not touch the cam and never observes FeederOverride); mismatch ->
 * `failed`. Restart-uncertain
 * recovery marks any restored accepted/running ledger entry `failed`
 * (`restart_uncertain`) and never re-actuates.
 *
 * The owner never branches on the requesting client/source: every accepted
 * request is treated identically (operator constraint 2026-07-19).
 *
 * DEPLOYED as REST-managed rule `hex_night_load_override` (script embedded in
 * the rule action; openhab/managed-resources.json is the manifest). Keep this
 * file and the live rule script in lockstep when editing.
 */

const { actions, cache, items, time } = require('openhab');

const EARTHSHIP_NIGHT_LOAD_OWNER_VERSION = 'night-load-owner-v1';
const LEDGER_VERSION = 'night-load-request-ledger/v1';

const OVERRIDE_REQUEST = 'NightLoadOverride_Request';
const OVERRIDE_RESULT = 'NightLoadOverride_Result';
const DEVICE_REQUEST = 'NightLoadDevice_Request';
const DEVICE_RESULT = 'NightLoadDevice_Result';
const OVERRIDE_SWITCH = 'OverrideSwitch';
const FEEDER_OVERRIDE = 'FeederOverride';

const DEVICE_ITEMS = {
  dishwasher: 'Dish_Washer_Power',
  shureflo: 'ShurefloPump_Power',
  'goat-cam': 'Goat_Plugs_Outlet1_Switch',
};

// Exact owned-load matrices.
const ON_MATRIX = [
  ['Dish_Washer_Power', 'OFF'],
  ['ShurefloPump_Power', 'OFF'],
];
const OFF_MATRIX = [
  ['ShurefloPump_Power', 'ON'],
];

const BUSY_KEY = 'earthship.night-load-owner.busy';
const SEQ_KEY = 'earthship.night-load-owner.seq';
const MAX_LEDGER_BYTES = 8192;
const MAX_LEDGER_ENTRIES = 32;
const LEDGER_READBACK_ATTEMPTS = 20;
const LEDGER_READBACK_POLL_MS = 50;
const SWITCH_READBACK_ATTEMPTS = 20;
// Bounded provider/coupling verification re-poll. Slow TP-Link/coupling latency
// must not be read as a false mismatch on the single +1s check; re-poll up to
// VERIFY_ATTEMPTS x VERIFY_POLL_MS (mirroring the ledger readback loop) before
// declaring a mismatch. Fail-closed: a never-correct transition still fails.
const VERIFY_ATTEMPTS = 20;
const VERIFY_POLL_MS = 250;
// Request-staleness window, values verbatim from feeder-owner.js.
const MAX_REQUEST_AGE_MS = 2 * 60 * 1000;
const MAX_REQUEST_FUTURE_SKEW_MS = 30 * 1000;
const NULL_STATES = new Set(['NULL', 'UNDEF']);
const TERMINAL_STATUSES = new Set(['completed', 'failed', 'denied']);
const COMMANDS = new Set(['ON', 'OFF']);

// ---- clock / item helpers -------------------------------------------------

function now() {
  return time.ZonedDateTime.now();
}

function nowText() {
  return now().toString();
}

// UTC instant string (ends in 'Z'); strict-parseable by real Instant.parse().
// All durable ledger and result timestamps are written in this form so a
// production readback never re-parses a bracketed ZonedDateTime rendering.
function nowInstantText() {
  return now().toInstant().toString();
}

function nowMillis() {
  return epochMillis(now());
}

// A ZonedDateTime `ms` in the future. Prefers plusNanos (sub-second, real
// js-joda) and falls back to fractional plusSeconds for the harness.
function afterMs(ms) {
  const base = now();
  if (typeof base.plusNanos === 'function') return base.plusNanos(Math.round(ms * 1e6));
  return base.plusSeconds(ms / 1000);
}

// Bounded re-poll mirroring the ledger readback loop. `probe()` returns
// { ready: true } once the provider/coupling state is satisfied, else
// { ready: false, reason }. onReady() runs on the first satisfied poll; onFail()
// runs with the last blocking reason after VERIFY_ATTEMPTS exhaust (fail-closed).
function pollVerify(probe, onReady, onFail, attempt = 1) {
  actions.ScriptExecution.createTimer(afterMs(VERIFY_POLL_MS), () => {
    let outcome;
    try {
      outcome = probe();
    } catch {
      outcome = { ready: false, reason: 'execution_error' };
    }
    if (outcome && outcome.ready) {
      onReady();
      return;
    }
    if (attempt >= VERIFY_ATTEMPTS) {
      onFail((outcome && outcome.reason) || 'provider_mismatch');
      return;
    }
    pollVerify(probe, onReady, onFail, attempt + 1);
  });
}

// Real time.ZonedDateTime.now().toString() ends in a bracketed zone id
// (e.g. ...-06:00[America/Denver]) and openHAB renders DateTime item states
// with colon-less offsets (e.g. ...-0600); real time.toInstant()/Instant.parse()
// is strict and accepts only 'Z' instants. Normalize both non-Z forms so any
// historical, bracketed, or item-state timestamp still parses. Belt-and-braces
// to the instant-form writes above.
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

function state(name) {
  try {
    return String(items.getItem(name).state);
  } catch {
    return 'NULL';
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

// ---- result contract ------------------------------------------------------

function postResult(resultItem, payload) {
  items.getItem(resultItem).postUpdate(JSON.stringify(payload));
}

function safeResult(resultItem, requestId, status, reason, extra = {}) {
  try {
    postResult(resultItem, {
      requestId, status, reason, at: nowInstantText(), ...extra,
    });
  } catch {
    // The durable request ledger remains the authoritative receipt.
  }
}

// ---- request parsing (shared contract with feeder-owner.js) ---------------

function parseBase(raw) {
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
  return parsed;
}

function parseOverrideRequest(raw) {
  const parsed = parseBase(raw);
  if (typeof parsed.command !== 'string' || !COMMANDS.has(parsed.command)) {
    throw new Error('request_invalid');
  }
  return {
    requestId: parsed.requestId,
    requestedAt: parsed.requestedAt,
    requestedAtMs: epochMillis(parsed.requestedAt),
    command: parsed.command,
  };
}

function parseDeviceRequest(raw) {
  const parsed = parseBase(raw);
  if (typeof parsed.device !== 'string' || !Object.prototype.hasOwnProperty.call(DEVICE_ITEMS, parsed.device)) {
    throw new Error('request_invalid');
  }
  if (typeof parsed.command !== 'string' || !COMMANDS.has(parsed.command)) {
    throw new Error('request_invalid');
  }
  return {
    requestId: parsed.requestId,
    requestedAt: parsed.requestedAt,
    requestedAtMs: epochMillis(parsed.requestedAt),
    device: parsed.device,
    command: parsed.command,
  };
}

function isStale(request, currentMs) {
  return (
    Number.isFinite(request.requestedAtMs)
    && (
      currentMs - request.requestedAtMs > MAX_REQUEST_AGE_MS
      || request.requestedAtMs - currentMs > MAX_REQUEST_FUTURE_SKEW_MS
    )
  );
}

// ---- durable ledger (shared verbatim with feeder-owner.js) ----------------

function validLedgerEntry(entry) {
  return Boolean(
    entry
    && typeof entry === 'object'
    && !Array.isArray(entry)
    && typeof entry.requestId === 'string'
    && /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/.test(entry.requestId)
    && typeof entry.status === 'string'
    && ['accepted', 'running', ...TERMINAL_STATUSES].includes(entry.status)
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

function updateLedger(ledger, requestId, status, reason, updatedAt) {
  return {
    version: LEDGER_VERSION,
    entries: ledger.entries.map((entry) => (
      entry.requestId === requestId
        ? { ...entry, status, reason, updatedAt }
        : entry
    )).slice(0, MAX_LEDGER_ENTRIES),
  };
}

function recoverInterruptedLedger(ledger, updatedAt) {
  return {
    version: LEDGER_VERSION,
    entries: ledger.entries.map((entry) => (
      ['accepted', 'running'].includes(entry.status)
        ? { ...entry, status: 'failed', reason: 'restart_uncertain', updatedAt }
        : entry
    )),
  };
}

// ---- lock / policy commit -------------------------------------------------

function releaseBusy(token) {
  if (cache.shared.get(BUSY_KEY) === token) cache.shared.remove(BUSY_KEY);
}

function nextSeq() {
  const current = Number(cache.shared.get(SEQ_KEY));
  const next = (Number.isFinite(current) ? current : 0) + 1;
  cache.shared.put(SEQ_KEY, String(next));
  return next;
}

// Owner-committed policy state via postUpdate (never a command echo), then
// persist and read-verify. OverrideSwitch is policy truth, not provider
// readback.
function commitOverrideSwitch(target) {
  const sw = items.getItem(OVERRIDE_SWITCH);
  sw.postUpdate(target);
  settleItemUpdate();
  for (let attempt = 0; attempt < SWITCH_READBACK_ATTEMPTS; attempt += 1) {
    if (String(sw.state) === target) {
      sw.persistence.persist('jdbc');
      return;
    }
    settleItemUpdate();
  }
  throw new Error('override_commit_failed');
}

// ---- restart recovery -----------------------------------------------------

// Best-effort recovery of a single ledger: a restart between accept and
// completion leaves an accepted/running entry that must never be replayed.
function recoverLedgerItem(itemName) {
  try {
    const requestItem = items.getItem(itemName);
    const ledger = parseLedger(requestItem);
    if (
      cache.shared.get(BUSY_KEY) === null
      && ledger.entries.some((entry) => ['accepted', 'running'].includes(entry.status))
    ) {
      const recovered = recoverInterruptedLedger(ledger, nowInstantText());
      writeLedger(requestItem, recovered, recovered.entries[0].requestId, recovered.entries[0].status);
    }
  } catch {
    // Recovery is non-fatal on the cross-ledger / reconcile path; the manual
    // path performs its own fatal recovery of its own ledger below.
  }
}

function reconcile() {
  recoverLedgerItem(OVERRIDE_REQUEST);
  recoverLedgerItem(DEVICE_REQUEST);
}

// ---- override transition --------------------------------------------------

function scheduleOverrideVerify(request, initialLedger, token) {
  let ledger = initialLedger;

  const fail = (rawReason) => {
    const reason = ['provider_mismatch', 'coupling_pending'].includes(rawReason)
      ? rawReason
      : 'execution_error';
    try {
      ledger = updateLedger(ledger, request.requestId, 'failed', reason, nowInstantText());
      writeLedger(items.getItem(OVERRIDE_REQUEST), ledger, request.requestId, 'failed');
    } catch {
      // The failed result remains the only safe receipt without persistence.
    }
    safeResult(OVERRIDE_RESULT, request.requestId, 'failed', reason, { command: request.command });
    releaseBusy(token);
  };

  if (request.command === 'ON') {
    // Re-poll the ON matrix. The goat cam is decoupled from the night-load
    // override (operator instruction 2026-07-22): the override never commands
    // it, so the override path neither drives nor observes FeederOverride.
    // The manual device goat-cam leg still verifies the coupling side effect.
    const probe = () => {
      if (ON_MATRIX.some(([item, value]) => state(item) !== value)) {
        return { ready: false, reason: 'provider_mismatch' };
      }
      return { ready: true };
    };
    pollVerify(probe, () => {
      try {
        ledger = updateLedger(ledger, request.requestId, 'completed', 'completed', nowInstantText());
        writeLedger(items.getItem(OVERRIDE_REQUEST), ledger, request.requestId, 'completed');
        postResult(OVERRIDE_RESULT, {
          requestId: request.requestId, command: 'ON', status: 'completed', reason: 'completed', at: nowInstantText(),
        });
        releaseBusy(token);
      } catch (error) {
        fail(error.message);
      }
    }, fail);
  } else {
    // OFF: Shureflo must be provider-confirmed ON before the OverrideSwitch OFF
    // commit. Retain ownership ON until that is proven; re-poll for a slow
    // provider before declaring a mismatch.
    const probe = () => (state('ShurefloPump_Power') === 'ON'
      ? { ready: true }
      : { ready: false, reason: 'provider_mismatch' });
    pollVerify(probe, () => {
      try {
        ledger = updateLedger(ledger, request.requestId, 'running', 'release-ready', nowInstantText());
        writeLedger(items.getItem(OVERRIDE_REQUEST), ledger, request.requestId, 'running');
        postResult(OVERRIDE_RESULT, {
          requestId: request.requestId, command: 'OFF', status: 'running', reason: 'release-ready', at: nowInstantText(),
        });
        commitOverrideSwitch('OFF');
        ledger = updateLedger(ledger, request.requestId, 'completed', 'completed', nowInstantText());
        writeLedger(items.getItem(OVERRIDE_REQUEST), ledger, request.requestId, 'completed');
        postResult(OVERRIDE_RESULT, {
          requestId: request.requestId, command: 'OFF', status: 'completed', reason: 'completed', at: nowInstantText(),
        });
        releaseBusy(token);
      } catch (error) {
        fail(error.message);
      }
    }, fail);
  }
}

function beginOverrideTransition(request, ledger, token) {
  if (request.command === 'ON') {
    // Commit policy ON (postUpdate + persist + read-verify) before commanding
    // any load, then apply the exact OFF matrix.
    commitOverrideSwitch('ON');
    for (const [item, value] of ON_MATRIX) items.getItem(item).sendCommand(value);
  } else {
    // Retain visible OverrideSwitch ON; command Shureflo ON and confirm before
    // the OFF commit happens in the verification step.
    for (const [item, value] of OFF_MATRIX) items.getItem(item).sendCommand(value);
  }
  scheduleOverrideVerify(request, ledger, token);
}

function handleOverride(triggerEvent, syntheticId) {
  const requestItem = items.getItem(OVERRIDE_REQUEST);
  const currentMs = nowMillis();
  if (!Number.isFinite(currentMs)) {
    safeResult(OVERRIDE_RESULT, syntheticId || 'unknown', 'failed', 'clock_invalid');
    return;
  }

  let request;
  if (syntheticId) {
    const command = String(triggerEvent.receivedCommand).toUpperCase();
    if (!COMMANDS.has(command)) return; // ignore junk external commands
    request = {
      requestId: syntheticId, requestedAt: nowInstantText(), requestedAtMs: currentMs, command,
    };
  } else {
    try {
      request = parseOverrideRequest(triggerEvent.receivedCommand);
    } catch (error) {
      safeResult(OVERRIDE_RESULT, 'unknown', 'failed', error.message);
      return;
    }
    if (isStale(request, currentMs)) {
      safeResult(OVERRIDE_RESULT, request.requestId, 'denied', 'request_stale');
      return;
    }
  }

  let ledger;
  try {
    ledger = parseLedger(requestItem);
  } catch (error) {
    safeResult(OVERRIDE_RESULT, request.requestId, 'denied', error.message);
    return;
  }

  // Fatal recovery of this ledger; best-effort cross recovery of the other.
  if (
    cache.shared.get(BUSY_KEY) === null
    && ledger.entries.some((entry) => ['accepted', 'running'].includes(entry.status))
  ) {
    ledger = recoverInterruptedLedger(ledger, nowInstantText());
    try {
      writeLedger(requestItem, ledger, ledger.entries[0].requestId, ledger.entries[0].status);
    } catch {
      safeResult(OVERRIDE_RESULT, request.requestId, 'denied', 'ledger_recovery_failed');
      return;
    }
  }
  recoverLedgerItem(DEVICE_REQUEST);

  if (ledger.entries.some((entry) => entry.requestId === request.requestId)) {
    safeResult(OVERRIDE_RESULT, request.requestId, 'denied', 'duplicate');
    return;
  }

  const token = `${request.requestId}:${nowText()}`;
  if (cache.shared.get(BUSY_KEY, () => token) !== token) {
    safeResult(OVERRIDE_RESULT, request.requestId, 'denied', 'busy');
    return;
  }

  ledger = acceptedLedger(ledger, request.requestId, nowInstantText());
  try {
    writeLedger(requestItem, ledger, request.requestId, 'accepted');
  } catch (error) {
    releaseBusy(token);
    safeResult(
      OVERRIDE_RESULT, request.requestId, 'failed',
      error.message === 'ledger_readback_failed' ? 'ledger_readback_failed' : 'ledger_persist_failed',
    );
    return;
  }

  try {
    postResult(OVERRIDE_RESULT, {
      requestId: request.requestId, command: request.command, status: 'accepted', reason: 'accepted', at: nowInstantText(),
    });
    postResult(OVERRIDE_RESULT, {
      requestId: request.requestId, command: request.command, status: 'running', reason: 'transitioning', at: nowInstantText(),
    });
    beginOverrideTransition(request, ledger, token);
  } catch (error) {
    const reason = error.message === 'override_commit_failed' ? 'override_commit_failed' : 'execution_error';
    try {
      ledger = updateLedger(ledger, request.requestId, 'failed', reason, nowInstantText());
      writeLedger(requestItem, ledger, request.requestId, 'failed');
    } catch {
      // The failed result remains the only safe receipt without persistence.
    }
    safeResult(OVERRIDE_RESULT, request.requestId, 'failed', reason, { command: request.command });
    releaseBusy(token);
  }
}

// ---- device transition ----------------------------------------------------

function scheduleDeviceVerify(request, initialLedger, token) {
  const providerItem = DEVICE_ITEMS[request.device];
  let ledger = initialLedger;

  const fail = (rawReason) => {
    const reason = ['provider_mismatch', 'coupling_pending'].includes(rawReason)
      ? rawReason
      : 'execution_error';
    try {
      ledger = updateLedger(ledger, request.requestId, 'failed', reason, nowInstantText());
      writeLedger(items.getItem(DEVICE_REQUEST), ledger, request.requestId, 'failed');
    } catch {
      // The failed result remains the only safe receipt without persistence.
    }
    safeResult(DEVICE_RESULT, request.requestId, 'failed', reason, {
      device: request.device, command: request.command,
    });
    releaseBusy(token);
  };

  // Re-poll the provider generation (and, for the goat cam, its FeederOverride
  // coupling) before declaring a mismatch. Goat Cam ON clears FeederOverride
  // (-> OFF); Goat Cam OFF sets it (-> ON). Completion waits for that side effect.
  const probe = () => {
    if (state(providerItem) !== request.command) return { ready: false, reason: 'provider_mismatch' };
    if (request.device === 'goat-cam') {
      const expected = request.command === 'ON' ? 'OFF' : 'ON';
      if (state(FEEDER_OVERRIDE) !== expected) return { ready: false, reason: 'coupling_pending' };
    }
    return { ready: true };
  };
  pollVerify(probe, () => {
    try {
      ledger = updateLedger(ledger, request.requestId, 'completed', 'completed', nowInstantText());
      writeLedger(items.getItem(DEVICE_REQUEST), ledger, request.requestId, 'completed');
      postResult(DEVICE_RESULT, {
        requestId: request.requestId, device: request.device, command: request.command,
        status: 'completed', reason: 'completed', at: nowInstantText(),
      });
      releaseBusy(token);
    } catch (error) {
      fail(error.message);
    }
  }, fail);
}

function handleDevice(triggerEvent) {
  const requestItem = items.getItem(DEVICE_REQUEST);
  const currentMs = nowMillis();
  if (!Number.isFinite(currentMs)) {
    safeResult(DEVICE_RESULT, 'unknown', 'failed', 'clock_invalid');
    return;
  }

  let request;
  try {
    request = parseDeviceRequest(triggerEvent.receivedCommand);
  } catch (error) {
    safeResult(DEVICE_RESULT, 'unknown', 'failed', error.message);
    return;
  }
  if (isStale(request, currentMs)) {
    safeResult(DEVICE_RESULT, request.requestId, 'denied', 'request_stale');
    return;
  }

  let ledger;
  try {
    ledger = parseLedger(requestItem);
  } catch (error) {
    safeResult(DEVICE_RESULT, request.requestId, 'denied', error.message);
    return;
  }

  if (
    cache.shared.get(BUSY_KEY) === null
    && ledger.entries.some((entry) => ['accepted', 'running'].includes(entry.status))
  ) {
    ledger = recoverInterruptedLedger(ledger, nowInstantText());
    try {
      writeLedger(requestItem, ledger, ledger.entries[0].requestId, ledger.entries[0].status);
    } catch {
      safeResult(DEVICE_RESULT, request.requestId, 'denied', 'ledger_recovery_failed');
      return;
    }
  }
  recoverLedgerItem(OVERRIDE_REQUEST);

  if (ledger.entries.some((entry) => entry.requestId === request.requestId)) {
    safeResult(DEVICE_RESULT, request.requestId, 'denied', 'duplicate');
    return;
  }

  const token = `${request.requestId}:${nowText()}`;
  if (cache.shared.get(BUSY_KEY, () => token) !== token) {
    safeResult(DEVICE_RESULT, request.requestId, 'denied', 'busy');
    return;
  }

  // A device request may command only when the override policy is exactly OFF
  // (NULL/UNDEF/ON all deny). Ownership by the override is never raced.
  if (state(OVERRIDE_SWITCH) !== 'OFF') {
    releaseBusy(token);
    safeResult(DEVICE_RESULT, request.requestId, 'denied', 'override_active', {
      device: request.device, command: request.command,
    });
    return;
  }

  // Provider health: an offline/uninitialized provider cannot be verified.
  if (NULL_STATES.has(state(DEVICE_ITEMS[request.device]))) {
    releaseBusy(token);
    safeResult(DEVICE_RESULT, request.requestId, 'denied', 'provider_offline', {
      device: request.device, command: request.command,
    });
    return;
  }

  ledger = acceptedLedger(ledger, request.requestId, nowInstantText());
  try {
    writeLedger(requestItem, ledger, request.requestId, 'accepted');
  } catch (error) {
    releaseBusy(token);
    safeResult(
      DEVICE_RESULT, request.requestId, 'failed',
      error.message === 'ledger_readback_failed' ? 'ledger_readback_failed' : 'ledger_persist_failed',
      { device: request.device, command: request.command },
    );
    return;
  }

  try {
    postResult(DEVICE_RESULT, {
      requestId: request.requestId, device: request.device, command: request.command,
      status: 'accepted', reason: 'accepted', at: nowInstantText(),
    });
    postResult(DEVICE_RESULT, {
      requestId: request.requestId, device: request.device, command: request.command,
      status: 'running', reason: 'commanded', at: nowInstantText(),
    });
    items.getItem(DEVICE_ITEMS[request.device]).sendCommand(request.command);
    scheduleDeviceVerify(request, ledger, token);
  } catch (error) {
    try {
      ledger = updateLedger(ledger, request.requestId, 'failed', 'execution_error', nowInstantText());
      writeLedger(requestItem, ledger, request.requestId, 'failed');
    } catch {
      // The failed result remains the only safe receipt without persistence.
    }
    safeResult(DEVICE_RESULT, request.requestId, 'failed', 'execution_error', {
      device: request.device, command: request.command,
    });
    releaseBusy(token);
  }
}

// ---- entry ----------------------------------------------------------------

function runNightLoadOwner(triggerEvent) {
  if (!triggerEvent || typeof triggerEvent.itemName !== 'string') {
    reconcile();
    return;
  }
  const { itemName } = triggerEvent;
  if (itemName === OVERRIDE_REQUEST && typeof triggerEvent.receivedCommand === 'string') {
    handleOverride(triggerEvent, null);
    return;
  }
  if (itemName === DEVICE_REQUEST && typeof triggerEvent.receivedCommand === 'string') {
    handleDevice(triggerEvent);
    return;
  }
  if (itemName === OVERRIDE_SWITCH && typeof triggerEvent.receivedCommand === 'string') {
    const command = String(triggerEvent.receivedCommand).toUpperCase();
    handleOverride(triggerEvent, `override-switch:${command}:${nowMillis()}:${nextSeq()}`);
    return;
  }
  reconcile();
}

runNightLoadOwner(typeof event === 'undefined' ? null : event);
