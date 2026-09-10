# BMS atomic source preflight — September 10

Written design43ccb08 approved in Hexmem8691. Source-transform dependency20820d9
passed independent spec/quality review, genuine RED34 and GREEN34, full1232
unit tests in90files. Coordinator reran focused34 successfully. This is source
verification only; no new transformations, Things, Items, links or observer were
installed. Three superseded original observer draft files remain staged separately.

## Shared polling and installed capabilities

Read-only live REST checks confirm battery802Core ONLINE, refresh5000ms,
start40244 and length64. Existing raw data Thing is ONLINE, uses register40255,
uint16 and updateUnchangedValuesEveryMillis30000. It offers a String channel.
JavaScript Scripting and Modbus add-ons are installed. Existing transformation
registry contains JS scripts, but these facts do not prove that the new scripts
have run through the installed binding transformation pipeline.

Version5.2.1 source shows `ModbusPollerThingHandler.childHandlerInitialized`
(lines386–389) only adds a data handler to `childCallbacks`; callback delegation
(lines139–148) passes the shared result to each child. Regular polling registers
in poller initialization (lines328–369), not child initialization. Additional
observational child Things therefore do not themselves register another periodic
poll. Do not send REFRESH commands or change poller configuration during rollout.

Sources:
- [Version-matched poller handler](https://raw.githubusercontent.com/openhab/openhab-addons/5.2.1/bundles/org.openhab.binding.modbus/src/main/java/org/openhab/binding/modbus/handler/ModbusPollerThingHandler.java)
- [JavaScript transformation contract](https://www.openhab.org/addons/automation/jsscripting/#js-transformation)

The REST transformations resource supports registry CRUD and service discovery,
not an apply/test endpoint. Do not invent such an endpoint or treat a registry
listing as installed-engine execution. Qualification must use a separately
reviewed installed-engine path without touching existing control resources.

## Incremental persistence estimate

All database checks used the managed JDBC service configuration privately,
five-second connection/statement timeouts and a read-only transaction. No secrets
were printed or stored. JDBC resolves to this host's loopback address.

Two changing envelopes per5000ms successful poll imply34,560 input rows per
24-hour day, or12,614,400 per365-day year. Representative worst-width numeric
envelopes contain70 raw /73 scale UTF-8 bytes. PostgreSQL measured their text
sizes as74/77bytes and composite timestamp/text row sizes as103/106bytes.
These are expression sizes, not measured physical table growth. Existing sampled
JDBC String tables have a unique btree time index. Allowing200–300bytes per row
for tuple/index/page overhead gives roughly6.9–10.4MB/day or2.5–3.8GB/year for
the input stream. WAL, backups, vacuum/bloat and replication are additional.

The observer adds at most1,440 steady valid-heartbeat rows per24-hour day,
plus immediate status/reason/value changes. Actual SoC changes and unavailable
transitions make its volume workload-dependent. It is not bounded to heartbeats
alone and must be measured after qualification.

Current database size was16,530,242,583bytes. The local PostgreSQL/OpenHAB
filesystem had707,182,149,632bytes available (63percent used). The estimated
increment is not a present capacity blocker; this is a point-in-time estimate,
not a promise of annual physical growth or unlimited retention.

Preserve everyChange plus restoreOnStartup. Do not change global persistence or
add another history store. Measure actual row cadence and storage after the new
observational source is enabled; no historical backfill is authorized.

## Remaining release gates

Corrected observer implementation/tests and create-only descriptor are unfinished.
Require exact original ItemStateEvent topics/source checks, source timestamp and
scale-change barriers, invalid/fault/restart handling and single-output restriction.
Before activation: installed transformation qualification, write-disabled source
configuration, affected-resource snapshots, unchanged control/scaler/persistence
hashes and natural atomic events. Readers remain on their current contracts until
live evidence qualifies the new one. Task82 remains held.

## Source completion update — September 10, after d12f4c3

The earlier unfinished-draft descriptions above record the initial preflight,
not current source status. Corrected observer8073985 now validates original
ItemStateEvent envelopes, scale-change barriers, health transitions, cache
restart and clock rollback. Its genuine RED was53failed/2passed against the
original draft; GREEN89focused and1245full-suite tests followed.
Descriptor d12f4c3 replaces the final incompatible staged draft with explicit
create-only disabled resources. Its RED was4new descriptor failures while54
observer tests stayed green; GREEN92focused and1248full-suite tests passed.
Independent descriptor spec/quality and whole-branch source review are clean.
All source files are committed; only the ignored worktree dependency link remains
untracked. Installed-engine qualification, enforced disabled-state creation,
natural source/observer events and reader migration still require live evidence.
Source review approval is not a runtime activation receipt.
