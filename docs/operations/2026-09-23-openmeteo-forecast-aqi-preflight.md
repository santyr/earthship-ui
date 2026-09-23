# Forecast_AQI file-first preflight — September 23

`Forecast_AQI` remains REST-managed. Read-only live registry checks found one
String Item labeled “US Air Quality Index,” tag `forecast`, no category/group
or Item metadata, and one managed link to
`openmeteo:air-quality:local:aq:forecastHourly#us-aqi-as-string` with no link
configuration. The OpenMeteo air-quality Thing is already file-owned. The
Item's live state and any credentials were not exported into Git.

`openhab/file-config/items/openmeteo-forecast-aqi.items` now stages that exact
Item and link definition. It is deliberately absent from `ownership.json` and
must not be installed while the managed providers exist. A source test checks
both the definition and this non-ownership boundary.

The existing restore-based OpenHAB 5.2.1 provider rehearsal was extended with
a closed `--candidate forecast` selector. It loaded the staged source in a
networkless disposable container after removing only the managed Forecast_AQI
Item/link from the restored private snapshot. Exact live presentation fields,
file-owned provider and link target matched on first boot and after a full JVM
restart. Removing the file withdrew both resources; restoring their managed
definitions through REST matched again. The first run reached restart success
but exposed an absent optional `category` field in the rollback helper. That
nullable-field assumption was fixed and covered by a unit test; the complete
rerun passed. Both owned containers were removed and absence verified. No
production Item/link or state was changed.

This is **not** a live migration or a JDBC/history qualification. Before an
attended cutover, verify persisted state and forecast-series prefix across
file reload/full restart in isolation; privately snapshot the exact live
managed Item/link and JDBC mapping/history; then perform a reversible,
single-provider transfer and verify the next natural binding refresh. Do not
declare file ownership or alter the live link until those gates pass.

Verification: 1,697 UI/source tests, three qualifier selector tests and the
complete isolated provider/restart/rollback run passed. The Git-owned source
has not been installed on the production host.
