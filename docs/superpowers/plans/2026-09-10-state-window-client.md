# State-window client implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Supply the bounded, no-look-ahead historical state-window request required by the approved Home temperature correction.

**Architecture:** Add an opt-in argument to the existing history client, sharing its bounded response reader. Do not switch consumers in this dependency task. Home day ownership, rollover, visibility restoration and browser acceptance remain required subsequent implementation before release.

**Tech Stack:** JavaScript, Vitest, existing fetch client.

## Global Constraints

- Existing getHistory callers retain their current behavior.
- Never request itemState=true or substitute the current Item value at an old boundary.
- Keep this path separate from sensor update metadata and all source-health calculations.
- No OpenHAB controls, persistence settings, notifications, learned state or telemetry producers change. Task 82 remains held.
- Retain existing response byte/row limits, abort propagation and malformed-body errors.

## Scope and acceptance

Approved spec: docs/superpowers/specs/2026-09-10-ui-day-history-design.md.
This completes its client dependency only. It does not fix the user-visible
high/low problem until Home opts in and gains local-day ownership. Keep this
branch isolated until that integration and independent whole-branch review.

### Task 1: Opt-in start-state carry with half-open clipping

**Files:** Modify src/lib/openhab/client.js; create tests/state-window-client.test.js.

**Interfaces:** Existing getHistory(name, options) gains optional boolean
includeStartState, default false. With true, starttime and endtime must be
offset-qualified date-time strings, finite under Date.parse; end must not
precede start. Equality returns [] without fetching. Valid nonempty requests
send boundary=true and keep only finite numeric row timestamps in [start,end).
Returned points retain time/state/unit shape, including invalid numeric states;
they convey state-in-effect, not original source observation time.

- [ ] Step 1: Write tests before changing source. Use real Response JSON bodies
and mock only fetch. Cover carry retention, clipping at/beyond end, negative
out-of-window and malformed timestamps, invalid numeric state preservation,
empty range no request, malformed/reversed/unqualified ranges no request,
default path unchanged, HTTP/body/byte-limit errors and abort signal forwarding.
Core test code:

```js
import { afterEach, expect, it, vi } from 'vitest';
import { createClient, MAX_HISTORY_RESPONSE_BYTES } from '../src/lib/openhab/client.js';
const starttime = '2026-09-04T06:01:00Z';
const endtime = '2026-09-04T06:03:00Z';
const start = Date.parse(starttime), end = Date.parse(endtime);
const client = () => createClient({ openhabUrl: '', apiToken: '' });
afterEach(() => vi.unstubAllGlobals());
it('keeps start state but discards native future end boundary', async () => {
  const rows = [{time:start,state:'65.48'}, {time:start+105525,state:'65.3'},
    {time:end,state:'65.48'}, {time:end+1,state:'100'},
    {time:start-1,state:'100'}, {time:null,state:'100'}];
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({data:rows})));
  vi.stubGlobal('fetch', fetcher);
  expect(await client().getHistory('Outdoor', {starttime,endtime,includeStartState:true}))
    .toEqual(rows.slice(0,2));
  const url = new URL(fetcher.mock.calls[0][0], 'http://fixture');
  expect(url.searchParams.get('boundary')).toBe('true');
  expect(url.searchParams.has('itemState')).toBe(false);
});
it.each([
  [undefined,endtime], ['',endtime], ['invalid',endtime],
  ['2026-09-04T06:01:00',endtime], [endtime,starttime], [starttime,null],
])('rejects unqualified range %s %s before I/O', async (a,b) => {
  const fetcher = vi.fn(); vi.stubGlobal('fetch',fetcher);
  await expect(client().getHistory('Outdoor', {starttime:a,endtime:b,includeStartState:true})).rejects.toThrow();
  expect(fetcher).not.toHaveBeenCalled();
});
```

Complete the other enumerated cases using the same real Response fixture and
explicit result/exception assertions. For the byte limit set Content-Length
to MAX_HISTORY_RESPONSE_BYTES+1; for malformed body use data:{}; for abort
make fetch reject an AbortError and assert the exact signal and rejection.

- [ ] Step 2: Run `npm test -- --run tests/state-window-client.test.js` and
record expected behavior failures before source edits. The baseline client
suite must remain passing. Do not count setup/import errors as RED.

- [ ] Step 3: Extend the existing method destructuring with
`includeStartState = false`. At its beginning implement:

```js
let startMs;
let endMs;
if (includeStartState) {
  const qualified = (value) => typeof value === 'string'
    && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value);
  startMs = qualified(starttime) ? Date.parse(starttime) : NaN;
  endMs = qualified(endtime) ? Date.parse(endtime) : NaN;
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) {
    throw new HistoryResponseError('Invalid state history window', 'invalid-history-window');
  }
  if (startMs === endMs) return [];
}
```

After constructing existing URLSearchParams, add
`if (includeStartState) q.set('boundary', 'true');`.
After existing body and row-limit validation, replace the mapping receiver:

```js
// Native start boundary means state-in-effect, not original observation time.
// Native end boundary can contain a later value: always discard it.
const rows = includeStartState
  ? d.data.filter((point) => typeof point?.time === 'number'
    && Number.isFinite(point.time) && point.time >= startMs && point.time < endMs)
  : d.data;
```

Return rows.map with the existing time/state/unit mapper unchanged. No extra
request, timestamp synthesis, numeric-state normalization or current-item read.

- [ ] Step 4: Run `npm test -- --run tests/state-window-client.test.js tests/client.test.js`,
then `npm test -- --run` once and `git diff --check`. Record counts and warnings.
Check that only the two intended code/test files changed.

- [ ] Step 5: Commit only those files as `fix: bound opt-in history start carry`.
Self-review and report RED/GREEN commands, outputs and any concerns. Independent
task review is required; do not merge, push, deploy or switch Home in this task.

## Self-review

The plan covers the client's finite explicit range, empty-window behavior,
start carry, no-look-ahead, default compatibility, cancellation and response
limits. Home lifecycle, DST/race/browser tests and full user-visible verification
remain subsequent work; this dependency cannot close the approved UI spec.
