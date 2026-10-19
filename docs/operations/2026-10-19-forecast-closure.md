# WeatherNext and household forecast closure

This is the current tracker for the operator's goal to identify and close WeatherNext and household forecasting bugs and gaps. It extends the retained [consumer inventory and audit](2026-10-19-weathernext-ml-consumer-audit.md); immutable original audits and historical forecasts remain unchanged. Automatic actuation stays disabled.

| ID | Finding | Status and evidence |
|---|---|---|
| WNML-01–05 | Radiation interval interpretation, retired daily energy dependency, incompatible scoring indexes, unscheduled weather evaluation, parser dependency coupling | Previously deployed; see [consumer repairs](2026-10-19-weathernext-consumer-repairs.md). Current thermal and four energy scoring reports refresh. |
| FC-01 | UI hourly forecast selected the 336-hour source, ignoring newer retained interim runs | Corrected in source; deployment verification pending. Independent 24-hour and 336-hour profiles retain original source, availability and issue identities. Near-term hours overlay the extended hourly outlook; daily summaries retain their extended issue. Missing extended coverage can still serve explicitly identified near-term coverage. All contributing originals are rechecked before publication. |
| FC-02 | Today’s rain unavailable when an original cannot cover elapsed calendar-day intervals | Corrected in source; deployment verification pending. UI total explicitly covers remaining complete native hourly intervals, beginning at the next whole hour and ending at next local midnight. The in-progress interval is excluded; no prorating or fabricated observations. Legacy daily JSON and numeric Items keep their full-day meaning. |
| FC-03 | UI accepted a future publication timestamp as current | Corrected in source; deployment verification pending. Future-dated details are unavailable. A modal fixture that generated its issue before moving the test clock now regenerates it after the clock change. |
| FC-04 | Household observation usually expires before the next five-minute publication | Confirmed live, investigation open. At 21:45 UTC its final verification was 21:45:33 and expiry 21:45:37; the original inverter/load measurement’s 30-second validity was the limiting source. The endpoint correctly refuses expired advice, but the operator loses visibility between cycles. Original telemetry validity must not be renewed. |

## Cadence and provenance

Collection runs hourly at :41, retaining the latest full-range run and any newer interim run, reusing unchanged originals. UI publication runs at :47. Native thermal/PV serving continues every five minutes. No additional Google downloads are required for the publication fix.

Google documents hourly initializations, 48-hour interim horizons and 360-hour full cycles initialized at 00/06/12/18 UTC. Earth Engine dissemination targets are interim initialization plus 7h25m and full cycles at 08:10/14:10/20:10/02:10 UTC, with delivery variance. See [dissemination](https://developers.google.com/weathernext/guides/dissemination) and [model specifications](https://developers.google.com/weathernext/guides/models). Collection timing does not guarantee upstream availability.

The composite publication is versioned separately from single-issue model inputs. Its extended source remains the detail's top-level source; `profiles.nearTerm` and `profiles.extended` identify independent coverage and status. Overlaid hours identify `nearTerm`; unmarked hours use the extended profile. Current-day remaining precipitation retains its own profile and exact interval. This publication does not enter training or immutable scoring as a fictitious single forecast issue.

## Verification

- WeatherNext suite: 235 cases, 232 passed and three optional integration skips; includes different numerical short/long forecasts, loss of extended coverage, expired sources, compact payloads and short-original corruption during publication.
- Frontend suite: all 2,569 tests across 170 files passed. Production build passed.
- Broader household/native regression run and live dual-profile/browser verification are in progress.
- Live household energy, profiled energy, chronology and all four performance endpoints returned HTTP 200 with fresh timestamps at 21:49 UTC. The general observation endpoint's HTTP 503 is tracked as FC-04, rather than misreported as complete integration.

Closure requires live readbacks for deployed fixes and resolution or explicit classification of every confirmed tracker finding. Pending outcome maturity and unqualified model skill remain measurement limitations, not grounds for inventing accuracy or enabling actuators.
