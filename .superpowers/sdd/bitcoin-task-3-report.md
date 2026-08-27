# Bitcoin Task 3 report: candlestick chart store and modal presentation

Status: implemented, self-reviewed, and verified. This report is included in the Task 3 commit.

## Scope delivered

- Extended `openChart` and `chartStore` with a backward-compatible `presentation` field. Existing callers default to `line`; only the exact `candlestick` value is accepted; closing retains the selected presentation.
- Added a candlestick render adapter inside `ChartModal.renderLatest`. It aggregates only the first loaded series over the active history window with `bitcoinCandleInterval(activeHours)`, builds the full Bitcoin candle option, and derives accessible latest-OHLC text from the same candle array.
- Kept the shared history request, cancellation and stale-load guards, five-minute refresh, period controls, focus trap and restoration, close behavior, error handling, resize observation, and chart disposal pipeline unchanged.
- Preserved the existing line option and extrema-marker branch for every non-candlestick chart.
- Clears accessible candle state at each load start, close, request/option error, no-client result, and empty result so prior OHLC values cannot leak into a new state.
- Opted in only the Home Bitcoin chart. Outdoor, Indoor, Battery, Wind, Rain, Solar, and Pressure remain implicit line charts.
- Did not add compact Home candles in this task.

## TDD evidence

Store RED, before the presentation field existed:

    npm test -- tests/chart-store.test.js
    1 passed, 3 failed
    Expected line/candlestick, received undefined

Store GREEN:

    npm test -- tests/chart-store.test.js
    4 passed

Modal RED, before the render adapter existed:

    npm test -- tests/ui/ChartModal.test.js
    13 passed, 7 failed
    The option remained a line/time-axis option and exposed no latest candle OHLC

Modal GREEN:

    npm test -- tests/ui/ChartModal.test.js
    20 passed

Call-site RED, before Bitcoin opted in:

    npm test -- tests/chart-call-sites.test.js
    3 passed, 1 failed
    Bitcoin lacked presentation: 'candlestick'

Focused GREEN:

    npm test -- tests/chart-store.test.js tests/ui/ChartModal.test.js tests/chart-call-sites.test.js tests/chart-options.test.js
    4 files passed, 33 tests passed

Full Vitest verification, run once after self-review:

    npm test
    85 files passed, 1046 tests passed

## Self-review

- All four selectors were exercised through the modal: 4h uses 15-minute buckets, 24h uses 60-minute buckets, 7d uses 360-minute buckets, and 30d uses browser-local daily buckets.
- Tests assert ECharts candlestick type, `[open, close, low, high]` values, bucket timestamps, and the whole-dollar accessible OHLC summary.
- Candlestick tests cover reload clearing, request error, empty history, render failure, resize rerender, and close disposal. The pre-existing abort, queued-load, focus, refresh, partial-error, timeout, and line-extrema regressions remain green.
- The production diff branches only rendering and accessible candle state; it does not duplicate or replace the modal lifecycle.
- `git diff --check` passed before full verification.

## Concerns

- No product blocker identified.
- The host's sandboxed patch helper intermittently failed with `bwrap: loopback: Failed RTM_NEWADDR`; the installed `apply_patch` command was used outside that broken wrapper for narrow patch edits. This did not affect tests or product behavior.
