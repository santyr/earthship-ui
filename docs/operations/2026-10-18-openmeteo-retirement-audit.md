# Open-Meteo removal preparation audit

Observed 2026-10-18 at approximately 16:17 UTC. Source revision: `6e76f4963f93046f1cbe8790672e04920dc8828f`. This is a read-only dependency audit, not a removal or qualification result. The machine-readable record is [the retirement inventory](2026-10-18-openmeteo-retirement-inventory.json).

## Live dependencies to remove or replace

Authenticated local OpenHAB reads confirmed three Things and twelve native Item/channel links. All twelve linked Items are file owned (`editable=false`). Installed definitions comprise five `openmeteo-*.items` files and `things/openmeteo.things`.

The installed binding is a custom JAR at `/usr/share/openhab/addons/com.obones.binding.openmeteo-0.5.0.jar`. The add-on catalog query succeeded but did not list it. Removing only a catalog entry would leave the installed integration behind; cutover must handle the actual JAR, Things and links. The inventory records its byte digest without copying the binary.

A further live rule, `hex_current_aqi_evidence`, observes the Open-Meteo AQI Thing and `Current_US_AQI`, then writes `Current_US_AQI_Evidence_JSON`. Its installed owners are `/etc/openhab/automation/js/current-aqi-evidence.js` and `/etc/openhab/items/current-aqi-evidence.items`. These are present in the current root checkout but absent from the isolated migration branch. Removal must include this producer and its UI/alert receipt consumers, not merely the numeric AQI Item and links. No qualified Google AQI replacement exists in the migration contract.

| Linked surface | Cutover disposition | Current evidence |
|---|---|---|
| `Forecast_Temp`, `Forecast_Daily_High`, `Forecast_Daily_Low` | Replace with qualified Google temperature values | Replacement not qualified |
| `Forecast_Cloudiness`, `Forecast_Radiation`, `Forecast_Daily_PrecipSum` | Replace with qualified Google forcing and interval contracts | Replacement not qualified |
| `Forecast_PrecipProb`, `Forecast_Daily_PrecipProbMax` | Remove or explicitly unavailable unless a separately qualified mapping is established | No native probability mapping established |
| `Forecast_Daily_WeatherCode`, `Forecast_Daily_UVIndex` | Remove or explicitly unavailable unless separately qualified | No qualified mapping established |
| `Current_US_AQI`, `Forecast_AQI`, derived AQI receipt/rule | Remove provider integration and obsolete consumer dependencies | No qualified Google AQI replacement |

Six relevant timers are active: `forecast-intel`, `forecast-json`, `forecast-pre-dusk`, `forecast-temperature-score`, `energy-forecast-snapshot` and `thermal-provisional-forecast`. Their services were inactive between runs at the observation. `forecast-intel-fetch-recovery` is loaded but its timer was inactive. These states alone do not establish which individual timer makes external requests. Stop incumbent acquisition/learning writers first at cutover; rebind retained scoring, energy and thermal consumers to the new source rather than indiscriminately deleting those independent services. Inspect installed overrides and private environment references during deployment without publishing their values.

## Source and state inventory

The scanner covered Git-tracked and nonignored UTF-8 regular files in `openhab`, `src`, `scripts`, `deploy`, `tests`, `.github` and `public`, bounded to 4 MiB per file. It matched provider-name variants, native linked Item names, the existing forecast worker's literal publication names and selected legacy module/receipt identities. It retained identifiers, line numbers and file digests, never source-line contents or credentials.

At the pinned revision this found **232 matching branch files and 1,001 reference lines**. A separate scan of the current root checkout found **77 matching files with different bytes or no corresponding matching branch entry**. The record keeps those overlays separate; it does not attribute their bytes to the pinned migration revision or modify them.

The record also lists the existing forecast worker's **57 top-level functions**, **20 literal forecast publication names**, and **27 literal state-access/default keys**. Some keys are nested filter fields (`P`, `b`), not distinct top-level learning namespaces. This is an audit surface, not a declaration that every listed function or key should be deleted.

Temperature filters/buckets, pending targets, weather-derived PV calibration, prediction/error histories and scored markers require a fresh Google/local namespace. Local observations, physical constants, battery/source epochs and independently learned non-weather behavior retain their existing qualification. Mixed state such as `d_direct`, `learning_evidence` and SoC evidence requires lineage review before preservation; renaming the state file is not enough. No old state was loaded into the new model and no new reset was applied by this audit.

Each source match has an intended treatment or an explicit unresolved-dependency classification. Provider-specific migration/qualification tooling is a removal candidate; mixed Bitcoin, Astro, JDBC and group-provider tools need narrow dependency edits rather than deleting unrelated functionality. Temporary incumbent capture/comparison code must leave the active project at cutover. Historical documentation and detached, truthfully labeled research remain distinct from executable integration.

## Verification and remaining work

The audit checked all twelve live linked Item identities against the source/live union, checked that each listed removal/rebinding action remains unapplied, and required discovery of the root-only AQI rule and the custom binding JAR. Registry endpoints for Things, links, Items, rules and add-on catalog all returned HTTP 200. Response digests, installed-file digests and loaded-unit states are retained in the JSON. No Item values, rule bodies, environment values or authentication material are published.

Text searches do not prove complete transitive dependency coverage. Dynamic state, functions in other modules, installed overrides, bundle activation and the final outbound-request path still require semantic review and attended verification. Task 9 remains partial: this inventory prepares removal; it does not satisfy the post-retirement network/dependency gate.

Real WeatherNext raster access, required-variable qualification, fresh downstream weather-dependent fitting, the normalized production-provider boundary, the actual removal/reset patch and post-cutover outcomes remain unfinished. Production continues on its existing source. See [readiness](weathernext-readiness.md), [the reset/removal contract](openmeteo-retirement.md) and [the access diagnosis](2026-10-18-weathernext-ee-raster-diagnosis.md).
