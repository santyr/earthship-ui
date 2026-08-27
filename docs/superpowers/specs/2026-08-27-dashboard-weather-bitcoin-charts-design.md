# Dashboard Weather Learning and Bitcoin Charts

**Date:** 2026-08-27  
**Status:** Approved in conversation; implementation pending

## Goal

Make the Home dashboard describe the current local day and the site's learned
forecast rather than rolling or raw-provider approximations. Improve compact
trend visibility for indoor temperature and Bitcoin without making the Home
screen less readable at the supported 1340x800 and 1280x720 viewports.

This increment changes five related surfaces:

1. Home indoor and outdoor daily extrema;
2. current and forecast weather-condition icons;
3. learned daily and hourly forecast values;
4. the shared forecast-detail modal; and
5. Home and modal Bitcoin charts.

## Scope and safety boundaries

- OpenHAB remains the durable store for measurements and learned forecast
  state.
- Raw forecasts remain the only inputs to scoring. Corrected values must never
  be fed back as observations or forecast errors.
- Only quantities with validated correction models are adjusted: temperature
  and PV. Precipitation, wind, and radiation remain provider values.
- Existing control and advisory authority is unchanged. This work changes
  forecast production and presentation, not equipment actuation.
- Missing or malformed data is shown as unavailable. The UI does not invent
  observations, candles, or forecast values.

## 1. Current-day indoor and outdoor extrema

The Home page will stop displaying `OutdoorTemp_24h_High`,
`OutdoorTemp_24h_Low`, `IndoorTemp_24h_High`, and `IndoorTemp_24h_Low` in its
temperature cards. Those items describe a rolling day and therefore include
part of yesterday.

At mount and every five minutes, Home will fetch indoor and outdoor temperature
history from local midnight through the current instant. A shared pure helper
will parse the persisted QuantityType states and return the minimum and maximum
valid observations. The current live reading participates as a fallback so a
new day with sparse persistence can still show an honest current-day high and
low. If neither persistence nor a current reading is valid, both values remain
unavailable.

The labels remain compact `H … / L …`; their semantics become “today so far.”
The clock and history range continue to use the browser's local Mountain time,
including DST boundaries.

## 2. Indoor temperature sparkline and card layout

Home will fetch six hours of indoor temperature history alongside the existing
outdoor, battery, and pressure histories. The indoor card will use the same
two-column visual hierarchy as Outdoor:

- the icon, current temperature, humidity, and today's extrema occupy the
  reading column;
- a compact six-hour sparkline occupies the remaining width;
- the sparkline uses the same temperature-band color as the indoor icon; and
- the whole card remains keyboard- and pointer-activatable for the existing
  24-hour Indoor Temperature modal.

Font sizes, gaps, and chart width may tighten at the two supported dashboard
viewports, but the current reading remains the dominant element. Text and chart
must not overlap or clip.

## 3. Partly-cloudy condition icons

The shared weather icon adapter will normalize both WMO codes and textual/icon
states. WMO code 2 and case-insensitive variants such as `partly cloudy`,
`partially cloudy`, `partly-cloudy`, and their day/night icon names resolve to
the appropriate Material Design partly-cloudy icon. A valid explicit icon name
that is not one of these aliases remains untouched.

Forecast components continue using the WMO map. The Home current-condition
card uses the normalized adapter rather than passing `SkyConditionIcon`
through blindly. Unknown or unavailable current conditions retain the existing
safe partly-cloudy fallback.

## 4. Learned daily forecast values

`forecast_intel.py` remains responsible for applying learned corrections so
all consumers receive the same displayed values.

Daily high and low values in `Forecast_Daily_JSON` and
`Forecast_10Day_JSON` will apply the existing Kalman corrections:

```text
corrected high = raw provider high - learned high bias
corrected low  = raw provider low  - learned low bias
```

