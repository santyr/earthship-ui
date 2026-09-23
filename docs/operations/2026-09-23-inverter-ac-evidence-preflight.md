# Independent inverter AC evidence: source-only preflight

September 23, 2026. No `Inverter_AC_Evidence_JSON` Item or
`hex_inverter_ac_evidence` rule has been installed or enabled. The existing
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
is source-level evidence only, not production qualification.

## Gates before activation or accounting

1. Qualify OpenHAB 5.2.1 rule compilation and trigger behavior in an isolated
   runtime, including inverter/bridge status transitions and the original
   event object. The existing live observation must not be used to send a
   synthetic value or hardware command.
2. Add the exact output-Item exclusion to the file-owned JDBC strategy and
   rehearse immutable write/readback, restart and rollback. Install the
   file-owned Item and disabled rule only after that exclusion is verified.
3. Deploy a strict Solar-PV reader for this **separate** stream, with invalid-row,
   gap, epoch, expired-field and topology-period barriers. Its current v1
   three-field parser must remain unchanged. The Solar-PV repository requires
   Hexmem context before writes; that service was unavailable during this
   preflight, so no cross-repo edit was made.
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
