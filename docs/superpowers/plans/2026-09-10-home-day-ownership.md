# Home current-day history integration plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Finish the approved user-visible current-day temperature carry and rollover correction.

**Architecture:** Home opts its two daily temperature reads into the bounded state-window client. Daily arrays carry a shared local-midnight identity. Both commit-time and render-time checks prevent yesterday's results from appearing as today's. Existing rolling sparklines retain their meaning.

**Tech Stack:** Svelte 5, JavaScript, Vitest, Playwright.

## Global Constraints

- Correct Home's indoor and outdoor current-day high/low calculation.
- Preserve the existing layout, current temperature presentation, independent freshness alerts, six-hour charts, Bitcoin candles and rolling-24-hour Item contracts.
- No OpenHAB controls, persistence settings, notifications, learned state or telemetry producers change. Task 82 remains held.
- At the first existing minute clock tick after a day change, invalidate old-day temperature histories and start a fresh daily request.
- Check again on tab visibility restoration, so a sleeping tablet does not wait for its next five-minute refresh.
- No screenshots are required.

## Dependencies and scope

Approved spec: docs/superpowers/specs/2026-09-10-ui-day-history-design.md.
Requires reviewed client task from 2026-09-10-state-window-client.md:
getHistory(name,{starttime,endtime,signal,includeStartState:true}) returns
state-in-effect history clipped to [start,end), not freshness evidence.
Do not dispatch this task until that task passes review.

### Task 1: Day-owned Home temperature history with runtime regression tests

**Files:** Modify src/screens/Home.svelte, src/lib/ui/homeCardState.js,
tests/home-card-state.test.js and tests/e2e/home-runtime.spec.js.

**Interfaces:** Add exported historyExtremaForDay(points, historyDayStart,
nowMs, currentValue=null), returning the existing {high,low} shape. It consumes
the localDayHistoryRange and historyExtrema functions already in the module.
Home stores temperatureHistoryDay as a nullable string and continues storing
outdoorTodayHistory/indoorTodayHistory as arrays.

- [ ] Step 1: Add failing pure and browser tests before production changes.
Pure test core (add the new function to the existing import):

```js
it('excludes yesterday history even before the replacement fetch completes', () => {
  const yesterday = localDayHistoryRange(new Date('2026-09-09T23:59:50-06:00')).starttime;
  const now = Date.parse('2026-09-10T00:00:10-06:00');
  expect(historyExtremaForDay([{time:now-3600000,state:'95'}],yesterday,now,65))
    .toEqual({high:65,low:65});
});
it.each(['2026-03-08T23:59:00-06:00','2026-11-01T23:59:00-07:00',
  '2026-09-10T23:59:00-06:00'])('accepts matching local day %s', stamp => {
  const now = Date.parse(stamp);
  const day = localDayHistoryRange(new Date(now)).starttime;
  expect(historyExtremaForDay([{time:now-1000,state:'95'}],day,now,65))
    .toEqual({high:95,low:65});
});
```

Also assert invalid clock/day identity yields current-only extrema, including
null current yielding null/null; matched-day invalid numeric states remain
excluded. Preserve all existing local-day/DST tests.

Extend openHomeFixture with optional asynchronous historyRows callback:
callback receives {name,startMs,endMs,url}; undefined selects the existing
fixture data, otherwise its returned array is the persistence data. Make only
the route handler async. Existing fixture users remain unchanged.

Add Playwright tests to that same spec using page.clock.install before opening
Home, at 23:59:10 in America/Denver (set test context timezone explicitly).
Use response rows at start=95, interior=50 and end=999 for outdoor; choose
equivalent distinguishing indoor values. Assert both native start values appear
in daily extrema and the end values never do. Record requested boundary=true
only for daily temperatures, not rolling histories, Bitcoin or power.

