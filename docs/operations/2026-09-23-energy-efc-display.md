# Energy Analytics EFC display clarification

The apparent EFC reset was a display-basis change, not a database reset.
Read-only production SQL on September 23 found 63 consecutive
`energy_analytics.daily_battery` rows for epoch `discover_4_module_2026`,
July 19–September 19. Their daily-EFC sum was 9.809006045339062 and the
last stored cumulative estimate was 9.80900604534. September 10 had quality
`insufficient_data`; the older series is therefore an estimate over available
history, not a qualified lifetime counter. Those rows remain in PostgreSQL.

The live v3 UI payload instead reports 0.4347889408117881 EFC from three
completed qualified power-evidence days, September 20–22, under cutover
2026-09-20T15:18:58.261099Z. `energy_power_reader` has no SELECT on the
legacy table, so the UI now carries only a frozen, explicitly dated pre-cutover
snapshot in `src/lib/energy/priorEfcEstimate.js`. It appears in Details only
when the current validated qualified payload names the same bank epoch and a
window starting after September 19. The main card remains the more defensible
observed-window number and names its start/end dates. The two figures are never
added or presented as one cycle count. If the historical table is corrected,
re-audit this snapshot before updating it; if the bank epoch changes, it is
automatically hidden.

The Energy modal also replaces unsupported v3 values with explicit pending
states, exposes the available daily discharge field, and does not substitute
legacy winter/SoH/curtailment values into qualified fields. The Battery Vitals
row gives Analytics two columns on the primary Lenovo M9 layout. The UI payload,
publisher, database, BMS Items and control paths are unchanged.

Verification: 1,694 UI tests, production build and six Energy browser checks
passed, including a 1340x800 card/modal overflow regression. This release does
not qualify AC load, winter replay, high-SoC exposure, SoH or observed
curtailment; those producer/evidence tasks remain open.
