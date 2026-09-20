# Full database restore refresh

The August 20 full-database restore point is stale. The September 20 analytics
schema rehearsal cannot replace it. The full refresh uses
`scripts/verify-openhab-full-backup.py` and the established private backup root:

```bash
python3 scripts/verify-openhab-full-backup.py --destination-root /home/sat/backups/earthship-energy
```

Requires the existing PostgreSQL driver/config parser, local PostgreSQL utilities,
the local `postgres:16` Docker image and `apply_patch` on PATH. Do not run a second
copy while an existing rehearsal is active.

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
recovery remain false, with Actionable severity. The scheduled monitor still
needs its reference changed from the old archive; this assessment sent no DM.
Unit tests cover SQL identifier safety and bounded accumulator shape;
read-only PostgreSQL VALUES tests verify order invariance, duplicate sensitivity
and value sensitivity.
