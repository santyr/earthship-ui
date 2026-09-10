# BMS Observation Transforms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and independently test the two source-envelope transformations required by the approved atomic BMS observation design.

**Architecture:** Each standalone script transforms one binding numeric-state input to a closed JSON string, attaching its own single binding-processing timestamp. The later observer validates numeric ranges and freshness; these scripts retain invalid text as explicit rejectable evidence. This dependency does not install resources or activate the superseded observer.

**Tech Stack:** OpenHAB 5.2.1 JavaScript Scripting, plain JavaScript IIFEs, Node vm and Vitest.

## Global Constraints

- Approved authority: `docs/superpowers/specs/2026-09-10-bms-atomic-observations-design.md`, Hexmem 8691.
- Timestamp means binding read-processing observation time, not BMS hardware time or simultaneous register acquisition.
- No Item snapshot lookup, network call, persistence call, timer, command, or dependency import belongs in the transformation.
- Preserve everyChange plus restoreOnStartup and all existing controls, poll intervals, scalers, learned state and DM behavior. Task 82 remains held.
- The three already-staged observer/descriptor/test files are a superseded draft. Preserve them staged and unchanged; never include them in this dependency commit.
- Do not install transformations, Items, links, Things or rules during this task. Runtime qualification, storage cost and reader migration are separate gates.

## File boundaries and remaining work

Create only `openhab/transform/bms_soc_raw_observation.js`,
`openhab/transform/bms_soc_scale_observation.js`, and
`tests/openhab/bms-observation-transforms.test.js`.
The two scripts deliberately contain no shared imported helper: OpenHAB loads each
transformation in its own context, and the approved producer prohibits imports.

This plan covers the source-envelope dependency, not the whole BMS release.
Subsequent observer work must replace the invalid ItemStateUpdatedEvent contract
with exact-source original ItemStateEvent input, envelope validation, cache and
scale-change barriers. Descriptor work must add only write-disabled observational
Things and String links. Deployment still requires installed-engine tests,
storage-volume estimates, snapshots, unchanged-control hashes and natural events.

Source preflight on September 10: live poller remains ONLINE at refresh 5000 ms,
start 40244 and length 64. Existing raw Thing uses readStart 40255 and uint16;
String channels exist, and jsscripting/modbus are installed. Version 5.2.1
`ModbusPollerThingHandler.childHandlerInitialized` adds data handlers to
`childCallbacks`; its callback delegator passes the shared read result to those
handlers. Regular poll registration belongs to the poller initialization, not
child registration. This source evidence does not replace live activation checks.

References:
- https://www.openhab.org/addons/automation/jsscripting/#js-transformation
- https://raw.githubusercontent.com/openhab/openhab-addons/5.2.1/bundles/org.openhab.binding.modbus/src/main/java/org/openhab/binding/modbus/handler/ModbusPollerThingHandler.java

### Task 1: Atomic raw and scale source transformations

**Files:**
- Create: `openhab/transform/bms_soc_raw_observation.js`
- Create: `openhab/transform/bms_soc_scale_observation.js`
- Test: `tests/openhab/bms-observation-transforms.test.js`

**Interfaces:**
- Consumes: OpenHAB global `input`, the binding numeric state's original string representation; standard `Date.now()` returns source processing time.
- Produces: a JSON string with exactly `{version:1,field:'raw'|'scale',observedAt:number,value:string}`. `value` is untrimmed `String(input)`. Invalid strings are not replaced with a previous value or converted to null/zero. The observer rejects them.
- VM completion value must be the returned string, matching OpenHAB's documented IIFE transformation contract; no module exports or script-action wrapper.

- [ ] **Step 1: Write failing executable transformation tests.** Use this fixture and parameterize both source files. Do not fabricate a helper implementation in the test.

