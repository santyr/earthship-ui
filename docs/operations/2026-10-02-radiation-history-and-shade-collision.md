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
The installed preimage predates the source-tested cyclic initial-state
correction, so this one-file release includes that correction as well as the
coincident-transition fix. It preserves a modeled closed interval spanning
midnight; this is a modeled schedule, not a claim of measured shade state.
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

## October 2 live deployment

The reviewer accepted the final range through `1d63090`. Review found that an
identical HTTP poll could mask a failed radiation restore; the qualifier now
holds HTTP at 503 across JVM restart, removes the prior fetch marker, requires
a new observed 503, verifies restored state/history, then allows fresh recovery.
The corrected real-container run exited zero and removed its owned resources.
Merged-tree verification passed 3,044 Python tests and 74 subtests in 333.66
seconds, 1,984 JavaScript tests, and the frontend build before push/deployment.

The exact source was pushed to `origin/main` and installed at approximately
09:30 MDT. Private rollback source is retained mode 0600 in the mode-0700
directory `/home/sat/.local/state/thermal-intel/shade-source-rollback-pUa05Q`.
The preimage SHA-256 is
`f2bcbe5021a68cde2a824f50311acc99a499f828b490a9ba6dad57bf13489a8e`;
the installed candidate is
`80bfbfc70e53dad8063e0290a991d53bd3d8d6c6f6fa4b790a2cebd3a29d2b81`.
No other thermal runtime file or trained artifact was replaced.

The new Item, Thing and sole READONLY link are noneditable file resources;
Thing status is ONLINE. Exact deployed definition hashes match Git. JDBC
uniquely mapped the radiation Item to **664 / `public.item0664`**, with its first
natural row at `2026-10-02T15:30:39.039114Z`. Multiple naturally advancing
original decoder receipts match the persisted raw JSON, with expiry exactly
120 seconds after decoder time. A checked receipt had decoder time 15:31:32Z,
receiver time 15:31:32.966989Z and expiry 15:33:32Z. The existing JDBC policy
hash is unchanged. The restricted `energy_power_reader` currently lacks
SELECT on the new table; no grant or strict-day reader was activated.

The user-level UI service restarted successfully at PID 346291. Served Svelte
modules preserve Office Hallway in Home and omit its Earthship reading/series.
Its existing backend identity remains 663 / `Bedroom_Temperature`; persisted
rows increased naturally from 321 to 322 rather than being deleted. The
sensor/parser, role mapping and thermal-input configuration were not edited.

Installed-runtime replay reproduced the October 1 as-issued output exactly and
passed the previously failing solar-sensitivity diagnostic at runtime pin
`7316fa8b...`. The existing shadow service then exited zero at 09:32:13 MDT.
Its 72-point low-confidence output generated at
`2026-10-02T15:32:11.579258Z` matches both the latest JDBC state and original
capture `20261002T153211Z-559a9d4532336f33.json.gz`, with output digest
`559a9d4532336f3363eb49d7b25d6a226cfde5ce233c718271ce8b11d3bae1a8`.
The embedded artifact still has its original training revision. OpenHAB stayed
at PID 1696; there were no new OpenHAB ERROR/Exception lines in the checked
post-deployment interval. No controls, questions, journal labels, collectors,
training, learning/calibration or graduation were activated.

Durable collection is live, but the restricted grant, strict clean-day reader,
complete-day evidence and later production restart continuity remain separate
gates. Preserve `item0664` if disabling collection. Source rollback must verify
the candidate/preimage hashes and atomically restore the private `behavior.py`;
observational-definition rollback parks only these two new definition files
outside watched directories. Neither rollback drops history or changes controls.

## Approved restricted-reader grant — October 2

The operator separately approved SELECT on only `public.item0664`. The live
Item-name lookup again uniquely returned 664 before the database owner applied
`GRANT SELECT ON TABLE public.item0664 TO energy_power_reader;`. Readback shows
SELECT true and INSERT/UPDATE/DELETE false. The actual restricted reader also
read the latest two original receipts in a bounded read-only repeatable-read
transaction. No other table privilege, writer, learner or collector was changed.

This supersedes the missing-grant gate in the deployment checkpoint above.
The strict radiation interval/day reader is still unimplemented. October 2 is
partial: the receiver restarted at 08:16 MDT and durable history began at
09:30 MDT. October 3 is the first possible complete day, assessable after
October 4 local midnight if source continuity passes. Neither held numeric
radiation nor HTTP polling may backfill missing source evidence. Production
restart continuity and learning remain separate gates.
