# BMS Atomic Observer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the undeployed observer draft with the approved exact-source atomic-envelope validator.

**Architecture:** Receive original ItemStateEvent objects from two dedicated String Items, validate the envelope and source before updating independently timestamped caches, and publish only BMS_SOC_Evidence_JSON. Health transitions and restarts clear cached evidence; actual scale changes require another raw observation. Source-transform dependency20820d9 is complete and must be exercised by the new observer tests.

**Tech Stack:** OpenHAB JavaScript Scripting, openhab-js cache/items, Java Instant/UUID, Node vm and Vitest.

## Global Constraints

- Authority: `docs/superpowers/specs/2026-09-10-bms-atomic-observations-design.md`, approved43ccb08/Hexmem8691.
- Source timestamp means binding processing time, not physical sampling time. Never replace missing observation time with observer invocation time.
- Exact ItemStateEvent type, topic, Item name and binding String channel source are required. Generic triggers must not filter by source; foreign input must reach invalidation logic.
- Raw0–65534; scale-32767–32767; finite scaled SoC0–100; reject nonzero underflow. Strict input text rejects whitespace, units and decimal/exponent formats.
- Independent age limit120000ms, valid heartbeat60000ms, closed version1 output. Invalid records have null measurement fields.
- Preserve controls, DM behavior, learned state, everyChange and restoreOnStartup. Task82 remains held.
- No commands, network or persistence queries. The only Item reads are BMS_Comms_Status and BMS_DevicePresent. The only output is BMS_SOC_Evidence_JSON.
- Replace the two already-staged draft observer/test files in scope, preserving their historical RED report. Leave the staged resource descriptor unchanged; it remains unusable until a later descriptor task. Commit only the two task files.
- No live installation, reader migration, merge or push in the worker task.

## Interfaces and file boundaries

Modify `openhab/rules/bms-soc-evidence.js` and
`tests/openhab/bms-soc-evidence.test.js` only.

Consumes original direct Java event or `event.raw.get('event')` containing
`getType()`, `getTopic()`, `getItemName()`, `getItemState()` and `getSource()`.
The event deliberately has NO timestamp getter: source time is inside its JSON.

| Item | Field | Data Thing suffix |
| --- | --- | --- |
| BMS_SOC_Raw_Observation_JSON | raw | socRawObservation |
| BMS_SOC_Scale_Observation_JSON | scale | socScaleObservation |

Topic is exactly `openhab/items/<Item>/state`. Source is exactly
`org.openhab.core.thing$modbus:data:schneiderBatterySunSpec:battery802Core:<suffix>:string`.
Source envelope has exactly version, field, observedAt, value; no other keys.

The later descriptor task owns creation of those Things/Items/links and generic
triggers with live-verified config keys `topic`, `types`, `source`, `payload`.
This observer task leaves descriptor tests unchanged until that task, and makes
no claim that the old descriptor is compatible with the corrected observer.

### Task 1: Exact-source envelope and cache lifecycle

**Files:**
- Modify: `openhab/rules/bms-soc-evidence.js`
- Modify/test: `tests/openhab/bms-soc-evidence.test.js`
- Read: `openhab/transform/bms_soc_raw_observation.js`
- Read: `openhab/transform/bms_soc_scale_observation.js`

**Interfaces:**
- Consumes the event and producer contracts above plus health Item snapshots.
- Produces unchanged closed output schema version, streamEpoch, recordedAt, status, reason, observedAt, scaleObservedAt, validUntil, soc.
- Private cache key `earthship.bms-soc-evidence.v1`; cache state owns source watermarks, processing barriers, scale/raw dependency and successful publication receipt.

- [ ] **Step 1: Adapt the real-script test harness before touching production.** Replace fabricated updated-event timestamps with original ItemStateEvent envelopes created by the actual transform scripts. Preserve the existing deny-by-default Item/Java harness, add deny functions for fetch/commands/timers, make UUID vary across cache restarts, and expose cache clearing and absolute clock control. Use this event helper (inside the harness; `now` is its injected clock):

