# Git-owned, file-first openHAB configuration

Operator-approved2026-09-20. This supersedes the former REST-managed-only policy,
not the safety boundaries. `/etc/openhab/AGENTS.md` carries the host-side policy.
`ownership.json` is the explicit migration inventory; resources absent from it
retain their existing provider until inventoried and deliberately migrated.

Use exactly one provider per resource. Preserve Item names, Thing/channel IDs,
rule IDs where supported, links, metadata, groups, persistence mappings, state
semantics and bounded control ownership. No opportunistic renaming or cleanup.

Text Items use openHAB's supported `.items` format:
[official stable Item configuration](https://www.openhab.org/docs/configuration/items.html).
Canonical source files live here; deploy only their declared destinations.
Preparing a source file does not transfer runtime ownership. Existing managed
resources remain managed until a verified, receipt-backed cutover removes that
provider and loads the file definition. Never create overlapping definitions.
`items/openmeteo-current-aqi.items` is now installed as the sole provider for
`Current_US_AQI` and its OpenMeteo channel link. Isolated provider/link,
state/JDBC and full-restart checks passed before the attended cutover; live
provider/state and historical-prefix readback passed afterward. The private
rollback snapshot and completed natural-writer check are recorded in
`docs/operations/2026-09-23-openmeteo-aqi-item-cutover.md`. The source file's
pre-cutover warning remains a guard against installing it alongside a managed
provider on another host.
`items/openmeteo-forecast-aqi.items` is now the sole file provider for
`Forecast_AQI` and its hourly OpenMeteo channel link. Networkless provider,
managed-rollback and exact `REFRESH`-state/JDBC recovery checks passed before
the attended one-Item/one-link transfer. The live Item and link are noneditable,
the special `REFRESH` state recovered, and the two older JDBC rows retained Item
ID 582. The next natural 48-value binding series after transfer is still a
separate verification gate; see
`docs/operations/2026-09-23-openmeteo-forecast-aqi-item-cutover.md`.
Three observational forecast JSON Items now share
`items/forecast-json.items`; their isolated provider/JDBC/full-restart checks,
live managed rollback and return, state preservation and unchanged history are
recorded in `docs/operations/2026-09-23-forecast-json-item-cutover.md`.
Their first natural post-transfer publisher run succeeded at 15:17 MDT with
exact live Item/JDBC state matches under preserved identities; see the cutover
receipt.
The additive observational `Forecast_Prediction_Receipt_JSON` is file-owned
in `items/forecast-prediction-receipt.items`. Its dated values prevent unchanged
once-daily prediction Items from being mistaken for today's forecast. The
first natural producer write remains a separate runtime verification gate.
`items/inverter-ac-output-observation.items` is an additional file-owned,
read-only link to the existing inverter AC-power channel. Its canonical JS
transform is `openhab/transform/inverter_ac_output_observation.js`. This
observation is active for provenance qualification only; it is not a load
accounting source. The bounded live binding event, JDBC readback and
withdrawal/restoration trial are recorded in
`docs/operations/2026-09-20-ac-load-qualification.md`.

## Staged migration and rollback

1. Inspect exact live configuration, metadata, links, groups, consumers and history
   mapping. Save private before-state and current Git/source hashes.
2. Qualify syntax/provider hot reload with an owned observational probe, removed
   afterwards. No hardware commands or fabricated telemetry for validation.
3. Pause only the affected publisher/owner, allow active work to finish, remove
   the old provider, deploy the tracked file and verify one noneditable provider.
4. Verify exact configuration and real state recovery/publication, unchanged
   history mapping and protected definitions. Restore original schedule state.
5. Record ownership only after readback. On failure, remove the owned file from
   the watched tree before restoring the saved managed object; retain evidence.

Observation-only resources go first. Protected pump/battery/control migrations
require restore/restart/rollback qualification and preserved fail-closed behavior;
do not infer authority to actuate hardware or restart all of openHAB from this
configuration policy. Full service restart still requires explicit approval.

Managed-only exceptions need reproducible secret-free exports and restore steps.
Git is not a complete system backup: retain private/encrypted credentials,
JSONDB/userdata, PostgreSQL history and learned artifacts separately. A clean
restore rehearsal remains required before declaring the whole migration complete.
Do not commit raw tokens, passwords, private keys, runtime state or telemetry.

The first migrated resource is `Energy_Analytics_JSON`, an observational String
Item with a separate state publisher. Its file ownership, persisted-state restore,
unchanged JDBC mapping/history and fresh publication were verified 2026-09-20.
See `docs/operations/2026-09-20-file-first-initial-migration.md` in the repository.
The older managed configuration tool now
refuses `editable:false` resources rather than attempting to recreate ownership.
Its actual provider rollback and return were subsequently rehearsed successfully;
see `docs/operations/2026-09-20-item-provider-rollback.md`. This is specific to the
unlinked observational analytics Item, not general protected-control recovery.

`Thermal_Model_JSON` is also file-owned after isolated OpenHAB/JDBC provider,
rollback, hot-reload and full-restart rehearsal and an attended live provider
round trip. Its Item name, shadow-only publisher, restored state and JDBC identity
610/history prefix were preserved. The first natural post-transfer publication
matched live Item state, JDBC row 231 and its private forcing capture; see
`docs/operations/2026-09-23-thermal-item-file-cutover.md`.

## Read-only inventory

Run `python3 openhab/scripts/config_inventory.py` from the repository root.
It emits a deterministic registry graph (apart from capture timestamps), without
state values, labels, configuration values or script bodies. Exit status 1 means
an unresolved dependency, duplicate identity or ownership discrepancy was found;
transport/format errors also fail rather than returning a partial success.
Use `--summary` for compact counts/issues rather than the full registry graph.
`--extended` additionally inventories installed add-on identities/versions,
registered transformation identities/configuration key names and UI page
identities/components/configuration key names. It excludes UI props/slots,
script bodies, labels and configuration values. Any failed endpoint aborts the
command instead of presenting partial success. These extra surfaces are
descriptive inventory, not verified ownership, dependency analysis or restorable
exports. Filesystem-only scripts, external services and private backups still
require separate inventory.
File/non-managed links also require explicit ownership declarations, using
`kind: link` and `id: <itemName> -> <channelUID>`. The Bitcoin receipt's verified
file-owned link is declared; missing declarations, provider drift and absent
declared links now fail the graph check.
`editable:false` is reported as non-managed, not assumed to mean file-owned.
Only the separately verified manifest declares file ownership.

This is not a restore export, an atomic snapshot, a complete installation backup,
or a safety classifier. Rule dependencies embedded in executable bodies, metadata
values, link profiles, persistence strategies, UI pages, installed add-ons,
external services and private configuration require separate review. Do not use
an empty issue list as permission to migrate a resource or claim restart safety.
See `docs/operations/2026-09-20-file-first-inventory.md` for the initial scope.

## Registered transformation recovery snapshot

`transform-source-archive.json` preserves all 15 registered file transformations
read back on September 20, 2026. Each entry contains its exact UTF-8 source,
destination, registry type and SHA256. JSON encoding deliberately preserves
missing final newlines in `astro.map~` and `temp_icons.scale`. Every archived
body matched both the live registry's function and its installed file; each
decoded content hash and byte-for-byte filesystem comparison passed.

This is an exact recovery snapshot, not a bulk deployment list, active ownership
transfer or permission to restore obsolete behavior. Existing tracked transforms
under `openhab/transform/` remain their canonical maintained sources. In
particular, `voltage_to_soc_fine.js` is legacy voltage-derived SoC logic: archiving
it does not make it an authority for the Discover lithium bank. `astro.map~` is
an editor-backup artifact that happens to be registered; preserve that fact
without treating it as an approved new transform. No live files were changed.

`openhab/transform/astro.map` is now the canonical source for the existing
`/etc/openhab/transform/astro.map`. Its initial Git version matched the live
file byte-for-byte (SHA-256
`25f76f802ab403d97bcf4608ffce41529455a1de79a7964fd805ba7d8f8dc7ad`)
on September 23. No live reload or overwrite was needed. It supplies the
Sun/Moon Astro MAP-profile links, including all eight moon phases and the
explicit night icon. The similarly named `astro.map~` is not an approved
deployment target.
`items/astro-icons.items` is installed as the sole provider for
`SunPhaseIcon`, `MoonPhaseicon` and their Astro MAP-profile channel links.
The September 23 attended hot-load transfer preserved names, categories,
Sun/Moon group memberships, states, JDBC identities 90/60 and all existing
history rows. It did not restart the production service. The first natural
post-transfer Astro update remains a separate verification gate, especially
for the infrequently changing Moon phase Item; see the
[cutover receipt](../../docs/operations/2026-09-23-astro-icon-item-cutover.md).
The networkless, disposable `scripts/qualify-astro-icon-provider.py` rehearsal
passed exact file Item/link readback on first boot and full restart, then
file withdrawal and managed Item/link rollback. It removed its owned
container; it did not write to production or establish natural-update/JDBC
recovery.

Recovery must select an explicitly reviewed entry, verify its stored content
hash and destination, preserve a private current-file backup, and verify the
installed registry after provider hot reload. Check current canonical sources
before using this dated snapshot. This archive excludes credentials, unregistered
files, add-on binaries and external scripts; it is not a complete OpenHAB backup.

## JDBC persistence source (deployed September 23)

`persistence/jdbc.persist` reproduces the former managed JDBC strategy and is
installed at `/etc/openhab/persistence/jdbc.persist`. The private transfer
receipt is under `/home/sat/.local/state/earthship-ui/persistence-transfer/`;
the exact live provider readback is `editable:false`.
The September 23 AC evidence exclusion added `Inverter_AC_Evidence_JSON` to
the restore-only exceptions. Its file-owned Item is now installed from
`items/inverter-ac-evidence.items`, and the separate observational managed
rule `hex_inverter_ac_evidence` is enabled after a disabled create/readback
stage. The create-only resource descriptor retains `enabled:false` as its
safe initial installation state, not a description of current runtime state.
Its isolated
explicit-write/restart and bounded live hot-reload checks are in
`docs/operations/2026-09-23-ac-evidence-jdbc-exclusion.md`.
`python3 openhab/scripts/persistence_source.py` reads only the
strategy endpoint and renders it; unsupported fields, filters, aliases or custom
strategies are refused rather than omitted. It never reads connection settings.
Do not bulk-copy this directory into `/etc/openhab`. The ownership manifest
records this exact provider transfer and the inventory checks for provider drift.

Preserve the power observer's explicit immutable JDBC writes, its automatic
write exclusion and restore strategy. Preserve existing forecast behavior during
migration, including the existing `forecast, everyChange` combination. The
prepared `items/forecast-group.items` is **not installed**: in a disconnected
OpenHAB/PostgreSQL rehearsal, `gForecast*` failed to persist 48/7/7 synthetic
forecast series while the Group provider was absent, even though its ten
file-owned member references remained visible. Series before and after the
gap persisted and the missing gap series did not backfill. Do not hot-transfer
this Group; the stopped-service alternative still requires an attended live
restart decision. See the [gap receipt](../../docs/operations/2026-09-23-forecast-group-hot-jdbc-gap.md).
Preserve the existing managed Group until that safe transfer is qualified. The
[official persistence documentation](https://www.openhab.org/docs/configuration/persistence)
discourages that combination; reviewing it is separate from reproducing current
behavior. The transfer passed isolated syntax/load, strategy, rollback, restart,
forecast-series and power-writer qualification, then live exact strategy and
history readback. Its provider-free interval remains unqualified for natural
sensor coverage. Separately,
`python3 scripts/check-persistence-parser.py` has passed with the installed
OpenHAB 5.2.1 parser in a bounded, offline JVM. It verifies syntax, selector types
and strategy tokens; malformed syntax was rejected. Whole-host restart/restore
and protected-control behavior are not proven by this provider transfer.
The harness uses installed jars, never the running OpenHAB process or REST writes.

See `docs/operations/2026-09-20-persistence-provider-qualification.md` for the
isolated and live receipts. Continue observing the natural forecast publisher
and independent power writer; do not fill or silently score the collection gap.
