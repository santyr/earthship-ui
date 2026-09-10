'use strict';
const { items, cache } = require('openhab');
const Instant = Java.type('java.time.Instant');
const UUID = Java.type('java.util.UUID');
const MAX_AGE_MS = 120000;
const PUBLISH_MS = 60000;
const CACHE_KEY = 'earthship.bms-soc-evidence.v1';
const OUTPUT_ITEM = 'BMS_SOC_Evidence_JSON';
const SOURCES = {
  BMS_SOC_Raw_Observation_JSON: ['raw','socRawObservation'],
  BMS_SOC_Scale_Observation_JSON: ['scale','socScaleObservation'],
};
const ORIGINAL_EVENT_KEYS = [
  ['raw.event','raw'], ['scale.event','scale'],
  ['comms.event',null], ['device.event',null], ['event',null],
];
const now = Number(Instant.now().toEpochMilli());
let state = cache.private.get(CACHE_KEY);
if (!state || now < state.lastNow) {
  state = {
    epoch: UUID.randomUUID().toString(), raw: null, scale: null,
    water: {raw:-1,scale:-1}, floor: now, minRawAt: now,
    lastNow: now, lastPublished: null,
  };
}
state.lastNow = now;

function original(input) {
  try {
    if (input && typeof input.getItemName === 'function') {
      return {event:input,invalidField:null,clearAll:false};
    }
    if (input && input.raw && typeof input.raw.get === 'function') {
      const entries = ORIGINAL_EVENT_KEYS.flatMap(([key,field]) => {
        const value = input.raw.get(key);
        const present = typeof input.raw.containsKey === 'function'
          ? Boolean(input.raw.containsKey(key))
          : typeof input.raw.has === 'function'
            ? input.raw.has(key)
            : value !== null && value !== undefined;
        return present ? [{field,value}] : [];
      });
      if (entries.length > 1) return {event:null,invalidField:null,clearAll:true};
      if (entries.length === 1) {
        const [{field,value}] = entries;
        if (value === null || value === undefined) {
          return {event:null,invalidField:field,clearAll:field === null};
        }
        return {event:value,invalidField:null,clearAll:false};
      }
    }
  } catch (_) {}
  return {event:null,invalidField:null,clearAll:false};
}
function itemName(input, raw) {
  try { return raw ? String(raw.getItemName()) : input && input.itemName; }
  catch (_) { return input && input.itemName; }
}
function integer(text, signed) {
  if (typeof text !== 'string' || !(signed ? /^[+-]?\d+$/ : /^\d+$/).test(text)) return null;
  const value = Number(text);
  return Number.isSafeInteger(value) ? value : null;
}
function invalidate(field) {
  state[field] = null;
  state.water[field] = Math.max(state.water[field], now);
  if (field === 'scale') {
    state.raw = null;
    state.water.raw = Math.max(state.water.raw, now);
  }
}
function clearInputs() {
  state.raw = null; state.scale = null;
  state.floor = Math.max(state.floor, now);
  state.minRawAt = Math.max(state.minRawAt, now);
}
function healthy() {
  try {
    return String(items.getItem('BMS_Comms_Status').state).trim() === 'OK'
      && String(items.getItem('BMS_DevicePresent').state).trim() === '1';
  } catch (_) { return false; }
}
function accept(name, raw) {
  if (!Object.hasOwn(SOURCES, name)) return;
  const [field, channel] = SOURCES[name];
  try {
    const source = `org.openhab.core.thing$modbus:data:schneiderBatterySunSpec:battery802Core:${channel}:string`;
    if (!raw || String(raw.getType()) !== 'ItemStateEvent'
        || String(raw.getTopic()) !== `openhab/items/${name}/state`
        || String(raw.getSource()) !== source) { invalidate(field); return; }
    const body = String(raw.getItemState());
    if (body.length > 1024) { invalidate(field); return; }
    const e = JSON.parse(body);
    const keys = ['version','field','observedAt','value'];
    if (!e || typeof e !== 'object' || Array.isArray(e)
        || Object.keys(e).length !== keys.length || !keys.every(key=>Object.hasOwn(e,key))
        || e.version !== 1 || e.field !== field || typeof e.value !== 'string'
        || !Number.isSafeInteger(e.observedAt) || e.observedAt <= 0 || e.observedAt > now) {
      invalidate(field); return;
    }
    const at = e.observedAt;
    if (at <= state.floor || at <= state.water[field]) return;
    state.water[field] = at;
    const value = integer(e.value, field === 'scale');
    if (value === null || now-at > MAX_AGE_MS
        || (field === 'raw' ? value < 0 || value > 65534 : value < -32767 || value > 32767)) {
      invalidate(field); return;
    }
    if (field === 'raw' && at < state.minRawAt) return;
    if (field === 'scale' && (!state.scale || state.scale.value !== value)) {
      state.raw = null;
      state.minRawAt = Math.max(state.minRawAt, at);
    }
    state[field] = {at,value};
  } catch (_) { invalidate(field); }
}

const input = typeof event === 'undefined' ? null : event;
const decoded = original(input);
const raw = decoded.event;
const name = itemName(input,raw);
const sourceReady = healthy();
if (decoded.clearAll) clearInputs();
else if (decoded.invalidField) invalidate(decoded.invalidField);
if (!sourceReady || name === 'BMS_Comms_Status' || name === 'BMS_DevicePresent') clearInputs();
if (sourceReady && !decoded.clearAll && !decoded.invalidField) accept(name,raw);

function record() {
  const unavailable = {
    version:1,streamEpoch:state.epoch,recordedAt:now,status:'unavailable',
    reason:sourceReady ? 'input_unavailable' : 'source_unavailable',
    observedAt:null,scaleObservedAt:null,validUntil:null,soc:null,
  };
  if (!sourceReady || !state.raw || !state.scale) return unavailable;
  if (state.raw.at > now || state.scale.at > now
      || now-Math.min(state.raw.at,state.scale.at) > MAX_AGE_MS) {
    return {...unavailable,reason:'input_stale'};
  }
  const soc = state.raw.value * Math.pow(10,state.scale.value);
  if (!Number.isFinite(soc) || soc < 0 || soc > 100 || (state.raw.value !== 0 && soc === 0)) {
    return {...unavailable,reason:'invalid_scaled_soc'};
  }
  return {...unavailable,status:'valid',reason:'ok',soc,
    observedAt:state.raw.at,scaleObservedAt:state.scale.at,
    validUntil:Math.min(state.raw.at,state.scale.at)+MAX_AGE_MS};
}
const next = record();
const previous = state.lastPublished;
const changed = !previous || previous.status !== next.status || previous.reason !== next.reason || previous.soc !== next.soc;
const due = next.status === 'valid' && previous && now-previous.recordedAt >= PUBLISH_MS;
if (changed || due) {
  try {
    items.getItem(OUTPUT_ITEM).postUpdate(JSON.stringify(next));
    state.lastPublished = next;
  } catch (_) { console.warn('BMS SoC evidence publication failed'); }
}
cache.private.put(CACHE_KEY,state);
