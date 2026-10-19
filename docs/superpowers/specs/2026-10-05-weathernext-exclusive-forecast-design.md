**Owner-directed release update (2026-10-19):** deploy WeatherNext as soon as its source/contract/operational checks pass and assess/tune accuracy from production data. The former 30-day acquisition wait is removed as a provider-cutover prerequisite. Training/holdout and shadow evidence continue to govern scientific qualification claims, not whether an explicitly unqualified, operationally admitted Google-only forecast may enter monitored production. See section 10. Actuation remains disabled.

**Execution update (2026-10-18):** Operator authorized execution and clarified a clean restart of weather-related ML: WeatherNext 3 is the sole external forecast source; qualified local measurements remain training/scoring truth. At production cutover, completely remove Open-Meteo integration and provider-specific learning state from OpenHAB and Earthship UI. No post-cutover capture-only service or fallback. See `docs/operations/openmeteo-retirement.md` for the reset/removal contract and `docs/operations/weathernext-readiness.md` for verified status. Google access and native Earth Engine extraction now work after correcting backing-storage OAuth scope and source-clock handling. Bounded 360-hour private collection/shadow recording are installed and scheduled, with all three precipitation products retained separately. Production remains on the incumbent pending the existing qualification/cutover gates; see the current readiness report.

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

Open-Meteo is the incumbent **qualification control** during migration only. It remains operational until WeatherNext ingestion, provenance, local adaptation, solar-energy use, and required weather variables pass their gates. Once those gates pass, production forecast generation moves to WeatherNext and Open-Meteo acquisition, integration code/configuration and provider-specific learning state are removed as part of that cutover.

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

Start weather-related ML from scratch in a separate WeatherNext namespace. Training inputs are WeatherNext 3 forecasts and qualified local measurements; local station, irradiance, rain and relevant household outcomes remain the ground truth. No Open-Meteo forecast, feature, fitted weight, bias/Kalman seed, pending training target or learned error history may initialize or train the new weather model. Start with raw WeatherNext and an explicit untrained correction state until Google/local pairs support fitting.

Open-Meteo may remain a separate pre-cutover evaluation control; its scores and forecasts never enter candidate fitting, preprocessing, hyperparameter selection or online correction. Weather-dependent downstream learned components also need a provenance audit and fresh Google/local fitting before promotion. An old fixed PV/thermal artifact may be used for a pre-cutover forcing comparison only; that experiment does not qualify its old weather-trained coefficients for the new model. Physical specifications, local sensor histories, household actions and independently learned non-weather behavior retain their identities and existing qualification rules. Full reset details are in `docs/operations/openmeteo-retirement.md`.

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

## 10. Monitored production and model qualification

The operator directed prompt deployment on October 19, followed by assessment and
tuning from production data. Provider cutover and a claim of validated local-model
accuracy are separate decisions. There is **no fixed 30-day acquisition wait**.
The former 60-day training/30-day holdout and 14-day model-shadow targets do not
block an explicitly unqualified monitored-production deployment.

Provider cutover requires dated evidence that:

- bounded Google access succeeds without paid fallback, original run/site/source
  identities reproduce, and recent complete manual and normal scheduled captures
  cover the declared horizon;
- required temperature, solar and precipitation contracts have verified units,
  native grids/intervals, availability clocks, freshness, DST and missingness;
  unsupported consumers are explicitly unavailable or removed;
- weather-dependent learning starts in fresh Google/local state, with no old
  forecasts, fitted weights, biases, targets or scoring history imported;
- publication, withdrawal, source/ownership/lock admission and degraded-mode
  behavior pass; full repository tests/build pass for the exact deployment source;
- existing aggregate resource safeguards, disabled actuation, private credentials,
  reviewed release/ownership handoff and coordinated complete provider retirement
  remain intact. Manual rollback prerequisites remain recorded; recovery rehearsal
  is deferred.

