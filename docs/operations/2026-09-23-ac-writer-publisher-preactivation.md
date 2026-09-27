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

September 24 clarification: that additional reader-role source grant is **not
required** by the intended production path. `ac-day --apply` uses the writer
credential, and its separate AC/PV history readers each open a read-only
database transaction. A bounded live diagnostic under `energy_power_writer`
resolved `item0653` and read 119 qualified AC intervals over ten minutes; the
same role read 119 intervals in each of the three qualified power streams from
`item0648`. Independently, `energy_power_reader` queried the approved daily
AC revision table through the exact v4 reader (zero rows, as expected). The
v4 UI publisher selects that daily table, not raw `item0653`. Therefore the
earlier failure was specific to testing an unfinished `ac-day --dry-run` with
the UI reader credential. Use the existing writer credential with `--dry-run`
when the first day completes; the command and source transports remain
read-only in that mode. Do not grant the UI reader raw evidence access solely
to satisfy that diagnostic. This does not waive first-day, fault/restart,
recovery-point, or v4 publication gates.

The operator subsequently approved that exact raw-evidence read privilege.
On September 24 `energy_power_reader` was granted SELECT on only
`public.item0653`. Fresh readback returned SELECT=true and
INSERT/UPDATE/DELETE=false, and an actual restricted-role query could read the
table. This did not activate the daily writer or v4 publisher, or relax their
evidence gates.

At 22:18 MDT, a new read-only production census found 5,189 `item0653`
receipts since the 20:55:12Z cutover, in one epoch with no sequence gaps:
5,188 valid and the original startup-unavailable barrier. The latest receipt
was 04:18:27Z. The `item0652` observation table occupied 928 KiB and the
`item0653` evidence table 1,776 KiB including indexes; the daily AC table
still held zero rows. This extends passive continuity evidence to roughly
7h23m, but is not a completed Denver day, fault or restart test. A fresh
readback confirmed all five approved privilege checks true, the additional
reader SELECT on `public.item0653` false, and no AC publisher activation.

## September 24 storage and retention decision

A new read-only census at approximately 03:45 MDT found 9,019 validated-stage
`item0653` receipts since cutover: 9,018 `valid`, the original startup barrier,
one epoch, sequence 1–9,019 with no break, and strictly increasing JDBC times.
`item0652` held 9,728 transform-stage rows. PostgreSQL total relation sizes
were approximately 1.44 MiB and 2.96 MiB respectively; the AC daily revision
table remained empty. At this early rate the combined stream is on the order
of single-digit MiB per day, low single-digit GiB per year, against 599 GiB
currently free on the host filesystem. This is a capacity estimate, not a
retention or backup guarantee.

The September 24 verified full-component recovery point includes both streams
and the AC daily table in its exact 514-table restore. Its fixed source
fingerprints counted 6,791 transform-stage rows and 6,064 evidence rows;
the daily table was still empty at capture. This proves both streams are in
the current database recovery scope, not that later rows or the first completed
AC revision are backed up off-host.

Current retention decision: retain **both** raw streams and all append-only
daily revisions; do not exclude either Item from JDBC, prune rows, or collapse
the transform stage into the validated stage. The former is the rule input and
forensic provenance, while the latter is the qualified reader's source. Review
growth and recoverability after the first completed AC day and again with a
longer observation window before proposing any deletion or partition policy.
The complete-day, physical-fault, restart, and post-first-day restore gates
remain open; this decision alone does not enable the writer or v4 publisher.

## September 27 storage and natural-restart follow-up

