# WeatherNext Earth Engine raster access diagnosis

Date: 2026-10-18. Project: `earthship-weather-research`. Principal: `weathernext-reader@earthship-weather-research.iam.gserviceaccount.com`. These are bounded read-only diagnostics, with no production forecast changes or paid fallback.

> **Latest status:** A matching service-account mean reduction succeeded at 18:07Z. Native-projection extraction still fails. See the dated update below; earlier failures are retained as historical evidence.

## Earlier verified result

Project configuration returns `REGISTERED_NOT_COMMERCIALLY`; own-permissions testing confirms `earthengine.computations.create`, `earthengine.assets.get`, `earthengine.config.get`, `serviceusage.services.use` and `resourcemanager.projects.get`. The operator applied a project Owner grant; the agent changed no IAM. This fixes the former project access denial, but does not establish that Owner is needed. The intended narrower roles remain Earth Engine Resource Viewer and Service Usage Consumer.

SDK initialization, run discovery, image properties/band names/native projection and a constant-raster reduction all return success. WeatherNext raster computations return HTTP 500 internal errors. This is an observed failure in the Google path, not proof of its internal cause: dataset backing access/ingestion versus reader-specific dataset authorization still needs Google diagnosis.

The tested station image is `202610180700_202610180800`, initialized 07:00Z and valid 08:00Z. Its real native projection is EPSG:4326 with affine transform `[0.05, 0, -180.025, 0, -0.05, 90.025]`; the 12 documented station bands are present. Both station and gridded collections also fail at initialization 00:00Z, hour 1. Each query is one site, one band and one image; no full run/global raster was downloaded.

| Fixed diagnostic | Result |
|---|---|
| Project config / algorithms / discovery | HTTP 200 |
| Run and station image metadata | HTTP 200 |
| Constant raster, first value at site, scale 5000, maxPixels 16 | Value 1 |
| Native-projection `getRegion` at the site | HTTP 500 |
| `getRegion` with native nominal scale | HTTP 500 |
| `getRegion` with measured native affine coefficients | HTTP 500 |
| Native first-value `reduceRegion`, maxPixels 16 | HTTP 500 |
| Both grids, 00Z and 07Z runs, first hour | HTTP 500 |
| Tiny rectangle fully inside the nearest native station cell | HTTP 500 |

The primary SDK point diagnosis transferred 991,384 bytes including SDK bootstrap, took 5.349 seconds and peaked at 61,112 KiB RSS. The final constant/rectangle comparison used 991,226 bytes and 3.911 seconds. These are failed point-query measurements, not a successful full-horizon benchmark. Diagnostics used the existing shared host launcher and fixed 75-second acquisition/90-second job budgets. No CPU/memory/swap safeguard changed.

## Minimal reproduction for Google support

Use the private reader credential on the existing verified project. Do not include the credential, token or authorization headers in a support request. The following is the native first-value query; authentication setup is intentionally omitted.

```python
import ee

# ee.Initialize(credentials=PRIVATE_READER, project="earthship-weather-research")
collection = ee.ImageCollection(
    "projects/gcp-public-data-weathernext/assets/weathernext_3_0_0_0p05deg"
)
image = ee.Image(collection.filter(
    ee.Filter.eq("start_time", "2026-10-18T07:00:00Z")
).filter(ee.Filter.eq("forecast_hour", 1)).limit(1).first())
selected = image.select(["station_head_temperature_2m_mean"])
projection = selected.projection()
point = ee.Geometry.Point([-105.7744609, 38.3739919])
print(selected.reduceRegion(
    reducer=ee.Reducer.first(), geometry=point,
    crs=projection, scale=projection.nominalScale(),
    maxPixels=16, bestEffort=False,
).getInfo())
```

Representative actual request IDs:

- Native point: `b2a88b89-8b33-4d8b-bf5b-38b5b13330e9`, computation `S6RQIWF436WWXHRRURGRNR3S`.
- Station native reduction: `c5565ad6-f129-4ebe-a217-29a0d89373d7`, computation `VMWDNZCMLC7RDMHBKE53RC3D`.
- Gridded 00Z reduction: `79c3e3b2-45c9-4a66-a54b-a68da3c36cba`, computation `OAXBR7L6YVBDOGDY4XC3UYN2`.
- Native one-cell rectangle: `0d326466-f755-43e3-8cea-6fb713a0b7a7`, computation `D2J7AN2A5MGR6HK5OE5OZYD4`.

