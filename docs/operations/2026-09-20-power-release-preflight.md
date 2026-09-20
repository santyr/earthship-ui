# Qualified power production release preflight

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
