# Current US AQI Item: file-first production transfer

September 23, 2026. The managed `Current_US_AQI` Number Item and its single
managed `openmeteo:air-quality:local:aq:current#us-aqi` link were transferred
to the Git-owned `openmeteo-current-aqi.items` definition. This is one
observation-only Item/link transfer, not a blanket OpenHAB migration.

Before the live operation, the installed OpenHAB 5.2.1 grammar accepted the
source. A networkless restore-based rehearsal verified the exact file-owned
Item/link on first boot and after restart, then managed rollback. A separate
isolated OpenHAB/PostgreSQL run verified an AQI state and JDBC historical prefix
survived file hot reload and full JVM/container restart. Its numeric value was
synthetic and never sent to production. Both test containers were removed.

Live preflight required the exact managed Item/link, generated noneditable
semantics metadata, ONLINE file-owned AQI Thing and channel, one JDBC Item
identity (`587`), a numeric live state matching the latest persisted value,
581 history rows, and absence of the target file. The guarded cutover saved
the exact REST originals and complete Item/link JSONDB files in a private
mode-0700 directory, with files mode 0600:

`/home/sat/.local/state/openhab-config-migration/openmeteo-aqi-20260923T181809Z`

The full JSONDB copies may contain unrelated private settings; do not commit,
print or move them to public storage. After that backup, the script withdrew
the managed link and Item, observed their absence, installed the source at
`/etc/openhab/items/openmeteo-current-aqi.items`, and verified file-owned
Item/link identity, state restoration, JDBC historical prefix and Thing health.
It made no Item command, synthetic state update, binding refresh or OpenHAB
restart. On any mismatch before completion, the script was prepared to move
the owned file out of the watched tree and restore the exact managed Item/link.
That rollback path was qualified in isolation; it was not invoked live.

Independent readback found installed/source SHA-256
`82b92ebe0d10f439d067fa309f8ee28b1fa5fd693e0abd8c2e1b0caa9241e530`,
mode 0644, `editable:false` for both Item and link, unchanged AQI state
`37.708336`, AQI Thing `ONLINE/NONE`, and the last changed-value JDBC row still
present. The post-cutover ownership inventory reports 421 managed/eight
non-managed Items, 260 managed/two non-managed links, 81 managed/three
non-managed Things, one file-owned JDBC strategy and zero issues. The restored
unchanged state did not create an extra JDBC change row.

The next natural OpenMeteo binding fetch completed at 12:51:20 MDT. OpenHAB
logged a `Current_US_AQI` change from 37.708336 to 37.75463 with source
`org.openhab.core.thing$openmeteo:air-quality:local:aq:current#us-aqi`.
The file-owned Item read 37.75463 afterward, and JDBC identity 587 advanced
from 581 to 582 rows with the matching value at
2026-09-23T18:51:20.448051Z. The same fetch updated the `Forecast_AQI`
time series with 48 values. This closes the natural production-writer gate
for the transferred Item/link; it does not qualify indefinite operation or
off-host recovery. The private snapshot remains same-host rollback material.
