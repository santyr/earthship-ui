# Google consumer migration repairs — October 19

These repairs implement the confirmed [consumer audit findings](2026-10-19-weathernext-ml-consumer-audit.md). Production accuracy remains unqualified; original receipts and forecasts remain available for their original replay. Automatic actuation stays disabled.

## Algorithms and consumers

- **WNML-01:** native thermal forcing now holds each Google trailing hourly radiation mean throughout its original interval. Temperature keeps its independent interpolation. Rising/falling/zero radiation, fractional origins and exact boundaries have regression coverage. A new source-bound model was fitted from the same retained qualified local measurements through October 19 06:00 UTC; no OpenMeteo inputs or incumbent coefficients were used. Model artifact: `bd23cc37fe80c2a9918d0c22f69c363721f3aef49c9246321d1acdfe92858916`.
- **WNML-02:** current v7/v8 Google cycles prepare canonical planner energy inputs from the same-issue PV, topology and terrain declarations. They reuse the existing PV/storage numerical functions, distinguishing potential generation, modeled capture and nominal unaccepted DC energy. Targets are explicitly rolling 24 hours, not a complete next night. The first scheduled repaired cycle at 21:00 UTC retained typed trajectory inputs, a conditional storage projection and `generated_shadow_only` candidate generation. Missing owner/action qualification can still make the overall plan incomplete. Active source collection no longer reads retired daily state or its Item. Historical daily replay stays isolated; the old pinned compatibility-parameter file is not a numerical input to current Google cycles.
- **WNML-03:** under the existing shared lock, the four mutable pre-Google sample indexes and reports were moved to a private retained archive. All original forecasts/outcomes remain in place. The new indexes retained their first Google-only samples and all four reports refreshed at 20:38 UTC. New source deployments retain prior Google stages in the score dispatch. A subsequent review found that learned-load admission also needed to check the nested energy-runtime manifest; incompatible originals are excluded from the current scorer and remain available to their original runtime. Reports must distinguish pending targets from scored outcomes.
- **WNML-04:** `weathernext-evaluate.service` now scores original daily issues against qualified local temperature, solar and rain measurements. The first operational report retained 11 temperature pairs; one solar window and one rain day were pending. It performs no fitting, promotion or Google acquisition. Solar windows start at the next whole hour after original publication and end at local midnight; rain uses the next complete local day. Original availability and sensor/policy identities remain pinned.
- **WNML-05:** the pure forecast parser imports a small range helper without celestial or visual dependencies. The exact three-file parser refactor is deployed in the live UI checkout, preserving other signed-off changes. Package-free parser import and Python/browser publication contracts pass.

## Acquisition, cadence and allowed usage

Google documents hourly WeatherNext 3 initializations. Main cycles initialized at 00/06/12/18 UTC have 360-hour coverage, with target Earth Engine availability at 08:10/14:10/20:10/02:10 UTC. Interim runs have 48-hour coverage and target availability at initialization plus 7h25m. Typical delivery variance is ±15 minutes; occasional delays can exceed an hour. These are publication estimates, not deadlines. See [dissemination](https://developers.google.com/weathernext/guides/dissemination) and [model horizons](https://developers.google.com/weathernext/guides/models).

Installed hourly schedule (local hour; Denver's whole-hour UTC offset preserves minute alignment):

| Job | Minute | External acquisition |
|---|---:|---|
| Acquire full-range and newer interim originals | :41, up to 30 seconds jitter | Bounded Earth Engine statistics only |
| Retain local shadow issue | :44, up to 30 seconds jitter | None |
| Publish production weather UI | :47 | None |
| Score mature weather outcomes | :52, up to 30 seconds jitter | None |

These offsets put normal interim delivery before collection and stagger the local jobs. They are a scheduling margin, not a dependency guarantee; each consumer independently validates original source availability and freshness. A delayed release is picked up by a later hourly collection.

The collector reuses complete retained runs without renewing their first-seen/completion clocks. It keeps short and long originals separately: near-term consumers can select newer interim data, while the single-issue extended forecast retains full-range coverage. The first deployed collection reused the existing 12:00 UTC full run and acquired the 14:00 UTC interim run: eight requests, 1,029,236 response bytes, about 12.4 seconds and 73,296 KiB peak RSS. Per-run request/response/time caps remain unchanged; no paid fallback, exports or full-ensemble download was enabled.

Cloud Monitoring reported **153.5276 EECU-seconds (0.04265 EECU-hours)** for successful completed requests since October 1 Pacific midnight, observed October 19 20:43 UTC. This is about **0.0284%** of the Community tier's documented monthly 150 EECU-hour allowance. It is reported usage so far, subject to reporting lag, not a future-use projection or an independent verification of tier configuration. See [Earth Engine noncommercial tiers](https://developers.google.com/earth-engine/guides/noncommercial_tiers). Request counts and response bytes are separate from EECU usage.

The physical native forecast still refreshes locally every five minutes. Physical thermal/load training remains in the existing morning job; the separate WeatherNext correction candidate remains weekly. Refreshing local views does not cause extra Google downloads. The morning native source pin now uses the repaired source, preserving the daily schedule and shared resource admission.

## Validation and limits

Evidence retained privately includes the original audit readbacks, index migration hashes, exact immutable deployment manifests, acquired Google snapshots, source maintenance handoff, original first-cycle planner receipt, weather monitor report and timer readbacks. The host and OpenHAB were not restarted; no equipment commands were issued.

Focused verification: 230 WeatherNext tests, 134 trajectory/planner regressions, 50 thermal interval/native tests, 25 browser parser tests and 25 Python/browser publication-contract checks. The learned-load transition regression first reproduced the runtime mismatch; the scoring/outcome/forecast selection then passed 26 tests. The two older cycle fixtures also require the new trajectory source closure and the intentional Google energy-plan behavior; their tests preserve the independent thermal/battery assertions.

Unsupported categorical weather codes, probability/AQI and unsupported legacy daily PV/trough targets remain unavailable. They must not be fabricated from rolling scenarios. Solar/rain outcomes that have not matured remain pending. Existing PV decomposition, terrain and nominal-storage assumptions remain provisional. This deployment restores correct data flow and prospective monitoring; it does not certify model skill or action effects.
