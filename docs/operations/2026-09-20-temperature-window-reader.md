# Qualified daily temperature evidence foundation — September 20

Implemented a pure interval reader and restricted read-only history adapter.
This is source-only foundation work; daily forecast learning has not yet been
migrated, and no live code, model state, timer, Item or control was changed.

## Evidence contract

`select_temperature_window` and `fetch_temperature_window` assess an elapsed,
half-open window of at most 25 hours. They consume every persisted change point,
not a five-minute sample grid that could omit a brief observed high or low.
They return qualified observed extrema, exact covered duration, longest uncovered
gap, total duration and a full-coverage flag. These are receipt-as-of evidence
metrics, not assertions of the physical day's true extrema or learning permission.

The shared point/grid barrier engine is unchanged: invalid/malformed rows,
receipt expiry, conflicting observations and restart epochs remain barriers.
Persistence delay cannot be backdated into coverage. A carry retains its original
timestamp; a next-day boundary value cannot alter yesterday's extrema. Empty
or wholly expired evidence returns no extrema. Neither interpolation nor numeric
history fallback is allowed.

The adapter uses one dedicated read-only repeatable-read transaction, the exact
Weather_Temperature_Evidence_JSON mapping, bounded queries and at most 10,000
rows including original carry. An incomplete/failed query returns no partial
result and exposes no database details. Invalid requests fail before connection.

## Verification

- 23 new regressions; 81 focused reader/transport tests passed.
- Full OpenHAB Python suite: 1,101 passed, 42 subtests passed, one skipped,
  in 139.07 seconds. Log: `/tmp/hex-temperature-window-tests.log`.
- Independent pre-refactor point-reader oracle: 7,200 selections over 12
  deterministic histories exactly matched interval coverage, longest gap and
  extrema. This oracle loaded the committed pre-change implementation, not the
  refactored point helper.
- Tests cover 23/24/25-hour days, actual Denver DST boundaries, sub-grid extrema,
  delayed persistence, expiry, stale replay, invalid barriers, restart epochs,
  conflicting duplicates, row bounds and transport failure.

Live restricted reads, with no learned-state writes:

| Window (UTC) | Covered / total seconds | Longest gap | Observed low / high F |
| --- | ---: | ---: | ---: |
| Sep19 06:00–Sep20 06:00 | 20576.812587 / 86400 | 65823.187413 | 48.02 / 60.08 |
| Sep20 06:00–12:55:47.970595 | 24947.970595 / 24947.970595 | 0 | 38.3 / 48.02 |

Yesterday is correctly partial because collection began in the evening. Today's
elapsed window is fully covered, but is not a completed day.

## Remaining integration

Daily `measured_day_weather` still reads numeric outdoor history; its high/low
results feed both daily Kalman learning and day-3 high scoring. Both consumers
must migrate together. Rain and PV have separate evidence contracts and are not
qualified by this temperature work.

Before activation, add a bounded worker and explicit cutover/coverage policy,
validate result metadata, preserve existing model state and consumed markers,
and record qualified scoring provenance without relabeling old forecast origins.
The existing same-day and day-3 forecast horizons must not be conflated. Failed
or insufficient evidence must skip temperature updates without numeric fallback.
No coverage threshold was silently adopted by this foundation change.

Natural thermal training remains active under PID2326440, started06:50:29MDT.
It was observed, not restarted. Its eventual result and the next natural shadow
publication remain separate outstanding gates.
