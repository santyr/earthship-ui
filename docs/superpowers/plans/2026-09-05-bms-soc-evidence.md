# Validated BMS SoC Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Supply the tested observational BMS evidence producer needed by the approved freshness and outcome rollout.

**Architecture:** One self-contained GraalJS rule emits one atomic JSON evidence record. No existing rule is changed. A disabled standalone descriptor documents the exact runtime resources without activating them.

**Tech Stack:** OpenHAB 5.2.1 GraalJS, Node VM, Vitest.

## Global Constraints

- Task 82 remains held.
- The rule may postUpdate only BMS_SOC_Evidence_JSON; no commands, notifier, network, database writes or persistence calls.
- Preserve everyChange plus restoreOnStartup; no periodic-persistence workaround.
- Preserve existing scaler outputs, comms cache, physical-control gates, thresholds, learned state, DM behavior and schedules.
- Source implementation is not live activation; no runtime resources are changed in this task.
- Source contract and schema are exactly the approved design in docs/superpowers/specs/2026-09-05-bms-soc-evidence-design.md.

### Task 1: Tested source and disabled resource descriptor

**Files:**
- Create: `openhab/rules/bms-soc-evidence.js`
- Create: `openhab/bms-soc-evidence-resources.json`
- Create: `tests/openhab/bms-soc-evidence.test.js`

**Interfaces:**
- Consumes actual Java update events (direct, or converted event.raw Map).
- Produces the closed version-1 BMS_SOC_Evidence_JSON record in the design.
- Uses cache.private.get/put, items.getItem, Java Instant and UUID only.
- Self-contained runtime source is loaded unchanged by the test VM; no test-only export API or secondary installed-module assumption.

- [ ] **Step 1: Write failing exact-script tests.** Read the source inside the harness only after the test starts. Missing source must produce an explicit failed expectation, not an import failure. Use this minimal harness structure, extending it with named failure cases below:

```js
import { readFileSync, existsSync } from 'node:fs';
import vm from 'node:vm';
import { expect, it } from 'vitest';
const url = new URL('../../openhab/rules/bms-soc-evidence.js', import.meta.url);
function harness() {
  expect(existsSync(url), 'evidence rule source exists').toBe(true);
  const source = readFileSync(url, 'utf8');
  const values = new Map();
  const posts = [];
  const health = { BMS_Comms_Status: 'OK', BMS_DevicePresent: '1' };
  let now = Date.parse('2026-09-05T20:00:00Z');
  let fail = false;
  const run = (event) => vm.runInNewContext(source, {
    event,
    require: (name) => {
      expect(name).toBe('openhab');
      return { cache: { private: { get: k => values.get(k), put: (k,v) => values.set(k,v) } },
        items: { getItem: (name) => ({ state: health[name] ?? 'NULL',
          postUpdate: value => { expect(name).toBe('BMS_SOC_Evidence_JSON');
            if (fail) throw new Error('injected publication failure');
            posts.push(JSON.parse(value)); } }) } };
    },
    Java: { type: name => {
      if (name === 'java.time.Instant') return { now: () => ({ toEpochMilli: () => now }) };
      if (name === 'java.util.UUID') return { randomUUID: () => ({ toString: () => 'a2267947-12ad-49f0-9e58-92913e46ad7a' }) };
      throw new Error('unexpected Java class');
    } }, console: { warn: () => {} },
  });
  const update = (item, value, at = now, sourceOverride) => {
    const channel = item === 'BMS_SOC_Raw' ? 'socRaw' : 'socSf';
    const original = { getType: () => 'ItemStateUpdatedEvent', getItemName: () => item,
      getItemState: () => ({ toString: () => String(value) }),
      getSource: () => sourceOverride ?? `org.openhab.core.thing$modbus:data:schneiderBatterySunSpec:battery802Core:${channel}:number`,
      getLastStateUpdate: () => ({ toInstant: () => ({ toEpochMilli: () => at }) }) };
    run({ raw: new Map([['event', original]]) });
  };
  return { run, update, posts, health, values, advance: ms => { now += ms; },
    setFail: value => { fail = value; }, now: () => now };
}
it('requires independently observed raw and scale, including unchanged updates', () => {
  const h = harness();
  h.update('BMS_SOC_Raw', '99');
  expect(h.posts.at(-1).status).toBe('unavailable');
  h.update('BMS_SOC_ScaleFactor_Raw', '0');
  expect(h.posts.at(-1)).toMatchObject({ status: 'valid', soc: 99, observedAt: h.now() });
  h.advance(60000);
  h.update('BMS_SOC_ScaleFactor_Raw', '0');
  h.update('BMS_SOC_Raw', '99');
  expect(h.posts.at(-1).status).toBe('valid');
});
```

