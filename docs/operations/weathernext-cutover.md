# WeatherNext cutover preparation

Status: **production provider not deployed; release gates unmet**. Collector and shadow schedules are deployed. The Google-only provider adapter is implemented for offline integration, but production still uses its incumbent worker. See [readiness](weathernext-readiness.md), [resolved API findings](2026-10-18-weathernext-api-compatibility.md), [the migration plan](../superpowers/plans/2026-10-05-weathernext-exclusive-forecast.md) and [the binding reset/removal contract](openmeteo-retirement.md).

Source retirement now removes both obsolete standalone publisher families, the old thermal weather commands/provider import, and four closed operator tools with their exclusive tests/templates. Journal/schema commands and Google/local acquisition helpers remain. See the [current source and verification record](2026-10-18-weathernext-native-selection.md) for the exact remaining worker/tool graph and fixture corrections. This source preparation has not changed installed services or model receipts.

## Prepared provider boundary

`weather_learning.provider.load_production_forecast` selects an original, prospectively available WeatherNext archive object for the authoritative site and requested horizon. The default requires temperature, GHI, direct solar, precipitation, wind and cloud means. Original native capsules are rederived before conversion; initialization, availability, site, required-variable coverage and the exact decision bind the result. Missing/stale/incomplete source is unavailable; invalid selected source is refused. The adapter has no network fallback, fitted-state reader, seeder, publisher or equipment API.

The immutable provider snapshot records its original snapshot/run, issue identity, required variables and horizon. Issue identity uses the same original-source/decision digest as the Google/local feature builder. Its separate `weathernext3-temperature-v1` namespace starts explicitly `UNTRAINED`, without parent artifacts. Results remain release-unauthorized.

The prepared Google publisher uses `weather_learning.provider.forecast_payloads` and `publication_states` directly through the operational publication path. The old `forecast_intel.build_forecast_payloads` bridge is removed; that worker accepts only incumbent dictionaries and refuses a Google cohort before loading legacy model state. Its dictionary calculation body is unchanged. The Google provider retains its separate original-source identity and fresh learning namespace. This remains preparation: no production unit or Item has switched to the new writer.

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


## Native source selection prepared (October 18)

Explicit Google-only native and receipt-serving configuration profiles now reach household collection, preparation, publication, scoring and immutable deployment staging without the forecast database credential. Inference opens the collector archive read-only; Google input mismatch refuses before publication, and receipt/deployment/model/source/resource checks remain. A real private source-selection preparation selected 26 original rows in 0.713 seconds without model admission or live changes. Verification: 115 native execution/staging, 175 pinned WeatherNext and 140 native/household/energy regressions passed. See [the native selection record](2026-10-18-weathernext-native-selection.md). Installed production remains incumbent; final Google-only removal/source closure, fresh Google/local fitting and all release gates still precede attended cutover.


## Installed model family preserved (October 18)

The migration source now preserves the installed fourteen-parameter irradiance/shade equations and source-bound validation. Google production profiles refuse older model families; scheduled fitting selects the preserved family, the full 83-source/context package verifies, and the UI accepts its removed-shade domain without granting authority. A retained real-data replay exactly matches all 288 forcing steps and 24 hourly rows; this uses old coefficients only for parity, not promotion. Final checks: 125 relevant Python, 175 WeatherNext and 2,598 frontend tests passed, plus UI build. See [model-family preservation evidence](2026-10-18-weathernext-irradiance-family.md). Final provider retirement/source closure and real fresh fitting remain ahead of cutover.


## Bounded publication runtime prepared (October 18)

The [publication runtime](2026-10-18-weathernext-publication-runtime.md) now adds
fixed state-only REST, existing shared-lock exclusion, admission checks after
pacing, source-digest/freshness checks and immutable pre-write/result evidence.
Its standard-library I/O helper preserves existing thermal imports and avoids
pulling the numerical stack into the pinned WeatherNext environment. Verification:
196 pinned package, 55 existing I/O and 84 source-bound native integration tests
passed. Real retained Google input also passed local HTTP simulation. An actual
GET-only OpenHAB preflight verified the eleven Item contracts and correctly
refused an existing `Forecast_Radiation` channel link; no state update occurred.
The qualified release/file-ownership caller, operational configuration and
coordinated retirement remain required; no CLI, timer or live writer was added.

## Operational publisher caller prepared (October 18)

The [worker and prepared units](2026-10-18-weathernext-production-worker.md) now
connect the library runtime to an explicit private reviewed-release decision,
27-file source closure, original gate-report pins, installed Item definitions,
authoritative site and stopped-incumbent checks. The CLI defaults to read-only;
`--publish` is explicit. Existing resource safeguards and the two-hour JSON cadence
are preserved. All 211 package tests pass; systemd accepts both uninstalled units.
The live registry correctly refuses the still-active three incumbent timers. No
private release grant, installed publisher, service stop or source cutover was
performed. Complete release evidence and source retirement before activation.

## Household caller retirement prepared (October 18)

The [native selection record](2026-10-18-weathernext-native-selection.md) now
documents Google-only publication/scoring/staging factories and score dispatch v2.
The new dispatch retains only pinned Google history and no legacy scorer. Handoff
preimages use a separate metadata-only verifier; active model verification and
resource/evidence safeguards remain. All 256 cases in 30 affected modules passed
in 72.16 seconds from a committed isolated export. This increment also corrects
two stale source-closure assertions discovered by predecessor CI. Current-head
full CI, remaining standalone legacy source removal, final source freeze/fresh
release fits and attended activation are still required; nothing was deployed.


## Native Astro worker input completed (October 19)

The prepared operational worker now reads the existing native Astro Item through
its bounded admitted transport and passes original bytes/read-completion time to
the already-qualified provider adapter. Its 28-file runtime pin includes the
unchanged Astro validator. Invalid or missing context leaves daylight unavailable
without substituting weather values or weakening release/resource admission.
All 19 worker and 220 pinned package tests pass; actual retained Google and native
Astro inputs verify ten days and 232 daylight labels without writes or new Google
requests. See the [typed preparation evidence](2026-10-19-weathernext-native-astro-serving.json).
This closes the source wiring gap, not installed activation, final-source fresh
fitting or the approved acquisition/model/variable/downstream/release gates.
