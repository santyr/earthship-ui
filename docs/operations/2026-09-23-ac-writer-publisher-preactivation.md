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

The real restricted credentials lack the new-table grants. Read-only inspection showed `energy_power_reader` has no SELECT on `energy_analytics.daily_ac_snapshots`; `energy_power_writer` has no SELECT/INSERT on that table, no USAGE on its identity sequence, and no SELECT on exact AC source table `public.item0653`. The existing writer does have SELECT on `Power_Evidence_JSON` (`public.item0648`) and `public.items`. An attempted exact-scope production grant was rejected by the approval gate before command execution. A fresh readback confirmed all five missing privileges remain false; there was no partial grant or workaround.

The proposed least-privilege additions are: SELECT on `energy_analytics.daily_ac_snapshots` for `energy_power_reader`; SELECT and INSERT on that table, USAGE on `energy_analytics.daily_ac_snapshots_snapshot_id_seq`, and SELECT on `public.item0653` for `energy_power_writer`. No table UPDATE/DELETE/TRUNCATE, schema DDL, raw-table write, hardware-control or wider role grant is requested. Explicit operator approval for these exact production privilege changes is required before reattempting them. Even after grants, AC publication remains off until the first complete day after September 25 06:00Z and the remaining source fault/restart/retention checks are qualified.
