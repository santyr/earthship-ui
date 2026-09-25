# Read-first AC-load UI v4 contract

The dashboard accepts `earthship-energy-ui/v4` before any AC publisher is enabled. V1–v3 remain accepted unchanged. V4 is exactly the v3 payload plus one top-level `acLoad` object. The v3 `energy.latest.loadKwh` remains `null` and `accounting.loadStatus` remains `ac_load_evidence_unqualified`; this prevents a separate AC day from being mistaken for the latest PV/battery day or for an energy balance.

`acLoad` has exact keys `policy`, `cutover`, `topologyFrom`, `topologyUntil`, `status`, and `latest`. Its policy is `qualified_inverter_ac_output_v1`. `latest` is `null` only with status `unavailable`, or an object with exact keys `date`, `windowStart`, `windowEnd`, `observedKwh`, `coverage`, and `revision`. Revision has exact `id`, `sha256`, and `computedAt` fields. The value is measured inverter AC output integrated over available intervals, not a full-day extrapolation. Status is `observed` when coverage is at least 90%, otherwise `partial`. No day with zero coverage has a numeric value.

The reader rejects days outside the evidence cutover or attested inverter-only topology, non-midnight/DST-invalid local windows, unfinished days, future revisions, and bad identifiers or values. The UI explicitly labels coverage and says that DC PV and AC load cannot be subtracted into a valid balance. Open-ended `topologyUntil` means the operator's current attestation remains in force until a reported change; the publisher must read the current policy on each run and select completed days only.

This is presentation readiness, not AC publication. The first eligible complete local day is September 24, 2026, assessable after September 25 06:00Z. Solar_PV now has an append-only AC-day revision store, strict selected-revision reader, and source-only v4 projector. A scheduled writer/publisher, production fault/restart/retention evidence, and the first complete-day qualification are still required. No existing v3 payload is converted or silently given a load value. If the power series is empty but an AC day is qualified, the compact card labels the AC observation and date rather than saying there is no daily data.

At September 24 17:28 MDT, the restricted read-only reader found 12,250
qualified AC intervals from local midnight to the check: 99.80592% coverage,
122.116 seconds missing, and 4.089576 kWh integrated over observed intervals.
This is a **partial-day diagnostic**, not a stored revision or published
household load. The evidence Item continued to publish a fresh
`inverter_output` receipt; no AC-day writer timer is installed. The roughly
118-second OpenHAB-restart gap remains real and must not be filled or treated
as zero Watts. The increase in missing time since the 12:29 MDT checkpoint
was under one second; no second material outage was detected by this check.

The first completed-day restricted-reader `ac-day --dry-run` for **2026-09-24**
passed on September 25 at 08:20 MDT. It selected the exact
`Inverter_AC_Evidence_JSON` Item, midnight-to-midnight Denver window,
September 23 20:55:12.284Z evidence/topology cutover and still-open topology
attestation. Qualified AC coverage was 0.9985752893518797, observed inverter
output 5.5172159036110715 kWh, common AC/PV coverage 0.9985123148148157,
common-window AC 5.516895523888905 kWh and DC PV 4.415048876388867 kWh.
The output explicitly withheld `balance_kwh` as cross-domain. This closes the
first-day dry-run gate only: no daily AC revision was appended or published.
Review the revision backup, fault/restart/retention gates and UI semantics
separately before activating the writer or v4 publisher.

Solar_PV now has a separate `energy-ui-publish --dry-run` path that performs
the production read, v4 projection and exact payload encoding without a token
or OpenHAB write. The September 25 read-only trial validated a 2,403-byte v4
payload with AC status `unavailable`, as expected while the daily revision
table is empty; immediate readback left `Energy_Analytics_JSON` unchanged on
v3. The full analytics suite passed 862 tests. This validates the preview
contract, not a populated AC day or authority to switch the installed
publisher to v4.
