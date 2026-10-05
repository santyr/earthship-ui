# WeatherNext 3 exclusive forecast migration — design

**Date:** 2026-10-05  
**Status:** Proposed revised design; WeatherNext access request submitted, approval pending.  
**Project:** `santyr/earthship-ui`, coordinated with `santyr/Solar_PV`.  
**Inspected Earthship revision:** `8a5a4ddb95917c64b19454d9277a656d4b599757`.

Source identifiers refer to `docs/operations/weathernext-sources.md`. Google-service facts must be rechecked at implementation and again at production cutover because WeatherNext 3 is new and its access/terms can change.

## 1. Goal and end state

Replace Open-Meteo as the Earthship's external forecast provider with WeatherNext 3 **after WeatherNext proves adequate on this site**. The permanent architecture should contain one external forecast source, not a provider ensemble:

```text
WeatherNext 3
    │
    ├── temperature / dew point
    ├── solar radiation
    ├── precipitation
    ├── cloud / pressure / wind
    └── ensemble statistics
             │
             ▼
Earthship local adaptation
             │
     ┌───────┼────────┐
     ▼       ▼        ▼
weather   energy    thermal
actuals   actuals   actuals
```

Open-Meteo is the incumbent **qualification control** during migration only. It remains operational until WeatherNext ingestion, provenance, local adaptation, solar-energy use, and required weather variables pass their gates. Once those gates pass, production forecast generation moves to WeatherNext and Open-Meteo is retired from normal acquisition and learning.

The post-cutover system does **not** silently fall back to Open-Meteo. If WeatherNext is unavailable or stale, the system reports a degraded forecast, retains the last still-eligible WeatherNext issue according to freshness policy, and continues using live local measurements for current-state logic. A different external fallback would require a separate design and explicit provenance.

No actuator authority, protection-threshold changes, pump/shade control, charger control, or new notifications are part of this migration.

## 2. Why a single-provider design

WeatherNext already exposes probabilistic information through its ensemble-derived statistics, so a permanent Open-Meteo + WeatherNext ensemble would add provider plumbing, separate bias states, failover ambiguity, and model-provenance complexity without being necessary for the project's primary goal.

The Earthship's useful ensemble is instead:

1. WeatherNext's atmospheric forecast distribution.
2. The site's qualified measurements.
3. A local adaptation model that learns systematic microclimate and system-response errors.

A temporary head-to-head period is still essential because replacing an incumbent solely on reputation would be an uncontrolled regression. The comparison is a migration test, not the target architecture.

## 3. Existing repository constraints

At the inspected revision, `forecast_intel.py` still fetches Open-Meteo, derives solar-resource/PV inputs from `shortwave_radiation_sum`, publishes `Forecast_10Day_JSON`, and retains a closed PV calibration release gate. The new work must not bypass these gates during shadow evaluation. [R1]

The UI remains a LAN client of OpenHAB REST/SSE. Google credentials and direct WeatherNext access stay backend-only. Existing forecast payload versions, size limits, current measured-weather display, and tablet constraints remain intact until the cutover adapter is independently tested. [R3, R4]

Solar_PV remains the electrical-system authority. WeatherNext can improve meteorological forcing but cannot redefine qualified PV, load, battery, or safety evidence. [R5]

## 4. Access, cost, and acquisition policy

The preferred initial backend is the WeatherNext 3 **precomputed statistics** Zarr data on Google Cloud Storage, not the full 64-member ensemble. The statistics path is selected specifically to avoid Requester Pays and large member-level downloads. [S1]

Default policy:

```text
paid_access_allowed = false
full_ensemble_allowed = false
requester_billing_project = none
cloud_compute_allowed = false
```

The reader must reject a full-ensemble URI, an injected `userProject`/billing-project setting, or an automatic paid fallback before any such request is sent. A real bounded probe must measure bytes transferred, runtime, memory, and whether the chosen access path behaves as expected. [S2]

If point extraction from the statistics Zarr layout is impractical on the home server, stop and review a separate noncommercial Earth Engine retrieval design. Do not automatically enable paid Cloud resources. [S3]

## 5. WeatherNext run selection and publication latency

