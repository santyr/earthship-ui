# WeatherNext cutover preparation

Status: **production provider not deployed; release gates unmet**. Collector and shadow schedules are deployed. The Google-only provider adapter is implemented for offline integration, but production still uses its incumbent worker. See [readiness](weathernext-readiness.md), [resolved API findings](2026-10-18-weathernext-api-compatibility.md), [the migration plan](../superpowers/plans/2026-10-05-weathernext-exclusive-forecast.md) and [the binding reset/removal contract](openmeteo-retirement.md).

## Prepared provider boundary

`weather_learning.provider.load_production_forecast` selects an original, prospectively available WeatherNext archive object for the authoritative site and requested horizon. The default requires temperature, GHI, direct solar, precipitation, wind and cloud means. Original native capsules are rederived before conversion; initialization, availability, site, required-variable coverage and the exact decision bind the result. Missing/stale/incomplete source is unavailable; invalid selected source is refused. The adapter has no network fallback, fitted-state reader, seeder, publisher or equipment API.

The immutable provider snapshot records its original snapshot/run, issue identity, required variables and horizon. Issue identity uses the same original-source/decision digest as the Google/local feature builder. Its separate `weathernext3-temperature-v1` namespace starts explicitly `UNTRAINED`, without parent artifacts. Results remain release-unauthorized.

The typed path in `forecast_intel.build_forecast_payloads` accepts this object without entering the incumbent state/seed path. It refuses supplied incumbent PV predictions or temperature corrections. Existing dictionary callers retain their existing behavior. This is preparation, not a runtime provider selector: no current scheduled caller constructs the new object and no unit or Item has been switched.

Raw Google temperatures can be represented by the existing version-1 detail contract, which declares no temperature correction, with added provider/source/issue/model identity. Unsupported precipitation probabilities and weather codes remain null; PV remains null until separately qualified Google/local downstream integration exists. Hourly daylight uses an optional, source-qualified native Astro schedule; absent or incompatible Astro remains null. No legacy model seed is invoked. A fitted Google/local candidate still needs its own validated serving integration before it may be presented as trained.

GHI/direct solar retain native trailing-hour interval semantics. Daily accumulation requires every local-day interval, including 23/25-hour DST days; temperature extrema require every instantaneous local-day hour. Partial first/last days remain unavailable. Availability is distinct from release qualification and daily source coverage is distinct from a fully prospective outcome window.

## Work required before the attended release

1. Access and full native collection were verified on October 18 after the documented scope/clock corrections; retain those original proofs and continue prospective collection. Successful extraction does not replace the required acquisition/skill intervals.
2. Verify a pinned deployment stage, existing private configuration and original-source retention. Activate only the bounded collector/shadow schedules that have passed their live checks. Record natural publications and the actual source/model/runtime identities.
3. Complete the plan's prospective acquisition, Google/local training, untouched evaluation and normal shadow-inference intervals. Qualify solar/rain and weather-dependent PV/thermal consumers on actual paired evidence. Fixed incumbent-artifact attribution is a comparison experiment, not permission to inherit its fitted weights. Preserve qualified local measurements, physical configuration and independent non-weather learning.
4. Finish the actual production publisher/provider selection and fresh Google/local fitted-model integration. The [serving preparation](2026-10-18-weathernext-serving-preparation.md) now defines explicit withdrawal bytes for all three forecast JSON views and native Astro daylight. Finish operational partial-write/retry handling and deliberate replacement/withdrawal of every remaining numeric consumer; prepared bytes are not an installed publisher. Resolve or remove unsupported AQI/UV/probability/weather-code dependencies; do not invent substitutes.
5. Prepare and review one complete removal/reset patch. Refresh [the source/live removal inventory](2026-10-18-openmeteo-retirement-audit.md), including current root overlays, the custom binding JAR, AQI evidence producer/receipt, installed overrides, dynamic state and transitive consumers. The inventory is candidate coverage, not a final no-integration proof.
6. Verify the repository's complete CI/test/build checks, private state preimages and pinned pre-cutover revision. Recovery rehearsals and a broader backup project remain deferred.

## Attended release order

Stop incumbent acquisition/learning writers first. Deploy the qualified Google provider and fresh namespace, then remove Open-Meteo binding/Things/channels/links, provider code and learned-state imports, obsolete tooling, comparison controls and unsupported consumers in the same release. Rebind retained local scoring, energy and thermal services deliberately. Do not retain a selectable incumbent branch, dormant fetch function, capture-only collector or automatic external fallback in the deployed project.

The prepared typed adapter does not itself perform this removal. The incumbent dictionary path and acquisition code still exist today and must leave the final active project. Preserve old records only in truthful detached research history outside deployed readers.

Verify natural publication, source and model identities, UI null/stale behavior, required energy/thermal consumers, writer ownership and absence of outbound Open-Meteo requests. Verify startup dependencies and reboot behavior in the attended operational qualification. Do not reboot this host merely to exercise the current offline adapter. Local observations must continue during WeatherNext failures; forecast-dependent features become visibly degraded with no new notification or actuator authority.

## Current implementation checks

The provider's synthetic tests cover original-source mismatch, wrong site, stale/late/missing source, serving/learning identity, immutability, fresh namespace, refusal of incumbent corrections/PV, both DST transitions, null values and the existing detail-size limit at maximum horizon. The actual frontend parser is checked with Python-produced synthetic detail payloads. Existing forecast characterization tests cover the unchanged dictionary path. None of these tests qualifies real source availability, forecast skill, a production publisher, reset/removal, operational startup or a live cutover.

## Serving preparation update — October 18

[Actual Google/native Astro payload preparation](2026-10-18-weathernext-serving-preparation.md) now verifies 337 source targets, ten UI days, native daylight, explicit three-view withdrawal and real-parser compatibility without production writes. Tests: 156 WeatherNext, 150 existing forecast/Astro and 2,589 frontend cases pass; UI build passes. Full qualified publication, fitted-model integration, required numeric consumers, complete removal and release intervals remain unfinished.

## Publication mechanics update — October 18

[Commit-last publication mechanics](2026-10-18-weathernext-publication-mechanics.md) now cover three JSON views and eight retained numeric Items, readback verification and complete best-effort withdrawal after any failure. Home/Weather suppress stale legacy arrays behind a parsed Google withdrawal. A complete-day aggregation error was corrected without backdating issues. Tests: 167 WeatherNext, 150 existing forecast/Astro and 2,591 frontend cases pass; build passes. These mechanics have only been exercised against injected stores; the qualified release worker, shared-lock/ownership admission, retained attempt evidence and required native energy/thermal consumer translation are still needed before any production selection.

## Native source integration update — October 18

[Google native input capsules](2026-10-18-weathernext-native-inputs.md) now pass through the existing native collector, thermal capture, frozen household contexts and physical energy projection in tests without weather codes or legacy forecast SQL. Complete original API data and causal clocks are retained. A bounded Google-only private context v4 handles larger originals while preserving older/public limits; unsupported weather-code evidence is unavailable. Tests: 175 WeatherNext and 140 native/household/runtime/energy cases pass. Native live/serving configuration, the installed model family's final immutable deployment and qualified worker selection remain unfinished. Stage the complete removal/source closure before fitting real release artifacts so retirement does not invalidate the new fit binding.
