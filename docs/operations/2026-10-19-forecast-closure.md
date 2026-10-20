# WeatherNext and household forecast closure

This is the current tracker for the operator's goal to identify and close WeatherNext and household forecasting bugs and gaps. It extends the retained [consumer inventory and audit](2026-10-19-weathernext-ml-consumer-audit.md); immutable original audits and historical forecasts remain unchanged. Automatic actuation stays disabled.

| ID | Finding | Status and evidence |
|---|---|---|
| WNML-01–05 | Radiation interval interpretation, retired daily energy dependency, incompatible scoring indexes, unscheduled weather evaluation, parser dependency coupling | Previously deployed; see [consumer repairs](2026-10-19-weathernext-consumer-repairs.md). Current thermal and four energy scoring reports refresh. |
| FC-01 | UI hourly forecast selected the 336-hour source, ignoring newer retained interim runs | Deployed and read back at 21:52 UTC: near-term initialization 14:00 UTC, extended initialization 12:00 UTC, ten days and 224 hourly points. Independent 24-hour and 336-hour profiles retain original source, availability and issue identities. Near-term hours overlay the extended hourly outlook; daily summaries retain their extended issue. Missing extended coverage can still serve explicitly identified near-term coverage. All contributing originals are rechecked before publication. |
| FC-02 | Today’s rain unavailable when an original cannot cover elapsed calendar-day intervals | Deployed and read back; live Chromium verified the remaining label and trace total. UI total explicitly covers remaining complete native hourly intervals, beginning at the next whole hour and ending at next local midnight. The in-progress interval is excluded; no prorating or fabricated observations. Legacy daily JSON and numeric Items keep their full-day meaning. |
| FC-03 | UI accepted a future publication timestamp as current | Deployed in the live UI and covered by the full frontend suite. Future-dated details are unavailable. A modal fixture that generated its issue before moving the test clock now regenerates it after the clock change. |
| FC-04 | Household UI rejects the canonical trajectory energy qualification | Root cause confirmed: backend emits `conditional_uncalibrated_scenario`, UI accepted only `not_assessed` or `not_graduated`. Parser now accepts the conditional value only for energy. Actual retained v4 observation parses; expired sources remain expired and effective mode unavailable. Deployed: the actual v4 observation endpoint now returns HTTP 200 and the browser parses it with expired mode unavailable. |
| FC-05 | One temporary publisher refusal loses the entire hourly publication | Bounded recovery added and tested: restart after 60 seconds, at most three starts in fifteen minutes; the window encloses maximum-duration failures as well as immediate refusals. Each start keeps the original per-attempt budgets and source checks. No extra Google requests. Final reviewed service and immutable package deployed; live publication completed at 22:03:57 UTC. |
| FC-06 | An older test still required the live collector to read retired daily state | Updated assertion to require no retired state/receipt access and unchanged historical data. Historical daily replay tests remain intact. Updated test passed in the complete household/native regression run. |
| FC-07 | Short retry window did not bound repeated slow failures | Independent review identified starts at 0/170/340 seconds escaping the original five-minute limit. Corrected to a 900-second window with burst three, enclosing the fourth potential start at 510 seconds. Regression and final live service property verified. |

## Cadence and provenance

Collection runs hourly at :41, retaining the latest full-range run and any newer interim run, reusing unchanged originals. UI publication runs at :47. Native thermal/PV serving continues every five minutes. No additional Google downloads are required for the publication fix.

