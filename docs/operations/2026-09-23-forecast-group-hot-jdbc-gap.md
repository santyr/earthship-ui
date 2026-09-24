# gForecast hot-handoff JDBC gap: release failure

On September 23 MDT, `scripts/qualify-forecast-group-hot-jdbc.py` used a
disconnected, disposable OpenHAB/PostgreSQL pair with the installed
`jdbc.persist` source and all ten forecast members loaded from their three
Git-owned `.items` files. Only synthetic future time-series events were
posted in the fixture; no production Item, Group, database or service changed.

An earlier registry-only rehearsal had shown all ten file-owned member
references surviving managed Group deletion, file Group load, an isolated
restart and managed rollback. That made a hot handoff plausible but did not
test the JDBC `gForecast*` selector. The JDBC rehearsal tested that missing
contract directly, using three forecast members with 48/7/7 future values
at disjoint target windows:

| Provider stage | JDBC result |
| --- | --- |
| Managed Group before deletion | All three series persisted. |
| Group absent, ten member references still present | None of the three series persisted. |
| File Group loaded | All three new series persisted; the missing gap windows still had zero rows. |
| Managed Group restored | All three new series persisted. |

The initial run waited 90 seconds for the gap series and found none. A second
run confirmed the same absence after a shorter bounded wait, then completed
the file-owned and rollback checkpoints. Each successful checkpoint checked
exact target timestamps, values and preservation of earlier history. The
three gap windows had zero rows even after the file Group resumed. Both
OpenHAB and PostgreSQL test containers were removed; a fresh production
inventory still showed `gForecast` managed and zero ownership issues.

This is a **failed release gate** for a REST-delete/replace hot handoff. The
visible `groupNames` references do not ensure JDBC forecast-series routing
while the Group itself is absent. Do not attempt this path in production,
even during a short interval between scheduled OpenMeteo fetches. The
stopped-service JSONDB-to-file handoff remains separately rehearsed, but its
production restart and protected-control safety decisions remain open.
