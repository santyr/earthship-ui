# Forecast_AQI file-first preflight — September 23

This dated preflight is superseded for production ownership by the attended
[cutover receipt](2026-09-23-openmeteo-forecast-aqi-item-cutover.md). The
natural post-transfer binding-series check remains open.

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

At this provider checkpoint, this was **not** a live migration or a
JDBC/history qualification. The separate state/JDBC follow-up is below. Before
an attended cutover, the actual forecast-series behavior and live recovery
semantics must be resolved, then the exact managed Item/link and available
JDBC mapping/history must be privately snapshotted. The single-provider
transfer must be reversible and followed by a natural binding refresh. Do not
declare file ownership or alter the live link until those gates pass.

Follow-up: the closed `--candidate forecast` mode of the isolated
OpenHAB/PostgreSQL recovery harness passed. A synthetic String state written
only inside the disposable OpenHAB instance produced one JDBC row. File
withdrawal/reload restored that state and retained the row prefix; a full JVM
restart did the same. The owned OpenHAB and PostgreSQL containers were removed,
with zero production writes. Live read-only checks show the managed Item state
is the special value `REFRESH`; OpenHAB's JDBC persistence endpoint currently
returns zero rows for this Item. The restricted SQL reader denied access to its
underlying Item table, as expected. This isolated synthetic-state result does
not prove future hourly series delivery through the real binding, nor does it
establish a live state-restoration requirement for `REFRESH`. Those semantics,
the private live snapshot and a reversible attended cutover remain open.

Read-only event-log follow-up resolves the current managed-provider behavior:
at 16:51:26 MDT the binding emitted `ItemTimeSeriesEvent` and
`ItemTimeSeriesUpdatedEvent` for `Forecast_AQI`, each reporting 48 values;
earlier hourly refreshes did the same. The Item has no `gForecast` membership,
so the file-owned JDBC strategy's forecast selector does not apply. The
OpenHAB JDBC REST endpoint reports zero rows for this Item, consistent with
that selector and its `REFRESH` state. A file-provider cutover must preserve
the real 48-value binding event stream, not invent historic JDBC rows or
reclassify `REFRESH` as a measured AQI value. Live cutover remains deferred.

A later read-only check through the configured JDBC connection resolved the
underlying `public.items` mapping to Item ID 582 and found two older rows in
`public.item0582`, last written July 17. The zero-row REST response therefore
must not be treated as proof of an empty SQL table. A live cutover must retain
that exact historical prefix while withholding any claim that it represents
the current 48-value forecast series. At 17:51:27 MDT on September 23 the
managed binding again emitted both 48-value time-series events, and the Thing
was ONLINE; the Item state remained the special value `REFRESH`.

Verification: 1,697 UI/source tests, four qualifier selector tests and both
isolated provider/restart/rollback and state/JDBC restore runs passed. The
Git-owned source has not been installed on the production host.
