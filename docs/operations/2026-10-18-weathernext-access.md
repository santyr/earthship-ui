# WeatherNext connection proof and retrieval design

Date: 2026-10-18. Project: `earthship-weather-research`. Reader: `weathernext-reader@earthship-weather-research.iam.gserviceaccount.com`. Operator supplied access approval and installed the private credential outside Git.

## Current status (reverified 2026-10-19T01:49Z)

Earth Engine access is working with the existing service account. The registration, permission and raster failures recorded below are historical; they do not call for further IAM grants, personal-account authentication or API enablement. The [API compatibility report](2026-10-18-weathernext-api-compatibility.md) explains the corrected storage OAuth scope and source-clock handling, the successful full-horizon captures, and the current documentation audit.

A fresh bounded native-cell collection completed at 2026-10-19T01:49:19Z (October 18 locally): `ARCHIVED`, run `ee:2026-10-18T12:00:00+00:00`, 360 hours, 12 bands and 4,320 present values. It took 12.097 seconds, received 1,272,068 bytes over seven requests, peaked at 73,880 KiB RSS and verified noncommercial registration. Original rows and metadata passed the separate clock/cell/completeness check. The snapshot is in a separate private diagnostic archive; it published nothing and did not update installed archives, models or services. All 56 selected acquisition regression tests passed in 0.287 seconds. This verifies acquisition, not completed provider cutover or predictive qualification; see the compatibility report for the exact scope and snapshot identity.

## Initial connection evidence

The credential belongs to the intended service account/project, is owned by the worker user, has mode 600, and its containing directory has mode 700. OAuth authentication and statistics-bucket listing returned success. Metadata and a real native temperature cell were read successfully without a requester billing project or billing header. Credentials and extracted forecasts were not committed or served to browsers.

OpenHAB regional configuration confirms 38.3739919, -105.7744609 and America/Denver. The bounded diagnostic read selected the nearest 0.1-degree cell (38.4000015, 254.1999969 east). It read `temperature_2m_mean` from run `20261018_02hr_01_preds`, valid at 2026-10-18T03:00Z. This is a retrospective connection test, not an as-issued forecast or skill result. It transferred 19,624,367 bytes in 5.698 seconds with 89,308 KiB peak RSS under the shared resource launcher.

The first 0.05-degree temperature chunk exceeded the diagnostic 64 MiB compressed-object ceiling and was refused before downloading. Metadata shows global spatial chunks: `[1, 3601, 7200]` at 0.05 degrees and `[1, 1801, 3600]` at 0.1 degrees. The station chunk is 103,708,800 bytes decoded. Selecting one cell cannot avoid reading/decompressing the compressed global chunk. One 0.1-degree temperature hour required approximately 19.6 MB; 360 such hours would be approximately 7.1 GB for that variable alone if comparable. This extrapolation is a planning estimate, not a measured full run. Repeated multi-variable, multi-percentile GCS collection would be inefficient for this home server.

Private diagnostic artifacts: `.superpowers/sdd/weathernext-access-20261018/`; no secrets are included in this report.

## Approved bounded Earth Engine retrieval

The existing migration design explicitly calls for a separately reviewed noncommercial Earth Engine design when GCS point extraction is impractical. Proposed change: retain WeatherNext statistics, independent provenance, archive and normalization contracts, but perform native-cell extraction through Earth Engine in the existing dedicated project.

- Use only a verified noncommercial Community project; refuse paid/commercial configuration. Registration/API enablement and any IAM changes are separate attended account setup, never automatic remediation of an access failure.
- Begin with one run, one band and one site. Expand only after measuring response size, latency and request quota usage.
- Use the exact native projection/cell rather than a geographic-region average. Query station temperature/dew point separately from the 0.1-degree solar/rain/wind/cloud fields.
- Limit each synchronous request to a fixed site, explicit run, selected bands and at most 360 hourly targets. Reject oversized responses, missing targets, schema changes and exhausted deadlines. No batch exports, global reductions, asset creation, BigQuery jobs, rented compute, paid fallback or requester billing.
- Preserve `start_time`, `end_time`, `forecast_hour`, upstream ingestion time, asset identity and Earthship first-observed/ingestion times. Historical retrieval never reconstructs prospective availability.
- Keep the existing host shared-resource admission and one collector lock. Archive compact point records locally, outside Git and browser assets.
- Keep production on the incumbent until required variable/horizon and prospective comparison gates pass. All new actuation remains disabled.

Operator approved this bounded Earth Engine design in chat on 2026-10-18. Registration and actual access were subsequently verified as recorded in the current status above. Paid access remains prohibited.

## Historical Earth Engine preflight

The read-only project configuration request on 2026-10-18 returned HTTP 403 with reason `SERVICE_DISABLED` for Earth Engine. OAuth authentication succeeded. The operator subsequently enabled the API. A second configuration GET at 14:15:13Z returned `Project earthship-weather-research is not registered to use Earth Engine.` The operator reports a generic console registration error. No computation, registration, IAM or billing change was performed by the agent. The alternate official registration route is https://code.earthengine.google.com/register?project=earthship-weather-research; account owner permissions and the actual failed registration response must be checked before diagnosing its cause.

The official SDK attaches the dedicated project in an Earth Engine quota-routing header. That header is allowed only on approved Earth Engine endpoints, with the exact project, and computation is refused until a live project-configuration response confirms `REGISTERED_NOT_COMMERCIALLY`. It is not permission to attach a GCS requester-billing header or use a different/billed backend.

## Sources

Google GCS layout/cost policy: https://developers.google.com/weathernext/guides/gcs

Google Earth Engine collections/properties: https://developers.google.com/weathernext/guides/earth-engine

Google noncommercial tiers: https://developers.google.com/earth-engine/guides/noncommercial_tiers


## Historical project-permission check (14:46Z)

The operator enabled Cloud Resource Manager, then reported completing the exact noncommercial reverification and granting `roles/earthengine.viewer` and `roles/serviceusage.serviceUsageConsumer` to the reader. After more than seven minutes, the read-only own-permissions check still returned HTTP 200 with no granted permissions among `earthengine.computations.create`, `earthengine.assets.get`, `earthengine.config.get`, `serviceusage.services.use` and `resourcemanager.projects.get`. The fresh EE configuration GET at 2026-10-18T14:46:29Z returned HTTP 403 `Permission 'earthengine.config.get' denied`.

This verifies an effective access denial, not its administrative cause or registration status. The operator has been asked to check the exact principal on the **project IAM** page: https://console.cloud.google.com/iam-admin/iam?project=earthship-weather-research. Service-account resource permissions are a different surface. The agent made no IAM changes. No further point query or scheduler activation is justified until this check succeeds.


## Historical IAM resolution and raster failures (14:54Z onward)

After the operator added the exact reader principal with Owner on project IAM, all five requested permissions became effective. Configuration GET at 2026-10-18T14:54:00Z returned HTTP 200 and `REGISTERED_NOT_COMMERCIALLY`. The earlier empty permission results are historical. The reader need not be given further privileges to investigate the observed failure.

The next live CLI probe reached WeatherNext computation but returned an EE internal error. Native metadata and a constant raster control succeed; WeatherNext raster reads fail across both grids and two runs. See [the bounded diagnosis and Google support handoff](2026-10-18-weathernext-ee-raster-diagnosis.md). No successful EE snapshot, full 360-hour measurement or scheduler activation is claimed. No paid backend/fallback was enabled.
