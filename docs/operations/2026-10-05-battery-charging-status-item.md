# Battery charging-status Item — attended file handoff

`BatteryChargingStatus` is now the sole file-owned, unlinked Switch after the
October 5 attended managed/file round trip. Its exact label, display writer,
charging semantics and original Item-154 JDBC history are preserved. The
production source release gate remains closed; a natural changed writer/JDBC
receipt and household restart qualification remain separate live gates.
The earlier candidate and native rehearsal sections retain their original scope.

## Exact scope and live preflight

The candidate declares only:

```text
Switch BatteryChargingStatus "BatteryChargingStatus"
```

The original Item has no tags, groups, metadata or channel links. Its sole
inspected writer is the already file-owned `UpdateBatteryIcon` display rule;
the Home battery-direction display consumes it. The original writer source
matches `/etc/openhab/automation/js/battery-icon.js` exactly, SHA-256
`bc6c0954b232902d4b5af444b6381cf5c8ea4af062aa5a12b8195de364729b45`,
with sole file ownership and IDLE/NONE status. This preserves its existing
current-based hysteresis; it does not supply source-freshness authority.

Read-only native SQL confirms JDBC identity **154** and **97,347** original
rows at the fixed preflight cutoff. A recoverable ordered CSV/gzip prefix and
exact original Item/writer descriptors are retained privately. These are
preparation evidence; a later transfer must take a fresh guarded backup and
compare the fixed prefix rather than expecting unchanged total row counts.

The October 5 18:26Z live inventory has zero structural issues. Of its 17
unlinked/ungrouped/literal-unmentioned review candidates, 16 belong to Goat and
remain outside this task. The literal census is a review prompt, not a proof
that dynamic/external consumers are absent or permission for a bulk transfer.

## Qualification

`scripts/qualify-battery-charging-status-provider.py` reuses the existing
OpenHAB 5.2.1 networkless provider harness with exactly this Item and Switch
type. It passed exact descriptor/state-description comparison, sole file
ownership and unchanged source bytes. Fresh first-boot state is NULL, correctly
distinguished from JDBC restoration. Its owned container/tmpfs were removed.

`scripts/qualify-battery-charging-status-jdbc.py` reuses the existing disposable
OpenHAB/PostgreSQL harness. Separate ON and OFF rehearsals both passed:

- Original Switch state persisted through the unchanged file JDBC strategy.
- File withdrawal and original managed restoration, with exact history prefix.
- Managed withdrawal and forward file transfer, with state/history restoration.
- Hot file loading and full-JVM restart, with state and original history intact.
- Owned OpenHAB/PostgreSQL cleanup and zero production writes.

Neither exercise contains the production charging writer, channel links or hardware.
Synthetic values are confined to disposable isolation.

Independent review of commit `0c7d121` against `d0dbf0d` is clear of
Important/Critical findings. It confirms the exact Switch descriptor, absent
production target, unchanged ownership manifest, isolated ON/OFF transport,
native recovery/cleanup logs and all 15 retained capsule hashes. The recovered
original compressed history contains exactly 97,347 rows.

Reproduction:

```bash
python3 scripts/qualify-battery-charging-status-provider.py
python3 scripts/qualify-battery-charging-status-jdbc.py --state ON
python3 scripts/qualify-battery-charging-status-jdbc.py --state OFF
```

Candidate source SHA-256:
`546d5498d3392b6ea041850d7a869783b7a3f29a56a49e5cfdbdb97a6200802a`.
Private mode-0700 capsule:
`/home/sat/.local/state/openhab-config-migration/battery-charging-status-candidate-20261005-t3wlwuh_/`.
Mode-0600 native history, preimages, source, qualifier pins, logs and manifest
are retained. Original CSV/history identities are never committed to Git.

## Closed attended transport

`scripts/migrate-battery-charging-status-item.py` now prepares the exact
one-Switch round trip. Its `--check` path is read-only; `--apply` refuses before
database or credential access while the release gate is closed. The only
permitted writes are withdrawal/restoration of this original Item descriptor
and disable/enable of its exact file-owned display writer. Item state/command
writes, rule execution and all other resource mutations are rejected.

Before any withdrawal it requires the pinned source/writer, absent destination,
exact managed descriptor and JDBC identity, matching latest native state, and
unchanged unrelated definitions, installed files and JVM. It saves recoverable
original and writer-paused history prefixes in a private capsule. The transfer
includes an actual original managed rollback before final file installation.
Watched-file removal requires the created inode and source hash; matching bytes
from another inode never establish ownership.

Failure recovery checks accepted-but-unacknowledged writes, re-pauses a writer
whose final enable may have succeeded, and restores the original provider before
resuming it. Genuine later writer/JDBC state is retained without rebasing the
original history prefix or sending a synthetic state update. Unknown provider,
file, writer or history drift refuses automatic recovery.

