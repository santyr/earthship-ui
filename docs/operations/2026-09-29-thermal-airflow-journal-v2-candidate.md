# Window/skylight journal vocabulary: isolated v2 candidate

The operator chose separate window and skylight states. The production
`thermal_intel.action_events` journal still permits only legacy actions,
including the ambiguous `vent`, and its exact v1 schema fingerprint is
`786e9b7bf3ca5587f08bcdcd960239a88bf887a8b31c4ea5eddcbc808c496efb`.
No household journal row or schema was changed here.

`thermal_model/airflow_migration.py` is an **explicit, default-off** candidate.
It accepts only that exact v1 schema/ACL/owner preimage, requires the actual
database owner, and changes only the `action_events_action_check` constraint
inside one PostgreSQL transaction to add `window` and `skylight`. Its exact
normalized PostgreSQL 16 postimage is
`f3e09cdd6cbd82bcd34475485bbf326bbc4789f4bcb1f4e050d9fba213378790`.
An unexpected preimage, owner, postimage or lock timeout fails closed and
rolls back; a second call on an exact v2 schema is a no-op. The release flag
remains `False`, so the migration refuses before connecting to a database.

Disposable PostgreSQL tests created a fresh exact v1 journal and runtime
role, rehearsed the constraint change and rolled it back to measure the
postimage, then proved the actual migration preserved an existing `vent` row,
accepted independently named window/skylight rows, preserved same-action
correction links, rejected a cross-action correction atomically, and passed
v2 audit. A deliberately wrong expected fingerprint restored the exact v1
schema. The migration and existing journal/history suites passed 39 tests;
the later correction test passed again. All owned test containers were removed.

The source-side as-of-origin reader now preserves its historical v1 output
shape by default. A pure, explicitly versioned v2 projection keeps window and
skylight states separate, marks `vocabulary_version: 2`, refuses a later
correction at an earlier origin, and leaves legacy `vent` missing rather than
deriving it. The database-backed v2 reader is still default-off; it refuses
before connecting until a coordinated household cutover qualifies that path.
The v1 reader rejects unexpected v2 rows instead of silently discarding them.
The migration, existing journal, schema, origin and action-history suites pass
84 tests; no production model forcing or action label changed.

This is **not ready for household application**. The installed v4 trainer and
publisher still use the v1 journal/runtime contract. After a production v2
schema change, their old exact schema-audit command would reject the journal.
Before live migration, qualify a coordinated runtime/reader upgrade and
rollback, a private full journal/ACL backup and isolated restore, exact
production owner/role preflight, and an attended maintenance window. Only
then enable the migration under specific authorization. Keep the v2
confirmation sender and ingress gated until their own genuine signed
question/reply, durable-storage and recovery checks pass. Legacy `vent` rows
must never be recoded as window or skylight observations, and neither new
state may silently feed legacy `vent_open` model forcing.
