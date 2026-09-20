# First natural qualified-era forecast capture

The ordinary September20 forecast service started at06:40:29MDT and completed
at06:40:30 with `Result=success`. No replay, forced job, synthetic target or test
DM was used for this verification.

## Immutable origin and actual publication

One decision was naturally recorded:

- Decision ID: `19f39fb4-e0e6-4f10-8edd-59abd2c56602`
- Issued: `2026-09-20T12:40:29.864907Z`
- Prediction day: September20; bank epoch: `discover_4_module_2026`
- Advisory: `none`
- Trough target: September20 20:00 through September21 11:00MDT
  (`2026-09-21T02:00:00Z`–`2026-09-21T17:00:00Z`)
- Source revision matches the installed forecast script exactly:
  `7d14bbef3982ea33faf58b4b2dc2cbca182144af105f868d818e6f719d174cd7`

Three immutable child results exist: accepted publication of `Thermal_Advisory`,
accepted publication of `Predicted_SoC_Trough_Tomorrow`, and deep-cycle notification
`not_eligible`. Production canonical record validators accepted all four records.
Read-only OpenHAB checks matched the advisory category and numeric trough to the
frozen origin. Accepted API results are not proof of operator behavior or a causal
reward; no notification delivery was claimed for an ineligible warning.

There are zero trough outcomes and zero frozen selections. This is correct before
the target night completes. The log's `completed trough: accepted; samples=0`
does not mean a night was scored. September21 06:40 is still before target end;
September22 06:40 is the first eligible ordinary assessor run, subject to actual
complete-window qualified SoC coverage and persisted outcome verification.

## Hourly learning eligibility

The log reported `hourly qualified evidence: targets=0 scored=0`. Saved state
contains65targets:41pre-cutover origins and24new origins captured naturally at
September20 06:40:29MDT. All new targets cover September21 00:00–23:00MDT, so
none was elapsed/mature at this run. Pre-cutover origins are correctly excluded;
they were not relabeled or recaptured to manufacture learning evidence.

The first ordinary eligible scoring run is September21 06:40, when up to seven
new targets should have matured. Actual receipt qualification and persisted
per-hour model evidence still need verification then. This closes the natural
origin-capture gate, not the first qualified model-update gate.

All checks used read-only database transactions, filesystem reads and Item GETs.
No model, threshold, schema, scheduling, evidence row or Item was changed.
