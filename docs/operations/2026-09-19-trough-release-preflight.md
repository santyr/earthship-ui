# Completed-night scoring: refreshed release preflight

Status: backup/restore/migration rehearsal verified; **production not migrated
or activated**. Live learning is preapproved; this is a verification checkpoint,
not a renewed approval gate. Task82 and protected-control boundaries remain.

## Compatible source

Earthship `feat/completed-trough-integration`3015eda incorporates current main
5f44e10. AST comparison proves score_hourly_targets exactly matches deployed
qualified-learning source and the runtime wrapper is present in main(). Full
script suite:1014passed,42subtests,1expected separately exercised PostgreSQL skip,
138.86seconds. The delta from main remains completed-trough adapter/integration,
its tests and release documentation—not a replacement of hourly learning.

Solar `feat/advisory-trough-assessment`9ab7461 incorporates current main008f856,
including the live-health correction receipt.523analytics tests pass in22.30s.
Neither branch was merged into production main during this preflight.

Installed forecast SHA remains
39ce12e0a600aaef71cb94904b41884d1faf5367bf48ef3019713e8088b85743.
The old September10 plan's6a3d176... precondition is superseded; its unrelated
advisory code is still not deployed. Preserve the current hourly-learning
drop-in and its2026-09-20T00:30:09Z cutover throughout the next release.

## Production preflight

- Analytics migration ledger is[1,2], both matching staged source checksums.
- Atomic BMS source mapping is613 (`BMS_SOC_Evidence_JSON`).
- `discover_4_module_2026` bank epoch exists.
- Advisory decisions/results each have zero rows; writer/assessor role names
  are absent. No synthetic production origin was inserted.
- Existing forecast and energy timers remained active with original schedules.
  No production job was forced or interrupted.

## Verified private snapshot

Read-only repeatable-read snapshot exported to pg_dump. Per-table row counts and
canonical JSON row fingerprints were calculated within that same snapshot,
avoiding a moving-baseline comparison while normal services continue.

Private directory: `/tmp/trough-activation-backup-x4d0_p5m` (sat,0700).
Archive: `energy_analytics.dump` (sat,0600),4,909,873bytes.
Manifest: `backup-manifest.json` (sat,0600),status restore_verified.
Archive SHA256:
`5cc60bf19e666c8e82e4f7d3c6190dcde37638bb26d851ab607dfb95013bc60f`.
Verified at2026-09-20T00:39:21.776604Z.

The archive restored all16energy_analytics tables into a disposable postgres16
container with no network or exposed ports. Every table count/fingerprint
matched, including363,630forecast snapshot rows. The isolated database then
applied exact migrations3/4 transactionally and read back ledger[1,2,3,4]. All
preexisting data table fingerprints remained identical; new outcome/selection
tables were empty. No fake outcome was necessary to demonstrate the migration.
The owned temporary container was removed after verification. Private backup
and manifest remain available; no production data was deleted. This is a
same-host scoped recovery artifact, not offhost disaster recovery.

Reproduction tool: `scripts/verify-energy-schema-backup.py`. It checks existing
migration checksums, refuses unexpected ledger versions, produces a new private
directory, validates exact owned-container identity before removal, and never
applies production SQL or modifies schedules. Migration directory argument is
the staged Solar analytics/sql/migrations path. Generated credentials are not
printed, persisted in the manifest, or passed in command arguments.

## Next live cutover

Use the reconciled version of the September10 attended release plan, updating
the installed-source hash above and all date-dependent observations. Reverify
current source/role/ledger/bank/timer state, retain private script/config/model
backups and this verified archive, briefly pause existing affected timers and
wait for active jobs, then apply only3/4 with bounded locks/statements. Merge
compatible Solar source while paused, provision separate least-privilege
writer/assessor roles, install capture/assessment helpers and the compatible
forecast source, preserve hourly settings, set a new assessment cutover, and
initialize only Forecast_Trough_Error_7d to UNDEF. Restore prior timer states.
No full forecast replay, test DM, learned-state reset, threshold change, or
manual hardware command is part of this release.

Do not claim natural qualification from this rehearsal. Capture must first
record an actual scheduled forecast and accepted publication. Its entire
20:00–11:00 target must elapse before assessment, with the unchanged90percent
qualified SoC coverage gate. Rewards remain observational, not causal or bandit
eligible. A compatible scoring-disabled rollback must be ready before cutover;
restoring the original premature scorer is not safe rollback.
