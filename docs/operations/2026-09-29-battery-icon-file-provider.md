# BatteryIcon file-provider handoff

`BatteryIcon` is a UI icon value, but its managed definition has custom
`stateDescription` metadata: value is one space and pattern is
`"Battery Icon [%s]" <iconify>`. A plain `String BatteryIcon` declaration would
lose that format. The staged `openhab/file-config/items/battery-icon.items`
preserves the exact value and pattern. It was installed only after the
qualifications and guarded cutover described below.

On September 29, an isolated, networkless OpenHAB 5.2.1 file-provider run
matched the live Item's name, type, label, category, tags, Groups, metadata
value/config and REST state-description. The sole DTO difference was
`metadata.stateDescription.editable`: `true` for the live managed Item and
`false` for the isolated file-owned Item. This is an ownership change, not a
format change. The owned container and tmpfs were removed after the test.

A separate snapshot-based, networkless OpenHAB rehearsal removed both the
managed Item and its managed `stateDescription` registry entry before boot.
The file provider reproduced the expected metadata. After file withdrawal,
REST restored the managed Item and separately restored its `stateDescription`
metadata; readback matched the original definition, including managed
`editable:true`. The owned container was removed, and production writes were
zero. An earlier disposable attempt removed only the Item, exposing that
surviving managed metadata overrides the file provider; that container was
also removed.

The live `BatteryIcon` is still REST-managed, unlinked and ungrouped. Its
unique JDBC mapping is Item 31, with 136,507 rows and a current/persisted
`iconify:mdi:battery-70` state at the read-only check. The
`UpdateBatteryIcon` rule runs every 30 seconds; its script SHA-256 was
`834544eb8a9648a6c3082a8a135b3d22b5ef5ae0922a86fb9ee3e4f4fb110e2f`.
That same rule also updates `BatteryChargingStatus`, so disabling it during
icon migration could interrupt another live status signal. Do not do that.

The guarded adapter keeps the writer running, allows only later natural JDBC
rows during the handoff, preserves the exact pre-transfer Item 31 history
prefix, and restores managed ownership plus metadata on failure. Six focused
history tests reject rewrites, deletions, backfills, same-timestamp additions
and identity changes while accepting later appends. Four adapter tests cover
the closed release gate, metadata equivalence, provisional transfer and
metadata-preserving rollback. A read-only production check passed over all
136,507 existing Item 31 rows; the exact 9,694,006-byte CSV backup was
rehearsed in `/tmp` with mode 0600 and automatically removed.

The disposable OpenHAB/PostgreSQL rehearsal then passed synthetic persistence,
managed rollback, forward file transfer, hot reload and full JVM restart.
`stateDescription` metadata matched at each provider transition. Both owned
containers and the disposable database were removed; production writes were
zero. The live adapter's `--check` passed with the expected Item, writer SHA,
JDBC mapping/state, source hash and absent file target.

## Attended production handoff — September 29, 03:06 MDT

`--apply` created the private rollback directory
`/home/sat/.local/state/openhab-config-migration/battery-icon-20260929T090642Z`
with a managed registry receipt and mode-0600 Item 31 CSV. It moved only
`BatteryIcon` to the exact file source; the `UpdateBatteryIcon` rule remained
enabled. Independent readback found file ownership, unchanged
`iconify:mdi:battery-70` state, exact custom metadata with file-owned
`editable:false`, matching source/installed SHA-256
`c130f3be1e04dcf05eb8920b8d9e4acebfbd8dfd33963135aa14985535ed491d`,
and the unchanged 136,507-row Item 31 prefix. No later JDBC rows had appeared
at the readback. The writer was IDLE and `BatteryChargingStatus` remained OFF.
The ownership manifest is file/provisional and the live inventory has zero
issues. The backup remains private; no OpenHAB restart, synthetic icon update
or control change was part of this cutover.

The first natural `BatteryIcon` writer change with a new Item 31 row remains
the verification gate before changing the manifest to `verified`. Do not
manufacture an icon update to close that gate.
