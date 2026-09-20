# Qualified power production release preflight

## Production source/schema deployed

Solar_PV main is now `d4151a1`. Qualified writes verify all21source references
and3bank epochs read-only instead of seeding/updating them; production read-only
comparison passed. The opt-in monitor reads selected qualified snapshots rather
than legacy daily tables and distinguishes first-day-not-due, missing materialized
days and present partial evidence. All700analytics tests pass.

The attended source/schema cutover is complete. Existing six energy timers were
captured and paused, all associated jobs verified inactive, exact rehearsed
migration5 applied transactionally with2-second lock/30-second statement limits,
and the clean production checkout fast-forwarded from19ff30a to d4151a1. Ledger
1–5/checksums match, the new table has zero rows, service definitions are
unchanged, and all original timer states were restored. Private before/after
receipt: `/tmp/power-production-schema-qxe7f3pn`.

Restricted-role provisioning and activation of the writer/publisher/monitor
policy options are still pending. Existing publisher remains v2; no synthetic
daily row or hardware action was performed. This supersedes the earlier
source/schema-pending status below, while retaining the rehearsal evidence.

Operator directed production deployment as soon as it is sensible, without
waiting for unrelated cleanup. Collection and UI v3 reader are live; accounting
writer/publisher activation remains pending the checks below.

## Completed-day storage

Solar_PV `6fcd97f`, pushed on `feat/qualified-power-accounting`, adds exact
America/Denver day bounds, including23/25-hour DST days. The writer refuses
unfinished days. Undeployed migration0005 enforces this independently on INSERT
and assigns computed_at from the database clock, ignoring caller-supplied time.
Readers reject a revision computed before its represented day completed.
All693analytics tests pass, including actual PostgreSQL direct-SQL bypass and DST
tests. Only synthetic fixtures moved to August; live cutover remains unchanged.

## Restore and migration rehearsal verified

Private snapshot archive and manifest:
`/tmp/power-activation-backup-8n11l8uz/energy_analytics.dump` and
`backup-manifest.json`. Archive SHA256:
`5f8837e75666e1de13eeb2dc224a079892e152b0e89f50e496f2fdc8cf356cf5`.
The production ledger was exactly1–4 with matching source checksums. All18
analytics table counts/fingerprints matched after restore into an owned,
network-isolated PostgreSQL16container. Exact migration5 then applied; ledger
became1–5, existing data fingerprints remained unchanged, and the new power
snapshot table was empty. The temporary container was removed; backup retained.
No production SQL mutation, synthetic daily row, grant or scheduler change.

The first two attempts failed because the old verifier concatenated full JSON
rows and exceeded the disposable container's768MiB memory limit. Kernel cgroup
OOM records and private PostgreSQL stderr confirmed the cause. The verifier now
hashes canonical JSON rows to fixed-size SHA256 values, sorts/aggregates those,
and compares count plus aggregate digest. Duplicates remain significant. The
manifest identifies `sorted_row_sha256_md5_v2`; comparisons are within the same
exported production snapshot, not against an older changing database. Production
forecast history had375,006rows/189MiB during diagnosis. Failed containers were
removed and private archives retained; no production data was affected.

Reproduce: `scripts/verify-energy-schema-backup.py MIGRATION_DIRECTORY --power`.
The original no-flag migrations3/4 rehearsal mode remains available. Each mode
requires an exact starting ledger and source checksums. Error details remain in
private files rather than exposing database content in conversational errors.

## Immediate release dependencies

Update: dependencies1and2below are implemented and tested in d4151a1; the
source/schema portion of3is deployed as recorded above. Remaining immediate
work is restricted roles, policy flags, and live publisher/monitor verification.

1. The aggregate CLI still calls `seed_reference_data` before qualified writes.
   Replace that with read-only reference verification for the qualified path;
   do not grant a snapshot writer permission to rewrite bank/source definitions.
2. `read_quality_state` still joins legacy daily tables. Route its qualified
   mode to selected qualified evidence so activation cannot create false stale
   analytics notifications. Preserve actual missing/partial-data distinctions.
3. Provision and verify restricted reader/writer roles, pause affected existing
   jobs for the attended migration/source cutover, preserve exact timer state,
   enable explicit policy options, and verify live readback. Do not create new
   competing schedules or force forecasts/DMs/hardware actions.

First naturally materialized qualified day can appear after local midnight;
September20 has only post-cutover coverage and must remain visibly partial.
The full-day qualification gate and independent AC-load acquisition are not
proven by this preflight. File-first migration remains ordered after accounting.