WeatherNext's model initialization time is not its public availability time. The archive must record at least:

- model/run initialization time;
- upstream object/version or equivalent source identity;
- first time the Earthship collector actually observed the run as available;
- ingestion completion time;
- target interval;
- household decision time that consumed the run.

Only a forecast that was available by the household decision time is eligible for prospective scoring or operational inference. Historical backfills with unknown original availability are retrospective studies, not as-issued operational evidence. [S8]

For short horizons, the selector may use the newest WeatherNext run whose published product covers the needed target window. For longer horizons, use an eligible main run with the necessary range. The exact run schedule is discovered from upstream metadata rather than encoded as an assumption.

## 6. Weather variables and provider mapping

The migration should use WeatherNext products intentionally rather than blindly map field names.

### Temperature and dew point

Use the WeatherNext near-surface/station-head product where supported. Temperature is the first local-adaptation target because the Earthship has strong local measurements and temperature can be evaluated independently of battery curtailment or load behavior. [S7, S12]

### Solar

Capture surface downward solar radiation/GHI and direct-beam radiation where available. Preserve their native interval semantics and units before converting them. These two signals should be evaluated separately for:

- PV resource prediction;
- south-glazing/thermal gain prediction;
- direct-versus-diffuse behavior.

Do not assume that an hourly percentile series sums to the same percentile of daily energy.

### Precipitation

WeatherNext exposes more than one precipitation formulation. During shadow qualification, archive the supported candidates separately and score them against the source-qualified local rain gauge. Select one **WeatherNext precipitation product** by a predeclared rule using training/evaluation data; do not expose multiple precipitation heads as permanent competing providers.

### Wind, pressure, cloud

Collect these when inexpensive because they may improve local correction, thermal prediction, and weather context. They do not need independent production promotion unless an existing Earthship consumer depends on them.

## 7. Archive and provenance contract

Create a private, immutable weather archive separate from OpenHAB persistence. Suggested records:

- `Site`
- `RunRef`
- `ForecastPoint`
- `Snapshot`
- `Issue`
- `Outcome`
- `ModelArtifact`
- `EvaluationReport`
- `ReleaseDecision`

Every normalized point records provider/model version, source run, native grid/cell, statistic (mean/p10/p25/p50/p75/p90 where available), original units, normalized units, valid interval, source digest, quality flags, first-seen time, and historical-eligibility metadata.

The archive must not fabricate original issue times from later backfills. Current observations never substitute for missing historical forecast issues.

## 8. Local adaptation model

The first production candidate should remain simple enough to diagnose. The model sequence is:

1. raw WeatherNext;
2. WeatherNext with provider-specific bounded bias correction;
3. regularized local residual model using WeatherNext distribution/features plus qualified local innovations available by issue time.

Open-Meteo correction state is never applied to WeatherNext. During the comparison period, Open-Meteo remains a separate baseline only.

Candidate features may include:

- WeatherNext central estimate and spread;
- forecast lead time;
- local hour/day/season;
- sun geometry;
- qualified recent forecast error available before the issue;
- pressure, cloud, wind, dew point where useful;
- known household/sensor configuration epochs.

Training/evaluation is chronological. Scalers, feature choices, calibration, and hyperparameters are fit only inside training folds. Overlapping target windows require an embargo so future outcomes cannot leak into earlier predictions.

## 9. Energy and thermal use

### Solar/PV

First score WeatherNext solar forcing against qualified measured irradiance. Only after the meteorological signal is understood should the pipeline score available PV and harvested PV. Battery-full curtailment must not be mislabeled as poor solar-resource prediction.

Then hold the existing Earthship energy model fixed and swap only the weather forcing. Refit energy coefficients only as a separate experiment. Preserve bank/hardware epochs and current PV release gates.

### Battery

Use the improved weather forecast to test full-charge likelihood, charge timing, evening SoC, and overnight trough at their actual issue origins. A no-full day is a censored/no-full outcome, not an invented charge time.

### Thermal

Hold the accepted thermal artifact fixed and compare Open-Meteo-forced versus WeatherNext-forced trajectories on identical windows. Only after that attribution experiment may thermal parameters be refit. Better weather cannot bypass existing thermal graduation/action-evidence rules.