Add focused tests for: direct Java event; missing/wrong/persistence/REST/delegated source;
raw65535, -1, fraction, partial numeric, units, NULL/UNDEF/empty/NaN/Infinity;
scale sentinel/out-of-int16/fraction/partial; scaled101, overflow and nonzero underflow;
zero raw; future/noninteger/nonfinite/missing/delayed timestamps; duplicates and
out-of-order updates; scale-only expiry with original raw timestamp preserved;
known fault/missing health clears both fields; recovery needs both new observations;
restart never trusts restored JSON; minute cadence and immediate value/status changes;
failed publication retried on next normal invocation; one output Item and closed schema.
Add descriptor assertions for exactly the six triggers and no original-rule mutation.
Every rejection test first establishes valid state and then verifies it becomes
unavailable (except trusted duplicates/out-of-order events, which are ignored).

- [ ] **Step 2: Run RED.**

Run `npm test -- --run tests/openhab/bms-soc-evidence.test.js` and preserve the
expected assertion failures before creating either production file.

- [ ] **Step 3: Implement the self-contained rule.** Use named constants and small
local functions for event extraction, strict integer parsing, cached input
acceptance, record construction and publication. The following flow defines the
implementation; follow the design's exact schema/values and reject unexpected
runtime shapes rather than using Item snapshots as event substitutes:

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
  BMS_SOC_Raw: ['raw', 'socRaw'],
  BMS_SOC_ScaleFactor_Raw: ['scale', 'socSf'],
};
const now = Number(Instant.now().toEpochMilli());
let state = cache.private.get(CACHE_KEY);
if (!state) state = { epoch: UUID.randomUUID().toString(), raw: null, scale: null,
  water: { raw: -1, scale: -1 }, floor: now, lastPublished: null };
