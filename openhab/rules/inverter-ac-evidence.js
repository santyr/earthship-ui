'use strict';
// Independent, observational inverter-output evidence. Never infer total
// household load or change the existing three-field Power_Evidence_JSON stream.
const { items, things, cache } = require('openhab');
const Instant = Java.type('java.time.Instant');
const UUID = Java.type('java.util.UUID');
const ZonedDateTime = Java.type('java.time.ZonedDateTime');
const Persistence = Java.type('org.openhab.core.persistence.extensions.PersistenceExtensions');

const SOURCE_ITEM = 'Inverter_AC_Output_Observation_JSON';
const OUTPUT_ITEM = 'Inverter_AC_Evidence_JSON';
const INVERTER = 'modbus:inverter-split-phase:1ed74db72c:e853aec444';
const BRIDGE = 'modbus:tcp:1ed74db72c';
const CHANNEL = `${INVERTER}:acGeneral#ac-power`;
const FIELD = 'inverter.ac_output_w';
const TTL = 30000;
const KEY = 'earthship.inverter-ac-evidence.v1';
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
    return [INVERTER, BRIDGE].every(uid => {
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
      const keys = ['ac.event', 'event'].filter(key =>
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
    if (now - at >= TTL || !/^(0|[1-9][0-9]{0,4}) W$/.test(receipt.value)) {
      throw new Error('expired or noncanonical Watt value');
    }
    const watts = Number(receipt.value.slice(0, -2));
    if (!Number.isSafeInteger(watts) || watts > 20000) throw new Error('out of range');
    state.water = at;
    state.value = { observedAt: at, watts, raw: receipt.value };
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
    validUntil: state.value.observedAt + TTL, watts: state.value.watts }
  : { status: 'unavailable', reason: !sourceReady ? 'source_unavailable'
    : state.value ? 'input_stale' : state.reason,
    observedAt: null, validUntil: null, watts: null };
const next = { version: 1, basis: 'inverter_output', streamEpoch: state.epoch,
  sequence: state.sequence + 1, recordedAt: now, fields: { [FIELD]: field } };
if (!state.lastPublished || JSON.stringify(state.lastPublished.fields) !== JSON.stringify(next.fields)) {
  // Consume identity on ambiguous enqueue; a missing publication is a barrier.
  state.sequence = next.sequence;
  // A newer barrier supersedes any older UI post that failed previously.
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
    // Exclude this Item from automatic change persistence before activation.
    Persistence.persist(output.rawItem, stamp, encoded, 'jdbc');
    state.lastPublished = next;
    state.pendingPost = encoded;
  } catch (_) { console.warn('Inverter AC evidence persistence enqueue failed'); }
}
if (state.pendingPost) {
  try {
    items.getItem(OUTPUT_ITEM).postUpdate(state.pendingPost);
    state.pendingPost = null;
  } catch (_) { console.warn('Inverter AC evidence state publication failed'); }
}
cache.private.put(KEY, state);
