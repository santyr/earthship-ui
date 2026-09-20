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

Recovery must select an explicitly reviewed entry, verify its stored content
hash and destination, preserve a private current-file backup, and verify the
installed registry after provider hot reload. Check current canonical sources
before using this dated snapshot. This archive excludes credentials, unregistered
files, add-on binaries and external scripts; it is not a complete OpenHAB backup.

## Prepared persistence source (not deployed)

`persistence/jdbc.persist` reproduces the live September 20 managed JDBC strategy
configuration. `python3 openhab/scripts/persistence_source.py` reads only the
strategy endpoint and renders it; unsupported fields, filters, aliases or custom
strategies are refused rather than omitted. It never reads connection settings.
The checked-in file is preparation, not a provider transfer: do not bulk-copy this
directory into `/etc/openhab`. The ownership manifest still records only the
verified Item transfer.

Preserve the power observer's explicit immutable JDBC writes, its automatic
write exclusion and restore strategy. Preserve existing forecast behavior during
migration, including the existing `forecast, everyChange` combination. The
[official persistence documentation](https://www.openhab.org/docs/configuration/persistence)
discourages that combination; reviewing it is separate from reproducing current
behavior. JDBC provider cutover needs syntax/load qualification, exact strategy
readback, rollback and real acquisition/persistence verification. No live
persistence change is claimed by renderer unit tests. Separately,
`python3 scripts/check-persistence-parser.py` has passed with the installed
OpenHAB 5.2.1 parser in a bounded, offline JVM. It verifies syntax, selector types
and strategy tokens; malformed syntax was rejected. Runtime built-in strategy
resolution, provider transfer and restore/rollback still need live qualification.
The harness uses installed jars, never the running OpenHAB process or REST writes.

The exact prepared JDBC strategy DTO has subsequently passed actual file-provider
readback in a disconnected disposable OpenHAB5.2.1 instance. See
`docs/operations/2026-09-20-persistence-provider-qualification.md`. Production
remains managed. Actual JDBC write/restore behavior, provider rollback and
collection-gap handling still require qualification before production cutover.
