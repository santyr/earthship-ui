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

The first prepared candidate is `Energy_Analytics_JSON`, an observational String
Item with a separate state publisher. The older managed configuration tool now
refuses `editable:false` resources rather than attempting to recreate ownership.
