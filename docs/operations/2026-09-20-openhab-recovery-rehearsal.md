# OpenHAB recovery rehearsal

Operator requested a full restore test, isolated execution and cleanup.
The database, durable OpenHAB files and integrated startup were exercised.
Production remained active with MainPID `4060018`; no production restart,
hardware command, external notification or deployment was performed.

## Verified results

- The previously verified database archive `full-restore-0lnrkogj/openhab.dump`
  was hash-checked, restored with `--create` and **without** `--no-owner` or
  `--no-privileges`. Privately captured cluster roles were restored first.
  All **510 tables** matched the original snapshot's count and four SHA256
  row-hash limb sums. Ownership/ACL restoration commands completed successfully.
- Fresh private archives captured `/etc/openhab`, durable `/var/lib/openhab`
  and `/usr/share/openhab/addons`. All **1,399 file/link entries** matched after
  extraction: 61 configuration, 1,336 userdata and two add-on entries.
  Sparse-file verification includes logical size and nonzero block contents;
  regular files use SHA256. Runtime UID/GID is deliberately remapped to9001.
- The pinned official OpenHAB5.2.1 image booted using the restored configuration
  and database. Restored authentication worked. All **429 Item definitions**,
  **35 rule definitions** and **262 links** matched live definitions under the
  compared fields. Tags, group membership and channel lists are unordered;
  rule action order is preserved. Exact archive verification separately covers
  captured private configuration and metadata beyond these REST comparisons.
- All **84 Things** loaded. The sole definition difference was the systeminfo
  Thing's generated channels: 72 additional container-storage channels and
  host-dependent descriptions/labels. None of its308 original channels was lost.
  This is an inspected environment difference, not a blanket ignored mismatch.
- JDBC registered and378 Items had restored or computed nonempty states in the
  final comparison. A separate exact check of `Energy_Analytics_JSON` (JDBC609)
  matched the backup's latest value by SHA256, proving actual history recovery
  rather than merely counting computed startup values.
- Three uninitialized rules exactly matched production's three intentionally
  disabled rules. This is not a new restore failure.

Private evidence: `/home/sat/backups/earthship-energy/runtime-recovery-1x76m17d/`.
`qualification.json` consolidates the component results; the final integrated
report is under `integrated-run-qhy2zvij/`. `state-proof-run.json` and
`state-recovery-proof.json` retain the exact-state check. Private SQL roles,
configuration, credentials, registry differences and raw logs are never Git data.
The retained runtime archives total approximately665MiB; the existing2.2GiB
database archive is referenced rather than duplicated.

## Restore issues found and resolved in the test environment

1. Nostr LMDB files are sparse, including a256GiB logical file. Ordinary tar
   expanded holes; the incomplete137GiB test copy was stopped and removed.
   `tar --sparse` preserves the durable userdata in a46MiB archive. Regressions
   verify sparse round-trip and detection of mutations inside former holes.
2. Excluded `tmp` and `cache` directories must be recreated before adding
   container aliases for `/var/lib/openhab`. Otherwise Karaf extracts add-ons
   into one location while Maven searches another. All add-ons came from the
   local582MiB KAR; the successful runtime needed no internet download.
3. Native libraries need an executable disposable temporary filesystem. The
   runtime retains non-root execution, dropped capabilities, read-only root,
   AppArmor and seccomp; no host security profile was disabled.
4. JDBC initializes using `CREATE TABLE IF NOT EXISTS`, which fails even when
   the table exists if the database is read-only. Integrated startup therefore
   used a writable **isolated clone**, leaving the integrity-check database
   unchanged. PostgreSQL's cloned data directory also requires mode0700.
5. REST can briefly appear and disappear during feature installation. An early
   standalone registry probe failed with404 after its file and database checks
   passed. The subsequent integrated probe completed with readiness retries.
   The raw standalone report is retained; its nonzero exit is not hidden or
   represented as a successful end-to-end execution.

## Reusable tooling and limits

`scripts/rehearse-openhab-recovery.py` captures private runtime archives and
rehearses the explicitly pinned database recovery point. It requires local
PostgreSQL/Docker tools, the existing private backup/config access and approved
elevation. Do not run unattended or concurrently with another rehearsal.
The final orchestration verifies immutable database contents first, then calls
`scripts/rehearse-openhab-runtime.py` on that same disposable database, avoiding
the additional physical clones used during this investigation. The underlying
components were exercised here; the final streamlined orchestration was not
rerun through another full database pass. Five focused regression tests pass.

Both runtime and database are disconnected from external networks; the integrated
runtime shares only the isolated database's network namespace. There are no
published ports, host mounts, devices or Docker socket. Writable runtime paths
are disposable tmpfs; database test volumes are removed with their owned container.
Final label checks found no remaining test containers. Failed/superseded copies,
the one-off clone helper and owned test directories were removed. The approved
official image and useful private recovery evidence remain.

This is **not whole-host or off-host disaster-recovery qualification**. The
database recovery point is from earlier on September20; runtime files and role
definitions were captured later while production remained running. It is not
one atomic global snapshot or a guarantee of zero lost updates. Rebuildable
userdata cache/tmp/logs and nested backups were excluded. External services,
host jobs, agent credentials outside OpenHAB, learned-model files outside the
captured paths, actual device connectivity and protected-control restart safety
were not qualified. Existing off-host deferral and production restart approval
requirements remain in force. No backup-monitor target was changed.
