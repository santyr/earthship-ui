# Bitcoin display Item migration preflight

## Completed after operator approval, September 20 14:58 MDT

The operator approved label normalization. The live file-owned Item now has
label `BTC 24h Change` and display pattern `%.2f %%`, preserving its original
name, group, Number type, absence of links and JDBC139/item0139 identity.
Canonical source: `openhab/file-config/items/bitcoin-change.items` (the obsolete
draft was removed). Installed/source SHA256 both match:
`729a3e183266a42e641f09417990be445536a7c8d888b45c7f1e91cee1fd5ada`.

The attended transfer verified persisted numeric state, rehearsed rollback to
the original managed definition and back to the normalized file provider,
and verified the unchanged historical prefix, other rule definitions and links.
Only the calculation rule was paused; it returned IDLE/NONE. Natural updates
at14:58:55 and14:59:25 confirm normal calculation resumed. No feed/pump operation,
synthetic Item update or full OpenHAB restart was used. Six guard tests pass.
One private rollback/evidence record is retained at
`/tmp/bitcoin-item-transfer-4vw4m5m3` (0700 directory,0600 files,264KiB).
The earlier sections below are historical attempts, superseded by this receipt.
At the operator's cleanup request, the four obsolete failed-attempt directories
were removed after validating their ownership/Item identity and the retained
successful rollback record. Historical paths below no longer designate backups.

The approved [official OpenHAB Docker image](https://www.openhab.org/docs/installation/docker)
`openhab/openhab:5.2.1-debian` is downloaded,825924248bytes. Repository digest:
`sha256:bfd4a60e90da18cf917a9004bbc22354fc818825f3c6f0351e471a2e938d6c3c`.
Both Java and `/bin/sh` entrypoint tests returned `operation not permitted` under
the network-none/capability-dropped isolation settings. This is not a successful
restore rehearsal, and the exact restriction is not yet attributed. No host
security setting was relaxed. All disposable image test containers were removed;
the requested image is retained for subsequent restore work.

## Historical preflight

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

## Attempt and verified rollback

The installed 5.2.1 Item parser accepts the draft and preserves its model label,
but the live file provider interprets the embedded bracketed formatting and
registers a different label (`"BTC 24h Change`). Exact definition verification
therefore rejected the transfer. The original managed definition and persisted
numeric value were restored, the new file removed, and the writer returned IDLE.
Final recovery verified; receipt `/tmp/bitcoin-item-transfer-0dcuay6v`.
No price-feed link, Thing, hardware control or historical rows were deleted.

The script now refuses execution until this representation issue is resolved.
Earlier pre-delete checks also established that disabled rules report
UNINITIALIZED/DISABLED, and numeric JDBC restoration must compare exact decimal
values rather than text formatting. Missing and empty icon categories are
equivalent; meaningful label differences are not silently accepted.
Next step is explicitly normalizing the malformed managed label and its display
format, or retaining a reproducible managed exception—not bypassing the check.