```js
const names = {raw:'BMS_SOC_Raw_Observation_JSON',scale:'BMS_SOC_Scale_Observation_JSON'};
const channels = {raw:'socRawObservation',scale:'socScaleObservation'};
const envelope = (field, value, at = now) => vm.runInNewContext(
  readFileSync(new URL(`../../openhab/transform/bms_soc_${field}_observation.js`, import.meta.url),'utf8'),
  {input:value,Date:{now:()=>at}}, {timeout:1000});
const originalEvent = (field, value, at = now, overrides = {}) => ({
  getType: () => 'ItemStateEvent',
  getTopic: () => `openhab/items/${names[field]}/state`,
  getItemName: () => names[field],
  getItemState: () => ({toString:()=>envelope(field,value,at)}),
  getSource: () => `org.openhab.core.thing$modbus:data:schneiderBatterySunSpec:battery802Core:${channels[field]}:string`,
  ...overrides,
});
const update = (field,value,at=now,overrides={}) =>
  run({raw:new Map([['event',originalEvent(field,value,at,overrides)]])});
```

Cache initialization is a strict processing barrier: run an initial invocation,
advance one millisecond, then scale followed by raw can establish validity.
Use `h.run()`, `h.advance(ms)`, `h.now()`, `h.update(field,value,at,overrides)`,
`h.originalEvent(...)`, `h.posts`, `h.values`, `h.health`, `h.setFail(bool)`,
`h.setNow(ms)` and `h.restart()` in tests. `restart()` clears the cache Map only.

- [ ] **Step 2: Write the contract regressions.** Update existing numeric, age, schema, expiry and publication tests to the new interface. Retain all corresponding risk coverage, not their obsolete timestamp API expectations. Add these executable assertions using the adapted harness:

```js
function establishValid(h,raw='99',scale='0') {
  h.run(); h.advance(1);
  h.update('scale',scale); h.update('raw',raw);
  expect(h.posts.at(-1)).toMatchObject({status:'valid',soc:Number(raw)*10**Number(scale)});
}

it('keeps source time when an unchanged scale arrives after delayed raw',()=>{
  const h=harness(); h.run(); h.advance(1); h.update('scale','0');
  const at=h.now(); h.advance(1000); h.update('raw','99',at);
  expect(h.posts.at(-1)).toMatchObject({status:'valid',observedAt:at});
  h.advance(60000); h.update('scale','0');
  expect(h.posts.at(-1)).toMatchObject({observedAt:at,scaleObservedAt:h.now(),validUntil:at+120000});
});

it('requires another raw observation when scale arrives second or changes',()=>{
  const h=harness(); h.run(); h.advance(1);
  h.update('raw','990'); h.update('scale','-1');
  expect(h.posts.at(-1).status).toBe('unavailable');
  h.advance(1); h.update('raw','990');
  expect(h.posts.at(-1)).toMatchObject({status:'valid',soc:99});
  h.advance(1); h.update('scale','-2');
  expect(h.posts.at(-1).status).toBe('unavailable');
  h.advance(1); h.update('raw','990');
  expect(h.posts.at(-1)).toMatchObject({status:'valid',soc:9.9});
});

it('does not miss a queued health fault after the snapshot has recovered',()=>{
  const h=harness(); establishValid(h); h.advance(1);
  h.run({itemName:'BMS_Comms_Status',newState:'STALE'});
  expect(h.health.BMS_Comms_Status).toBe('OK');
  expect(h.posts.at(-1).status).toBe('unavailable');
  h.advance(1); h.update('scale','0'); h.update('raw','80');
  expect(h.posts.at(-1)).toMatchObject({status:'valid',soc:80});
});

it.each([
  {getType:()=> 'ItemStateUpdatedEvent'},
  {getTopic:()=> 'openhab/items/BMS_SOC_Raw_Observation_JSON/statechanged'},
  {getSource:()=> 'org.openhab.core.persistence.jdbc'},
  {getSource:()=> null},
  {getItemState:()=> '{'},
  {getItemState:()=> ''},
])('invalidates bad event provenance or body %#',overrides=>{
  const h=harness(); establishValid(h); h.advance(1);
  h.update('raw','99',h.now(),overrides);
  expect(h.posts.at(-1)).toMatchObject({status:'unavailable',observedAt:null,soc:null});
});

it.each([
  e=>({...e,extra:true}),e=>({...e,version:2}),e=>({...e,field:'scale'}),
  e=>({...e,value:99}),e=>({...e,observedAt:String(e.observedAt)}),
  e=>({...e,observedAt:e.observedAt+1}),e=>({...e,observedAt:1.5}),
  ()=>null,()=>[],()=>({}),
])('rejects malformed closed envelopes %#',mutate=>{
  const h=harness(); establishValid(h); h.advance(1);
  const body=JSON.stringify(mutate({version:1,field:'raw',observedAt:h.now(),value:'99'}));
  h.update('raw','99',h.now(),{getItemState:()=>body});
  expect(h.posts.at(-1).status).toBe('unavailable');
});

it('clock rollback starts a new unavailable epoch and needs new evidence',()=>{
  const h=harness(); establishValid(h); const first=h.posts.at(-1);
  h.setNow(h.now()-1000); h.run();
  expect(h.posts.at(-1).status).toBe('unavailable');
  expect(h.posts.at(-1).streamEpoch).not.toBe(first.streamEpoch);
  h.advance(1); h.update('scale','0'); h.update('raw','99');
  expect(h.posts.at(-1).status).toBe('valid');
});
```

