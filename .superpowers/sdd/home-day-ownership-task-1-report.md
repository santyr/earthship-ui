# Home day ownership Task 1 implementation report

## Implemented

- Added `historyExtremaForDay(points, historyDayStart, nowMs, currentValue)` so daily extrema accept persisted rows only when their recorded local-day identity matches the current clock day, otherwise falling back to the live value.
- Home now owns a nullable `temperatureHistoryDay`, requests start-state carry only for the two daily temperature histories, rejects late prior-day commits, and derives indoor/outdoor extrema through the day-aware helper.
- The existing minute timer now reconciles local-day changes, clears old daily history immediately, and starts a new refresh. Visible `visibilitychange` also reconciles the day; destruction removes the exact listener while retaining existing refresh coordinator and timer cleanup.
- Extended the browser fixture with an asynchronous request-range-aware `historyRows` callback. Default non-Bitcoin fixture rows now derive timestamps from the explicit request range, avoiding browser/Node clock drift while keeping all samples inside `[start,end)`.
- Added pure and browser regressions for DST/local-day identity, invalid inputs, boundary carry/clipping, rollover pending state, late response rejection, visibility restoration/cleanup, GET-only behavior, error-free runtime, and 1340x800 horizontal bounds.

## TDD evidence

### RED

- `npm test -- tests/home-card-state.test.js`
  - 1 file executed; 186 prior tests passed and all 6 new tests failed with the expected `TypeError: historyExtremaForDay is not a function` before production changes.
- `npx playwright test tests/e2e/home-runtime.spec.js --grep "Home local-day temperature history ownership" --reporter=line`
  - 4/4 new cases failed before production changes: end-boundary values leaked into extrema, rollover/late responses did not have day ownership, and no daily request carried `boundary=true`.
- After the production implementation, the first focused browser run was 3/4 green. The rollover test remained blocked because its test callback accidentally deferred the indoor six-hour request as well as the new-day daily requests. Narrowing the deferment to the explicit next-midnight request range corrected the fixture.
- The first complete Home runtime run was 7/9 green. Both legacy settled cases lost their synthetic high because their default persistence rows used Node `Date.now()` and the reviewed client now correctly clips against the browser's explicit request end. Deriving default fixture timestamps from each request range restored the intended strictly in-window state sequence.

### GREEN

- `npm test -- tests/home-card-state.test.js`: 192/192 passed.
- Focused new browser cases: 4/4 passed in 6.3s.
- Fresh final `npm test`: 89 files, 1,174/1,174 tests passed in 4.32s.
- Fresh final complete `home-runtime.spec.js`: 9/9 passed in 15.0s.
- `npm run build`: succeeded; 795 modules transformed in 708ms.
- `git diff --check`: clean before report/commit; rerun in final commit gate.

## Warnings

- Playwright emitted the existing warning that `NO_COLOR` is ignored because `FORCE_COLOR` is set.
- Vite emitted its existing advisory about chunks larger than 500 kB after minification.

## Files changed

- `src/lib/ui/homeCardState.js`
- `src/screens/Home.svelte`
- `tests/home-card-state.test.js`
- `tests/e2e/home-runtime.spec.js`
- `.superpowers/sdd/home-day-ownership-task-1-report.md`

## Self-review

- Daily boundary carry is opt-in only for indoor/outdoor current-day temperature requests; load, gust, six-hour histories, Bitcoin, and rolling-24-hour Item contracts are unchanged.
- Current temperatures remain part of extrema and remain visible while new-day history is pending.
- The latest-generation coordinator still owns cancellation; the day identity guard independently prevents a late old-day result from publishing.
- Layout, current-value presentation, freshness alerts, charts, controls, OpenHAB persistence, notifications, learned state, and telemetry producers were not changed.
- Deferred browser responses are released in `finally`, all new cases assert no attempted non-GET requests and no page errors, and the visibility listener is tested after route destruction.

## Concerns

None. This is fixture evidence around controlled browser clocks, not a claim of a live overnight observation.
