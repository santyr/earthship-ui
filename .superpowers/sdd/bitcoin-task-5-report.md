# Bitcoin Task 5: combined dashboard verification

Date: 2026-08-27

Worktree: `/home/sat/earthship-ui/.worktrees/dashboard-weather-bitcoin`

Verified product head: `710ee0a4f4fdefe796fb1f925c454152b286a44c`

## Result

No integration defect was found. No product code was changed. Controller
review identified an acceptance-test gap, so the Home Playwright fixture and
assertions were strengthened after the original evidence-only report commit.

## Fresh verification evidence

### 1. Focused Bitcoin and chart integration tests

Command:

```sh
npm test -- tests/bitcoin-candles.test.js tests/ui/BitcoinCandles.test.js tests/chart-store.test.js tests/ui/ChartModal.test.js tests/chart-call-sites.test.js tests/chart-options.test.js tests/home-tablet-contract.test.js
```

Exit status: 0. Vitest passed 7 test files and 63 tests in 1.60s.

### 2. Complete unit suite

Command:

```sh
npm test
```

Exit status: 0. Vitest passed 85 test files and 1,046 tests in 4.51s. No
unhandled errors were reported.

### 3. Production build

Command:

```sh
npm run build
```

Exit status: 0. Vite transformed 791 modules and wrote `dist/` in 678ms.

Warning: Vite issued its chunk-size advisory for minified `echarts` and icon
bundles larger than 500 kB. This did not fail the build.

### 4. Combined browser verification

Command:

```sh
npm run test:e2e -- tests/e2e/home-runtime.spec.js tests/e2e/weather-detail-modal.spec.js tests/e2e/weather-earthship-layout.spec.js
```

Exit status: 0. Playwright passed 12 tests in 16.2s using one worker. The
checks covered Home's settled, long, unavailable, and stale states; the
Home/Weather twelve-hour detail modal; and Weather/Earthship bounds at both
required viewports: 1340x800 and 1280x720.

Warning: Node reported that `NO_COLOR` is ignored because `FORCE_COLOR` is set.
This did not affect any browser assertion.

### 5. Repository state

Before writing this ignored report, the following command exited 0:

```sh
git diff --check && git status --short --branch && git rev-parse HEAD
```

`git diff --check` was silent, `git status --short --branch` showed only
`## feat/dashboard-weather-bitcoin`, and `HEAD` was
`710ee0a4f4fdefe796fb1f925c454152b286a44c`. `.superpowers/` is ignored, so
the report must be force-added deliberately for the evidence-only commit.

## Concerns

No product defect was observed. The two non-failing environment/build warnings
above remain informational.


## Acceptance-test correction

Controller review identified that the original Home browser fixture exercised
only green and red compact candles, and that its item-name-only request log
could not prove the exact 4-hour modal refetch or a completed candle rerender.

### RED

After adding only the neutral SVG assertion, the focused command below failed
in both settled target viewports exactly because the compact chart lacked the
orange neutral fill. Each failure received only green/red fills; the two
unavailable/stale cases continued to pass.

```sh
npm run test:e2e -- tests/e2e/home-runtime.spec.js
```

Result: 2 failed, 2 passed. The missing expected fill was `#f7931a`.

### Fixture and assertion coverage

The E2E-only fixture now records each persistence request as its item name plus
its actual URL. BTC data has quarter-hour up, down, and equal-open/close
patterns; the 4-hour response has a deterministic fresh offset. The settled
Home test proves all three actual compact SVG fills: green `#22c55e`, red
`#ef4444`, and neutral orange `#f7931a`.

After selecting the exact `4h` control, it waits for one additional
`BTC_USD_Price` request, parses the captured URLs, and proves the modal
window changes from exactly 24 hours to exactly 4 hours with a later/narrower
range. It also waits for a ready 4-hour accessibility description and proves
its latest OHLC sentence differs from the initial 24-hour result, which shows
the new response reached the rendered chart path.

### GREEN and regression verification

Focused Home browser test:

```sh
npm run test:e2e -- tests/e2e/home-runtime.spec.js
```

Exit status: 0. All 4 tests passed in 8.4s at 1340x800 and 1280x720.

Focused unit tests:

```sh
npm test -- tests/bitcoin-candles.test.js tests/ui/BitcoinCandles.test.js tests/chart-store.test.js tests/ui/ChartModal.test.js tests/chart-call-sites.test.js tests/chart-options.test.js tests/home-tablet-contract.test.js
```

Exit status: 0. Vitest passed 7 files and 63 tests in 1.68s.

Required combined browser suite:

```sh
npm run test:e2e -- tests/e2e/home-runtime.spec.js tests/e2e/weather-detail-modal.spec.js tests/e2e/weather-earthship-layout.spec.js
```

Exit status: 0. Playwright passed all 12 tests in 16.4s. Node again emitted the
non-failing `NO_COLOR`/`FORCE_COLOR` environment warning.