Completed September 24, 25 and 26 local days passed strict read-only AC-day
qualification. The September 24 day was requalified immediately before a
restricted append-only apply, which stored snapshot ID 1 with SHA-256
`e774316ef29dbf50c0536191ba3c306894ace16e013199b96af714aca4038deb`.
A fresh-process retry returned `inserted=false`, the same ID and digest. The
restricted v4 preview now selects September 24 as `observed`; the live Energy
Analytics Item remains v3. The source-only 00:40 local AC-day unit is not
installed or enabled. A second full database snapshot and isolated restore
at `/home/sat/backups/earthship-energy/full-restore-e66yrzn3/` passed on
September 27: all 515 tables matched, including the first AC daily row;
the archive SHA-256 is
`3addab90dfc970294c04c111581f6120a0844c7acd5460559667063937279a38`.
The owned restore container was removed and Docker volumes returned to 819.
The recovery point is same-host only; off-host disaster recovery remains
Actionable in the read-only backup checker.

The natural attended OpenHAB restart on September 24 supplies live restart
evidence without another control outage. A bounded read of `item0653` from
15:45–17:00Z found 853/853 parse-valid receipts across two epochs. The new
epoch began at 16:17:40.422Z with `source_unavailable`, followed at
16:17:41.750Z by `input_unavailable`. The strict AC interval reader left
16:15:48.518–16:17:46.765Z (118.247 seconds) uncovered, rather than carrying
the old Watt value over the restart. This closes the observed restart-boundary
behavior check, not the physical-source fault gate. As of September 27, raw
`item0653` still contains 66,881 rows from the original cutover through
20:40:19.999Z and occupies about 23.2 MB; no pruning policy was activated.

A separate natural source-connectivity fault occurred on September 26 while
OpenHAB itself stayed up. At 04:12:47 MDT, OpenHAB logged Modbus TCP connect
timeouts to the inverter gateway endpoint; at 04:13:17 it logged `No route to
host` on ports 502/503. In the same stream epoch, the AC evidence Item stored
`source_unavailable` at 10:12:47.614Z and `input_unavailable` at
10:13:19.406Z, then a new valid source receipt at 10:13:24.620Z. All 223
bounded 10:05–10:25Z records parse under the strict schema, and the interval
reader leaves 10:12:42.174–10:13:24.620Z (42.446 seconds) uncovered. This
qualifies the observed Modbus source-loss and recovery path without inducing
equipment failure; it does not prove behavior for every physical fault mode.

## September 27 guarded activation

After the first-revision 515-table restore passed, September 25 and 26 were
requalified and appended as AC revisions 3 and 4. Fresh-process retries
returned `inserted=false` with matching IDs and digests. The restricted v4
publication preview selected September 26 as `observed`, with no DC/AC
balance. The reviewed `energy-ac-day` service and 00:40 local timer, v4
publisher drop-in, and updated backup-check manifest were installed. Loaded
systemd `ExecStart` readback matched the reviewed commands; the AC timer is
enabled with its next run September 28 at 00:40 MDT.

The existing five-minute publisher timer naturally ran at 15:15 MDT and
completed successfully. Live `Energy_Analytics_JSON` then read back as
`earthship-energy-ui/v4` with September 26 observed inverter AC load
6.122461860277783 kWh, 99.947118055556% coverage and revision 4. The
first natural AC-day timer run remains unobserved. This activation relies on
the current inverter-only topology attestation and observed Modbus-loss
behavior; it is not a claim that every possible physical source failure has
been tested. The recovery point predates revisions 3 and 4 and is same-host
only; off-host disaster recovery remains deferred.

## September 24 rule restart regression

Read-only REST inspection found the active `hex_inverter_ac_evidence` rule's
script SHA-256 exactly matches the tested Git source
`880b492e2d0d13b6d1d12c34a6a437f13ef2a58745acaa10c3cb1f9c4134a4ab`;
its status was `IDLE/NONE` with five triggers. The focused harness now asserts
that loss of the private cache creates a new stream epoch and an unavailable
barrier even if the next Watt value is numerically unchanged; only a later
original binding receipt can make the new epoch valid. All 27 focused tests
passed. This is isolated rule-contract evidence, **not** a live OpenHAB restart,
physical fault, full-day coverage, or permission to activate AC publication.
