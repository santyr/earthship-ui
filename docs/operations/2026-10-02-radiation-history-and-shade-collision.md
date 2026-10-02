# Radiation history, shade collision and Office Hallway display

## Approved scope

The operator approved durable read-only radiation history and the coincident
shade-timing correction on October 2. Radiation is observational; collection
does not authorize calibration, forecast promotion or household controls.
The subsequent UI clarification keeps Office Hallway on Home and removes its
Earthship-page reading and visible history series only. Sensor 223 collection,
its existing backend Item/history and thermal input remain unchanged.

## Source and isolated verification

The new file-owned `Weather_Radiation_Evidence_JSON` String is linked only to
`http:url:weatherRadiationEvidence:snapshot`. The HTTP Thing reads the existing
local receiver endpoint every 30 seconds. The complete original receipt is
stored by the existing JDBC `everyChange, restoreOnStartup` strategy; polling
does not renew decoder timestamps or expiry.

`scripts/qualify-weather-radiation-jdbc.py` exercised real OpenHAB 5.2.1 HTTP
and JDBC bindings against disconnected, disposable PostgreSQL/OpenHAB
containers. It verified unchanged polls, persisted expiry barriers, HTTP-503
fault and fresh-source recovery, Item/link withdrawal and recovery with history
prefix preservation, actual JVM restart with exact old-receipt restoration,
and a newly received post-restart receipt. The inherited persistence-provider
round trips explicitly report their collection gaps, not source continuity.
HTTP-503 does not require a framework OFFLINE status; the test proves the
binding fetched the error and checks that held state does not mint history or
renew source expiry. No host ports, devices or configuration mounts were used.
The script exited zero and removed both owned containers and test storage.
This is not a whole-host restart or production-continuity qualification.

Coincident quarter-hour-rounded shade times represent zero closed duration in
the existing cyclic model. The correction emits no contradictory simultaneous
transitions and reports open day/night state. Strict ordered-transition
validation is unchanged. Eight behavior cases and a full forecast regression
failed before the correction and passed afterward.

Only `thermal_model/behavior.py` is eligible for installation into the existing
thermal runtime: the repository contains other, undeployed thermal candidates.
An isolated copy of the actual installed runtime with just this file changed
has runtime revision
`7316fa8b1e408544463b3f44e64772e56c7f36b57a9d6325ccca3353bea03af5`,
versus installed preimage
`7f57eb3f00dcc13e09958d6200d99e0ff172be48c5659ad660de22e90bd19095`.
The October 1 and October 2 saved forcing captures reproduced their as-issued
outputs exactly under the explicitly pinned candidate. The October 1
`--solar-scale 1.5` diagnostic failed on original installed source with the
schedule collision and produced a usable forecast with the correction.
These are replay/collision checks, not measured-radiation training or proof of
forecast accuracy. The trained model's revision must not be rewritten.

The modified full suites passed 3,044 Python tests and 74 subtests (no skips),
and 1,984 JavaScript tests across 135 files. The production frontend build
passed with the existing chunk-size warning.

## Production gates

Before installation, require unchanged runtime preimage, absent radiation
Item/Thing/link and destination files, current local receiver receipts, a
private narrow rollback backup, and an unchanged OpenHAB process. Install only
the new observational definitions and the single qualified thermal file.
Require natural HTTP/JDBC receipts and uniquely discover the new JDBC Item
mapping; never guess its table number. A restricted-reader grant, strict
interval/day reader and complete clean days are separate gates before learning.
October 2 includes receiver restart boundaries and is not a complete clean day.

Restart only the user-level UI service after merging the source tree, then
verify transformed production modules. Do not restart OpenHAB for this work.
Backend Office Hallway history must remain present; Home retains the reading.
The thermal collector, questions, training-label writes, household controls,
new learning/calibration and model graduation remain outside this release.

Deployment evidence is pending; isolated success alone is not a live claim.
