'use strict';

const { actions, cache, items, time } = require('openhab');

const EARTHSHIP_FEEDER_OWNER_VERSION = 'feeder-request-v1';
const LEDGER_VERSION = 'feeder-request-ledger/v1';
const REQUEST_ITEM = 'GoatFeeder_ManualRequest';
const RESULT_ITEM = 'GoatFeeder_ManualResult';
const ACTUATOR_ITEM = 'Goat_Plugs_Outlet2_Switch';
const COUNTER_ITEM = 'GoatFeedings';
const BUSY_KEY = 'earthship.feeder-owner.busy';
const LAST_START_KEY = 'earthship.feeder-owner.last-start-ms';
const MAX_LEDGER_BYTES = 8192;
const MAX_LEDGER_ENTRIES = 32;
const COOLDOWN_MS = 5000;
const MAX_REQUEST_AGE_MS = 2 * 60 * 1000;
const MAX_REQUEST_FUTURE_SKEW_MS = 30 * 1000;
const LEDGER_READBACK_ATTEMPTS = 20;
const LEDGER_READBACK_POLL_MS = 50;
const NULL_STATES = new Set(['NULL', 'UNDEF']);
const TERMINAL_STATUSES = new Set(['complete', 'failed', 'denied']);

function now() {
  return time.ZonedDateTime.now();
}

function nowText() {
  return now().toString();
}

// UTC instant string (ends in 'Z'); strict-parseable by real Instant.parse().
// All durable ledger and result timestamps are written in this form so that a
// production readback never re-parses a bracketed ZonedDateTime rendering.
function nowInstantText() {
  return now().toInstant().toString();
}

function nowMillis() {
  return epochMillis(now());
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

function postResult(requestId, status, reason, at = nowInstantText()) {
  items.getItem(RESULT_ITEM).postUpdate(JSON.stringify({
    requestId,
    status,
    reason,
    at,
  }));
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
  if (
    (typeof parsed.requestedAt !== 'string' || !Number.isFinite(epochMillis(parsed.requestedAt)))
  ) {
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
    && ['accepted', 'running', ...TERMINAL_STATUSES].includes(entry.status)
    && typeof entry.reason === 'string'
    && typeof entry.at === 'string'
    && Number.isFinite(epochMillis(entry.at))
    && (entry.updatedAt === undefined || (
      typeof entry.updatedAt === 'string' && Number.isFinite(epochMillis(entry.updatedAt))
    ))
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
    }, ...ledger.entries.filter((entry) => entry.requestId !== requestId)].slice(0, MAX_LEDGER_ENTRIES),
  };
}

