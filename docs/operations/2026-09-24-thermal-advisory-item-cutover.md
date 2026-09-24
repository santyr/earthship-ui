# Thermal_Advisory Item cutover — September 24, 2026

`Thermal_Advisory` is the legacy forecast-intelligence advisory display,
published by `forecast-intel.service`. It also gates that publisher's
prediction receipt and supplies the UI alert contract. It is **not** the
thermal physical model's shadow output, and moving its Item provider does
not graduate the model, enable advice from it, alter thresholds or actuate
equipment.

Read-only live preflight found the Item REST-managed, unlinked and ungrouped,
with exact state `none|No thermal action needed`, `forecast-intel` tag,
JDBC ID 576 and 48 history rows. The staged definition in
`openhab/file-config/items/thermal-advisory.items` matched its live DTO in
a disposable networkless OpenHAB test. A separate disconnected
OpenHAB/PostgreSQL rehearsal persisted a synthetic advisory state, passed
file-to-managed-to-file rollback, hot reload and full JVM restart with
unchanged history prefix, and removed its owned containers and database.
The UI alert contract's ten focused tests and four Item-migration source
tests passed. No production synthetic value was posted.

At 17:08 MDT the guarded live adapter created a private backup at
`/home/sat/.local/state/openhab-config-migration/thermal-advisory-20260924T230829Z`,
briefly paused `forecast-intel.timer`, exercised actual managed rollback,
and returned `file_owned_verified`, `jdbc_histories_preserved=true` and
`timer_active=true`. Independent REST readback found the original value,
label and tag under `editable=false`. The installed file's SHA-256 matched
the Git source; the ownership inventory had zero issues with 385 managed
and 47 non-managed Items.

The next natural `forecast-intel.service` run is September 25 06:40 MDT.
Verify its advisory publication, JDBC continuity and prediction receipt
before claiming post-cutover writer continuity. A repeated unchanged
advisory may not add a change-only JDBC row; distinguish successful
publication from a genuinely changed persisted Item value.
