'use strict';
// Source-bound observation of the native MPPT60 daily PV counter. This does
// not assert a completed-day kWh total or change forecast calibration.
const { items, things, cache } = require('openhab');
const Instant = Java.type('java.time.Instant');
const UUID = Java.type('java.util.UUID');
const ZonedDateTime = Java.type('java.time.ZonedDateTime');
const Persistence = Java.type('org.openhab.core.persistence.extensions.PersistenceExtensions');

const SOURCE_ITEM = 'MPPT60_PV_Day_Observation_JSON';
const OUTPUT_ITEM = 'MPPT60_PV_Day_Evidence_JSON';
const DATA_THING = 'modbus:data:9eb978a141:mppt60Energy:energyFromPVTodayWh';
const POLLER = 'modbus:poller:9eb978a141:mppt60Energy';
const BRIDGE = 'modbus:tcp:9eb978a141';
const CHANNEL = `${DATA_THING}:number`;
const FIELD = 'mppt60.pv_day_wh';
const TTL = 90000; // Three 30-second polls; a missed unchanged poll is not fresh evidence.
const PUBLISH_MS = 60000;
const KEY = 'earthship.mppt60-pv-day-evidence.v1';
const now = Number(Instant.now().toEpochMilli());

let state = cache.private.get(KEY);
if (!state || now < state.lastNow) {
  state = { epoch: UUID.randomUUID().toString(), floor: now, lastNow: now,
    water: -1, value: null, reason: 'input_unavailable', sourceReady: false,
    sequence: 0, lastPublished: null };
}
state.lastNow = now;

function healthy() {
  try {
    return [DATA_THING, POLLER, BRIDGE].every(uid => {
      const thing = things.getThing(uid);
      return thing && String(thing.status) === 'ONLINE';
    });
  } catch (_) { return false; }
}
function invalidate(reason) {
  state.value = null;
  state.reason = reason;
  state.water = Math.max(state.water, now);
}
function original(input) {
  try {
    if (input && typeof input.getItemName === 'function') return { raw: input, invalid: false };
    if (input && input.raw && typeof input.raw.get === 'function') {
      const keys = ['pv.event', 'event'].filter(key =>
        typeof input.raw.containsKey === 'function' ? input.raw.containsKey(key)
          : typeof input.raw.has === 'function' ? input.raw.has(key)
            : input.raw.get(key) !== null && input.raw.get(key) !== undefined);
      if (keys.length > 1) return { raw: null, invalid: true };
      if (keys.length === 1) return { raw: input.raw.get(keys[0]), invalid: true };
    }
    return { raw: null, invalid: Boolean(input && input.itemName === SOURCE_ITEM) };
  } catch (_) { return { raw: null, invalid: true }; }
}
function accept(raw) {
  try {
    if (!raw || String(raw.getItemName()) !== SOURCE_ITEM
        || String(raw.getType()) !== 'ItemStateEvent'
        || String(raw.getTopic()) !== `openhab/items/${SOURCE_ITEM}/state`
        || String(raw.getSource()) !== `org.openhab.core.thing$${CHANNEL}`) {
      throw new Error('untrusted event');
    }
    const body = String(raw.getItemState());
    if (body.length > 1024) throw new Error('oversized event');
    const receipt = JSON.parse(body);
    const keys = ['version', 'field', 'observedAt', 'value'];
    if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)
        || Object.keys(receipt).length !== keys.length
        || !keys.every(key => Object.hasOwn(receipt, key))
        || receipt.version !== 1 || receipt.field !== FIELD
        || !Number.isSafeInteger(receipt.observedAt) || receipt.observedAt <= 0
        || receipt.observedAt > now || typeof receipt.value !== 'string'
        || body !== JSON.stringify(receipt)) throw new Error('invalid envelope');
    const at = receipt.observedAt;
    if (at === state.water && state.value && receipt.value !== state.value.raw) {
      throw new Error('conflicting equal-time receipt');
    }
    if (at <= state.floor || at <= state.water) return;
    if (now - at >= TTL || !/^(0|[1-9][0-9]{0,5})$/.test(receipt.value)) {
      throw new Error('expired or noncanonical Wh value');
    }
    const wh = Number(receipt.value);
    if (!Number.isSafeInteger(wh) || wh > 100000) throw new Error('out of range');
    state.water = at;
    state.value = { observedAt: at, wh, raw: receipt.value };
    state.reason = 'ok';
  } catch (_) { invalidate('invalid_input'); }
}

const sourceReady = healthy();
if (!sourceReady) {
  invalidate('source_unavailable');
} else {
  if (!state.sourceReady) {
    state.floor = now;
    invalidate('input_unavailable');
  }
  const decoded = original(typeof event === 'undefined' ? null : event);
  if (decoded.invalid && !decoded.raw) invalidate('invalid_input');
  else if (decoded.raw) accept(decoded.raw);
}
state.sourceReady = sourceReady;

const fresh = sourceReady && state.value && state.value.observedAt <= now
  && now - state.value.observedAt < TTL;
const field = fresh
  ? { status: 'valid', reason: 'ok', observedAt: state.value.observedAt,
    validUntil: state.value.observedAt + TTL, wh: state.value.wh }
  : { status: 'unavailable', reason: !sourceReady ? 'source_unavailable'
    : state.value ? 'input_stale' : state.reason,
    observedAt: null, validUntil: null, wh: null };
const next = { version: 1, basis: 'mppt60_native_pv_day_wh', streamEpoch: state.epoch,
  sequence: state.sequence + 1, recordedAt: now, fields: { [FIELD]: field } };
const previous = state.lastPublished;
const changed = !previous || previous.fields[FIELD].status !== field.status
  || previous.fields[FIELD].reason !== field.reason || previous.fields[FIELD].wh !== field.wh;
const due = field.status === 'valid' && previous && now - previous.recordedAt >= PUBLISH_MS;
if (changed || due) {
  // Consume identity on ambiguous enqueue; a missing publication is a barrier.
  state.sequence = next.sequence;
  state.pendingPost = null;
  try {
    const output = items.getItem(OUTPUT_ITEM);
    const encoded = JSON.stringify(next);
    let stamp = ZonedDateTime.now();
    stamp = stamp.withNano(Math.floor(stamp.getNano() / 1000000) * 1000000);
    if (state.lastPersistenceAt && !stamp.isAfter(state.lastPersistenceAt)) {
      stamp = state.lastPersistenceAt.plusNanos(1000000);
    }
    state.lastPersistenceAt = stamp;
    Persistence.persist(output.rawItem, stamp, encoded, 'jdbc');
    state.lastPublished = next;
    state.pendingPost = encoded;
  } catch (_) { console.warn('MPPT60 PV evidence persistence enqueue failed'); }
}
if (state.pendingPost) {
  try {
    items.getItem(OUTPUT_ITEM).postUpdate(state.pendingPost);
    state.pendingPost = null;
  } catch (_) { console.warn('MPPT60 PV evidence state publication failed'); }
}
cache.private.put(KEY, state);