function original(input) {
  if (input && typeof input.getItemName === 'function') return input;
  if (input && input.raw && typeof input.raw.get === 'function') return input.raw.get('event');
  return null;
}
function integer(value, signed) {
  const text = String(value).trim();
  const pattern = signed ? /^[+-]?\d+$/ : /^\d+$/;
  return pattern.test(text) && Number.isSafeInteger(Number(text)) ? Number(text) : null;
}
function accept(input) {
  const raw = original(input);
  let name;
  try { name = raw ? String(raw.getItemName()) : input && input.itemName; }
  catch (_) { name = input && input.itemName; }
  const config = Object.hasOwn(SOURCES, name) ? SOURCES[name] : null;
  if (!config) return;
  const [field, channel] = config;
  let at, value;
  try {
    const expected = `org.openhab.core.thing$modbus:data:schneiderBatterySunSpec:battery802Core:${channel}:number`;
    if (!raw || String(raw.getType()) !== 'ItemStateUpdatedEvent' || String(raw.getSource()) !== expected) {
      state[field] = null; return;
    }
    at = Number(raw.getLastStateUpdate().toInstant().toEpochMilli());
    if (!Number.isSafeInteger(at) || at <= 0 || at > now) { state[field] = null; return; }
    if (at < state.floor || at <= state.water[field]) return;
    state.water[field] = at;
    value = integer(raw.getItemState(), field === 'scale');
  } catch (_) { state[field] = null; return; }
  const inRange = value !== null && (field === 'raw' ? value >= 0 && value <= 65534 : value >= -32767 && value <= 32767);
  state[field] = inRange && now - at <= MAX_AGE_MS ? { at, value } : null;
}
function healthy() {
  try {
    return String(items.getItem('BMS_Comms_Status').state).trim() === 'OK'
      && Number(String(items.getItem('BMS_DevicePresent').state)) === 1;
  } catch (_) { return false; }
}
function record() {
  const out = { version: 1, streamEpoch: state.epoch, recordedAt: now,
    status: 'unavailable', reason: 'input_unavailable', observedAt: null,
    scaleObservedAt: null, validUntil: null, soc: null };
  if (!healthy()) {
    state.raw = null; state.scale = null; state.floor = now;
    out.reason = 'source_unavailable'; return out;
  }
  if (!state.raw || !state.scale) return out;
  if (state.raw.at > now || state.scale.at > now || now - Math.min(state.raw.at, state.scale.at) > MAX_AGE_MS) {
    out.reason = 'input_stale'; return out;
  }
  const soc = state.raw.value * Math.pow(10, state.scale.value);
  if (!Number.isFinite(soc) || soc < 0 || soc > 100 || (state.raw.value !== 0 && soc === 0)) {
    out.reason = 'invalid_scaled_soc'; return out;
  }
  return { ...out, status: 'valid', reason: 'ok', soc, observedAt: state.raw.at,
    scaleObservedAt: state.scale.at, validUntil: Math.min(state.raw.at, state.scale.at) + MAX_AGE_MS };
}
accept(typeof event === 'undefined' ? null : event);
const next = record();
const previous = state.lastPublished;
const changed = !previous || previous.status !== next.status || previous.reason !== next.reason || previous.soc !== next.soc;
const due = next.status === 'valid' && previous && now - previous.recordedAt >= PUBLISH_MS;
if (changed || due) {
  try {
    items.getItem(OUTPUT_ITEM).postUpdate(JSON.stringify(next));
    state.lastPublished = next;
  } catch (_) { console.warn('BMS SoC evidence publication failed'); }
}
cache.private.put(CACHE_KEY, state);
```

The implementation must complete that flow as actual code, with no placeholders.
When a known fault clears input state, incoming fault-period values do not qualify
later recovery. A non-input trigger only reconciles health/expiry; it cannot
refresh observations. A cache restart starts unavailable until both fresh input
events. On publication failure, do not retain a successful receipt for the failed
new record. Numeric state fields use strict complete-string parsing.

Create the standalone descriptor with exactly this shape:

```json
{
  "version": 1,
  "items": [{"name":"BMS_SOC_Evidence_JSON","type":"String","label":"Validated BMS SoC evidence","category":"","tags":[],"groupNames":[]}],
  "persistence": {"serviceId":"jdbc","strategy":"everyChange","restoreOnStartup":true,"items":["BMS_SOC_Evidence_JSON"]},
  "rule": {
    "uid":"hex_bms_soc_evidence","name":"Validated BMS SoC evidence","enabled":false,
    "source":"openhab/rules/bms-soc-evidence.js",
    "triggers":[
      {"id":"raw","type":"core.ItemStateUpdateTrigger","configuration":{"itemName":"BMS_SOC_Raw"}},
      {"id":"scale","type":"core.ItemStateUpdateTrigger","configuration":{"itemName":"BMS_SOC_ScaleFactor_Raw"}},
      {"id":"comms","type":"core.ItemStateChangeTrigger","configuration":{"itemName":"BMS_Comms_Status"}},
      {"id":"device","type":"core.ItemStateChangeTrigger","configuration":{"itemName":"BMS_DevicePresent"}},
      {"id":"expiry","type":"timer.GenericCronTrigger","configuration":{"cronExpression":"0 * * * * ?"}},
      {"id":"startup","type":"core.SystemStartlevelTrigger","configuration":{"startlevel":100}}
    ]
  }
}
```

- [ ] **Step 4: GREEN and regression verification.** Run focused tests, then
`npm test -- --run tests/openhab` and `git diff --check`. No real OpenHAB calls.
Self-review event ordering, source equality, health invalidation, cache restart
and failed publication receipt semantics. Record commands and exact results.

- [ ] **Step 5: Commit and report.** Stage only the three implementation files.
Commit as `feat: add observational validated BMS SoC evidence producer`.
Write the detailed RED/GREEN report to the coordinator-provided path. Do not
merge, push, install resources, invoke runnow or migrate consumers.

## Completion boundary

Task review and final whole-branch review must pass before source integration.
The coordinator separately runs the full UI suite and verifies unchanged original
rule files. Reader migration, receipt-bound deployment, natural-event validation,
historical assessment and completed-window evidence remain actual outstanding
work; this source task is a dependency, not the completion of the broad objective.
