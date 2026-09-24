# Proposed attended `gForecast` cold cutover

Status: proposed, **not released**. The adapter
`scripts/migrate-forecast-group-offline.py` keeps `RELEASE_READY = False`.
Its `--check` is read-only; `--apply` is blocked before any backup, pump check
or OpenHAB stop until a specific attended maintenance decision is made.

## Why a stopped-service handoff is necessary

`gForecast` is the persistence selector for ten file-owned forecast Items.
The isolated hot-provider handoff lost forecast series posted while the Group
was absent, even though all ten member references later reappeared. Do not
REST-delete the production Group or attempt that hot handoff. The exact
stopped-service JSONDB edit, file load, full restart and managed rollback
preserved all ten references in a disconnected OpenHAB rehearsal, including
after a forced-kill simulation.

The last production OpenHAB stop on September 23 exhausted its 120-second
timeout and the JVM was SIGKILLed before restarting. Current Java no longer
has the earlier `jspawnhelper` version mismatch, but that does not prove a
clean future stop. During a real outage, OpenHAB rules and safety interlocks
are unavailable. The adapter refuses to stop unless both greywater pump
output Items read `OFF`, and checks them again immediately before the stop;
that is a necessary but **not sufficient** protected-control safety gate.

## Required attended decision and preflight

Choose a maintenance window with an operator able to observe the physical
system and abort/recover if OpenHAB does not restart. Specifically approve a
possible multi-minute OpenHAB outage and the prior forced-stop behavior.
Before flipping the release gate, review the live BMS/Schneider safety posture,
both physical pump outputs, service health, current configuration backup and
rollback paths. Do not start during an active pump cycle or other protected
control transition. Preserve the verified full database/runtime recovery point,
then run a fresh `--check`; it must find the managed Group, ten exact file-owned
members/links, ONLINE forecast Thing, pinned source hash, verified daily
natural writer gate and stable JDBC IDs 563–572. The September 24 03:13 MDT
read-only check passed but must not substitute for this fresh preflight.

## One attended transfer

After specific approval, set `RELEASE_READY = True`, rerun focused tests and
the fresh preflight, commit and push the reviewed adapter, then run one
attended `--apply`. It rechecks both pump output Items, stops OpenHAB, saves
the exact stopped Item JSONDB and source privately, removes only the managed
`gForecast` record while stopped, installs the pinned file Group, and starts
OpenHAB. It requires file-owned Group status, all ten member references and
file-owned member links, stable JDBC identities and preserved pre-cutover
history. This result is **provisional** until the next natural OpenMeteo
48-hour/7-day forecast series persists under the file Group without a gap.

If the provider or history gate fails, the adapter stops OpenHAB again,
removes only its unchanged pinned Group file, restores the saved managed Group
record without rewriting unrelated JSONDB entries, restarts and verifies ten
members. If restart or rollback fails, stop and use the private backup and
full recovery point under an attended recovery plan; never claim success from
an installed file alone. Do not prune recovery artifacts during the trial.

No battery, pump, feeder, Bitcoin or forecast acquisition rule is intentionally
changed. The operational risk is the whole OpenHAB interruption, not just the
forecast Group's label or membership.
