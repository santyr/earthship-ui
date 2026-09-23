# Forecast JSON Item file-provider cutover

At 13:18 MDT on September 23, the three observational JSON Items
`Forecast_Hourly_JSON`, `Forecast_Daily_JSON`, and `Forecast_10Day_JSON` moved
from REST-managed to Git-owned file definitions in
`openhab/file-config/items/forecast-json.items`. Names, String types, labels,
tags, category, states and JDBC item identities were preserved. There are no
channel links. The existing `forecast-json.service` remains the sole publisher;
its timer was paused only during the attended handoff and is active again.

Before production writes, an isolated OpenHAB 5.2.1 file-provider check matched
the live definition DTOs. A second isolated OpenHAB/PostgreSQL rehearsal used
three synthetic JSON states, including a roughly 35 KiB detail state, and
verified JDBC persistence, file-to-managed-to-file rollback, hot file reload,
and full JVM restart with exact state and history-prefix restoration. Both
containers and their tmpfs data were removed. No synthetic state was sent to
production.

The live preflight confirmed the naturally published states matched JDBC
history: hourly item580 had 870 rows, daily item581 had 863, and 10-day
item588 had 869. The 13:16 natural publisher completed with exit status0.
The attended transfer privately backed up the managed definitions and Item
JSONDB, removed only these three managed Items, installed the exact prepared
file, verified file ownership and original states, then performed an actual
rollback to managed ownership and return to file ownership. JDBC identity and
all original row hashes remained unchanged at each checkpoint. A final
comment-only source synchronization preserved all three states and providers.
The final source and installed file SHA256 is
`a70834e48b1b61180ee089b28d443de6b6ca61ff5ceb1743da1a58a6752eb78c`.
The rollback record is privately retained at
`/home/sat/.local/state/openhab-config-migration/forecast-json-20260923T191833Z`
(0700 directory, 0600 files). It is not a Git artifact.

The post-transfer registry reports 418 managed plus 11 non-managed Items,
including the three new file-owned Items; 260 managed plus two file links;
81 managed plus three file Things; 35 managed rules and one file persistence
service. The ownership manifest declares the three resources, and inventory
issues are zero. A subsequent natural publisher run under the new provider is
still needed to close this resource's live publication gate; the next scheduled
run is approximately 15:16 MDT. No full production OpenHAB restart was done.