The existing `Forecast_Tomorrow_High` and `Forecast_Tomorrow_Low` behavior is
unchanged, except that all daily displays now agree with those corrected
items. Per-day PV already uses learned `k_res` and remains the displayed PV
value. Precipitation probability/amount, wind, and radiation stay raw because
there is no validated correction model for them.

Raw daily high, low, and PV inputs remain in the scoring records. The producer
must never score a corrected value.

## 5. Learned hourly temperature correction

### Raw evidence capture

The daily forecast run will retain one consistent next-day raw temperature
forecast per target hour. Each record is keyed by its offset-aware target
timestamp and contains the raw provider value and capture timestamp. This
fixed daily capture avoids mixing frequently refreshed forecasts with
different lead times.

On later daily runs, fully elapsed targets are matched to the nearest valid
persisted outdoor-temperature observation within 15 minutes on either side of
the target timestamp; an equal-distance tie uses the earlier observation.
Targets without a trustworthy observation remain unscored. Scored targets are
removed immediately, unscored targets are pruned 72 hours after their target,
and no more than the newest 96 raw targets are retained.

### Hour-specific model

The state file gains 24 local-hour bias buckets. Each bucket contains a scalar
Kalman state (`b=0`, `p=10`, process noise `Q=0.10`, observation noise `R=9`)
and an observation count. The innovation is always:

```text
raw hourly forecast - measured outdoor temperature
```

Updates reject non-finite values and clamp the published correction to
plus-or-minus 20°F. DST timestamps are scored by their offset-aware instant and
then assigned to the corresponding local-hour bucket; repeated hours therefore
remain distinct evidence while contributing to the same clock-hour model.

### Cold-start and blending

Before a bucket has enough evidence, its fallback correction is interpolated
between the learned daily-low and daily-high corrections according to the raw
hourly temperature's position within that day's raw forecast range. This gives
cold hours more of the low correction and warm hours more of the high
correction without pretending an hour-specific history already exists.

As observations accumulate, `min(observation count / 14, 1)` gradually blends
from that fallback toward the hour bucket's learned correction. The final
published correction is clamped to plus-or-minus 20°F. No “learned hourly”
provenance is claimed when the bucket is still operating entirely from the
daily fallback; provenance reports the bucket observation count and blend
weight.

### Publication contract

Both `Forecast_Hourly_JSON` and each hourly `tempF` in
`Forecast_10Day_JSON` receive the same corrected hourly values. Daily summary
highs/lows use the daily Kalman corrections described above.

The detailed payload advances to contract version 2 and includes a required
root `temperatureAdjustment` object containing the daily high/low corrections,
hourly method, and generation-time bucket counts/weights. The UI parser accepts
both legacy version 1 raw payloads and version 2 corrected payloads during
rollout. Unsupported
versions remain unavailable. The UI deploys before or with the producer so a
new payload is never published to a parser that rejects it.

The two-hour JSON refresh loads the persisted correction state before building
payloads. It updates presentation but does not score observations or mutate the
models.

## 6. Twelve-hour forecast detail

The shared weather modal will display 12 forecast hours:

- for Today, the next 12 whole forecast hours, continuing across midnight when
  the payload contains the following day;
- for future days, 07:00 through 18:00 local time inclusive.

Coverage text, missing-hour counts, accessible descriptions, icon strips, and
the chart all use 12 as the expected count. Partial payloads preserve and show
every valid period they contain; the UI does not synthesize missing hours.

The compact day summary and chart continue to display temperature,
precipitation, radiation, wind, and condition. Version 2 temperature values are
already corrected by the producer; the UI does not apply a second correction.

## 7. Bitcoin candlestick charts

### Data semantics

The only required source is persisted `BTC_USD_Price`. The UI will aggregate
valid spot-price observations into local OHLC intervals:

- open: first valid observation in the interval;
- high: maximum valid observation;
- low: minimum valid observation; and
- close: last valid observation.

These are honest OHLC candles derived from this host's observations. They are
not exchange-native candles and contain no volume. Empty intervals are omitted.
A one-sample interval becomes a zero-body neutral candle rather than an
invented range.

