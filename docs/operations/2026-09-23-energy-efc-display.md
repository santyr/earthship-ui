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
Nearby labels now distinguish the BMS-reported cycle count from EFC, identify
remaining amp-hours rather than nominal capacity, and mark today's curtailment
hours as predicted rather than observed.

Verification: 1,694 UI tests, production build and six Energy browser checks
passed, including a 1340x800 card/modal overflow regression. This release does
not qualify AC load, winter replay, high-SoC exposure, SoH or observed
curtailment; those producer/evidence tasks remain open.

The qualified full-charge streak producer was subsequently published as
Solar_PV `41c1494`. It counts only contiguous, complete battery-evidence days:
`currentNoFullDays` describes the observed no-full run, while `daysSinceFull`
requires a witnessed 99% day in that run. Neither bridges a gap or partial day.
The existing `energy-ui-publish.timer` picked up the source at 17:00:29 MDT on
September 23 (exit 0). Read-only OpenHAB UI-proxy readback showed throughDate
September 22, battery status `ok`, latestReached99 `true`, and both streak
fields `0`. The focused analytics/UI contract suite passed 53 tests. The full
Solar_PV analytics suite passed 845 tests when run with both
`earthship-ui/openhab/scripts` and `Solar_PV/analytics/src` on `PYTHONPATH`;
the advisory worker integration test launches a child that needs both paths.

Solar_PV `c0854c7` subsequently projected atomic BMS SoC exposure into the
qualified UI payload only when every selected day has a source-qualified
observation and at least 90% atomic-source coverage, with no missing day.
Earthship UI `0e1b97d` labels the 90% and 95% figures as observed window
hours, not lifetime exposure. The September 23 17:10:17 MDT natural publisher
exited 0; exact OpenHAB readback for September 20–22 showed zero missing days,
49.589780374166665 hours above 90% and 32.48532843694444 hours above 95%,
matching the read-only qualified lifecycle report. Validation passed all 849
analytics tests, 1,696 UI tests, production build and six Energy browser checks
including the Lenovo modal overflow check. Winter, SoH, observed curtailment
and AC-load fields remain pending their separate evidence gates.
