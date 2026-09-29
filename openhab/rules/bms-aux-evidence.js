'use strict';
// Observation only. Only original events from the two Discover BMS Modbus
// channels can renew these fields; Item carries and derived values cannot.
const { items, things, cache } = require('openhab');
const Instant = Java.type('java.time.Instant');
const UUID = Java.type('java.util.UUID');
const ZonedDateTime = Java.type('java.time.ZonedDateTime');
const Persistence = Java.type('org.openhab.core.persistence.extensions.PersistenceExtensions');

const OUTPUT = 'BMS_Aux_Evidence_JSON';
const POLLER = 'modbus:poller:discoverBms190:bmsMain';
const BRIDGE = 'modbus:tcp:discoverBms190';
const SPECS = {
  'battery.remaining_ah': {
    item: 'BMS_Capacity_Remaining_Ah',
    thing: 'modbus:data:discoverBms190:bmsMain:capRemainAh',
    eventKey: 'capacity.event', min: 0, max: 450,
  },
  'battery.temperature_raw': {
    item: 'BMS_Temperature_Raw',
    thing: 'modbus:data:discoverBms190:bmsMain:tempRaw',
    eventKey: 'temperature.event', min: 23300, max: 33855,
  },
};
const FIELDS = Object.keys(SPECS);
const TTL = 120000;
const PUBLISH_MS = 60000;
const KEY = 'earthship.bms-aux-evidence.v1';
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

function healthy(uid) {
  try {
    const thing = things.getThing(uid);
    return thing && String(thing.status) === 'ONLINE';
  } catch (_) { return false; }
}
function invalidate(field, reason) {
  const slot = state.fields[field];
  slot.value = null;
  slot.reason = reason;
  slot.water = Math.max(slot.water, now);
}
function original(input) {
  try {
    if (input && typeof input.getItemName === 'function') return input;
    if (!input || !input.raw || typeof input.raw.get !== 'function') return null;
    const matches = FIELDS.map(field => SPECS[field].eventKey)
      .filter(key => input.raw.get(key) !== null && input.raw.get(key) !== undefined);
    if (matches.length !== 1) return null;
    return input.raw.get(matches[0]);
  } catch (_) { return null; }
}
function accept(raw) {
  const name = raw && typeof raw.getItemName === 'function'
    ? String(raw.getItemName()) : null;
  const field = FIELDS.find(key => SPECS[key].item === name);
  if (!field || !state.fields[field].ready) return;
  const spec = SPECS[field];
  try {
    if (String(raw.getType()) !== 'ItemStateEvent'
        || String(raw.getTopic()) !== `openhab/items/${spec.item}/state`
        || String(raw.getSource()) !== `org.openhab.core.thing$${spec.thing}:number`) {
      throw new Error('untrusted source event');
    }
    const text = String(raw.getItemState());
    if (!/^(0|[1-9][0-9]{0,5})$/.test(text)) throw new Error('noncanonical number');
    const value = Number(text);
    if (!Number.isSafeInteger(value) || value < spec.min || value > spec.max) {
      throw new Error('out-of-range number');
    }
    const slot = state.fields[field];
    if (now === slot.water && slot.value && value !== slot.value.raw) {
      throw new Error('conflicting equal-time report');
    }
    if (now <= slot.floor || now <= slot.water) return;
    slot.water = now;
    slot.value = { observedAt: now, raw: value };
    slot.reason = 'ok';
  } catch (_) { invalidate(field, 'invalid_input'); }
}

for (const field of FIELDS) {
  const slot = state.fields[field];
  const ready = healthy(BRIDGE) && healthy(POLLER) && healthy(SPECS[field].thing);
  if (!ready) invalidate(field, 'source_unavailable');
  else if (!slot.ready) {
    slot.floor = now;
    invalidate(field, 'input_unavailable');
  }
  slot.ready = ready;
}
const input = typeof event === 'undefined' ? null : event;
const raw = original(input);
if (raw) accept(raw);
else if (input && FIELDS.some(field => input.itemName === SPECS[field].item)) {
  invalidate(FIELDS.find(field => input.itemName === SPECS[field].item), 'invalid_input');
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
const next = { version: 1, basis: 'discover_bms_190_native_aux_v1',
  streamEpoch: state.epoch, sequence: state.sequence + 1,
  recordedAt: now, fields };
const previous = state.lastPublished;
const changed = !previous || FIELDS.some(field =>
  previous.fields[field].status !== fields[field].status
  || previous.fields[field].reason !== fields[field].reason
  || previous.fields[field].value !== fields[field].value);
const due = previous && now - previous.recordedAt >= PUBLISH_MS
  && FIELDS.some(field => fields[field].status === 'valid');
if (changed || due) {
  // A failed/ambiguous enqueue consumes identity; a later gap fails closed.
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
  } catch (_) { console.warn('BMS auxiliary evidence persistence enqueue failed'); }
}
if (state.pendingPost) {
  try {
    items.getItem(OUTPUT).postUpdate(state.pendingPost);
    state.pendingPost = null;
  } catch (_) { console.warn('BMS auxiliary evidence state publication failed'); }
}
cache.private.put(KEY, state);