function terminalLedger(ledger, requestId, status, reason, updatedAt) {
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

function releaseBusy(token) {
  if (cache.shared.get(BUSY_KEY) === token) cache.shared.remove(BUSY_KEY);
}

function safeOff(actuator) {
  if (!actuator) return;
  try {
    actuator.sendCommand('OFF');
  } catch {
    // The preserved one-second expire metadata is the independent OFF backstop.
  }
}

function safeResult(requestId, status, reason) {
  try {
    postResult(requestId, status, reason);
  } catch {
    // The durable request ledger remains the authoritative receipt.
  }
}

function runFeederOwner(triggerEvent) {
  const isManual = Boolean(
    triggerEvent
    && triggerEvent.itemName === REQUEST_ITEM
    && typeof triggerEvent.receivedCommand === 'string'
  );
  const requestItem = items.getItem(REQUEST_ITEM);
  let request = null;
  let ledger = null;
  const currentMs = nowMillis();
  if (!Number.isFinite(currentMs)) {
    if (isManual) safeResult('unknown', 'failed', 'clock_invalid');
    return;
  }

  if (isManual) {
    try {
      request = parseRequest(triggerEvent.receivedCommand);
    } catch (error) {
      safeResult('unknown', 'denied', error.message);
      return;
    }
    if (
      request.requestedAtMs !== null
      && (
        currentMs - request.requestedAtMs > MAX_REQUEST_AGE_MS
        || request.requestedAtMs - currentMs > MAX_REQUEST_FUTURE_SKEW_MS
      )
    ) {
      safeResult(request.requestId, 'denied', 'request_stale');
      return;
    }
  }

  try {
    ledger = parseLedger(requestItem);
  } catch (error) {
    if (isManual) safeResult(request.requestId, 'denied', error.message);
    return;
  }
  if (
    cache.shared.get(BUSY_KEY) === null
    && ledger.entries.some((entry) => ['accepted', 'running'].includes(entry.status))
  ) {
    ledger = recoverInterruptedLedger(ledger, nowInstantText());
    try {
      writeLedger(
        requestItem,
        ledger,
        ledger.entries[0].requestId,
        ledger.entries[0].status,
      );
    } catch {
      if (isManual) safeResult(request.requestId, 'denied', 'ledger_recovery_failed');
      return;
    }
    if (!isManual) return;
  }
  if (isManual) {
    if (ledger.entries.some((entry) => entry.requestId === request.requestId)) {
      safeResult(request.requestId, 'denied', 'duplicate');
      return;
    }
  }

  const invocationToken = `${isManual ? request.requestId : 'legacy'}:${nowText()}`;
  const owner = cache.shared.get(BUSY_KEY, () => invocationToken);
  if (owner !== invocationToken) {
    if (isManual) safeResult(request.requestId, 'denied', 'busy');
    return;
  }

  const volatileStartMs = Number(cache.shared.get(LAST_START_KEY));
  const durableStartMs = ledger.entries.length > 0
    ? epochMillis(ledger.entries[0].at)
    : Number.NaN;
  const lastStartMs = Math.max(
    Number.isFinite(volatileStartMs) ? volatileStartMs : Number.NEGATIVE_INFINITY,
    Number.isFinite(durableStartMs) ? durableStartMs : Number.NEGATIVE_INFINITY,
  );
  if (currentMs - lastStartMs < COOLDOWN_MS) {
    releaseBusy(invocationToken);
    if (isManual) safeResult(request.requestId, 'denied', 'cooldown');
    return;
  }

  if (isManual) {
    const acceptedAt = nowInstantText();
    ledger = acceptedLedger(ledger, request.requestId, acceptedAt);
    try {
      writeLedger(requestItem, ledger, request.requestId, 'accepted');
    } catch (error) {
      releaseBusy(invocationToken);
      safeResult(request.requestId, 'failed', error.message === 'ledger_readback_failed'
        ? 'ledger_readback_failed'
        : 'ledger_persist_failed');
      return;
    }
  }

  let actuator = null;
  let counter = null;
  let counterBefore = Number.NaN;
  try {
    if (isManual) {
      postResult(request.requestId, 'accepted', 'accepted');
      postResult(request.requestId, 'running', 'pulse_started');
    }
    actuator = items.getItem(ACTUATOR_ITEM);
    counter = items.getItem(COUNTER_ITEM);
    counterBefore = Number(counter.state.toString());
    if (!Number.isFinite(counterBefore)) throw new Error('counter_invalid');
    cache.shared.put(LAST_START_KEY, String(currentMs));
    actuator.sendCommand('ON');

    actions.ScriptExecution.createTimer(now().plusSeconds(1), () => {
      try {
        actuator.sendCommand('OFF');
        if (Number(counter.state.toString()) !== counterBefore) {
          throw new Error('counter_changed');
        }
        counter.postUpdate(String(counterBefore + 1));
        settleItemUpdate();
        if (Number(counter.state.toString()) !== counterBefore + 1) {
          throw new Error('counter_receipt_failed');
        }

        if (isManual) {
          ledger = terminalLedger(ledger, request.requestId, 'complete', 'complete', nowInstantText());
          writeLedger(requestItem, ledger, request.requestId, 'complete');
          postResult(request.requestId, 'complete', 'complete');
        }
      } catch {
        if (isManual) {
          try {
            ledger = terminalLedger(
              ledger,
              request.requestId,
              'failed',
              'execution_error',
              nowInstantText(),
            );
            writeLedger(requestItem, ledger, request.requestId, 'failed');
          } catch {
            // The matching failed result remains the only safe receipt if persistence is unavailable.
          }
          safeResult(request.requestId, 'failed', 'execution_error');
        }
      } finally {
        safeOff(actuator);
        releaseBusy(invocationToken);
      }
    });
  } catch {
    safeOff(actuator);
    if (isManual) {
      try {
        ledger = terminalLedger(ledger, request.requestId, 'failed', 'execution_error', nowInstantText());
        writeLedger(requestItem, ledger, request.requestId, 'failed');
      } catch {
        // The matching failed result remains the only safe receipt if persistence is unavailable.
      }
      safeResult(request.requestId, 'failed', 'execution_error');
    }
    releaseBusy(invocationToken);
  }
}

runFeederOwner(typeof event === 'undefined' ? null : event);