Google documents hourly initializations, 48-hour interim horizons and 360-hour full cycles initialized at 00/06/12/18 UTC. Earth Engine dissemination targets are interim initialization plus 7h25m and full cycles at 08:10/14:10/20:10/02:10 UTC, with delivery variance. See [dissemination](https://developers.google.com/weathernext/guides/dissemination) and [model specifications](https://developers.google.com/weathernext/guides/models). Collection timing does not guarantee upstream availability.

The composite publication is versioned separately from single-issue model inputs. Its extended source remains the detail's top-level source; `profiles.nearTerm` and `profiles.extended` identify independent coverage and status. Overlaid hours identify `nearTerm`; unmarked hours use the extended profile. Current-day remaining precipitation retains its own profile and exact interval. This publication does not enter training or immutable scoring as a fictitious single forecast issue.

## Verification

- WeatherNext suite: 236 cases, 233 passed and three optional integration skips; includes different numerical short/long forecasts, loss of extended coverage, expired sources, compact payloads and short-original corruption during publication.
- Frontend suite: all 2,570 tests across 170 files passed. Production build passed.
- Live Chromium on the actual Wi-Fi URL verified ten forecast days, the newer hourly run, remaining rain, the repaired household endpoint and both Energy charts, with zero page errors. Final reviewed publisher status: `PUBLISHED`.
- The three SDK cases skipped by system Python were exercised separately: all twelve Earth Engine module cases passed in the installed pinned environment, with no network and disposable credential material.
- Household/native suite: 2,136 passed and one opt-in resource test skipped, in 936.69 seconds. That resource smoke case then passed separately inside an actual capped production scope. All 2,137 distinct cases were exercised. Combined with frontend and WeatherNext, 4,943 distinct cases are verified.
- Independent source review found no further substantive issues after the slow-retry correction. Model accuracy and prospective outcome maturity are assessed separately from code correctness.
- Final live checks returned HTTP 200 for all eight household observation, chronology, energy and performance endpoints. The general observation endpoint's HTTP 503 is tracked as FC-04; its expiry was an incidental observation, not the cause of rejection. The parser already supports read-only inspection of expired plans with their mode explicitly unavailable.

All confirmed findings in this tracker are closed with deployed readbacks or test evidence, including the independent review correction. The [machine-readable closure record](2026-10-19-forecast-closure.json) retains counts, service/endpoint status and publication identities. Pending outcome maturity and unqualified model skill remain measurement limitations, not grounds for inventing accuracy or enabling actuators.

## Coverage and remaining measurement limits

| Boundary | Evidence |
|---|---|
| Acquisition and Google release cadence | Hourly :41 schedule; actual retained full and interim originals; unchanged cache availability clocks; bounded requests and reuse tests. |
| Publication and UI | Independent 24/336-hour profiles; per-source hashes, issue clocks and readbacks; 58,169-byte observed detail; profile-loss and tamper regressions; actual browser rendering. |
| Units and calendar intervals | Temperature/wind/depth/energy conversions; native trailing-hour radiation and rain; local-day and DST regressions; remaining precipitation excludes the interval in progress. |
| Thermal serving and training | Current 24-hour native trajectory; October 19 source-bound model artifact; daily 06:50 Denver training; five-minute serving. Forecast remains provisional with action labels withheld. |
| PV, storage and learned load | Fresh energy/profiled observation endpoints and typed Google trajectory inputs. Configured geometry, terrain and nominal storage assumptions remain explicitly conditional. |
| Outcome scoring | Four fresh Google-only reports; original issue/runtime lineage preserved. Mature targets are scored separately from pending 1/6/12/24-hour outcomes. No old accuracy is relabeled as current model skill. |
| Retired provider | Live inventories: 84 Things, 259 links and 492 add-on entries; zero OpenMeteo matches. Original historical replay evidence remains retained. |
| Authority and resources | No actuator requests or equipment commands; automatic actuation false throughout. Shared host admission and source/pressure/CPU/RAM/no-swap safeguards unchanged. Shared pool OOM counters remain zero. |

Missing owner/action-effect qualification, unsupported weather probabilities/codes/AQI, prospective outcome maturity and provisional physical calibration are intentional, explicit limits. They are not filled with invented values or used to enable actuation. This audit closes confirmed implementation defects; it does not establish calibrated forecast accuracy without matured local outcomes.


## October20 audit and approved deployment supersession

The [current audit](../audits/2026-10-20/requirements.md), [verification](../audits/2026-10-20/verification.md) and [approved deployment](../audits/2026-10-20/deployment.md) extend this historical record. PR36 is merged; its targeted source/runtime handoffs preserve existing selections, originals, authority and private overlays. PR37 installed the A19 automatic geometry-prewarm controller repair. PR38 closes the later A20 future-PV-selection defect with corrected candidate-only learning and the A21 test-isolation defect; their final source/gate/deployment readbacks are linked from that same audit. Earlier pending implementation, old-owner and production-unchanged statements are superseded only for the specifically evidenced surfaces. Current source, automated execution, actual installation and physical/statistical qualification remain separate. The October16 phase flags are historical milestones; the current requirement matrix reconciles each phase without relabelling hardware or future outcomes as software completion.
