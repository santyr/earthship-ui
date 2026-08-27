# Bitcoin Task 4 report: compact Home candlesticks

Status: implemented, self-reviewed, verified, and committed as fe4212f (feat: show bitcoin candles on home).

## Scope delivered

- Home fetches persisted `BTC_USD_Price` history on mount and every five minutes. The request begins at the current hour minus 23 hours and ends at the current time, so it covers the active hourly bucket plus the preceding 23 buckets.
- The Bitcoin tile keeps its existing current price and 24-hour percentage display, and now renders the existing compact `BitcoinCandles` component below them with explicit request bounds.
- The tile uses a bounded two-row grid with a nonzero candle area, `min-width: 0`, `min-height: 0`, and clipping. Browser checks prove the candle area has positive size and begins below both price and percentage at 1340x800 and 1280x720.
- The existing Bitcoin modal remains a candlestick presentation. Browser coverage verifies rendered candle SVG/OHLC text, usable exact 4h period selection, close, and focus restoration.
- Registered ECharts `CandlestickChart` in the existing modular adapter. This was necessary because the browser run exposed the exact runtime error: `Series candlestick is used but not imported`.

## TDD evidence

Initial RED:

- `npm test -- tests/home-tablet-contract.test.js` failed exactly because Home lacked the `BitcoinCandles` import.
- `npm run test:e2e -- tests/e2e/home-runtime.spec.js` failed in both settled-layout viewport cases because `.btc-candles svg` did not exist; both unavailable-state cases passed.
- After the compact component was added, a dedicated modular-import regression test failed because `CandlestickChart` was absent from `src/lib/charts/echarts.js`.

GREEN:

- `npm test -- tests/chart-imports.test.js`: 1 passed.
- `npm test -- tests/home-tablet-contract.test.js tests/bitcoin-candles.test.js tests/ui/BitcoinCandles.test.js tests/chart-call-sites.test.js`: 4 files, 34 tests passed.
- `npm run test:e2e -- tests/e2e/home-runtime.spec.js`: 4 passed, covering both 1340x800 and 1280x720.

## Full verification

- Fresh final `npm test`: 85 files, 1046 tests passed.
- A prior full run also passed 85 files / 1046 tests, but it occurred before the E2E-discovered ECharts registration fix. It was repeated once after the final source change so the final evidence is current.

## Self-review

- `git diff --check` passed.
- The history fetch uses the existing safe range helper, so a request failure yields an empty candle dataset without affecting live price or percentage text.
- Only the Bitcoin card uses the compact component; no other Home card or modal lifecycle was changed.
- The ECharts change registers only the missing tree-shakeable chart type; it keeps the existing core, component, and SVG registration model.

## Environment note

The host patch helper repeatedly failed before reading files with `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`. Per the task brief, all subsequent edits used narrow guarded Node rewrites that verified every expected target block before writing.

## Review correction

An independent review found that the first fixture edit had been lost during the guarded-rewrite recovery, leaving `BTC_USD_Price` on the monotonic fallback. A new browser assertion was written first and failed at both target viewports because the compact chart had green up-candle fills but no red down-candle fill. The fixture now derives an alternating up/down sequence from each observation's hour bucket, and the final Home E2E run confirms both `#22c55e` and `#ef4444` fills at 1340x800 and 1280x720.
