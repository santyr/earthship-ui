# WeatherNext cutover preparation

Status: **not deployed; release gates unmet**. The Google-only provider adapter is implemented for offline integration, but production still uses its incumbent worker. See [readiness](weathernext-readiness.md), [source-access diagnosis](2026-10-18-weathernext-ee-raster-diagnosis.md), [the migration plan](../superpowers/plans/2026-10-05-weathernext-exclusive-forecast.md) and [the binding reset/removal contract](openmeteo-retirement.md).

## Prepared provider boundary

`weather_learning.provider.load_production_forecast` selects an original, prospectively available WeatherNext archive object for the authoritative site and requested horizon. The default requires temperature, GHI, direct solar, precipitation, wind and cloud means. Original native capsules are rederived before conversion; initialization, availability, site, required-variable coverage and the exact decision bind the result. Missing/stale/incomplete source is unavailable; invalid selected source is refused. The adapter has no network fallback, fitted-state reader, seeder, publisher or equipment API.

The immutable provider snapshot records its original snapshot/run, issue identity, required variables and horizon. Issue identity uses the same original-source/decision digest as the Google/local feature builder. Its separate `weathernext3-temperature-v1` namespace starts explicitly `UNTRAINED`, without parent artifacts. Results remain release-unauthorized.

The typed path in `forecast_intel.build_forecast_payloads` accepts this object without entering the incumbent state/seed path. It refuses supplied incumbent PV predictions or temperature corrections. Existing dictionary callers retain their existing behavior. This is preparation, not a runtime provider selector: no current scheduled caller constructs the new object and no unit or Item has been switched.

Raw Google temperatures can be represented by the existing version-1 detail contract, which declares no temperature correction, with added provider/source/issue/model identity. Unsupported precipitation probabilities, weather codes and daylight remain null; PV remains null until separately qualified Google/local downstream integration exists. No legacy model seed is invoked. A fitted Google/local candidate still needs its own validated serving integration before it may be presented as trained.

GHI/direct solar retain native trailing-hour interval semantics. Daily accumulation requires every local-day interval, including 23/25-hour DST days; temperature extrema require every instantaneous local-day hour. Partial first/last days remain unavailable. Availability is distinct from release qualification and daily source coverage is distinct from a fully prospective outcome window.

## Work required before the attended release

1. Resolve the real WeatherNext raster failure and establish the reader's dataset entitlement. Verify one successful native point, then measure the full 360-hour, required-variable capture under existing shared host admission. Metadata and synthetic fixtures cannot replace this proof.
2. Verify a pinned deployment stage, existing private configuration and original-source retention. Activate only the bounded collector/shadow schedules that have passed their live checks. Record natural publications and the actual source/model/runtime identities.
3. Complete the plan's prospective acquisition, Google/local training, untouched evaluation and normal shadow-inference intervals. Qualify solar/rain and weather-dependent PV/thermal consumers on actual paired evidence. Fixed incumbent-artifact attribution is a comparison experiment, not permission to inherit its fitted weights. Preserve qualified local measurements, physical configuration and independent non-weather learning.
4. Finish the actual production publisher/provider selection and fresh Google/local fitted-model integration. Define explicit withdrawal/unavailable behavior for forecast Items; an unavailable adapter must not leave a stale forecast presented as current. Connect native Astro daylight through its validated context. Resolve or remove unsupported AQI/UV/probability/weather-code dependencies; do not invent substitutes.
5. Prepare and review one complete removal/reset patch. Refresh [the source/live removal inventory](2026-10-18-openmeteo-retirement-audit.md), including current root overlays, the custom binding JAR, AQI evidence producer/receipt, installed overrides, dynamic state and transitive consumers. The inventory is candidate coverage, not a final no-integration proof.
6. Verify the repository's complete CI/test/build checks, private state preimages and pinned pre-cutover revision. Recovery rehearsals and a broader backup project remain deferred.

## Attended release order

Stop incumbent acquisition/learning writers first. Deploy the qualified Google provider and fresh namespace, then remove Open-Meteo binding/Things/channels/links, provider code and learned-state imports, obsolete tooling, comparison controls and unsupported consumers in the same release. Rebind retained local scoring, energy and thermal services deliberately. Do not retain a selectable incumbent branch, dormant fetch function, capture-only collector or automatic external fallback in the deployed project.

The prepared typed adapter does not itself perform this removal. The incumbent dictionary path and acquisition code still exist today and must leave the final active project. Preserve old records only in truthful detached research history outside deployed readers.

Verify natural publication, source and model identities, UI null/stale behavior, required energy/thermal consumers, writer ownership and absence of outbound Open-Meteo requests. Verify startup dependencies and reboot behavior in the attended operational qualification. Do not reboot this host merely to exercise the current offline adapter. Local observations must continue during WeatherNext failures; forecast-dependent features become visibly degraded with no new notification or actuator authority.

## Current implementation checks

The provider's synthetic tests cover original-source mismatch, wrong site, stale/late/missing source, serving/learning identity, immutability, fresh namespace, refusal of incumbent corrections/PV, both DST transitions, null values and the existing detail-size limit at maximum horizon. The actual frontend parser is checked with Python-produced synthetic detail payloads. Existing forecast characterization tests cover the unchanged dictionary path. None of these tests qualifies real source availability, forecast skill, a production publisher, reset/removal, operational startup or a live cutover.
