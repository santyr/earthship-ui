# Thermal shadow observation Item file cutover

At 16:37 MDT on September 23, `Thermal_Model_JSON` moved from its REST-managed
provider to the Git-owned `openhab/file-config/items/thermal-model-shadow.items`.
This is an observational String Item written only by `thermal-model-shadow.service`;
it has no channel link. The shadow model, rule/control ownership and publisher
code were not changed. No full production OpenHAB restart or synthetic
production Item value was used.

Preflight read the live managed definition, current state, active timer, idle
service and JDBC mapping `public.item0610`, with 230 rows. The exact source
was first checked in a network-isolated disposable OpenHAB 5.2.1 instance.
A separate disposable OpenHAB/PostgreSQL run verified a 40 KiB synthetic state,
JDBC persistence, file-to-managed-to-file rollback, hot reload and full JVM
restart with the history prefix intact. Both owned containers and tmpfs data
were removed. The managed provider's empty category and file provider's null
category both mean no icon; every other compared definition field matched.

The attended adapter paused only `thermal-model-shadow.timer`, privately saved
the managed definitions and Item JSONDB at
`/home/sat/.local/state/openhab-config-migration/thermal-model-shadow-20260923T223737Z`,
transferred the one Item, exercised actual live managed rollback and return,
verified exact state and JDBC identity/history at each checkpoint, and restored
the timer. The final live Item is `editable:false`, String, correctly labeled,
with no link. Its 11,067-byte state remained present. The installed source and
tracked file share SHA256
`67f74ae74322b9256a6abcb091194e6d1fe5d6a2ec8efde6f5260076d177a68b`.
The inventory now declares this file-owned resource; the next natural shadow
publication must still be checked against the unchanged JDBC mapping.

The first natural post-transfer timer fired at 17:51:47 MDT. The publisher
exited successfully at 17:51:51, and the file-owned Item remained
`editable:false` with a new `shadow` state generated at
`2026-09-23T23:51:48.930701+00:00`. The existing JDBC Item ID stayed 610;
its row count advanced from 230 to 231 with a new row at
`2026-09-23T23:51:51.168242+00:00`. That row exactly matched the live Item
state, and the corresponding private forcing capture passed exact verification.
The timer remained active with its next run scheduled for 19:51:47 MDT. No
manual publication or synthetic production value was used.

This Item transfer does not qualify model accuracy, thermal advisory action
evidence, protected-control recovery or whole-installation file migration.
