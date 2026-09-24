# Attended `gForecast` cold cutover

Status: attended transfer completed at 10:18 MDT on September 24 and its
natural OpenMeteo series/JDBC gate passed at 11:17:49 MDT. See the
[cutover receipt](2026-09-24-gforecast-cold-cutover-receipt.md). The adapter
`scripts/migrate-forecast-group-offline.py` has been re-locked with
`RELEASE_READY = False` after the one approved stop/restart. Its `--check`
describes the former managed-state preflight and is not a post-cutover check.

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
output Items read `OFF` and the independent BMS/Schneider and critical-rule
checks pass, then repeats these checks immediately before the stop. These are
necessary but **not sufficient** protected-control safety gates.

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

The adapter now also refuses a stop unless the BMS communications watchdog,
Schneider safety and SouthOutlet control rules have healthy runtime status,
the atomic SoC receipt is fresh, and Schneider DC telemetry has an original
update within five minutes. It checks these again immediately before the stop,
alongside both pump outputs. This read-only guard does not substitute for
physical monitoring. Focused tests and one live read-only guard check passed
while `RELEASE_READY` remained false.

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

The restart also offers a passive check of the independent inverter-output
receipt stream: record the pre-stop epoch/sequence, then require a new epoch's
unavailable startup barrier followed by a fresh valid receipt and bounded
read-only JDBC continuity after OpenHAB returns. This is observational only;
it does not authorize AC-load publication or justify inducing a physical fault.