Private originals and traces are retained under `.superpowers/sdd/weathernext-access-20261018/`. No message has been sent to Google by the agent. Ask Google to investigate the raster-access failure for this reader/project and these computation IDs; no additional project privilege or paid-service enablement is justified by these results.

## Next action

Confirm whether the reader service account was included in the original WeatherNext dataset-access request. Project IAM and noncommercial Earth Engine registration are now verified; those checks and public statistics-bucket access do not establish this reader’s separate dataset entitlement. This is an unresolved question, not a diagnosed cause of HTTP 500. Do not grant further project privileges to test it.

Keep the collector uninstalled/disabled. Continue independent local implementation. Retry one bounded native point after a Google fix or another concrete dataset/access change; only a successful real point followed by measured 360-hour collection can justify scheduling. Do not poll identical failing computations or switch backends automatically.

Official query/property reference: [WeatherNext on Earth Engine](https://developers.google.com/weathernext/guides/earth-engine). Native extraction interface: [getRegion](https://developers.google.com/earth-engine/apidocs/ee-imagecollection-getregion).


## New-source verification at 15:54Z

A metadata check after the next publication discovered initialization `2026-10-18T08:00:00Z`, image `202610180800_202610180900`, rather than retrying the previously failing 07Z image. One bounded native station-temperature point read still returned HTTP 500: request `d8be8a75-0d81-4605-865e-f9b321881592`, computation `Q6BBS2ZSHVXYMWUXPNWH2E64`. It used 991,384 bytes / 6 requests including SDK bootstrap, 5.058 seconds and 61,068 KiB peak RSS. No real forecast snapshot or prospective evidence was accepted. This new-source result strengthens the support reproduction; it does not establish Google's internal cause.


## Successful account comparison and remaining query failure (18:07–18:10Z)

This update supersedes the earlier statement that all WeatherNext raster reads fail. The operator ran the fixed 08Z image / 09Z target query in Code Editor under their approved personal Google account and reported `station_head_temperature_2m_mean: 277.13543701171875` (3.985437 degrees C). At 18:07:25Z the agent ran the identical mean reduction using the existing service-account credential, project, site, band and 5000m scale. It returned HTTP 200 and exactly the same value. The agent changed no code, credential, IAM or registration setting to obtain this success. The reason earlier equivalent reductions failed is not established; this is not proof of a specific Google fix or account propagation delay.

A same-session comparison then returned the same temperature from both direct-image and filtered-collection mean reductions. Filtered source metadata also succeeded. In contrast, direct-image and filtered-collection native-projection `getRegion` still returned HTTP 500. Native-projection sampling and first-value reduction also failed, including when the measured EPSG:4326 affine transform was supplied explicitly. A one-hour six-variable call through the unchanged collector stopped at its first station-grid native extraction, before querying the gridded variables. Its failure does not establish whether those other variables succeed.

The current observed blocker is the collector's native-projection extraction path, not an established lack of service-account dataset approval. No further project privilege or credential change is justified by these results. The documented-scale mean query provides a working comparison path; adapting acquisition must preserve the approved source, spatial semantics, original evidence, target/byte/deadline bounds and missing-value behavior. Full-horizon acquisition and downstream qualification remain unverified; no collector was scheduled and no production value was published.

The successful service-account test took 4.737 seconds, transferred 991,063 bytes including SDK bootstrap and peaked at 60,472 KiB RSS. The subsequent query-shape comparison took 5.539 seconds. All diagnostics used the unchanged shared 256MiB / 24-task / 90-second admission. Private exact results are `approved-account-comparison.json`, `native-six-variable-probe.json`, `native-query-shape-isolation.json`, `native-cell-reduction-alternatives.json` and `explicit-native-transform-isolation.json` in the existing execution evidence directory. The personal-account result is operator-reported; the service-account result and query comparisons were observed directly by the agent.
