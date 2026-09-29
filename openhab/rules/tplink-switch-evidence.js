'use strict';
// Observational only: no switch commands. An unchanged channel update is
// evidence only when its original ItemStateEvent came from the exact Thing.
const { items, things, cache } = require('openhab');
const Instant = Java.type('java.time.Instant');
const UUID = Java.type('java.util.UUID');
const ZonedDateTime = Java.type('java.time.ZonedDateTime');
const Persistence = Java.type('org.openhab.core.persistence.extensions.PersistenceExtensions');

const OUTPUT = 'TPLink_Switch_Evidence_JSON';
const SPECS = {
  'load.dishwasher_state': {
    item: 'Dishwasher_Switch_Observation_JSON',
    thing: 'tplinksmarthome:hs103:a34b4957dc',
    channel: 'tplinksmarthome:hs103:a34b4957dc:switch',
    eventKey: 'dishwasher.event',
  },
  'load.shurflo_pump_state': {
    item: 'Cistern_Pump_Switch_Observation_JSON',
    thing: 'tplinksmarthome:hs103:08482dd378',
    channel: 'tplinksmarthome:hs103:08482dd378:switch',
    eventKey: 'cistern.event',
  },
};
const FIELDS = Object.keys(SPECS);
const TTL = 95000; // Three nominal 30-second polls plus bounded scheduler jitter.
const PUBLISH_MS = 60000;
const KEY = 'earthship.tplink-switch-evidence.v2';
const now = Number(Instant.now().toEpochMilli());

function newField() {
  return { floor: now, water: -1, ready: false, value: null,
    reason: 'input_unavailable' };
}
let state = cache.private.get(KEY);
if (!state || now < state.lastNow) {
  state = { epoch: UUID.randomUUID().toString(), lastNow: now, sequence: 0,
    fields: Object.fromEntries(FIELDS.map(field => [field, newField()])),
    lastPublished: null, pendingPost: null };
}
state.lastNow = now;

function invalidate(field, reason) {
  const slot = state.fields[field];
  slot.value = null;
  slot.reason = reason;
  slot.water = Math.max(slot.water, now);
}
function healthy(thingUID) {
  try {
    const thing = things.getThing(thingUID);
    return thing && String(thing.status) === 'ONLINE';
  } catch (_) { return false; }
}
function original(input) {
  try {
    if (input && typeof input.getItemName === 'function') return input;
    if (!input || !input.raw || typeof input.raw.get !== 'function') return null;
    const keys = FIELDS.map(field => SPECS[field].eventKey)
      .filter(key => input.raw.get(key) !== null && input.raw.get(key) !== undefined);
    if (keys.length !== 1) return null;
    return input.raw.get(keys[0]);
  } catch (_) { return null; }
}
function accept(raw) {
  const itemName = raw && typeof raw.getItemName === 'function'
    ? String(raw.getItemName()) : null;
  const field = FIELDS.find(name => SPECS[name].item === itemName);
  if (!field) return;
  const spec = SPECS[field];
  if (!state.fields[field].ready) return;
  try {
    if (String(raw.getType()) !== 'ItemStateEvent'
        || String(raw.getTopic()) !== `openhab/items/${spec.item}/state`
        || String(raw.getSource()) !== `org.openhab.core.thing$${spec.channel}`) {
      throw new Error('untrusted event');
    }
    const body = String(raw.getItemState());
    if (body.length > 256) throw new Error('oversized event');
    const receipt = JSON.parse(body);
    const keys = ['version', 'observedAt', 'value'];
    if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)
        || Object.keys(receipt).length !== keys.length
        || !keys.every(key => Object.hasOwn(receipt, key))
        || receipt.version !== 1 || !Number.isSafeInteger(receipt.observedAt)
        || receipt.observedAt <= 0 || receipt.observedAt > now
        || body !== JSON.stringify(receipt)
        || !['ON', 'OFF'].includes(receipt.value)) {
      throw new Error('invalid envelope');
    }
    const slot = state.fields[field];
    const at = receipt.observedAt;
    if (at === slot.water && slot.value && receipt.value !== slot.value.raw) {
      throw new Error('conflicting equal-time receipt');
    }
    if (at <= slot.floor || at <= slot.water) return;
    if (now - at >= TTL) throw new Error('expired receipt');
    slot.water = at;
    slot.value = { observedAt: at, raw: receipt.value };
    slot.reason = 'ok';
  } catch (_) { invalidate(field, 'invalid_input'); }
}

for (const field of FIELDS) {
  const slot = state.fields[field];
  const ready = healthy(SPECS[field].thing);
  if (!ready) invalidate(field, 'source_unavailable');
  else if (!slot.ready) {
    slot.floor = now;
    invalidate(field, 'input_unavailable');
  }
  slot.ready = ready;
}
const raw = original(typeof event === 'undefined' ? null : event);
if (raw) accept(raw);
else if (typeof event !== 'undefined' && event
         && FIELDS.some(field => event.itemName === SPECS[field].item)) {
  invalidate(FIELDS.find(field => event.itemName === SPECS[field].item), 'invalid_input');
}

const fields = {};
for (const field of FIELDS) {
  const slot = state.fields[field];
  const fresh = slot.ready && slot.value && slot.value.observedAt <= now
    && now - slot.value.observedAt < TTL;
  fields[field] = fresh
    ? { status: 'valid', reason: 'ok', observedAt: slot.value.observedAt,
      validUntil: slot.value.observedAt + TTL, value: slot.value.raw }
    : { status: 'unavailable', reason: !slot.ready ? 'source_unavailable'
      : slot.value ? 'input_stale' : slot.reason,
      observedAt: null, validUntil: null, value: null };
}
const next = { version: 2, basis: 'tplink_hs103_switch_report_v1',
  streamEpoch: state.epoch, sequence: state.sequence + 1, recordedAt: now,
  fields };
const previous = state.lastPublished;
const changed = !previous || FIELDS.some(field =>
  previous.fields[field].status !== fields[field].status
  || previous.fields[field].reason !== fields[field].reason
  || previous.fields[field].value !== fields[field].value);
const due = previous && now - previous.recordedAt >= PUBLISH_MS
  && FIELDS.some(field => fields[field].status === 'valid');
if (changed || due) {
  // An ambiguous persistence enqueue consumes a sequence number; never retry
  // it as if it were a continuous stream.
  state.sequence = next.sequence;
  state.pendingPost = null;
  try {
    const output = items.getItem(OUTPUT);
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
  } catch (_) { console.warn('TP-Link switch evidence persistence enqueue failed'); }
}
if (state.pendingPost) {
  try {
    items.getItem(OUTPUT).postUpdate(state.pendingPost);
    state.pendingPost = null;
  } catch (_) { console.warn('TP-Link switch evidence state publication failed'); }
}
cache.private.put(KEY, state);
