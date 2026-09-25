# September 25 qualified-day recovery point

The September 24 qualified daily power revision (snapshot ID 5) was inserted
before a new full-database read-only snapshot began at 2026-09-25 14:53:40Z.
`scripts/verify-openhab-full-backup.py` exported one PostgreSQL snapshot and
matched 515/515 table count-and-hash fingerprints against its networkless,
one-CPU isolated restore. The private manifest reports `restore_verified` at
15:47:27Z. `energy_analytics.daily_power_snapshots` had five rows in the
matched snapshot. The 2.2 GB custom archive's SHA-256 is
`0d3901d3c47cd6044c87ea0d2898a5f748d9871acfe14a342b9767725d1b5b87`.

Private receipt:
`/home/sat/backups/earthship-energy/full-restore-c1j2gw8a/backup-manifest.json`.
The directory is mode 0700; archive and manifest are mode 0600. Independent
read-only monitor assessment found it fresh, readable, restore-verified and
hash-matching. The Git-owned `energy-backup-check.service` and installed unit
now name this manifest, while its existing timer remains enabled. The same-host
point still lacks an off-host disaster-recovery copy and therefore remains
Actionable; no role/ACL, OpenHAB restart or protected-control claim follows
from this data-only restore.

The verifier now removes its exact-owned Postgres container **and** anonymous
data volume. Independent Docker readback found no owned restore container and
no net volume increase from the verifier. A later full analytics test run
exposed ten abandoned anonymous volumes from its disposable database fixture.
All ten were created during that exact test window, unreferenced by containers
and explicitly removed; Docker volume count returned to the pre-test 819.
Both that fixture and the Earthship thermal-journal fixture now use
`docker rm --force --volumes`; one integration test for each passed with the
volume count unchanged. Existing unrelated volumes were not pruned.
