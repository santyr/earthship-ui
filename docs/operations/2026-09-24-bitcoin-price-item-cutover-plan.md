# Attended Bitcoin price Item file-ownership cutover plan

Status: approved for one attended cutover on September 24. The operator
approved this exact Item/link transfer; the adapter's release gate is on.
The preflight still must pass immediately before `--apply`.

Execution receipt, 06:24 MDT: the focused suite passed 21 tests and the
immediate live preflight passed. The attended `--apply` created a private
current Item34 custom archive and JSONDB/REST snapshots, preserved the exact
1,090,946-row fixed JDBC prefix, and returned `file_provider_verified` with
a new natural Exec receipt. An independent readback found the file-owned
Item/link, unchanged two-member managed Group and matching natural receipt.
The private archive is retained. No OpenHAB restart or synthetic price write
was performed. The exact Item/link ownership entries were added to the Git
manifest; the post-cutover live inventory now reports zero issues.

## Exact scope and preflight

Transfer only the managed `BTC_USD_Price` Number Item and its empty-config
`exec:command:BTC_Price:output` link to the tested
`openhab/file-config/items/bitcoin-price.items` source. Keep the existing
`BTC_Price` Group managed, including its `Equipment` semantic metadata and
both member references. Do not alter the Exec Thing, `/etc/openhab/scripts/bitcoin.py`,
the receipt Item/link, percentage rule, database, credentials or any control.
No OpenHAB restart or synthetic price update is part of this cutover.

Run `scripts/migrate-bitcoin-price-item.py --check` immediately beforehand.
It must verify exact managed definitions, ONLINE Exec Thing, IDLE percentage
rule, receipt transform, fixed source digest and JDBC Item34 mapping/history.
At the September 24 02:57 MDT read-only checkpoint this passed with
1,090,544 rows before its two-minute exclusive cutoff; the feed continued
writing. This checkpoint is not a go-ahead for a later, drifted state.

## Attended execution and success evidence

1. Review the script and exact rollback below, then obtain specific approval
   for this production Item/link transfer. Only then flip `RELEASE_READY`,
   rerun focused tests and `--check`, commit and push the released adapter.
2. Run one attended `--apply`. Before touching OpenHAB it creates a private
   mode-0700 directory containing exact REST and JSONDB definitions, a
   PostgreSQL custom dump of `public.item0034`, an archive hash/readability
   proof, and a streaming SHA-256 of one fixed historical prefix. A separate
   actual production Item34 archive was already restored into a disconnected
   PostgreSQL clone with matching prefix; the new run still makes its own
   current backup. Stop if any backup or pre-transfer check fails.
3. Withdraw only the managed price link and Item, then install the exact
   reviewed `.items` source. Require file ownership of both resources,
   unchanged Group metadata/two members, unchanged JDBC Item34 mapping and
   exact fixed-prefix digest. Require a **new natural Exec receipt** later
   than installation whose price equals the live Item state, plus an IDLE
   percentage rule. The writer normally polls every 30 seconds; the adapter
   allows 120 seconds for this gate.
4. Read back the final state and private receipt. Do not claim source quote
   freshness from the local output receipt; this transfer only proves local
   writer recovery and historical continuity. Keep the successful private
   recovery archive until a separately approved retention decision.

## Failure and rollback boundary

If a provider, history, Group or natural-writer gate fails after mutation,
the adapter removes only its unchanged exact-source file, restores the saved
managed Item/link and verifies the fixed history prefix and Group. It retains
the private backup and failed file for diagnosis. If that guarded rollback
itself fails, stop and use the private Item34 archive/JSONDB snapshots under
an attended recovery plan; never silently restore a live database table or
erase new legitimate price rows. The expected user-visible risk is a brief
Bitcoin-card update gap during provider handoff, not a pump/battery control
change. An unqualified or failed transfer must not be presented as deployed.
