# First file-first OpenHAB migration

Verified 2026-09-20 at 17:24:06.164028 UTC (11:24 MDT).

The approved host policy in `/etc/openhab/AGENTS.md` now makes Git the intended
configuration authority, with staged provider transfers. Its former version is
preserved privately at `/tmp/openhab-policy-backup-llioVZ/AGENTS.before.md`.
Historical inventory in that document is explicitly not current runtime truth.

## Production change and checks

- Only the observational String Item `Energy_Analytics_JSON` changed provider.
  Its canonical source is `openhab/file-config/items/energy-analytics.items`,
  installed byte-for-byte at `/etc/openhab/items/energy-analytics.items` (0644).
- Source SHA256: `df044d1a295b37e282831b59184b00f31599cdb6268982ce40bfccaaa4ced2e8`.
- The existing publisher timer was paused, its service allowed to finish, and
  the managed Item removed through REST before the file was installed. Exactly
  one provider owns it: REST reports `editable:false`; managed JSONDB has no
  entry. Name, type, label, tags, groups and metadata were preserved (empty
  category normalized to null). No channel links existed.
- Persisted state restored before running the real-data publisher. JDBC mapping
  remains 609 / `item0609`. Historical row count and ordered value fingerprint
  through the original maximum timestamp matched exactly after transfer.
- All captured rule definition hashes were unchanged. The publisher timer was
  restored active; subsequent natural publication at 17:25:29 UTC succeeded
  with `earthship-energy-ui/v3`. The data-quality service also succeeded at
  17:20:29 UTC. No synthetic state, DM, actuator command or server restart.
- A temporary file-provider probe first demonstrated hot-load and unload.
  Registry absence and absence of probe JDBC mappings were checked afterward.
- The older managed-Item configuration tool now refuses file-owned resources;
  regression tests cover both initial detection and ownership drift before apply.
  Policy/source commit `c88ef8f` passed 1,539 UI/tooling tests.

Private before/after receipt: `/tmp/energy-item-file-cutover-h0sikpss`.
Private probe receipt: `/tmp/file-provider-probe-uurjo7pb`.
These temporary local receipts are not a durable off-host backup.

## Rollback and remaining gates

For an attended reversal, pause the existing publisher timer and wait for the
service to stop. Move this exact file outside the watched items directory, verify
registry absence, then restore the saved managed Item definition through REST.
Verify restored state or run the real-data publisher, confirm JDBC history and
configuration, then restore the original timer state. Never leave both providers
active or delete history to make a rollback appear clean.

Failure recovery was implemented in the cutover helper but was not exercised:
this successful migration does not prove a rollback rehearsal, full OpenHAB
restart, or clean-system restore. These remain required before protected-control
migration. Other resources retain existing ownership. Secrets, runtime userdata,
database history and learned models need separate protected backups, not raw Git
commits. Task 82 remains held.
