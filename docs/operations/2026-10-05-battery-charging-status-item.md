# Battery charging-status Item — isolated file candidate

`BatteryChargingStatus` remains the original managed, unlinked Switch. The
prepared file is **not installed** and no ownership declaration is added.
This continues the approved file-first migration pattern without changing the
display writer, Item name/type/label, charging semantics or persistence.

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

Twenty-eight offline boundary/failure tests exercise the round trip, each lost
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

Independent re-review clears the revised source SHA-256
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
installed or changed. The revised source's fresh full suite passes **4,150 tests,
10 skips and 91 subtests** in 377.42 seconds, with the exact re-reviewed source
and test hashes unchanged throughout. This qualifies the closed repository
transport; native exact-transport and live-use gates remain open.

Transport sources, failure evidence, test-environment pins, read-only preflight
and the refused 19:20Z restart attempt are retained in a separate mode-0700
capsule at
`/home/sat/.local/state/openhab-config-migration/charging-status-transport-20261005-1jw8wzqi/`.
Its mode-0600 files have retained manifests; the original candidate capsule and
its recoverable history are unchanged.

## Remaining live gates

The original candidate's isolated qualification and independent review are
complete, as is independent review of the closed transport. Qualify the exact
new transport against a disposable native provider/JDBC before live use. Revalidate
the existing writer, target absence, current provider/descriptor, original
history and protected definitions/PID at the actual handoff boundary. Pause
only this display writer if needed; preserve its original enabled state and
never stop the forecast publisher or another owner. Perform an actual original
managed rollback before final file ownership and verify a natural writer/JDBC
receipt. Never restore through synthetic production Item updates.

The already approved production restart remains blocked by host
authentication. This candidate is staged while that qualification is pending;
its isolated restart does not close the household restart gate. No production
service, rule, Item, link, control or notification changed in this preparation.
