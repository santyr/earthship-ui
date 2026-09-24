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

An 18:01:14 MDT 48-value time-series pair occurred during the provider
transfer, so it was not counted as natural binding recovery. The next hourly
OpenMeteo fetch at **18:51:28 MDT** emitted the natural
`ItemTimeSeriesEvent`/`ItemTimeSeriesUpdatedEvent` pair for `Forecast_AQI`,
each with 48 values. The same fetch emitted a 48-value `Forecast_Temp` pair
and changed file-owned `Current_US_AQI` from 34.884262 to 35.598328 with
the binding channel named as source. This closes the first natural
post-transfer forecast-series writer gate without a forced refresh.

Subsequent readback found installed/source SHA-256 still identical, mode
0644, `Forecast_AQI` and its one exact link both `editable:false`, AQI Thing
ONLINE, Item state still `REFRESH`, and stable JDBC Item identity 582 with
the same two legacy `REFRESH` rows. The time series is not represented by
those scalar JDBC rows and no numeric AQI is inferred from `REFRESH`.
The read-only file-first inventory returned zero issues (416 managed/15
nonmanaged Items, 259/4 links, 81/3 Things, 36 managed rules and one
file-owned persistence service). No synthetic production state, REFRESH
command, binding fetch or full OpenHAB restart was used. This qualifies the
first natural writer, not indefinite operation or off-host recovery.