The pure aggregation helper sorts observations, rejects invalid timestamps and
states, and never bridges missing intervals. Sub-day candles align to Unix
epoch interval boundaries; daily candles align to browser-local midnight so
the 30-day view remains calendar-correct across DST.

### Home card

Home will fetch the current aligned hour plus the preceding 23 hours of Bitcoin
history on mount and every five minutes. The Bitcoin card will retain the
current USD price and 24-hour percent change, then add up to 24 compact hourly
candles. The card chart has no axes, labels, tooltip, or animation and remains
subordinate to the price text.

Up candles use the existing positive green, down candles use the existing
negative red, and neutral/single-sample candles use Bitcoin orange. The card
continues opening the Bitcoin modal by pointer or keyboard.

This explicitly supersedes the 2026-07-17 audit decision that removed inline
Bitcoin history from Home.

### Modal

The existing chart store gains an explicit candlestick presentation kind.
`ChartModal` continues using the normal history request, loading, cancellation,
refresh, focus, error, and period-control paths, but selects a candlestick
option builder for Bitcoin.

Intervals adapt to the selected period:

| Period | Candle interval |
| --- | --- |
| 4 hours | 15 minutes |
| 24 hours | 1 hour |
| 7 days | 6 hours |
| 30 days | 1 day |

The modal exposes an accessible summary of the latest candle's open, high,
low, and close along with loading/error state. It does not render a misleading
line fallback when no complete price observations exist.

## 8. Component boundaries

- `homeCardState.js`: pure local-day extrema and current-condition icon
  normalization helpers.
- `forecastDetail.js`: version 1/2 parsing and deterministic 12-hour window
  selection.
- `forecast_intel.py`: raw forecast capture, hourly bias scoring/blending, and
  corrected payload publication.
- a focused Bitcoin candle module: pure history-to-OHLC aggregation and ECharts
  option construction.
- a compact reusable candle component: Home-card rendering only.
- `ChartModal.svelte`: chooses line or candlestick presentation while retaining
  its existing lifecycle and accessibility behavior.
- `Home.svelte`: orchestrates history refreshes and lays out the revised cards;
  it does not contain correction or OHLC algorithms.

## 9. Failure behavior

- A failed extrema or sparkline request leaves current readings usable and
  shows unavailable extrema/chart data.
- A missing learned model uses the bounded daily fallback; missing daily
  correction state means a zero correction, not a fabricated adjustment.
- A malformed version 2 payload is rejected under the same size, ordering,
  timestamp, and numeric validation as version 1.
- Failed Bitcoin history leaves the current price and percent change visible.
- A malformed Bitcoin sample is discarded independently; it cannot invalidate
  other candles.
- Existing stale forecast messaging remains visible and applies equally to
  corrected payloads.

## 10. Verification

Implementation follows test-driven development. Required evidence includes:

- pure tests for local-day range/extrema behavior, partly-cloudy aliases,
  hourly correction capture/scoring/blending, correction bounds, and raw-only
  scoring;
- producer contract tests proving corrected legacy/detail values, version 2
  provenance, standalone refresh behavior, and unchanged raw wind/rain/
  radiation;
- forecast parser/window tests for versions 1 and 2, 12-hour rolling and
  07:00-18:00 windows, DST ordering, and partial coverage;
- OHLC aggregation tests for sorting, boundaries, up/down/neutral candles,
  invalid samples, empty gaps, and all four modal periods;
- Svelte tests for the Indoor sparkline, current-day extrema, normalized
  condition icon, 12-hour modal, Bitcoin card candles, and modal candle mode;
- regression tests for line-chart call sites and chart-modal lifecycle;
- production build and the complete unit suite; and
- Playwright checks at 1340x800 and 1280x720 proving no overlap or clipping,
  keyboard activation, 12 visible forecast hours, and correctly colored
  Bitcoin candles in both Home and the modal.

No completion claim is made until the relevant tests, full suite, build, and
viewport checks pass against the final working tree.
