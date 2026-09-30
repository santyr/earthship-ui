'use strict';
// Source-bound, observational inputs for the display-only runtime estimator.
// The source Items remain unchanged; this rule never commands hardware.
const { items, things, cache } = require('openhab');
const Instant = Java.type('java.time.Instant');
const UUID = Java.type('java.util.UUID');
const ZonedDateTime = Java.type('java.time.ZonedDateTime');
const Persistence = Java.type('org.openhab.core.persistence.extensions.PersistenceExtensions');

const OUTPUT = 'BMS_Runtime_Input_Evidence_JSON';
const KEY = 'earthship.bms-runtime-input-evidence.v1';
const PUBLISH_MS = 30000;
const now = Number(Instant.now().toEpochMilli());
const SOURCES = {
  'battery.dc_current_ca': {
    item: 'DCData_Native_Current_Raw_cA', eventKey: 'current.event',
    thing: 'modbus:data:schneiderBatterySunSpec:battery802Core:currentRawCentiA',
    poller: 'modbus:poller:schneiderBatterySunSpec:battery802Core',
    bridge: 'modbus:tcp:schneiderBatterySunSpec', min: -32767, max: 32767, ttl: 90000,
  },
  'battery.dc_voltage_cv': {
    item: 'DCData_Native_Voltage_Raw_cV', eventKey: 'voltage.event',
    thing: 'modbus:data:schneiderBatterySunSpec:battery802Core:voltageRawCentiV',
    poller: 'modbus:poller:schneiderBatterySunSpec:battery802Core',
    bridge: 'modbus:tcp:schneiderBatterySunSpec', min: 4000, max: 6500, ttl: 90000,
  },
  'battery.ttd_min': {
    item: 'BMS_TimeToDischarge_Min', eventKey: 'ttd.event',
    thing: 'modbus:data:discoverBms190:bmsMain:ttdMin',
    poller: 'modbus:poller:discoverBms190:bmsMain',
    bridge: 'modbus:tcp:discoverBms190', min: 0, max: 100000, ttl: 120000,
  },
  'battery.ttf_min': {
    item: 'BMS_TimeToFull_Min', eventKey: 'ttf.event',
    thing: 'modbus:data:discoverBms190:bmsMain:ttfMin',
    poller: 'modbus:poller:discoverBms190:bmsMain',
    bridge: 'modbus:tcp:discoverBms190', min: 0, max: 100000, ttl: 120000,
  },
};
const FIELDS = Object.keys(SOURCES);

function newSlot() {
  return { floor: now, water: -1, ready: false, value: null, reason: 'input_unavailable' };
}
let state = cache.private.get(KEY);
if (!state || now < state.lastNow) {
  state = { epoch: UUID.randomUUID().toString(), lastNow: now, sequence: 0,
    fields: Object.fromEntries(FIELDS.map(field => [field, newSlot()])),
    lastPublished: null, pendingPost: null };
}
state.lastNow = now;

function online(uid) {
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
    if (input && typeof input.getItemName === 'function') return { raw: input, invalid: [] };
    if (!input || !input.raw || typeof input.raw.get !== 'function') {
      return { raw: null, invalid: [] };
    }
    const matched = FIELDS.filter(field => {
      const key = SOURCES[field].eventKey;
      return typeof input.raw.containsKey === 'function'
        ? Boolean(input.raw.containsKey(key))
        : typeof input.raw.has === 'function' ? input.raw.has(key)
          : input.raw.get(key) !== null && input.raw.get(key) !== undefined;
    });
    if (matched.length !== 1) return { raw: null, invalid: matched };
    const raw = input.raw.get(SOURCES[matched[0]].eventKey);
    return raw ? { raw, invalid: [] } : { raw: null, invalid: matched };
  } catch (_) { return { raw: null, invalid: [...FIELDS] }; }
}
function accept(raw) {
  const name = raw && typeof raw.getItemName === 'function'
    ? String(raw.getItemName()) : null;
  const field = FIELDS.find(key => SOURCES[key].item === name);
  if (!field || !state.fields[field].ready) return;
  const spec = SOURCES[field];
  try {
    if (String(raw.getType()) !== 'ItemStateEvent'
        || String(raw.getTopic()) !== `openhab/items/${spec.item}/state`
        || String(raw.getSource()) !== `org.openhab.core.thing$${spec.thing}:number`) {
      throw new Error('untrusted original event');
    }
    const valueText = String(raw.getItemState());
    if (!/^(0|-[1-9][0-9]*|[1-9][0-9]*)$/.test(valueText)) {
      throw new Error('noncanonical native value');
    }
    const value = Number(valueText);
    if (!Number.isSafeInteger(value) || value < spec.min || value > spec.max) {
      throw new Error('out-of-range native value');
    }
    const slot = state.fields[field];
    if (now <= slot.floor || now <= slot.water) return;
    slot.water = now;
    slot.value = { observedAt: now, raw: value };
    slot.reason = 'ok';
    return field;
  } catch (_) { invalidate(field, 'invalid_input'); }
}

