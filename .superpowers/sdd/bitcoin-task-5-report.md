# Bitcoin Task 5: combined dashboard verification

Date: 2026-08-27

Worktree: `/home/sat/earthship-ui/.worktrees/dashboard-weather-bitcoin`

Verified product head: `710ee0a4f4fdefe796fb1f925c454152b286a44c`

## Result

No integration defect was found. No product code or test was changed. This
report is the only file intended for the evidence commit.

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
