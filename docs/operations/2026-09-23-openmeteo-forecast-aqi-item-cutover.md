# Forecast_AQI file-provider production transfer

September 23, 2026, 18:01 MDT. The observational `Forecast_AQI` String Item
and its single `openmeteo:air-quality:local:aq:forecastHourly#us-aqi-as-string`
channel link moved from REST-managed to the Git-owned
`openhab/file-config/items/openmeteo-forecast-aqi.items`. No Thing, control
rule, persistence strategy or other Item was changed.

The source had already passed a networkless OpenHAB 5.2.1 provider/restart/
managed-rollback rehearsal. A separate disposable OpenHAB/PostgreSQL run
verified a String state and JDBC prefix across file reload and full JVM
restart. Immediately before the attended transfer, that recovery run was
repeated with the exact special `REFRESH` state: file reload and full restart
both restored it and preserved the isolated JDBC prefix. Both owned disposable
containers were removed. None of the isolated updates reached production.

Read-only production preflight required the exact managed Item/link, its
`REFRESH` state, ONLINE file-owned air-quality Thing, absent target file,
unchanged source SHA-256, JDBC Item ID 582 and two legacy rows. Both rows
contained `REFRESH`; neither is a measured AQI or the 48-value forecast
series. The managed binding had emitted paired 48-value time-series events at
17:51:27 MDT, establishing the pre-transfer behavior.

The attended adapter privately saved the original REST Item/link, complete
Item/link JSONDB files and JDBC-prefix digest in mode-0700/0600 storage at
`/home/sat/.local/state/openhab-config-migration/forecast-aqi-20260924T000112Z`.
The directory may contain unrelated private host data and must not be committed
or copied into public storage. It then withdrew only that managed link and
Item, observed their absence, installed the pinned source, and verified the
file provider. A guarded rollback path can withdraw the owned file and
restore the saved managed definitions on failure; no rollback was needed live.

Independent readback after transfer showed exact source/installed SHA-256
`5d9517fc7c68d22df252ed43c5dc551782438cf00cca81088c626f2a66914590`,
mode 0644, one `editable:false` Item and one `editable:false` link to the
unchanged channel, `REFRESH` state, Thing ONLINE, unchanged JDBC identity 582
and the same two historical rows. The source's old “prepared only” comment
remains a guard against installing it on another host while managed providers
still exist; it does not describe this host after the verified transfer.

This is a provider/state/history cutover receipt, not yet a natural-writer
receipt. The first post-transfer hourly OpenMeteo refresh must produce the
paired 48-value `ItemTimeSeriesEvent` and `ItemTimeSeriesUpdatedEvent` for
`Forecast_AQI` under the file-owned link. `REFRESH` must not be presented as a
numeric AQI, and no new JDBC row is expected merely from an unchanged special
state. No synthetic production state, REFRESH command, binding fetch or full
OpenHAB restart was used to claim that behavior.
