# Google-only serving bytes, withdrawal and native daylight

Observed October 18, 2026. This is a Task 8 preparation increment. The production provider and its scheduled publishers have **not** switched.

## Changed contract

The typed WeatherNext provider now produces an explicit unavailable detail and empty hourly/daily arrays when no eligible Google source exists. `publication_states` validates and serializes all three existing forecast Item values before any future writer can use them. It performs no state writes. Each payload retains its Google namespace, source/decision identity and explicit untrained model; no incumbent state, PV prediction, external fallback or seeder is used.

Previously the typed adapter raised on unavailable source, leaving a future caller without withdrawal bytes. The UI also classified an empty, freshly generated forecast as ready. The parser now treats empty forecasts as unavailable and recognizes explicit WeatherNext withdrawal. A contradictory unavailable detail carrying old predictions is rejected. The existing dictionary/production worker behavior is unchanged.

An optional native Astro input includes its exact original String state and actual acquisition time. The existing Astro validator checks its site, timezone, binding version (5.2.3 or greater), native event order, complete ten-day schedule and expiry. The provider additionally requires `recordedAt <= available_at <= decision_at`. It retains the original source hash and availability, uses sunrise end (`daylightStartAt`) through sunset start for hourly `isDay`, and carries native `daylightSeconds` in daily summaries. Missing, future, expired or incompatible Astro leaves those values null while independently valid Google weather remains available. No approximate daylight model is substituted. Unsupported probability, weather codes and PV remain null.

This establishes preparation semantics, not operational atomicity. A production publisher must still implement the qualified release boundary, retries/partial-write handling, retained issue evidence and deliberate replacement/withdrawal of every required numeric consumer before activation. The existing three-Item writer is not claimed to provide an atomic transaction.

## Actual source check

A read-only check fetched the authoritative OpenHAB site and original native Astro state, then selected an origin-eligible original Google archive. It prepared and parsed all three candidate states without publishing them:

- Decision: **2026-10-18 21:00:37.733415 UTC**; completion **21:00:37.962353 UTC**.
- Google initialization: **12:00 UTC**; actual archive acquisition completed **20:36:52.534100 UTC**.
- Original Google snapshot: `07efc2fb281f344104118d57ac5ef296cc6f491b5f94cb7c38ea8128a3b962e2`.
- Provider snapshot: `93ff7c333f77ee7e11017a7463d557697eefc1809f5e0ff3e9c52634fa68dd16`.
- Native Astro source: `97c5d2970818c35f92700489a634243b895e4fe9e0ee9d94666de75fd6e743a0`, observed **21:00:37.733410 UTC**.
- Private immutable preparation receipt: `f459941b986d947355b21dde703ff773bc5ee4d7ede0e349f1d0175e24cb2299`.
- **337** provider targets, **10** UI days and **224** UI hours with native daylight labels.
- Serialized hourly/daily/detail values: **1,636 / 552 / 49,118 bytes**, below existing bounds.
- **0.252 seconds**, **47,276 KiB peak RSS** under unchanged shared admission.

Original Google capsules were rederived; source/runtime hashes matched before and after preparation. The actual UI parser accepts the real detail as ready at its retained decision and accepts an explicitly **simulated empty archive** case as unavailable. The latter is a controlled degraded-mode test, not evidence of an actual production outage. Original Astro state, candidate bytes and receipts remain private mode 0600, outside Git and browser assets.

## Verification

Provider tests first failed for the missing Astro input/serialization and exception-only unavailable behavior. All three new UI withdrawal cases failed against the original parser (`ready` instead of `unavailable`) before the fix. A Python-produced synthetic three-Item fixture is checked against the producer and consumed by the real JavaScript parser.

- Full pinned WeatherNext suite: **156 passed, 4.921 seconds**.
- Existing forecast publication, site-clock and Astro validators: **150 passed, 1.17 seconds**.
- Full migration-branch frontend suite: **2,589 passed / 171 files, 42.27 seconds**.
- UI build: passed in **1.47 seconds**, with the existing large-chunk warning.

Initial test invocations were corrected rather than changing production safeguards: UI compilation first aborted with unrestricted native worker defaults; the established single-thread environment and supported Node 24 executable ran successfully. A direct system Node 18 invocation could not locate the shared dependency path and did not run tests. Existing forecast tests initially lacked the Solar_PV companion on `PYTHONPATH`; with that required dependency, all 150 passed. Observed memory PSI averages were zero; no guard was relaxed and no production restart occurred.

The installed collector/shadow runtime, production forecast worker, fitted models, notifications and equipment authority remain unchanged. This is one acquisition day, not additional reliability or qualification days. Fresh fitted-model serving, required-variable/regime evidence, qualification intervals, complete production publication and the attended Open-Meteo retirement remain outstanding. See [cutover](weathernext-cutover.md), [readiness](weathernext-readiness.md) and [retirement](openmeteo-retirement.md).
