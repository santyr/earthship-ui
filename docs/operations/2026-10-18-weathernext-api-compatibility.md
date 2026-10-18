# WeatherNext live API compatibility correction

Observed 2026-10-18; execution branch `feat/weathernext-migration-20261018`.

## Findings and correction

Rereading the current WeatherNext Earth Engine guide, both official starter notebooks, the dataset catalogues, dissemination schedule and Earth Engine authentication documentation exposed two incorrect implementation assumptions. A different acquisition backend or approximate spatial query is unnecessary.

1. The custom service-account loader requested only the Earth Engine OAuth scope. Google's authentication documentation requires an appropriate additional scope when external Cloud Storage data is referenced. Changing only the requested token scopes to Earth Engine plus **`devstorage.read_only`** changed the same native station query from HTTP 500 to HTTP 200. The fix retains the private pinned identity, credential-file checks, existing IAM, registration check, read-endpoint allowlist and no-requester-billing policy. No Cloud/Drive write scope, paid service or additional IAM permission was added.
2. The live `getRegion` row clock is initialization time, even though the WeatherNext guide describes `system:time_start` as valid time. For the actual 08Z run / 09Z target, the row reports 1792310400000 (08Z). The reader now retains each image's original `system:time_start`, requires the row clock to match it and accepts only initialization or target time. Forecast validity always comes from `end_time`, independently checked against `start_time + forecast_hour`. Older retained capsules without the explicit property keep their original target-clock validation. No original row is rewritten and no historical availability is inferred.

The native cell at this site is important: the 08Z/09Z station value at the native centre (-105.75, 38.35) was 276.058441 K, while the approximate 5000m site query returned 277.135437 K. The latter proved a request could succeed; it did not prove native-cell equivalence or general service-account access. Tests of a new target and solar field still failed before the storage-scope correction. The earlier diagnosis that only the collector query failed was too narrow. Whether a shared cached computation explains the isolated earlier successes is unproven and is not used as a release assumption.

## Verification

The regression tests failed against the previous code for the missing storage scope and the rejected initialization-clock metadata. All **123 pinned WeatherNext tests** then passed in **3.677 seconds**. The OAuth regression generates disposable key material in memory and inspects the actually signed authorization request through a local fake token exchange; no real or fixed private key is in a fixture.

A real one-hour, two-grid native query then successfully normalized temperature, downward/direct solar, precipitation, wind and cloud while retaining the original metadata and cells. It took 5.452 seconds, 992,022 transferred bytes including bootstrap, and 59,500 KiB peak RSS.

The unchanged collector CLI next retained a complete real **360-hour / 10-band / 3,600-point** snapshot:

- Run: `ee:2026-10-18T06:00:00+00:00`.
- Ingestion completed: `2026-10-18T18:20:30.335824+00:00`.
- Snapshot SHA256: `5dad9ef8ba9e13df4594a7f973004e7e406b1748e6cf54e4d58ade97ad564d44`.
- Elapsed: **10.11 seconds**; received **1,255,580 bytes** across **7 requests**; peak RSS **72,128 KiB**.
- Live noncommercial registration verified. Existing shared 256MiB / 24-task / 90-second collection admission and 75-second acquisition budget preserved.

The original snapshot is private in the execution evidence directory's `live-archive`; no extracted forecast or credential is committed or browser-served. This collection records actual first-observed/completion time, not prospective availability at initialization. It is one acquisition, not 30 days of reliability or a completed training/holdout evaluation. Production forecasts, model fitting, notifications and actuators were unchanged by these checks. Scheduling/deployment requires its own verified installed-state record.

## Official references reread

- [WeatherNext Earth Engine guide](https://developers.google.com/weathernext/guides/earth-engine).
- [Official 0.1-degree notebook](https://storage.googleapis.com/weathernext-public/colabs/WeatherNext_3_Starter_Guide_Earth_Engine_0p1deg.ipynb).
- [Official 0.05-degree notebook](https://storage.googleapis.com/weathernext-public/colabs/WeatherNext_3_Starter_Guide_Earth_Engine_0p05deg.ipynb).
- [Earth Engine authentication and scopes](https://developers.google.com/earth-engine/guides/auth#details_on_scopes).
- [Service-account setup](https://developers.google.com/earth-engine/guides/service_account).
- [Dissemination schedule](https://developers.google.com/weathernext/guides/dissemination).
- [0.1-degree catalogue and bands](https://developers.google.com/earth-engine/datasets/catalog/projects_gcp-public-data-weathernext_assets_weathernext_3_0_0_0p1deg).
- [0.05-degree catalogue and bands](https://developers.google.com/earth-engine/datasets/catalog/projects_gcp-public-data-weathernext_assets_weathernext_3_0_0_0p05deg).
