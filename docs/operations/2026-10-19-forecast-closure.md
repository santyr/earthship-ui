# WeatherNext and household forecast closure

This is the current tracker for the operator's goal to identify and close WeatherNext and household forecasting bugs and gaps. It extends the retained [consumer inventory and audit](2026-10-19-weathernext-ml-consumer-audit.md); immutable original audits and historical forecasts remain unchanged. Automatic actuation stays disabled.

| ID | Finding | Status and evidence |
|---|---|---|
| WNML-01–05 | Radiation interval interpretation, retired daily energy dependency, incompatible scoring indexes, unscheduled weather evaluation, parser dependency coupling | Previously deployed; see [consumer repairs](2026-10-19-weathernext-consumer-repairs.md). Current thermal and four energy scoring reports refresh. |
| FC-01 | UI hourly forecast selected the 336-hour source, ignoring newer retained interim runs | Deployed and read back at 21:52 UTC: near-term initialization 14:00 UTC, extended initialization 12:00 UTC, ten days and 224 hourly points. Independent 24-hour and 336-hour profiles retain original source, availability and issue identities. Near-term hours overlay the extended hourly outlook; daily summaries retain their extended issue. Missing extended coverage can still serve explicitly identified near-term coverage. All contributing originals are rechecked before publication. |
| FC-02 | Today’s rain unavailable when an original cannot cover elapsed calendar-day intervals | Backend deployed and read back at 21:52 UTC; UI deployment pending. UI total explicitly covers remaining complete native hourly intervals, beginning at the next whole hour and ending at next local midnight. The in-progress interval is excluded; no prorating or fabricated observations. Legacy daily JSON and numeric Items keep their full-day meaning. |
| FC-03 | UI accepted a future publication timestamp as current | Corrected in source; deployment verification pending. Future-dated details are unavailable. A modal fixture that generated its issue before moving the test clock now regenerates it after the clock change. |
| FC-04 | Household UI rejects the canonical trajectory energy qualification | Root cause confirmed: backend emits `conditional_uncalibrated_scenario`, UI accepted only `not_assessed` or `not_graduated`. Parser now accepts the conditional value only for energy. Actual retained v4 observation parses; expired sources remain expired and effective mode unavailable. Deployment pending. |
| FC-05 | One temporary publisher refusal loses the entire hourly publication | Bounded recovery added and tested: restart after 60 seconds, at most three starts in five minutes. Each start keeps the original per-attempt budgets and source checks. No extra Google requests. Deployment pending. |
| FC-06 | An older test still required the live collector to read retired daily state | Updated assertion to require no retired state/receipt access and unchanged historical data. Historical daily replay tests remain intact. Complete household/native regressions running. |

## Cadence and provenance

Collection runs hourly at :41, retaining the latest full-range run and any newer interim run, reusing unchanged originals. UI publication runs at :47. Native thermal/PV serving continues every five minutes. No additional Google downloads are required for the publication fix.

Google documents hourly initializations, 48-hour interim horizons and 360-hour full cycles initialized at 00/06/12/18 UTC. Earth Engine dissemination targets are interim initialization plus 7h25m and full cycles at 08:10/14:10/20:10/02:10 UTC, with delivery variance. See [dissemination](https://developers.google.com/weathernext/guides/dissemination) and [model specifications](https://developers.google.com/weathernext/guides/models). Collection timing does not guarantee upstream availability.

The composite publication is versioned separately from single-issue model inputs. Its extended source remains the detail's top-level source; `profiles.nearTerm` and `profiles.extended` identify independent coverage and status. Overlaid hours identify `nearTerm`; unmarked hours use the extended profile. Current-day remaining precipitation retains its own profile and exact interval. This publication does not enter training or immutable scoring as a fictitious single forecast issue.

## Verification

- WeatherNext suite: 236 cases, 233 passed and three optional integration skips; includes different numerical short/long forecasts, loss of extended coverage, expired sources, compact payloads and short-original corruption during publication.
- Frontend suite: all 2,570 tests across 170 files passed. Production build passed.
- Broader household/native regression run and live dual-profile/browser verification are in progress.
- Live household energy, profiled energy, chronology and all four performance endpoints returned HTTP 200 with fresh timestamps at 21:49 UTC. The general observation endpoint's HTTP 503 is tracked as FC-04; its expiry was an incidental observation, not the cause of rejection. The parser already supports read-only inspection of expired plans with their mode explicitly unavailable.

Closure requires live readbacks for deployed fixes and resolution or explicit classification of every confirmed tracker finding. Pending outcome maturity and unqualified model skill remain measurement limitations, not grounds for inventing accuracy or enabling actuators.
