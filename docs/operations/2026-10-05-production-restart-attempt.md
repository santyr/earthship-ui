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


## Daylight rule baseline refresh

After the operator required the fan to run only in daylight, the current
restart capsule was refreshed without a service action:
`/home/sat/.local/state/openhab-config-migration/restart-20261005-fan-daylight-p4m6vb5f/`.
The current native registry and all **56** source hashes include the qualified
fan source `bc269d77427c1fcf197844345992c30a240c7ca9922dbd984f035efa0373dedf`.
The **40** fixed-cutoff history archives are retained byte-for-byte from the
previous capsule. Fresh sparse-preserving configuration, userdata and add-on
archives total **1,801,789,440 bytes**; all 56 source files match the configuration
archive, and **95** JSONDB documents parse. The live fan is OFF, file-owned IDLE
with nine triggers; PID **1696** remains unchanged.

`/tmp/openhab-restart-directory` now selects this capsule. Its retained qualifier
uses the daylight worktree, and its mode-600 files are hashed in `manifest.json`.
The previous capsule remains retained. The capture is live and non-atomic;
production restart and restore qualification remain open. The earlier
charging-status changed-output gate has since closed with natural transitions,
as recorded in the outstanding-work checkpoint.


## Weather-health age baseline refresh

Following the attended two-age-Item hot handoff, the latest baseline at
**2026-10-06 01:42:46Z** is
`/home/sat/.local/state/openhab-config-migration/restart-20261005-weather-health-ages-zqc4ttzi/`.
It pins all **57** current source paths, including both the daylight fan and
age definitions, and retains **42** recoverable history prefixes: all 40 prior
prefixes plus the two age tables. Its fresh sparse-preserving archives total
**1,801,768,960 bytes**. All 57 files match the configuration archive and all
**95** JSONDB documents parse. Archived managed Item/link/metadata entries for
the newly file-owned ages are absent, preserving single-provider recovery.

The latest capsule has 53 mode-600 evidence files plus their manifest.
`/tmp/openhab-restart-directory` selects it; the retained qualifier points to
the age worktree and checks all 42 prefixes. The previous fan capsule remains
retained. Both new age Items have natural post-handoff JDBC writes. PID **1696**
is unchanged; no production service action occurred. Live backup capture is
non-atomic, and production restore/restart qualification remains open.


## Sky diagnostic baseline refresh

After the diagnostic Item hot handoff, the latest baseline at **02:47:15Z
October 6** is
`/home/sat/.local/state/openhab-config-migration/restart-20261005-sky-diagnostics-qfk5_4lu/`.
It pins **58** sources and **44** original history prefixes, including both
new diagnostic tables. All 58 sources match the configuration archive and
**95** JSONDB documents parse; archived managed diagnostic records are absent.
The sparse-preserving archives total **1,801,758,720 bytes**. Its 55 private
mode-600 files plus manifest are retained inside a mode-700 directory.
`/tmp/openhab-restart-directory` selects it. The retained qualifier points to
the diagnostic worktree and all 44 prefixes; earlier capsules remain retained.
PID **1696** is unchanged. Capture is live and non-atomic, and production
restore/restart qualification remains open pending host authentication.

The operator must authenticate the same command on the host:

```bash
sudo systemctl restart openhab.service
```

After a new JVM is observed, inspect startup logs and qualify native definitions,
sole providers, source hashes, disabled rules, telemetry and original history
prefixes. Explain any volatile runtime registration IDs separately; an empty
inventory issue list or command success alone cannot close the recovery gate.
