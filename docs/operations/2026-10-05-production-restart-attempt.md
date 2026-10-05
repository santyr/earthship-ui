# October 5 production restart attempt

The latest operator-requested attempt at **23:07:59.548832Z** again returned
`sudo: a password is required`; OpenHAB remains PID **1696**. The preflight
waited for the existing south pump's actual 15-minute timer to finish naturally
around 23:06Z. Both Item states and separate read-only physical outlet queries
then confirmed OFF. All **27** feeder ledger entries were complete, battery
telemetry was healthy, disabled rules matched the retained baseline and no
unexpectedly unhealthy rule was present. After the refusal, all **56** installed
source hashes still matched, both pump Items remained OFF and no new runtime
ERROR/Exception appeared. No restart or household command occurred.

This new mode-0600 receipt is retained separately from the sealed baseline:
`/home/sat/.local/state/openhab-config-migration/restart-operator-request-20261005-_eejcd65.json`.
Approval remains recorded; host authentication is still the required next step.

The operator-approved restart was attempted at **2026-10-05 21:12:38Z** with
`sudo -n systemctl restart openhab.service`. The host returned exit 1:
`sudo: a password is required`. No restart occurred. OpenHAB remains active on
**PID 1696**, started October 2 at 07:25:20 America/Denver. Operator approval
already exists; host authentication remains necessary.

Before the attempt, the baseline was refreshed after the attended
`BatteryChargingStatus` file handoff. It includes the live native registry,
all **56** declared installed file-source hashes and **40** original JDBC
history prefixes with recoverable private CSV archives. Current configuration,
userdata and add-on archives total **1,801,799,680 bytes**. All 56 declared
configuration sources match the configuration archive; **95** archived JSONDB
JSON documents parse. These live captures are not an atomic system snapshot or
a production restore qualification.

Both pump Items and read-only physical outlet queries confirmed OFF. The
scheduler was in cooldown; all 27 feeder ledger entries were complete. The
initial unprivileged userdata copy expanded a sparse LMDB cache; its owned
backup process was stopped and its partial archive removed. The final copy
uses sparse preservation and authorized privileged read access, retaining
private files inaccessible to the ordinary user. Production was untouched by
this backup recovery.

Read-only verification at **21:13:16Z** confirms all 56 installed source hashes
unchanged, the original disabled-rule set preserved, no unexpectedly unhealthy
rules and no new ERROR/Exception lines after the attempt. Battery telemetry is
healthy, both pump Items remain OFF, and `BatteryChargingStatus` remains
file-owned OFF. Production restart qualification and the charging-status
Item's genuine changed-output/JDBC gate remain open.

The mode-700 private capsule is
`/home/sat/.local/state/openhab-config-migration/restart-20261005-t2vrscku/`.
Its 63 evidence files are mode 600 and hashed by `manifest.json`; credentials
and native private registry exports are excluded from Git. It supersedes the
pre-handoff `restart-20261005-e19ac0u1` baseline, which remains retained.
`/tmp/openhab-restart-directory` selects the refreshed capsule. The retained
`qualification.py` uses the attended worktree's current ownership declaration.

The operator must authenticate the same command on the host:

```bash
sudo systemctl restart openhab.service
```

After a new JVM is observed, inspect startup logs and qualify native definitions,
sole providers, source hashes, disabled rules, telemetry and original history
prefixes. Explain any volatile runtime registration IDs separately; an empty
inventory issue list or command success alone cannot close the recovery gate.
