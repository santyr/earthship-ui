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

## September 28 observation-rule restart qualification

At 19:30 MDT, the live `hex_mppt60_pv_day_evidence` rule exactly matched the
reviewed source, was `IDLE/NONE`, and its data Thing, poller and bridge were
all ONLINE. The existing native Wh Item read 2,425 and the transformed
observation reported the same value. Its first 1,195 JDBC receipts parsed as
one epoch with contiguous sequences. Only this observational rule was briefly
disabled and re-enabled; no Modbus Thing, native Item/link, forecast or MPPT
control was changed. The rule returned to `IDLE/NONE`.

The old epoch ended at sequence 1,195. The new epoch's sequence-1 receipt at
`2026-09-29T01:30:59.575Z` was unavailable, followed by a naturally acquired
valid sequence-2 receipt with 2,425 Wh matching the native Item. All 1,197
persisted receipts passed the strict parser with exactly one barriered restart
and no sequence gap. This closes the observation-rule restart gate, not a
physical Modbus/Thing fault, a complete local day, restricted-reader grant,
forecast calibration or production quality publication.

## Native-counter reset timing and restricted read gate

A read-only inspection of the existing native Wh Item history found four
consecutive falls from positive daily totals to zero around 23:58 MDT
(September 24–27 local dates). This change-only history diagnoses the device's
reset timing; it does not prove that the new source-bound evidence stream
captured a reset. The strict day reader now permits exactly one zero reset in
the final three minutes of a local day, retains the earlier daily peak, and
still refuses earlier or nonzero drops and any subsequent rise. Focused reader
and adapter tests pass. The first source-bound reset must be observed naturally
and parsed before this exception is trusted for a live daily total.

After an operator reported a successful GRANT, a fresh restricted-role check
resolved the evidence Item to `public.item0655` but still found
`energy_power_reader` had no SELECT on that table. The restricted reader did
have SELECT on `public.item0656`, the separate TP-Link evidence table. On
September 28, the operator approved the exact PV grant. The Item 655 mapping
and table ownership were rechecked, and `GRANT SELECT ON TABLE public.item0655
TO energy_power_reader` was applied. Restricted-role readback found SELECT=true
and INSERT/UPDATE/DELETE=false. It parsed all 1,274 persisted receipts from
14:06:49.997Z through 02:48:40.524Z across two epochs, with no same-epoch
sequence gap. This closes the PV database privilege gate only; the day began
before the source-bound cutover, so no qualified full-day PV total or forecast
calibration was enabled.

## Forecast learner cutover guard

The daily forecast worker previously used the maximum of the change-only
`MPPT60_EnergyFromPV_Today` Item to score PV and update `k_res`/`d_direct`.
That history cannot prove a complete fresh source day. The reviewed source
now withholds the partial September 28 cutover day and, from September 29
onward, accepts only `fetch_qualified_pv_day` through the restricted
`energy_power_reader` connection and exact `MPPT60_PV_Day_Evidence_JSON`
identity. Reader failure, low coverage, wrong Item/cutover/date, site-zone
drift or missing provenance has no change-only fallback. It preserves a
bounded score-provenance record. The separate
`PV_QUALIFIED_CALIBRATION_RELEASE` remains false: a qualified day may score
forecast error, but cannot yet update coefficients until the complete-day and
fault/recovery gates are reviewed. The pre-cutover learned coefficients are
retained, not reset or retroactively labeled source-qualified. Focused PV and
adjacent forecast suites passed 191 tests. Production installation and the
next natural forecast run require separate readback below.