The existing ten release categories are operational acceptance checks under this
owner-directed policy. In particular, prospective acquisition means demonstrated
current manual/scheduled acquisition, not 30 elapsed days; temperature/solar/rain
reports must distinguish correct source contracts from unmeasured predictive
skill. No `PASS` may imply that an unobserved accuracy test succeeded. The release
packet must retain this policy/owner decision and list statistical evidence as
unavailable where appropriate. Operational release admission grants no new
physical control authority.

Record original predictions and qualified local outcomes in production, then
report error by horizon and represented weather regime. Keep chronological
training/embargo/untouched evaluation boundaries and existing numerical/support,
physical, source and action-evidence gates. Until evidence supports qualification,
learned outputs remain explicitly provisional/unqualified, and raw WeatherNext
can be served while a local correction is unavailable. A `SHADOW_ONLY` evaluator
result is scientific status, not an automatic block on the monitored provider
cutover approved here. It cannot be relabelled as validated skill.

Cloudy/clear days, diurnal swings, frontal events and rain events remain useful
assessment targets as they occur. The previous sample-duration targets may inform
later review; they are not hidden calendar prerequisites for this deployment.
Predeclare local-model comparison criteria before examining held-out outcomes.
The initial research target of 10% lower temperature MAE and any predeclared
non-inferiority tolerance remain assessment criteria, not mandatory waiting periods
for the provider change. Precipitation-head selection must retain its native
product identity and current uncertainty; insufficient event scores are disclosed.

The end state remains WeatherNext-only, with visible degradation on source failure
and no incumbent fallback.

## 11. Production cutover

Production cutover should be a small explicit provider-boundary change, not a rewrite of all forecasting logic.

Introduce a normalized provider snapshot consumed by `forecast_intel.py` (or a focused provider adapter extracted from it). During shadow, Open-Meteo supplies the production snapshot and WeatherNext supplies the comparison snapshot. At cutover, WeatherNext becomes the production snapshot source.

The cutover must preserve:

- existing OpenHAB Item names and UI contract where practical;
- qualified local observation semantics, with fresh WeatherNext-only weather-model state and provenance;
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

At the production cutover, all required consumers must have a qualified WeatherNext replacement or be explicitly removed/marked unavailable. Complete the prepared removal patch in the same attended cutover:

1. stop Open-Meteo acquisition and learning writers before activating fresh WeatherNext state;
2. remove the binding, Bridge/Things/channels/links, provider-specific Item definitions, rules/jobs, endpoint callers and deployment/ownership references from OpenHAB and the active Earthship UI project;
3. start weather learning from raw WeatherNext with qualified local measurements, or a separately fitted artifact whose complete training lineage contains only those sources;
4. detach old Open-Meteo state, pending targets, correction seeds and fitted weather-dependent artifacts from all production readers; do not merge their scores into WeatherNext skill;
5. remove temporary incumbent comparison UI and mark unsupported fields unavailable rather than retain an Open-Meteo dependency;
6. verify the cutover runtime has no Open-Meteo requests, capture-only jobs, installed binding, live links or automatic fallback.

Stage and review the removal beforehand; do not remove the incumbent before the replacement is ready. Historical records remain truthfully provider-labeled in Git or a private, detached research archive. Preserving history is not permission to ship executable Open-Meteo integration or use its data in new ML. A manual return to a pinned pre-cutover revision remains distinct from an installed runtime fallback. Recovery rehearsal remains deferred per operator instruction.

## 14. Definition of done

The migration is complete when:

- WeatherNext access and zero-paid-access policy are verified on the real worker identity;
- WeatherNext issues are archived with truthful availability provenance;
- required temperature, solar, precipitation, and other current forecast consumers have passed declared qualification gates;
- the local adaptation model has prospective evidence and reproducible artifacts;
- WeatherNext is the production external forecast source;
- Open-Meteo integrations are removed from OpenHAB and the active Earthship UI project at cutover, and new weather ML contains only WeatherNext/local-measurement lineage;
- provider outage produces explicit degraded behavior rather than hidden fallback;
- existing safety, PV, thermal, and notification gates remain intact;
- a pinned pre-cutover revision is recorded for a deliberate manual rollback; no dormant Open-Meteo runtime is retained;
- an engineering closure report records what improved, what did not, and which evidence supports retirement.