The initial `f735e76` transport had twenty-eight offline boundary/failure tests exercising the round trip, each lost
mutation acknowledgement, failed file readback, foreign-inode replacement,
transient writer status, genuine appended state, unrestored NULL/UNDEF state,
delayed JDBC catch-up and partial pending-file writes. Original-prefix drift
refuses recovery before withdrawing even an unrestored owned file. The shared
migration/countdown suite totals 75 passing tests. A separate read-only live
preflight passed with PID 1696, state OFF and 97,347 original rows. These tests
do not establish that this new transport has run against a native provider;
the earlier disposable ON/OFF rehearsals qualify its underlying provider/JDBC
operations. The exact new transport still requires native rehearsal and
the later live gates before opening its release gate.

Independent re-review of that initial transport cleared source SHA-256
`15593f5b4ad519d5e25e0459d9e05e75046e18826ed0ca2eb2a0891d96dfe873`
and tests
`7894e2d80abbb269e717f0f638eb9cd81c3948e07339e2cbf9f566f69e2371d8`:
both Important recovery findings and the minor pending-file cleanup issue are
resolved, with no remaining Important/Critical findings. The reviewer independently
executed the five corrected cases under mocked boundaries. This clears closed
staged integration, not live cutover or restart readiness.

Initial full-suite collection lacked the sibling analytics import path; the
next attempt exposed the system WebSockets 10.4 dependency mismatch in 27
existing messaging tests. Using the already installed qualified WebSockets
15.0.1 environment and analytics import path, the pre-review-fix suite passed
4,145 tests with 10 skips and 91 passing subtests. No host dependency was
installed or changed. That initial transport's fresh full suite passed **4,150 tests,
10 skips and 91 subtests** in 377.42 seconds, with the exact re-reviewed source
and test hashes unchanged throughout. This qualifies the closed repository
transport; native exact-transport and live-use gates remain open.

Transport sources, failure evidence, test-environment pins, read-only preflight
and the refused 19:20Z restart attempt are retained in a separate mode-0700
capsule at
`/home/sat/.local/state/openhab-config-migration/charging-status-transport-20261005-1jw8wzqi/`.
Its mode-0600 files have retained manifests; the original candidate capsule and
its recoverable history are unchanged.

## Exact transport and cold native JVM qualification

The exact transport now passes against a disconnected, owned OpenHAB 5.2.1
and PostgreSQL fixture, using the original **97,347** native Item-154 rows and
unchanged `UpdateBatteryIcon` writer. OpenHAB shares the PostgreSQL container's
networkless namespace; it has no host bind mounts, published ports, household
Things, links or actuators. The database's only host mount is its owned private
Unix-socket directory. The transport reads through a SELECT-only fixture role;
its on-disk production release gate remains false.

This rehearsal exposed a real filesystem defect: watched configuration and
private recovery directories can live on different filesystems. A hard link
then fails with `EXDEV`. Withdrawal now verifies and copies the owned source
into a mode-0600 recovery file, makes it durable, rechecks the watched inode,
and removes only that inode. A genuine separate-filesystem test reproduced the
old error. Copy-fsync failure leaves the watched file intact; a matching-byte
replacement after backup is retained and rejected.

Review also found asynchronous withdrawal recovery could stall after a
successful unlink followed by a sync/readback error. Two regressions reproduced
that failure. The transport now records actual unlink before either later
failure and waits for the known withdrawing provider to disappear before
restoring the original managed Item. Six cases cover directory-sync/readback
failure with zero, one or three lingering registry reads. Disappearance during
JDBC catch-up is accepted only while this exact owned withdrawal is pending;
foreign ownership and duplicate providers still refuse recovery.

Native execution passes the complete managed -> file -> original managed ->
final file round trip and every accepted-but-unacknowledged mutation (five
separate faults). Recovery also preserves a genuine ON update from the exact
writer while a fixture-only table lock delays its JDBC INSERT. The original
prefix is unchanged; the later native row gives **97,348** final rows. No
synthetic update to the selected Switch is used by the transport.

A cold isolated restart preserves exact Item/rule/Thing/link definitions, file
inode/source and both original/later history prefixes. The first comparator
correctly stopped on a changed trigger UUID. The bundled library generates that
UUID when the pinned writer supplies no explicit trigger ID; only its canonical
version-4 UUID and validated script-action registration are normalized, keeping
the original cron/type/configuration intact. Container-local Java PID **7** was
reused, so the repeated restart proves a new JVM with actual `/proc` start ticks
**28440313 -> 28463951** and independently changed host process/start epoch.
This does not substitute for production `MainPID` qualification. The retained
native OpenHAB log has zero ERROR/Exception lines. Both owned containers and
their socket directory were removed and their absence verified.

