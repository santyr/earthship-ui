# MPPT60 daily-PV evidence: observational live activation

September 28, 2026, 07:57–08:13 MDT. This activates source-qualified native
daily-Wh observations. It does **not** correct the forecast, publish a qualified
daily PV total, change MPPT controls, or authorize thermal actions.

## Preflight and file hot reload

The existing native MPPT60 Wh Item/link, 30-second poller, data Thing and TCP
bridge were left unchanged; all three Things read `ONLINE/NONE`. The two new
Items and rule were absent. The live file-owned JDBC strategy exactly matched
the prior canonical source SHA-256
`39299b96ec22d1e4860ead09f7b85e23f09f89b071e256a6a0609dda575c57a9`.
Before production, two isolated OpenHAB 5.2.1 rule boots and the existing AC
control passed. Separate networkless provider and disconnected PostgreSQL
rehearsals passed exact DTO, file→managed→file rollback, automatic-write
exclusion, explicit immutable write and new-JVM restore checks. Those fixtures
were removed.

A mode-0600 exact rollback preimage was temporarily placed in a private
directory. At 07:57:54 MDT the
reviewed candidate atomically replaced only
`/etc/openhab/persistence/jdbc.persist` (SHA-256
`2a36f252d839c5495d2cd71e32c10894ca9a989c8321fde9c36b07a0e7cd8947`).
REST immediately returned the exact full strategy DTO with `editable=false`.
The evidence Item is excluded from automatic `everyChange` but retains
`restoreOnStartup`; the transient observation Item is excluded entirely.
In a bounded four-minute readback across the hot reload, the existing power
and inverter-AC streams had 137 and 46 JDBC rows respectively, each in one
epoch with zero sequence gaps. This is a bounded continuity check, not a claim
that every household Item had gap-free collection.

## Read-side source and rule

The JS transform and two file-owned String Items were added at 08:00–08:03
MDT, with checked-in/installed SHA equality. The observation Item is linked
to the same native Modbus Wh channel, without changing the existing native
Item/link. Two natural transformed observations advanced their original
host-acquisition timestamps while the native counter advanced from 16 to 18
Wh. Its JDBC history was empty, as required by the exclusion. The unlinked
evidence output Item was initially `NULL` with no JDBC rows.

`hex_mppt60_pv_day_evidence` was created with zero triggers, disabled, then
given exactly the six reviewed observation/status/expiry/startup triggers and
the checked-in source. Disabled readback matched before it was enabled. The
rule has no `sendCommand` or actuator path. Its first durable row was an
unavailable `invalid_input` startup barrier, sequence 1, persisted at
`2026-09-28T14:06:49.997Z`. Natural source-attributed observations then
produced valid native-Wh evidence. At 08:13 MDT, all 11 JDBC rows passed the
independent strict v1 parser: one startup barrier, ten valid rows, one epoch,
contiguous sequences 1–11 and a last value of 34 Wh. The live rule was
`IDLE/NONE`, and its latest evidence Wh matched the native Item. No synthetic
telemetry, hardware command, forecast edit or control action was used.
Later the same morning, all 57 bounded JDBC receipts parsed under the strict
v1 reader: one startup barrier, 56 valid receipts, one epoch, contiguous
sequences 1–57, and 79 Wh matching the native counter. This extends the
natural-run observation; it does not qualify the partial September 28 day.

The canonical `openhab/file-config/persistence/jdbc.persist` now matches the
installed file byte-for-byte; the duplicate candidate copy was removed.
Both installed file-owned Item definitions and the transform also match their
Git sources by SHA-256. The OpenHAB ownership inventory has no issues. The
provider and disconnected JDBC rehearsals were repeated against that canonical
file, including automatic-write exclusions, explicit PV write, new-JVM
restore, four measured provider handoff gaps, and fixture cleanup. This does
not claim a whole-host production restart test.

## Boundaries and recovery

September 28 cannot qualify as a full local PV day because collection began
after midnight. September 29 is the first *possible* complete local day; the
strict reader may assess it no earlier than September 30 00:00 MDT and only
after receipt coverage, midnight reset, sequence and terminal-poll gates pass.
The source-only JDBC day reader has no production credential grant, caller,
scheduled learning path or forecast calibration release. Natural fault/restart
recovery, a full qualified day, chronological holdout and source retention
remain open. The managed rule is a file-first migration follow-up; the Items,
transform and JDBC strategy are file-owned.

To stop new collection, disable only `hex_mppt60_pv_day_evidence` and verify
`UNINITIALIZED/DISABLED`; retain its historical evidence for diagnosis. The
new file-owned observation and evidence Items can be withdrawn only after
checking their exact paths and hashes. The harmless JDBC exclusions may
remain. The temporary rollback copy was hash-checked and removed after live
verification; the prior file is recoverable from Git history at SHA-256
`39299b96ec22d1e4860ead09f7b85e23f09f89b071e256a6a0609dda575c57a9`.
If the strategy itself must be reverted, restore that exact preimage
atomically, verify its SHA and full REST DTO, then check existing
evidence continuity; a provider transition may introduce a collection gap.
Do not delete native MPPT history, the existing Item/link or the new JDBC
evidence rows as part of rollback.