For rollover hold the first new-day temperature responses behind a test-owned
promise, advance the clock across its minute tick, assert yesterday's extrema
are absent while the response is pending, then resolve with new-day rows and
assert those extrema. For late-response rejection, begin the initial pre-midnight
refresh at 23:59 with no accepted daily history yet, hold its response, move
browser Date to after midnight without firing
the minute timer, resolve the old response, and assert it does not publish old
extrema; then trigger the next clock tick and assert current-only/new-day state.
Use page.clock.setSystemTime and runFor for explicit scheduling, not real sleep.

Test visibility restoration across midnight using the same fixed clock plus a
visibilitychange event when document.visibilityState is visible. Assert a new
daily request without advancing five minutes. Navigate away/destroy and ensure
the added visibility listener produces no new temperature requests. Keep each
deferred response released in test cleanup so no route remains hanging.

For all new browser tests collect attempted non-GET requests and page errors;
assert neither occurs and that scrollWidth<=clientWidth at 1340x800. This is
fixture evidence, not a live overnight claim. Update pre-existing source-string
assertions only where the new helper genuinely changes wiring; retain behavior
assertions rather than replacing them with vacuous text checks.

- [ ] Step 2: Run focused Vitest and new browser tests and record expected RED
for missing helper / stale-day behavior before editing production source.

- [ ] Step 3: Implement the pure helper:

```js
export function historyExtremaForDay(points, historyDayStart, nowMs, currentValue = null) {
  const range = Number.isFinite(nowMs) ? localDayHistoryRange(new Date(nowMs)) : null;
  return historyExtrema(range && historyDayStart === range.starttime ? points : [], currentValue);
}
```

Import it in Home instead of its old historyExtrema import. Add
`let temperatureHistoryDay = $state(null);` beside the daily history arrays.
Extend fetchHistoryRange with final includeStartState=false argument, passing
that argument through to client.getHistory. Only the two daily temperature
calls pass true. Other callers retain false, and fetchHistorySafe is unchanged.

In the existing latest-generation temperature commit callback:

```js
indoorSpark = indoorSixHours;
if (range.starttime !== localDayHistoryRange(new Date()).starttime) return;
temperatureHistoryDay = range.starttime;
outdoorTodayHistory = outdoorDay;
indoorTodayHistory = indoorDay;
```

Replace the two extrema derivations with historyExtremaForDay using their
respective arrays, temperatureHistoryDay, wallClock and current temperature.

Add clock reconciliation next to the existing timers:

```js
function reconcileDayClock() {
  const oldDay = localDayHistoryRange(new Date(wallClock))?.starttime;
  wallClock = Date.now();
  const newDay = localDayHistoryRange(new Date(wallClock))?.starttime;
  if (newDay && newDay !== oldDay) {
    temperatureHistoryDay = null;
    outdoorTodayHistory = [];
    indoorTodayHistory = [];
    refreshTemperatureHistory();
  }
}
function handleDayVisibility() {
  if (document.visibilityState === 'visible') reconcileDayClock();
}
```

Use reconcileDayClock as the existing minute interval callback. Register
visibilitychange on mount and remove the exact listener on destroy. Keep the
five-minute interval and latest-refresh destruction. Do not change load-energy,
gust, chart interpolation, staleness or any OpenHAB side-effect path.

- [ ] Step 4: Run focused tests until green, then full Vitest, complete
home-runtime.spec.js and npm run build once. Record counts and warnings.
Run git diff --check and inspect all changes for scope/noninterference.

- [ ] Step 5: Commit intended files only and report full RED/GREEN evidence.
No merge/push/deploy by implementer. Independent task and final whole-branch
reviews precede integration; controller verifies live read-only requests after
release and updates the canonical tracker without claiming an overnight run.

## Self-review

This task plus the reviewed client dependency covers the approved UI spec's
carry, clipping, day identity, request races, visibility cleanup, DST and browser
requirements. Broader power/gust/plotting algorithms and BMS atomic production
remain separate required work. No new user-facing feature or control authority.
