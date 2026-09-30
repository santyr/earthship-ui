# Full database restore refresh

The August 20 full-database restore point is stale. The September 20 analytics
schema rehearsal cannot replace it. The full refresh uses
`scripts/verify-openhab-full-backup.py` and the established private backup root:

```bash
python3 scripts/verify-openhab-full-backup.py --destination-root /home/sat/backups/earthship-energy
```

Requires the existing PostgreSQL driver/config parser, local PostgreSQL utilities
and local `postgres:16` Docker image. Private JSON receipts are written by the
checked-in receipt helper; no session-local `apply_patch` executable is required.
Do not run a second copy while an existing rehearsal is active.

## Scope and controls

- Production access is a read-only repeatable-read transaction. The full custom
  dump and per-table fingerprints share one exported snapshot. All non-system
  tables are included, not only energy analytics; the initial inventory has 510
  tables across public, energy analytics, thermal and another application schema.
- Artifacts are private in a new directory (0700, files 0600). No database values,
  credentials or raw command errors are printed. Existing backups are retained.
- Source fingerprint queries have a five-minute statement timeout, two-second
  lock timeout, 16 MB work memory and no parallel workers. The dump is nice'd.
  At least 80 GiB free disk is required. Long-lived snapshots can delay vacuum
  cleanup; monitor the actual process and do not leave an abandoned reader alive.
- Restore runs in an owned, networkless PostgreSQL container capped at one CPU
  and 1 GiB memory, with no swap allowance or published ports. Archive input is
  streamed from disk. Only that identity- and label-verified container is removed.
- Table inventory, row count and four sums of SHA256 row-hash limbs are compared
  between source and restore. The accumulator is constant size, order-independent
  and duplicate-sensitive. This is a multiset integrity check, not a canonical
  cryptographic digest of the table. The archive has its own SHA256 digest.
- A `restore_verified` manifest is written only after restore succeeds and every
  table matches. A partial archive or source fingerprint file is not success.

## Explicit limits

This is a full **database data** rehearsal, using `--no-owner --no-privileges`.
It does not validate role/ACL restoration, external configuration, systemd jobs,
OpenHAB startup, protected-control recovery or off-host disaster recovery.
The backup-check reference must not change before successful readback. Its
off-host limitation stays Actionable under the operator's existing deferral.

The first execution completed at 2026-09-20T18:59:53.335249Z under the private
directory `/home/sat/backups/earthship-energy/full-restore-0lnrkogj`. All 510
tables matched their source-snapshot fingerprints; the owned container was
removed and the process exited zero. Independent assessment with the deployed
backup monitor confirmed fresh, readable, restore-verified and hash-matching.
The archive SHA256 is
`6e6fba4f7608500a0964f453b57fb9a20b1f39fb857ed66563139f8b437d5e31`.
Directory mode is 0700; manifest/archive modes are 0600. Off-host and disaster
recovery remain false, with Actionable severity. The scheduled monitor now uses
this manifest: Solar_PV `6f5d914`, 27 monitor/unit tests passed, exact unit readback
verified. Private rollback receipt: `/tmp/backup-monitor-adoption-fanm1yx4`.
Only the manifest path changed. Timer remains active, next randomized run
September 27 at 03:33:08 MDT. No manual job or DM was triggered.
Unit tests cover SQL identifier safety and bounded accumulator shape;
read-only PostgreSQL VALUES tests verify order invariance, duplicate sensitivity
and value sensitivity.

## September 30 coverage check and verified refresh

Before this refresh, the installed weekly backup monitor selected the September 27 full-database
restore under `/home/sat/backups/earthship-energy/full-restore-e66yrzn3/`, not
the August 20 archive. A fresh, non-notifying assessment on September 30
confirmed archive readability, matching SHA256, dated restore verification
within the seven-day limit, and private directory/archive modes 0700/0600.
The source snapshot began September 27 at 20:17:24Z and its 515-table restore
finished at 21:11:04Z. Same-host-only storage remains Actionable; this is not
off-host disaster recovery.

Read-only production metadata now reports 522 tables, with no removed tables
and seven additions absent from that snapshot: `public.item0655` through
`public.item0661`. Freshness of the older archive does not imply coverage of
those newer evidence histories or rows appended since its snapshot.

The authorized online snapshot under
`/home/sat/backups/earthship-energy/full-restore-volep77n/` started at
11:36:48.574176Z and passed the isolated restore at 12:31:17.290029Z:
**all 522 table fingerprints match**. Archive SHA256:
`031bb485f8a7d6f386ce3e146cf7793c84e95b3dfa934f710b8d7010ba8de065`.
Archive size is 2,344,864,758 bytes. Independent assessment confirms freshness,
readability, restore status, hash integrity and modes 0700/0600; Docker readback
confirms the identity-verified test container is absent after its guarded
`--volumes` removal. Existing real backups remain retained.

Only after that assessment, the existing user-level monitor's manifest path
was changed to this point. Thirty monitor/unit regressions pass. Exact loaded
unit/source readback passed; the unchanged weekly timer remains active, next
randomized run October 4 at 03:33:18 MDT. No manual monitor job or DM was
triggered. Private unit rollback:
`/home/sat/.local/state/earthship-energy/backup-monitor-adoption-4cpy3rla/`.
The rehearsal was networkless, one CPU, one GiB and no additional swap. No
OpenHAB stop, control change or off-host copy occurred. Same-host-only remains
Actionable, and role/ACL, external configuration and whole-host/control recovery
are not newly qualified. Publications and rows generated after the source
snapshot are not part of this point.