for (const field of FIELDS) {
  const spec = SOURCES[field];
  const slot = state.fields[field];
  const ready = online(spec.bridge) && online(spec.poller) && online(spec.thing);
  if (!ready) invalidate(field, 'source_unavailable');
  else if (!slot.ready) {
    slot.floor = now;
    invalidate(field, 'input_unavailable');
  }
  slot.ready = ready;
}
const input = typeof event === 'undefined' ? null : event;
const decoded = original(input);
for (const field of decoded.invalid) invalidate(field, 'invalid_input');
const acceptedField = decoded.raw ? accept(decoded.raw) : null;
if (!decoded.raw && !decoded.invalid.length && input
    && FIELDS.some(field => input.itemName === SOURCES[field].item)) {
  invalidate(FIELDS.find(field => input.itemName === SOURCES[field].item), 'invalid_input');
}

const fields = {};
for (const field of FIELDS) {
  const spec = SOURCES[field];
  const slot = state.fields[field];
  const fresh = slot.ready && slot.value && slot.value.observedAt <= now
    && now < slot.value.observedAt + spec.ttl;
  fields[field] = fresh
    ? { status: 'valid', reason: 'ok', observedAt: slot.value.observedAt,
      validUntil: slot.value.observedAt + spec.ttl, value: slot.value.raw }
    : { status: 'unavailable', reason: !slot.ready ? 'source_unavailable'
      : slot.value ? 'input_stale' : slot.reason,
      observedAt: null, validUntil: null, value: null };
}
const next = { version: 1, basis: 'native_runtime_inputs_v1',
  streamEpoch: state.epoch, sequence: state.sequence + 1, recordedAt: now, fields };
const previous = state.lastPublished;
// Coalesce high-rate current/voltage updates, but preserve every distinct
// native runtime observation: dropping one changes the estimator's median.
// Unchanged numeric TTD/TTF values still represent new physical receipts.
const runtimeObservation = acceptedField === 'battery.ttd_min'
  || acceptedField === 'battery.ttf_min';
const barrier = !previous || FIELDS.some(field =>
  previous.fields[field].status !== fields[field].status
  || previous.fields[field].reason !== fields[field].reason);
const due = previous && now - previous.recordedAt >= PUBLISH_MS
  && FIELDS.some(field => fields[field].status === 'valid');
if (barrier || due || runtimeObservation) {
  state.sequence = next.sequence; // consume on ambiguous enqueue
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
    // Exclude this Item from automatic JDBC writes before enabling the rule.
    Persistence.persist(output.rawItem, stamp, encoded, 'jdbc');
    state.lastPublished = next;
    state.pendingPost = encoded;
  } catch (_) { console.warn('Runtime input evidence persistence enqueue failed'); }
}
if (state.pendingPost) {
  try {
    items.getItem(OUTPUT).postUpdate(state.pendingPost);
    state.pendingPost = null;
  } catch (_) { console.warn('Runtime input evidence state publication failed'); }
}
cache.private.put(KEY, state);
