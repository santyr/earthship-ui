# Greywater next-pump display — September 20, 2026

The main page shows activity from both pump Items and the next pump's earliest
eligible time, not a promised start. The East-only investigation was removed
after the operator confirmed both pumps run; this is not a full-cycle safety test.

The controller selects South in even local hours and East in odd local hours,
with a 60-minute start-to-start gap. A delayed start can change selection.
It now appends versioned metadata to its existing status: `scheduleVersion`,
`evaluatedAt`, `scheduling`, and, when predictable, `nextEligibleAt` and `nextPump`.
Safety-blocked states do not promise a time. Triggers, gates and actuation are
unchanged; display projection errors cannot interrupt cycle/stop handling.

Source: `openhab/rules/southoutlet-cycle-current.js`, deployed SHA256
`641c6a70cbe757c4d3651d688f0ddffb0141721eff1c7753246ccf685083e919`.
Private receipt: `/tmp/greywater-next-display-o1dcid40`. Deployment checked both
pumps OFF, target idle and original source hash; other rule definitions were
preserved. No runnow or pump test occurred. The natural 18:42:00.343Z evaluation
published East eligibility at 19:24:00.609Z (1:24 PM America/Denver).

The UI rejects stale, malformed, unknown-version and contradictory hints rather
than duplicating controller policy. It labels the time "Earliest" and shows
"Conditions permitting"; full conditions remain accessible/in tooltips.
Fresh SSE status is checked against current wall time, while periodic clock
ticks still expire old hints, avoiding false future-time rejection between ticks.

A live textual browser check at 1340 × 800 observed Idle, Earliest East · 1:24 PM,
and Conditions permitting. All three text rectangles fit inside the approximately
203 × 70 pixel widget, one line each. No screenshots were needed.
Full verification: 102 files / 1,561 tests passed; production build passed with
the existing chunk-size warning.

The minute trigger remains for battery/comms/daylight safety and orphan recovery;
a separate timer handles the normal 15-minute stop. This display change does not
claim natural sunset, restart or full-cycle qualification.
