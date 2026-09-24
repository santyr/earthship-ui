# Forecast correction Item cutover — September 24, 2026

`Forecast_HighCorrection_F` and `Forecast_LowCorrection_F` are observational,
direct-published Number Items. At the live preflight both were REST-managed,
unlinked, and had persisted states 3.3 and -7.2 with JDBC IDs 596 and 597
(53 rows each). The installed producer is `forecast-intel.service`; this
cutover changed only Item ownership, not learning or forecast values.

The exact definitions are in
`openhab/file-config/items/forecast-corrections.items`. Before production
transfer, a networkless disposable OpenHAB provider matched both live Item
definitions and removed its container. A separate disconnected OpenHAB/JDBC
test persisted both synthetic states, exercised file-to-managed-to-file
rollback, preserved history on hot reload and full JVM restart, and removed
its OpenHAB container and PostgreSQL database. The focused source and
neighboring quality migration tests passed (4 tests). The live `--check`
found the same two IDs and row counts immediately before transfer.

At 16:46 MDT, the guarded `--apply` returned `file_owned_verified`. It
created a private backup under
`/home/sat/.local/state/openhab-config-migration/forecast-corrections-20260924T224609Z`,
paused only `forecast-intel.timer`, exercised actual managed rollback,
returned to the file provider, verified unchanged JDBC histories, and
restarted the timer. No synthetic value was posted to production.

Independent REST readback showed both Items `editable=false` with their
original values and labels. The ownership inventory reported zero issues
with 389 managed and 43 non-managed Items; the forecast timer was active.
Its next natural run is September 25 at 06:40 MDT. Verify both new JDBC
receipts from that run before claiming post-cutover publication; current
ownership, state, and history preservation are verified, but publication is
not yet observed.
