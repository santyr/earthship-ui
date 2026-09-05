# Analytics Corrective Release Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to execute with review checkpoints. This is an attended operational release of already reviewed code, not a new implementation task.

**Goal:** Install the reviewed append-only advisory schema prerequisite and release the historical heartbeat correction without rewriting existing measurements or enabling advisory capture.

**Architecture:** Apply only migration 0002 through the existing checksum-pinned transactional migrator after verifying an affected-schema backup. Then integrate reviewed heartbeat source into the Solar_PV main checkout, which the existing daily timer imports directly. Observe the existing schedule; never invoke aggregation with --apply for a canary.

**Tech Stack:** Existing PostgreSQL 16, psycopg2, Git, pytest and systemd user units; no new dependency or service.

## Global constraints

- Operator approved all pending work, including pending integration/release subject to tests and review (events:8668). This separate release is outside the completed source tasks' no-deployment scope.
- Task 82 remains held. No OpenHAB state/configuration writes, notifications, hardware controls, threshold changes, role grants, capture activation or learned-state resets.
- Preserve everyChange and restoreOnStartup. No periodic persistence workaround.
- Only migration 0002 may be applied; 0001 must match its recorded checksum. On drift, stop before writes.
- Preserve all existing daily rows, battery totals and historical reports. No backfill, manual aggregate --apply, or recomputation command.
- Keep the additive schema on source rollback; never DROP new evidence tables or delete migration history to make old code run.
- Tests and source review are already complete: storage 240 tests on main; heartbeat 275 tests at 3b82b94 with clean whole-branch review.

## Verified preflight

Main is clean at Solar_PV 7f0b58319f896e11dc2c868ff2715481b7ef9b7a. Heartbeat branch is 3b82b94d1e94a3007543f862b048321ee9d784c6. Migration 0002 SHA-256 is b39c6ccd5446f8750401a09123b0c053d5bc940b9a111f2100af8c1da1f37675.

Production read-only inspection: applied versions [1], pending [2], both advisory tables absent. Migration CREATE/INSERT/REFERENCES privileges exist. Daily aggregation's last run was successful September 5 00:21:29 MDT; next run September 6 00:20 with up to 120 seconds delay. Its --apply path rejects any pending migration, so the already integrated 0002 must be handled before that next run.

Both old and corrected explicit --dry-run aggregates for September 4 produced identical full JSON objects; no changed paths. This sampled-day comparison supplements, not replaces, regression tests.

Backup: /home/sat/backups/earthship-energy/advisory-release-20260905-TwqUKt/energy-analytics-before.dump, 1127071 bytes, mode0600 inside0700 directory; SHA-256 d2ce3049353df66999c84f25550650eede206ca094c39a99eef998c1548e552e. Verified isolated restore of14tables, all rows and4sequence values. The temporary container had --network=none and was removed. Original archive retains ownership/ACL metadata; disposable restore omitted owners/ACLs. The affected-schema backup is local only, not full-database disaster recovery.

## Task 1: Schema prerequisite release

- [x] Verify backup by full isolated restore and exact COPY/sequence-content comparison. Manifest is beside the archive.
- [x] Review this operational scope independently before production mutation.
- [x] Recheck migration checksum, pending set and target table absence. Fingerprint existing daily_battery, daily_pv, daily_load, daily_weather, daily_source_quality, system_epochs and metric_sources rows using read-only sorted row JSON digests.
- [x] Execute only the existing migration command, with bounded lock/statement waits:

```bash
PGOPTIONS='-c statement_timeout=10000 -c lock_timeout=1000' PYTHONPATH=/home/sat/Solar_PV/analytics/src python3 -m earthship_energy.cli migrate --apply --backup-manifest /home/sat/backups/earthship-energy/advisory-release-20260905-TwqUKt/backup-manifest.json
```

- [x] Require applied_now [2], then read back checksums and pending []. Verify both new tables empty, their enabled append-only triggers, PUBLIC privileges absent, and all seven existing row fingerprints unchanged. Do not insert a synthetic production record.

## Task 2: Reviewed source integration

- [x] Recheck clean Solar_PV main and exact reviewed branch identity; fetch origin and require main/origin unchanged at7f0b583.
- [x] Merge reviewed branch without editing its code:

```bash
git -C /home/sat/Solar_PV merge --ff-only fix/heartbeat-provenance
```

- [x] On integrated main run:

```bash
cd /home/sat/Solar_PV
PYTHONPATH=/home/sat/earthship-ui/openhab/scripts:$PWD/analytics/src python3 -m pytest analytics/tests -q
```

- [x] Require275passes. Repeat September4 aggregate --dry-run and compare to pre-release output; recheck stored daily/history fingerprints, timer unchanged, no pending migrations. Push origin/main and verify exact remoteSHA.
- [x] Record that this activates reviewed source for the next normal daily run, not that tomorrow's run has already passed. Completed-window outcomes, capture and broad algorithm audit remain open.

## Execution receipt

Independent operational review found no release blockers. Immediate source/hash/idle/pending checks passed. Migrator returned applied_now[2]; subsequent read-only inspection confirmed versions[1,2], pending[], both evidence tables empty, one enabled append-only trigger each covering UPDATE/DELETE/TRUNCATE, and zero PUBLIC table privileges.

Solar_PV fast-forwarded7f0b583..3b82b94. Full integrated suite:275passed in7.32s. September4 dry-run JSON matched the retained old analytics source (1de8aa0 analytics tree verified identical to7f0b583). Main and remote refs/heads/main both3b82b94d1e94a3007543f862b048321ee9d784c6; working tree clean. Timer remains active, next September6 00:20MDT; service remains inactive with its prior successful September5 00:21:29 exit. No manual daily run was requested.

Existing sorted row-JSON MD5 fingerprints matched before migration, after migration and after source integration:

| Table | Rows | Digest |
| --- | ---: | --- |
| daily_battery | 48 | 24a37e6cf437a395c86b0921a81217b1 |
| daily_pv | 48 | e14d27043746195d7c0893c6855951fa |
| daily_load | 48 | 5240af8b6ee23e18320aaddf49b077d2 |
| daily_weather | 48 | 78fd32430e60b2183f63a075e86316d0 |
| daily_source_quality | 1008 | 9c2f2fe91c83cb69229f0f312bd31296 |
| system_epochs | 3 | 99143e4ef60b1f51a3ea468641e7ecec |
| metric_sources | 21 | ae39048540af2dd293cf6ffebd641520 |

These are equality fingerprints, not security signatures; the archive is SHA-256 pinned. Forecast snapshot capture continues its existing append-only schedule and was not stopped. No role grants, producer activation, synthetic advisory rows, physical actions or historical recomputation occurred. The scope is the prerequisite schema and heartbeat source release only.

## Rollback

On migration error, the migrator rolls back its transaction. Read back pending versions and tables before retrying; never assume a timeout means no commit. On source verification failure, stop publication and prepare an exact reviewed revert of the heartbeat commits while retaining migration0002 and new evidence. Do not reset main or restore the schema dump automatically: that could discard newer forecast history. The backup is a recovery artifact requiring an attended, scoped restore after preserving newer evidence. No rollback action changes timer ownership, household controls or model authority.