## 10. Shadow comparison and cutover gates

The migration has two independent questions:

1. **Can WeatherNext reliably supply the data the Earthship requires?**
2. **Does WeatherNext + local adaptation perform well enough to replace the incumbent?**

Initial minimum evidence policy:

- at least 30 consecutive days of prospective WeatherNext acquisition before provider cutover review;
- at least 60 qualified temperature training days and a subsequent untouched 30-day temperature holdout when available;
- at least 14 days of normal prospective local-model shadow inference;
- explicit evaluation of cloudy days, clear days, large diurnal swings, frontal/cold events, and precipitation events represented in the sample;
- no unresolved timestamp/publication-time leakage;
- no unresolved solar-unit or DST integration issue.

For temperature, target a meaningful improvement over locally corrected Open-Meteo; a proposed promotion threshold is at least 10% lower MAE at the declared horizon. A non-inferiority rule may be used if WeatherNext is effectively tied while materially simplifying the architecture, but the tolerance must be declared before the final holdout is inspected.

For solar resource, require no material regression in daily energy error or high-error tails on qualified irradiance days. For precipitation, require enough actual events to reject a clearly worse WeatherNext head; until that variable is qualified, full Open-Meteo retirement is blocked if precipitation remains an operational dependency.

Promotion is by required variable/horizon. This permits a staged cutover, but the end state remains WeatherNext-only.

## 11. Production cutover

Production cutover should be a small explicit provider-boundary change, not a rewrite of all forecasting logic.

Introduce a normalized provider snapshot consumed by `forecast_intel.py` (or a focused provider adapter extracted from it). During shadow, Open-Meteo supplies the production snapshot and WeatherNext supplies the comparison snapshot. At cutover, WeatherNext becomes the production snapshot source.

The cutover must preserve:

- existing OpenHAB Item names and UI contract where practical;
- existing local temperature-learning semantics, reset/migration rules made explicit;
- PV/energy calibration gates;
- current notification policy;
- source-qualified evidence recording;
- failure/status visibility.

A WeatherNext issue must never masquerade as an Open-Meteo issue in historical state. Provider/model identity remains attached to every forecast and learned correction.

## 12. Post-cutover degraded mode

After Open-Meteo retirement:

- current conditions remain local-sensor driven;
- a still-fresh WeatherNext issue may remain usable according to explicit age/horizon rules;
- stale or unavailable WeatherNext produces `DEGRADED`/`UNAVAILABLE`, not an automatic provider swap;
- control/safety logic must not infer zero sun, zero rain, benign weather, or fresh values from missing data;
- local learning pauses for targets without an eligible issued forecast.

This behavior is easier to reason about and keeps ML provenance clean.

## 13. Open-Meteo retirement

Once all required current consumers have qualified WeatherNext replacements:

1. stop Open-Meteo from influencing forecasts or learned corrections;
2. run a defined stability interval with WeatherNext authoritative while Open-Meteo remains capture-only if desired for final diagnostics;
3. disable Open-Meteo acquisition;
4. remove its OpenHAB Thing/channels and provider-specific runtime code in a separate cleanup patch;
5. preserve historical Open-Meteo forecast/evaluation data as immutable research history;
6. remove temporary comparison UI after its evidentiary purpose ends, retaining concise forecast-health/model-skill views.

Do not delete historical provider identity or rewrite old records into WeatherNext format.

## 14. Definition of done

The migration is complete when:

- WeatherNext access and zero-paid-access policy are verified on the real worker identity;
- WeatherNext issues are archived with truthful availability provenance;
- required temperature, solar, precipitation, and other current forecast consumers have passed declared qualification gates;
- the local adaptation model has prospective evidence and reproducible artifacts;
- WeatherNext is the production external forecast source;
- Open-Meteo is absent from normal acquisition, prediction, and learning;
- provider outage produces explicit degraded behavior rather than hidden fallback;
- existing safety, PV, thermal, and notification gates remain intact;
- rollback can restore the last Open-Meteo production revision during the defined migration rollback window;
- an engineering closure report records what improved, what did not, and which evidence supports retirement.