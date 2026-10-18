# WeatherNext connection proof and retrieval design

Date: 2026-10-18. Project: `earthship-weather-research`. Reader: `weathernext-reader@earthship-weather-research.iam.gserviceaccount.com`. Operator supplied access approval and installed the private credential outside Git.

## Verified connection

The credential belongs to the intended service account/project, is owned by the worker user, has mode 600, and its containing directory has mode 700. OAuth authentication and statistics-bucket listing returned success. Metadata and a real native temperature cell were read successfully without a requester billing project or billing header. Credentials and extracted forecasts were not committed or served to browsers.

OpenHAB regional configuration confirms 38.3739919, -105.7744609 and America/Denver. The bounded diagnostic read selected the nearest 0.1-degree cell (38.4000015, 254.1999969 east). It read `temperature_2m_mean` from run `20261018_02hr_01_preds`, valid at 2026-10-18T03:00Z. This is a retrospective connection test, not an as-issued forecast or skill result. It transferred 19,624,367 bytes in 5.698 seconds with 89,308 KiB peak RSS under the shared resource launcher.

The first 0.05-degree temperature chunk exceeded the diagnostic 64 MiB compressed-object ceiling and was refused before downloading. Metadata shows global spatial chunks: `[1, 3601, 7200]` at 0.05 degrees and `[1, 1801, 3600]` at 0.1 degrees. The station chunk is 103,708,800 bytes decoded. Selecting one cell cannot avoid reading/decompressing the compressed global chunk. One 0.1-degree temperature hour required approximately 19.6 MB; 360 such hours would be approximately 7.1 GB for that variable alone if comparable. This extrapolation is a planning estimate, not a measured full run. Repeated multi-variable, multi-percentile GCS collection would be inefficient for this home server.

Private diagnostic artifacts: `.superpowers/sdd/weathernext-access-20261018/`; no secrets are included in this report.

## Proposed bounded Earth Engine retrieval

The existing migration design explicitly calls for a separately reviewed noncommercial Earth Engine design when GCS point extraction is impractical. Proposed change: retain WeatherNext statistics, independent provenance, archive and normalization contracts, but perform native-cell extraction through Earth Engine in the existing dedicated project.

- Use only a verified noncommercial Community project; refuse paid/commercial configuration. Registration/API enablement and any IAM changes are separate attended account setup, never automatic remediation of an access failure.
- Begin with one run, one band and one site. Expand only after measuring response size, latency and request quota usage.
- Use the exact native projection/cell rather than a geographic-region average. Query station temperature/dew point separately from the 0.1-degree solar/rain/wind/cloud fields.
- Limit each synchronous request to a fixed site, explicit run, selected bands and at most 360 hourly targets. Reject oversized responses, missing targets, schema changes and exhausted deadlines. No batch exports, global reductions, asset creation, BigQuery jobs, rented compute, paid fallback or requester billing.
- Preserve `start_time`, `end_time`, `forecast_hour`, upstream ingestion time, asset identity and Earthship first-observed/ingestion times. Historical retrieval never reconstructs prospective availability.
- Keep the existing host shared-resource admission and one collector lock. Archive compact point records locally, outside Git and browser assets.
- Keep production on the incumbent until required variable/horizon and prospective comparison gates pass. All new actuation remains disabled.

Operator approved this bounded Earth Engine design in chat on 2026-10-18. Project registration and actual access still require verification. Paid access remains prohibited.

## Earth Engine preflight

The read-only project configuration request on 2026-10-18 returned HTTP 403 with reason `SERVICE_DISABLED` for Earth Engine. OAuth authentication succeeded. The operator subsequently enabled the API. A second configuration GET at 14:15:13Z returned `Project earthship-weather-research is not registered to use Earth Engine.` The operator reports a generic console registration error. No computation, registration, IAM or billing change was performed by the agent. The alternate official registration route is https://code.earthengine.google.com/register?project=earthship-weather-research; account owner permissions and the actual failed registration response must be checked before diagnosing its cause.

The official SDK attaches the dedicated project in an Earth Engine quota-routing header. That header is allowed only on approved Earth Engine endpoints, with the exact project, and computation is refused until a live project-configuration response confirms `REGISTERED_NOT_COMMERCIALLY`. It is not permission to attach a GCS requester-billing header or use a different/billed backend.

## Sources

Google GCS layout/cost policy: https://developers.google.com/weathernext/guides/gcs

Google Earth Engine collections/properties: https://developers.google.com/weathernext/guides/earth-engine

Google noncommercial tiers: https://developers.google.com/earth-engine/guides/noncommercial_tiers
