# Tomorrow forecast Item cutover — September 24, 2026

`Forecast_Tomorrow_High`, `Forecast_Tomorrow_Low`, and
`Forecast_Tomorrow_PrecipProb` are direct-published, unlinked Number Items
written by `forecast-intel.service`. The high and low are also required for
the publisher's prediction receipt; this transfer changed Item ownership,
not their values, forecast calculation, or receipt gate.

The live read-only preflight found all three REST-managed with states 72.7,
43.9 and 39.0, and JDBC IDs 577, 578 and 579 with 74, 73 and 71 rows.
The exact file definitions are in
`openhab/file-config/items/forecast-tomorrow.items`. A disposable networkless
OpenHAB provider matched all three live definitions, then removed its
container. A separate disconnected OpenHAB/PostgreSQL rehearsal persisted
three synthetic states, passed file-to-managed-to-file rollback, preserved
history through hot reload and full JVM restart, and removed both containers
and the database. No production values were written by those tests.

At 16:53 MDT, the guarded live `--apply` created a private backup under
`/home/sat/.local/state/openhab-config-migration/forecast-tomorrow-20260924T225317Z`,
paused only `forecast-intel.timer`, exercised actual managed rollback, and
returned `file_owned_verified` with all three JDBC histories unchanged and
the timer active. No synthetic production value was posted.

Independent REST readback showed all three `editable=false` with their
original states, labels and `forecast-intel` tags. The ownership inventory
reported zero issues, with 386 managed and 46 non-managed Items. The next
natural forecast run is September 25 at 06:40 MDT; its new JDBC receipts
and prediction receipt remain the post-cutover publication gate.
