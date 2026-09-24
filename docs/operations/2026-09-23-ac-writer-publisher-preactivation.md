# AC writer and v4 publisher preactivation

The operator confirmed on September 23 that the home currently runs solely on inverter output, with no bypass or generator supplementation, and that this topology attestation remains valid until the operator reports a change. The checked-in AC policy's `effective_until: null` represents that open-ended attestation; it is not a substitute for source-health evidence or a guarantee against an unreported topology change. If a change is reported, stop qualifying new AC-load days under this policy until the topology and effective interval are revised.

Solar_PV `235e0c3` adds an explicit, unscheduled `energy-data ac-day` dry-run/apply command. It requires both checked-in evidence policies, a completed America/Denver day within the AC cutover and operator-attested topology, and no pending migrations before an apply. It re-reads the topology policy before a write. The live September 24 dry-run correctly refused the unfinished day before database access. No daily AC revision was written.

Solar_PV `519c2f7` adds an opt-in `energy-ui-publish --ac-evidence-policy` path. It requires the existing qualified power policy, reads bounded latest AC revisions, projects a separate v4 AC field and validates before the single OpenHAB write. The installed publisher's actual `ExecStart` lacks this flag, and the live `Energy_Analytics_JSON` remains v3 with no `acLoad` field. The source change therefore has not published AC load. The Solar_PV full suite passed 838 tests.

At approximately 16:06 MDT the independent AC Item had 828 durable rows since the 20:55:12Z cutover: 827 valid, one startup unavailable barrier, one epoch, no sequence gaps or duplicate timestamps. The strict last-hour interval reader reported 99.989% coverage. The persisted table occupied 335,872 bytes. This is one-hour continuity only, not completed-day, fault/restart, or retention qualification.

At 18:21 MDT a further read-only SQL check of `public.item0653` found 2,416
rows over 3h26m, sequence 1–2416 in one epoch, with no sequence gaps or
nonincreasing database timestamps. The JSON field reported 2,415 valid
receipts and only the original `invalid_input` startup barrier. The table and
indexes occupied 864 KiB at the earlier 2,409-row check. This extends the
natural continuity/volume observation but still does not test a full day,
physical source fault, restart, or retention behavior. No AC daily revision or
v4 publication was triggered.

At 18:22 MDT both AC streams were still being persisted: the transform-stage
`Inverter_AC_Output_Observation_JSON` table (`item0652`) had 2,431 rows and
occupied 520 KiB with its index, while the validated evidence table
(`item0653`) had 2,432 rows and occupied 872 KiB. The former is the live rule's
event input; the latter is the qualified reader's historical source. This
establishes an approximately duplicate write cadence, not authority to remove
the forensic transform-stage history. A retention/exclusion decision needs an
explicit recovery and source-provenance review before changing the file-owned
JDBC strategy.

The initial restricted credentials lacked the new-table grants. The first
exact-scope attempt was rejected before execution and confirmed to make no
partial change. The operator subsequently approved only those grants. On
September 23 at approximately 19:38 MDT, a single PostgreSQL transaction
granted SELECT on `energy_analytics.daily_ac_snapshots` to
`energy_power_reader`; SELECT and INSERT on that table, USAGE on
`energy_analytics.daily_ac_snapshots_snapshot_id_seq`, and SELECT on the exact
AC source table `public.item0653` to `energy_power_writer`. Fresh readback
found all five approved privileges true, UPDATE/DELETE on the AC table and
INSERT on the raw source table false, and zero AC daily rows. No writer,
publisher, table UPDATE/DELETE/TRUNCATE, raw-source write or hardware control
was activated. AC publication remains off until the first complete day after
September 25 06:00Z and the remaining source fault/restart/retention checks
are qualified.

At 20:22 MDT a strict, read-only AC day-reader diagnostic exposed a separate
permission gap: `energy_power_reader` can resolve Item ID 653 but its
information-schema inventory does not see `public.item0653`, and a direct
`has_table_privilege` check returned false for SELECT. The earlier approved
grant assigned that exact source-table SELECT only to the writer role. The
strict reader therefore refuses with “AC evidence persistence table missing”
before computing coverage. A separate exact SELECT grant for
`energy_power_reader` on `public.item0653` has been requested; it has not been
applied without approval. The stored AC daily table remains empty and the
live publisher remains v3 without the opt-in AC flag.

At 22:18 MDT, a new read-only production census found 5,189 `item0653`
receipts since the 20:55:12Z cutover, in one epoch with no sequence gaps:
5,188 valid and the original startup-unavailable barrier. The latest receipt
was 04:18:27Z. The `item0652` observation table occupied 928 KiB and the
`item0653` evidence table 1,776 KiB including indexes; the daily AC table
still held zero rows. This extends passive continuity evidence to roughly
7h23m, but is not a completed Denver day, fault or restart test. A fresh
readback confirmed all five approved privilege checks true, the additional
reader SELECT on `public.item0653` false, and no AC publisher activation.
