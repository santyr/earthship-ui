# Bitcoin display Item migration preflight

Read-only inventory identifies `BTC_Price_24h_PercentChange` as the next small
observational migration candidate. Its staged definition is in
`openhab/file-config/drafts/bitcoin-change.items`; it is NOT installed and the
managed provider remains authoritative. The draft preserves the unusual literal
quotes in the existing label; visual cleanup is not part of ownership transfer.

Verified live contract:

- Number Item, group `BTC_Price`, no tags, metadata or channel links.
- PostgreSQL Item139 / `public.item0139` holds the same stable identity.
- Sole rule reference in the registry is `hex_btc_24h_change`, currently IDLE;
  it is triggered by `BTC_USD_Price` updates and writes the calculated percentage.
- The underlying price Item34 is linked to `exec:command:BTC_Price:output`.
  The ONLINE Exec Thing invokes `/etc/openhab/scripts/bitcoin.py` every30seconds
  with timeout15 and autorun=false. Do not migrate or pause that acquisition
  Thing as an incidental part of this calculated-Item transfer.
- `/home/sat/bin/bitcoin.py` is a distinct older file, not the configured Exec
  command path. This does not establish that it has no other consumers or settle
  the outstanding credential externalization task. Neither file was printed.

Before cutover: qualify the draft's parsed label/group, capture exact Item/rule
definitions and persisted state in a private receipt, briefly pause only the
calculation rule, and verify it is idle/disabled. Remove the managed definition
before installing the file; require exact state restoration before re-enabling
the writer. Preserve the Item139 mapping and preexisting history prefix. On
failure remove only the new exact-owned file and restore the captured managed
definition. Then verify natural calculation, all other rule definitions, logs,
and actual file-to-managed-to-file rollback. No manual runnow, price injection,
upstream script edit or full OpenHAB restart is needed or authorized by this plan.

Only after successful cutover should the draft move to canonical `items/` and
the ownership manifest declare this Item file-owned. It is not yet migrated.
