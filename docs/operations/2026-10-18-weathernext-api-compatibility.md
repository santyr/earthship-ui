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


## Follow-up online contract audit

Reread on 2026-10-18 in response to the operator's concern that the implementation predates API access. This pass compared the current official Earth Engine guide, both downloaded official notebooks, both collection catalogues, dissemination schedule, service-account/scopes documentation and `ImageCollection.getRegion` API reference against the current reader, normalizer, collector and retained real responses. The two corrections above are already implemented; this audit does not represent a second deployment or new cloud request.

| Assumption | Documentation and actual implementation | Disposition |
|---|---|---|
| Authentication | External GCS-backed assets require a storage scope in addition to Earth Engine. The installed loader requests `earthengine` and `devstorage.read_only`. | Corrected; no additional IAM grant or personal-account token needed. |
| Forecast clock | Official notebooks use `end_time` for targets. The general guide calls `system:time_start` valid time, while retained live rows report initialization time. | Preserve original clock, validate row/metadata equality, derive target from cross-checked `end_time` and lead hour. Do not use `filterDate` to select forecast target time. |
| Spatial extraction | The notebooks demonstrate regional covering-grid reductions. `getRegion` officially supports a point and an explicit Projection; adding a metre scale resizes that projection. | Keep the actual native projection/cell and returned coordinates. Approximate 5000/10000-metre queries need not reproduce that cell and are not a replacement contract. |
| Collections and bands | The 0.05-degree collection provides station temperature/dewpoint; the 0.1-degree collection supplies solar, rain, wind, cloud and pressure statistics. | Correct grid assignment; fixed named statistical bands, no raw-ensemble download or spatial averaging of quantiles. |
| Units and intervals | Catalogues specify Kelvin, hourly solar energy in J/m², hourly precipitation in metres, pressure in Pa and cloud fraction. | Existing conversions and complete trailing-hour daily sums agree; missing intervals stay unavailable and daily quantiles are not sums of hourly quantiles. |
| Run horizon and delivery | Main 00/06/12/18Z runs have 360-hour horizons; interim runs have 48. Dissemination occurs hours after initialization and can be delayed. | Full-horizon discovery requires the requested lead hour; acquisition/decision availability remains separately recorded. A new initialization timestamp is not proof that data was already available. |
| Precipitation heads | Three distinct hourly rain products are documented and observed. | All three are now retained separately; product selection still requires paired local outcomes. |

The official notebook bytes were retained privately for reproducibility: 0.1-degree SHA256 `1762f318c422a5e88a125d4ecc725671211f3b7a12b487e4b4e7f86e748499e7`; 0.05-degree SHA256 `16290b9564f1e9b0f4f01669f99d776d4abcecfdfc18172d523f848dc410df52`. No notebook outputs or extracted forecasts were added to the repository.

Fresh verification: **128 tests passed in 3.467 seconds** using the pinned Earth Engine environment and existing shared job admission. The first invocation supplied a relative executable path and was refused before tests started; using the required absolute path resolved that invocation error without changing resource safeguards. The installed `weathernext_ee.py`, `normalize.py` and `worker.py` independently match the reviewed branch bytes. Read-only systemd checks report successful last collector/shadow runs and active timers. The previously retained real installed capture contains 360 hours / 12 bands / 4,320 points, including 360 values for each rain head; see the [rain capture evidence](2026-10-18-weathernext-rain-candidates.md).

**Decision:** retain the bounded native-cell Earth Engine acquisition architecture with its corrected scopes and clock parser. No further retrieval refactor is justified by this documentation comparison. This is not approval of every downstream consumer: fresh Google/local learning, required-variable and downstream qualification, production-provider integration and complete Open-Meteo retirement remain unfinished under the existing migration plan. Successful API access and passing regression tests do not establish local predictive skill.

Additional API reference: [ImageCollection.getRegion](https://developers.google.com/earth-engine/apidocs/ee-imagecollection-getregion).

The subsequent [fixed thermal comparison](2026-10-18-weathernext-fixed-thermal-attribution.md) exposed a downstream assumption unrelated to retrieval: the installed current thermal artifact uses a newer irradiance/shade model family than the older checkout fixture. Its separate comparison adapter now delegates family selection to the original executing runtime; actual fixed-model Google forcing replay succeeds without changing production. This does not change the acquisition decision above or qualify thermal skill.

## Current-source verification

This pass reread the current official Earth Engine guide, both collection band/property catalogues, dissemination schedule, service-account/scopes documentation and `getRegion` reference against the current reader, normalizer, transport and collector. It found no additional retrieval architecture mismatch. The two API corrections above are existing changes, not changes made in this pass.

After rereading the current official documentation, **all 182 WeatherNext package tests passed in 6.302 seconds** in the pinned Earth Engine environment through the shared resource admission runner. This includes the SDK bootstrap, signed OAuth scope, native projection, source-clock, normalization, transport, collector and archive checks. It is not a claim that the entire migration or downstream suite passed.

Retained live evidence from the unchanged collector, using the existing service-account credential, is a separate diagnostic **360-hour / 12-band / 4,320-point** snapshot:

- Initialization: `2026-10-18T12:00:00+00:00`.
- Collection completed: `2026-10-19T01:49:19.187211+00:00` (October 18 locally).
- Snapshot SHA256: `15ea934badb24e36220540ff27ff00bfaa84a10614407af10a592897f3b870fb`.
- Elapsed **12.097 seconds**, **1,272,068 bytes** over seven requests, **73,880 KiB peak RSS**.
- All 360 values were present for each of the 12 selected bands; both grids returned one stable native cell. Returned row clocks matched original metadata and were initialization clocks; forecast targets remained independently derived from `end_time` and lead hour.
- Live noncommercial registration verified; production writes and automatic actuation were false. Existing collection admission, transfer and deadline limits were preserved.

Original bytes, index and an aggregate contract check are private under the execution directory's `online-contract-recheck-archive`; nothing was written to the installed collector archive, model state or OpenHAB. No personal-account ADC, IAM change, paid fallback, fitting or service activation was used. The current parser also reconstructed all 4,320 normalized points exactly from those retained original responses, and the snapshot identity still matches its archive name. Installed `weathernext_ee.py`, `normalize.py` and `worker.py` are byte-for-byte equal to the reviewed branch. A read-only systemd check found the collector timer active and its last service execution successful (exit 0 at 2026-10-18 20:35:37 MDT). This latest verification reused the retained response and made no new cloud request.

**Decision:** retain the corrected native-cell Earth Engine reader. The generic guide's suggested approximate metre scales do not require resampling an explicitly supplied native projection; the `getRegion` API documents that supplying a scale resizes that projection. Keep the exact native cell for reproducible local learning. Likewise, the WeatherNext guide's `system:time_start` description still differs from actual returned rows; preserve the original clock and validate forecast targets independently.

The documented multi-hour dissemination lag means initialization age and observed availability must remain distinct. Hourly solar fields remain energy in J/m², converted to mean W/m² by dividing by 3,600; hourly precipitation remains metres converted to millimetres. These behaviors already agree with the implementation. This successful collection does not establish prospective reliability or local predictive skill. Production-provider integration, fresh downstream Google/local learning, qualification and complete Open-Meteo retirement remain unfinished.