```js
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const scripts = ['raw', 'scale'];
function execute(field, input, now) {
  const source = readFileSync(new URL(
    `../../openhab/transform/bms_soc_${field}_observation.js`, import.meta.url), 'utf8');
  let calls = 0;
  const forbidden = () => { throw new Error('forbidden transformation capability'); };
  const result = vm.runInNewContext(source, {
    input, Date: { now: () => { calls += 1; return now; } },
    require: forbidden, fetch: forbidden, setTimeout: forbidden,
    setInterval: forbidden, Java: { type: forbidden },
    items: new Proxy({}, { get: forbidden }),
    actions: new Proxy({}, { get: forbidden }),
    cache: new Proxy({}, { get: forbidden }),
  }, { timeout: 1000 });
  expect(calls).toBe(1);
  expect(typeof result).toBe('string');
  return JSON.parse(result);
}

describe.each(scripts)('%s source observation', field => {
  it.each(['99', '0', '-1', '-32768', '65535', '1.5', 'NULL', 'UNDEF', '',
    ' 99 ', '12 %', 'NaN', 'Infinity', '1e2', '"quoted"'])
  ('retains exact input text %j in a closed record', input => {
    expect(execute(field, input, 1789072800000)).toEqual({
      version: 1, field, observedAt: 1789072800000, value: input,
    });
  });
  it('stamps each unchanged observation without mutating earlier evidence', () => {
    const first = execute(field, '99', 1789072800000);
    const second = execute(field, '99', 1789072805000);
    expect(first.observedAt).toBe(1789072800000);
    expect(second.observedAt).toBe(1789072805000);
    expect(first.value).toBe(second.value);
  });
  it('does not hide clock rollback from the downstream validator', () => {
    expect(execute(field, '99', 1789072800000).observedAt).toBe(1789072800000);
    expect(execute(field, '99', 1789072799000).observedAt).toBe(1789072799000);
  });
});
```

- [ ] **Step 2: Record genuine RED.** Run `npm test -- tests/openhab/bms-observation-transforms.test.js`. New cases must fail because the transformation files do not exist, not because of a broken test import.

- [ ] **Step 3: Implement the exact raw script.** Do not add dependencies or live calls.

```js
(function (data) {
  return JSON.stringify({
    version: 1,
    field: 'raw',
    observedAt: Date.now(),
    value: String(data),
  });
})(input);
```

- [ ] **Step 4: Implement the exact scale script.** Do not perform scale multiplication in the transformation.

```js
(function (data) {
  return JSON.stringify({
    version: 1,
    field: 'scale',
    observedAt: Date.now(),
    value: String(data),
  });
})(input);
```

- [ ] **Step 5: Record GREEN and inspect scope.** Run the focused command from Step 2, then `npm test`, then `git diff --check`. Existing draft observer tests may pass but are not evidence of a usable observer contract. Record test counts and any failures without staging unrelated files.

- [ ] **Step 6: Commit only the three new dependency files.** The old draft is already staged, so an ordinary unqualified `git commit` would accidentally commit it. Use explicit path-only commit:

```bash
git add openhab/transform/bms_soc_raw_observation.js openhab/transform/bms_soc_scale_observation.js tests/openhab/bms-observation-transforms.test.js
git commit --only -m "feat: add atomic BMS source observation transforms" -- openhab/transform/bms_soc_raw_observation.js openhab/transform/bms_soc_scale_observation.js tests/openhab/bms-observation-transforms.test.js
git status --short
```

- [ ] **Step 7: Independent dependency review.** Review actual scripts and tests against the approved source contract, including exact keys, one timestamp read, retained invalid input and capability denial. Record the review in an ignored uniquely named SDD report. Do not merge/push/deploy as part of the worker task.

## Self-review

This plan implements only the independently testable producer dependency and
explicitly leaves observer validation, descriptor safety and runtime/storage
qualification open. Both field names, file names and envelope keys match the
approved interface. No placeholder implementation, Item reads, extra persistence
policy or privileged deployment step is included.
