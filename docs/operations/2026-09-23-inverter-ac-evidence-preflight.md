# Independent inverter AC evidence: source-only preflight

September 23, 2026 initial preflight. The separate Item and rule were then
activated as described in the [live receipt](2026-09-23-inverter-ac-evidence-activation.md). The existing
`Power_Evidence_JSON` v1 producer and Solar-PV strict three-field reader are
unchanged. This candidate exists to preserve that working contract while
qualifying inverter output for a future, explicitly topology-scoped load reader.

## Candidate contract

The separate v1 envelope has exact top-level keys `version`, `basis`,
`streamEpoch`, `sequence`, `recordedAt` and `fields`. `basis` is always
`inverter_output`, never an unconditional whole-house assertion. Its sole field
is `inverter.ac_output_w` with `status`, `reason`, `observedAt`, `validUntil`
and integer `watts`; unavailable fields carry null numeric/timestamp values.
The rule accepts only an original `ItemStateEvent` from the exact Modbus AC
channel through the canonical observation envelope. It requires the inverter
Thing and its TCP bridge to be ONLINE; a status-change trigger or ten-second
timer closes coverage on loss. A post-start, post-recovery receipt is required.
Freshness expires after 30 seconds. Exact integer Watt text from 0 to 20,000
is accepted; invalid, future, expired, replayed, or source-spoofed input is a
barrier. The upper bound is a conservative validation ceiling, not a measured
inverter rating or household-load claim.

Immutable, sequence-numbered snapshots are intended for explicit JDBC writes,
with the output Item excluded from automatic `everyChange` first. The rule is
observational and has no hardware action path. The draft file-owned output
Item, disabled create-only rule descriptor and 26 focused producer tests are
in source control. These tests include offline/recovery, ambiguous enqueue,
same-millisecond persistence ordering, and superseded pending UI posts. This
was initially source-level evidence only.

The September23 disposable OpenHAB 5.2.1 runtime check has now passed with
the locally cached JS/Graal bundles copied only into a networkless container's
tmpfs. The file-owned output Item loaded, the exact candidate triggers
registered, and a run-now invocation returned to IDLE after the rule body
posted a canonical `source_unavailable` envelope (the isolated instance has
no inverter Thing). All owned containers and tmpfs data were removed, including
earlier failed dependency/timing trials. This proves script compilation and
basic execution under that runtime, not Modbus event delivery, fault behavior
against real hardware, JDBC durability, or restart recovery. The repeatable
qualifier is `scripts/qualify-inverter-ac-evidence-runtime.py`.

## Gates before activation or accounting

1. Isolated compilation, trigger registration and basic execution passed.
   Natural live receipts have now passed original-event source validation;
   inverter/bridge loss and recovery remain unobserved. The existing live
   observation must not be used to send a synthetic value or hardware command.
2. The exact output-Item exclusion, isolated immutable write/readback,
   restart/rollback and live file hot reload passed; see
   [JDBC exclusion receipt](2026-09-23-ac-evidence-jdbc-exclusion.md). The
   file-owned output Item and separate rule are now active under the
   [live receipt](2026-09-23-inverter-ac-evidence-activation.md).
3. Solar-PV `24d2e89` now contains a strict, source-only reader for this
   **separate** stream, with invalid-row, gap, epoch, expired-field and finite
   topology-period barriers. The v1 three-field schema and its active reader
   remain unchanged. The full analytics suite passed (763 tests). No AC policy
   period, actual production stream, daily consumer or UI promotion is active.
   The operator directed that Hexmem not be used; verify subsequent changes
   against current source, tests and live state instead.
4. Observe natural production receipts, loss/recovery behavior when safely
   available, and bounded durable coverage before any daily AC-load balance.
   An operator-confirmed inverter-only topology is current, not a historical
   or future guarantee. A consumer must record that period and label its
   basis; no retroactive household-load totals follow from current topology.
5. Review raw-observation retention (measured near 15,840 JDBC rows/day) once
   the independent stream has proven durable; do not remove source history
   before the reader's evidence needs and recovery path are understood.

Official openHAB references for the status trigger and read-only Thing status
lookup: [Standard Triggers](https://www.openhab.org/docs/concepts/standard-triggers),
[openHAB JS Things](https://openhab.github.io/openhab-js/things.js.html).