Current source SHA-256:
`4c1ec58ad5696242d06d49e1554ece82cd01adda003a1875845a8a651862db6a`.
Current test SHA-256:
`f5d7c5389ac31706bb7c02b641b5f031d105568328a8c6c8e63370d80dd360cc`.
Independent review clears the post-unlink fix with no Important/Critical
findings and independently passes all six delayed-withdrawal regressions.
There are **37** transport cases; together with shared migration tests,
**60** pass. The fresh full suite passes **4,159 tests, 10 skips and 91
subtests** in **376.27 seconds**, using the already installed qualified test
environment described above. Source/test hashes stayed fixed during the run.
A fresh read-only production preflight passes with managed OFF, PID **1696**,
identity **154**, all **97,347** original rows, and no production writes.

A separate mode-0700 capsule retains mode-0600 source/tests, before/after
native proofs, actual native recovery histories, errors and corrected results,
private reproduction drivers, review pins, full-suite logs and cleanup proof:
`/home/sat/.local/state/openhab-config-migration/charging-status-exact-transport-20261005-ft52lt6b/`.
Its manifest seals the retained files. Original candidate and initial transport
capsules remain intact. Fixture credentials and native history stay out of Git.

## October 5 attended live handoff

The existing operator authorization to continue live file-first migration
covers this qualified observational Item. The [attended plan](../superpowers/plans/2026-10-05-battery-charging-status-cutover.md)
records the sequencing ruling: isolated recovery gates pass for this resource;
production whole-JVM restart remains a separate gate requiring host authentication.
The current literal live/source census finds only the unchanged display writer
and Home battery-direction display. The Item has no links, groups or tags;
the census does not prove the absence of dynamic external consumers.

An independently reviewed private bootstrap invoked the unchanged **4c1ec58...**
transport with a one-call in-memory release. Its added check preserves the original
candidate's raw CSV digest **b89e3ce4...** and compressed archive **eb9bf5b2...**
through every guarded phase. Extra observational checkpoints record both actual
file readbacks and the intermediate original managed provider. The bootstrap's
three injected checkpoint failures were independently tested: each restored the
managed Item and original enabled writer. The Git transport's release flag never
changed, and the imported flag was closed in `finally`.

Live readback at **2026-10-05T20:58:16.831761Z** confirms:

- First file provider, actual original managed rollback, then final file provider;
  exact source, Switch descriptor and created inode, recovered **OFF** throughout.
- JDBC identity **154**, all **97,347** original native rows, exact original and
  writer-paused prefixes, plus the earlier candidate prefix remain intact.
- All unrelated Item/rule/Thing/link definitions, installed sources and JVM match
  the original protected signature. PID remains **1696**.
- Original three disabled rules remain disabled; every other rule is healthy.
  `UpdateBatteryIcon` returns to its original enabled **IDLE/NONE** status.
- No new ERROR/Exception lines in the bounded runtime log, and read-only JSONDB
  inspection confirms the selected Item is absent from managed storage.

The native registry inventory at **20:58:51Z** has zero structural issues:
**354 managed / 91 non-managed Items**, **78 / 8 Things**, **35 / 8 rules** and
**219 / 49 links**. Exactly one ownership declaration is added after readback;
all prior declarations are unchanged. The source's original staging comments
are retained with its qualified bytes. Fresh focused transport/shared checks
pass **60** tests; code hashes remain those of the qualified 4,159-test suite.
No source revision, control, manual rule execution, synthetic state, SQL write or
production restart was performed by this handoff.

Recoverable original/writer-paused history, source and actual provider checkpoints:
`/home/sat/.local/state/openhab-config-migration/charging-status-file-9spb743v/`.
The separate mode-0700 attended evidence envelope is
`/home/sat/.local/state/openhab-config-migration/charging-status-attended-20261005-37dz7c3f/`.
It retains mode-0600 registry/ownership preimages, source/bootstrap/plan pins,
execution log, independent review, final readback, inventory and bounded logs.
Original candidate and exact-native qualification capsules remain intact.

## Remaining live gates

Observe a genuine naturally changed `UpdateBatteryIcon` output and its native
Item-154 JDBC row. The final current state/history are verified, but an unchanged
healthy cron evaluation does not create a changed-output receipt. Do not force
an ON/OFF value or call `/runnow` to manufacture this evidence. Keep the original
managed recovery point and the natural-output flag unqualified until its own proof.

The already approved production restart still requires host authentication.
Refresh its source/provider/history baseline after this intentional Item transfer,
then verify actual new JVM identity, recovered configuration/providers, every
pinned original history and fresh source telemetry. Isolated restart evidence
never closes that household gate. Full migration and protected-control recovery
remain incomplete.