Also cover exact-age120000 vs120001, stale original timestamps, missing each
required envelope key, direct original events and wrapped events, duplicate/
out-of-order trusted events, each foreign raw/scale source, restart with restored
Item snapshots, pre-barrier queued observations, absent/invalid health fields,
publication failure then normal retry, and single closed output. Check that
invalid scale recovery cannot reuse the pre-fault raw cache. Reuse parameterized
existing tests where their behavior remains required. Tests for old descriptor
stay unchanged and explicitly labeled as superseded draft, pending next task.

- [ ] **Step 3: Record genuine RED.** Run `npm test -- tests/openhab/bms-soc-evidence.test.js`. Confirm new behavior fails against the still-unchanged draft, rather than failing due to syntax or harness errors. Record actual failing/passing counts.

- [ ] **Step 4: Replace the observer with this implementation.** The `water` barrier advanced on invalid/foreign evidence is a processing rejection barrier, never a published source timestamp. It prevents queued pre-invalidation events from restoring a cleared value.

```js
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
    if (input && typeof input.getItemName === 'function') return input;
    if (input && input.raw && typeof input.raw.get === 'function') return input.raw.get('event');
  } catch (_) {}
  return null;
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
const raw = original(input);
const name = itemName(input,raw);
const sourceReady = healthy();
if (!sourceReady || name === 'BMS_Comms_Status' || name === 'BMS_DevicePresent') clearInputs();
if (sourceReady) accept(name,raw);

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
```

- [ ] **Step 5: Run GREEN and inspect safety.** Run `npm test -- tests/openhab/bms-soc-evidence.test.js tests/openhab/bms-observation-transforms.test.js`, then `npm test` and `git diff --check`. Confirm real source times survive delayed delivery, failures never advance successful publication receipt, and all old/new required risk cases are represented. Report any necessary deviation from the proposed implementation rather than silently changing the contract.

- [ ] **Step 6: Commit only the corrected observer and tests.**

```bash
git add openhab/rules/bms-soc-evidence.js tests/openhab/bms-soc-evidence.test.js
git commit --only -m "fix: validate atomic BMS source observations" -- openhab/rules/bms-soc-evidence.js tests/openhab/bms-soc-evidence.test.js
git status --short
```

The resource descriptor must still be staged and unchanged. Do not commit it.
Report to `.superpowers/sdd/bms-atomic-observer-task-1-report.md` (ignored), with
RED/GREEN evidence, scope and any remaining concerns. Do not overwrite the old
draft report, force-add ignored artifacts, merge, push or deploy.

## Self-review

Source validation, strict shape/types, original times, duplicate/out-of-order
handling, scale barrier, health transitions, restart, rollback, expiry and
publication receipt map to Task1 code and tests. Descriptor changes and installed
qualification are deliberately separate release gates, not claimed complete by
this dependency. Existing staged draft descriptor is explicitly incompatible.
