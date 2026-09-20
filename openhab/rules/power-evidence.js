'use strict';
// Observational only. No numeric Item carry, control commands or health writes.
const { items, cache } = require('openhab');
const Instant = Java.type('java.time.Instant');
const UUID = Java.type('java.util.UUID');
const ZonedDateTime = Java.type('java.time.ZonedDateTime');
const Persistence = Java.type('org.openhab.core.persistence.extensions.PersistenceExtensions');
const now = Number(Instant.now().toEpochMilli());
const TTL = 120000;
const KEY = 'earthship.power-evidence.v1';
const OUTPUT = 'Power_Evidence_JSON';
const sources = {
  Battery_Power_Observation_JSON: {
    field: 'battery.dc_power_w', trigger: 'battery',
    channel: 'modbus:data:schneiderBatterySunSpec:battery802Core:powerObservation:string',
    min: -32767, max: 32767,
  },
  PV_Input_Power_Observation_JSON: {
    field: 'pv.input_power_w', trigger: 'pv_input',
    channel: 'modbus:data:9eb978a141:mppt60Input:powerObservation:string',
    min: 0, max: 4294967294,
  },
  PV_Output_Power_Observation_JSON: {
    field: 'pv.output_power_w', trigger: 'pv_output',
    channel: 'modbus:data:9eb978a141:mppt60Output:powerObservation:string',
    min: 0, max: 4294967294,
  },
};
let state = cache.private.get(KEY);
if (!state || now < state.lastNow) {
  state = { epoch: UUID.randomUUID().toString(), floor: now, lastNow: now,
    values: {}, water: {}, lastPublished: null, sequence: 0 };
}
state.lastNow = now;
function invalidate(name) {
  state.values[name] = null;
  state.water[name] = Math.max(state.water[name] ?? -1, now);
}
function invalidateAll() {
  Object.keys(sources).forEach(invalidate);
}
function decode(input) {
  if (!input) return { raw: null, invalid: null };
  try {
    if (typeof input.getItemName === 'function') return { raw: input, invalid: null };
    if (input.raw && typeof input.raw.get === 'function') {
      const keys = [...Object.entries(sources).map(([name, s]) => [`${s.trigger}.event`, name]), ['event', '*']];
      const found = keys.filter(([key]) => {
        if (typeof input.raw.containsKey === 'function') return Boolean(input.raw.containsKey(key));
        if (typeof input.raw.has === 'function') return input.raw.has(key);
        return input.raw.get(key) !== null && input.raw.get(key) !== undefined;
      });
      if (found.length > 1) return { raw: null, invalid: '*' };
      if (found.length === 1) {
        const [[key, name]] = found;
        const raw = input.raw.get(key);
        return raw ? { raw, invalid: null } : { raw: null, invalid: name };
      }
    }
    // Timer invocations can carry no event. Item-shaped wrappers without an
    // original event cannot authenticate source and invalidate their own field.
    return { raw: null, invalid: input.itemName ? String(input.itemName) : null };
  } catch (_) { return { raw: null, invalid: '*' }; }
}
const decoded = decode(typeof event === 'undefined' ? null : event);
if (decoded.invalid === '*') invalidateAll();
else if (decoded.invalid && Object.hasOwn(sources, decoded.invalid)) invalidate(decoded.invalid);
if (decoded.raw) {
  let name;
  try {
    name = String(decoded.raw.getItemName());
    if (!Object.hasOwn(sources, name)) throw new Error('unexpected input');
    const source = sources[name];
    if (String(decoded.raw.getType()) !== 'ItemStateEvent'
        || String(decoded.raw.getTopic()) !== `openhab/items/${name}/state`
        || String(decoded.raw.getSource()) !== `org.openhab.core.thing$${source.channel}`) {
      throw new Error('source mismatch');
    }
    const body = String(decoded.raw.getItemState());
    if (body.length > 1024) throw new Error('oversized input');
    const receipt = JSON.parse(body);
    const keys = ['version', 'field', 'observedAt', 'value'];
    if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)
        || Object.keys(receipt).length !== keys.length || !keys.every(k => Object.hasOwn(receipt, k))
        || receipt.version !== 1 || receipt.field !== source.field
        || !Number.isSafeInteger(receipt.observedAt) || receipt.observedAt <= 0
        || receipt.observedAt > now || typeof receipt.value !== 'string') {
      throw new Error('invalid envelope');
    }
    // Canonical transform encoding also rejects duplicate JSON keys and lossy
    // numeric representations without accepting parser last-key-wins semantics.
    if (body !== JSON.stringify(receipt)) throw new Error('noncanonical envelope');
    const at = receipt.observedAt;
    if (at === state.water[name] && state.values[name]
        && (!/^[+-]?\d+$/.test(receipt.value)
          || Number(receipt.value) !== state.values[name].watts)) {
      throw new Error('conflicting equal-time receipt');
    }
    if (at > state.floor && at > (state.water[name] ?? -1)) {
      if (!/^[+-]?\d+$/.test(receipt.value)) throw new Error('invalid raw number');
      const watts = Number(receipt.value);
      if (!Number.isSafeInteger(watts) || watts < source.min || watts > source.max
          || now - at >= TTL) throw new Error('invalid or expired raw value');
      state.water[name] = at;
      state.values[name] = { observedAt: at, watts };
    }
  } catch (_) {
    if (name && Object.hasOwn(sources, name)) invalidate(name);
    else invalidateAll();
  }
}
const fields = {};
for (const [name, source] of Object.entries(sources)) {
  const value = state.values[name];
  const fresh = value && value.observedAt <= now && now - value.observedAt < TTL;
  fields[source.field] = fresh
    ? { status: 'valid', reason: 'ok', observedAt: value.observedAt,
      validUntil: value.observedAt + TTL, watts: value.watts }
    : { status: 'unavailable', reason: value ? 'input_stale' : 'input_unavailable',
      observedAt: null, validUntil: null, watts: null };
}
const next = { version: 1, streamEpoch: state.epoch, sequence: state.sequence + 1, recordedAt: now, fields };
const previous = state.lastPublished;
// Every accepted receipt must be published: suppressing changed timestamps
// would erase field-specific expiry and invalidation history.
if (!previous || JSON.stringify(previous.fields) !== JSON.stringify(fields)) {
  // Consume identity even on an ambiguous enqueue exception. Retrying a changed
  // payload under the same sequence would hide a possible missing publication.
  state.sequence = next.sequence;
  try {
    const output = items.getItem(OUTPUT);
    const encoded = JSON.stringify(next);
    let stamp = ZonedDateTime.now();
    stamp = stamp.withNano(Math.floor(stamp.getNano() / 1000) * 1000);
    if (state.lastPersistenceAt && !stamp.isAfter(state.lastPersistenceAt)) {
      stamp = state.lastPersistenceAt.plusNanos(1000);
    }
    state.lastPersistenceAt = stamp;
    // Automatic change persistence MUST exclude this Item before activation.
    // This overload queues the immutable value, never a later Item.getState().
    // Acceptance is not a durability acknowledgement: readers still detect gaps.
    Persistence.persist(output.rawItem, stamp, encoded, 'jdbc');
    state.lastPublished = next;
    state.pendingPost = encoded;
  } catch (_) { console.warn('Power evidence persistence enqueue failed'); }
}
if (state.pendingPost) {
  try {
    items.getItem(OUTPUT).postUpdate(state.pendingPost);
    state.pendingPost = null;
  } catch (_) { console.warn('Power evidence state publication failed'); }
}
cache.private.put(KEY, state);
