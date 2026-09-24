# `gForecast` attended cold cutover — provisional receipt

At 10:15 MDT on September 24 the operator confirmed both greywater pumps
physically OFF and remained present for the approved whole-OpenHAB restart.
The immediate read-only preflight found both pump Items OFF, healthy BMS
watchdog, Schneider safety and SouthOutlet rules, fresh atomic SoC and
Schneider DC telemetry, an ONLINE forecast Thing, ten exact managed Group
members, stable JDBC IDs 563–572 and a verified natural daily writer gate.
The focused adapter tests passed 10/10. A current integrated recovery rehearsal
had independently verified all 515 database tables, owners/ACLs, runtime files,
JDBC boot and material definitions; its private report is at
`/home/sat/backups/earthship-energy/runtime-recovery-j2q3iqn3/recovery-report.json`.

The released adapter stopped OpenHAB, saved the stopped Item registry and
pinned Group source privately at
`/home/sat/.local/state/openhab-config-migration/forecast-group-20260924T161521Z`,
removed only the managed `gForecast` record, installed the Git-owned Group
definition and restarted OpenHAB. The old JVM again timed out during SIGTERM
and systemd SIGKILLed it at 10:17:21 MDT. The new service is active under PID
282978. The adapter returned `file_provider_provisional`, verified all ten
member references, file-owned member links, unchanged JDBC IDs and preserved
pre-cutover history. Independent readback found the Group and members
file-owned, both pump Items OFF and protected controls healthy. The ownership
inventory is clean: 391 managed and 41 non-managed Items, zero issues.

The passive inverter-output evidence stream changed from epoch
`9cd81390-b13d-4d35-9779-65fb04c23abe` to
`643d73a8-57bd-41fd-9ec0-c974de3677ca`: sequence 1 was an unavailable
startup barrier, sequence 2 remained unavailable, and sequential valid
receipts began at sequence 3. This observes restart behavior only; it does
not qualify AC-load publication or physical-fault recovery.

The `gForecast` ownership manifest is deliberately `file`/`provisional`, and
the adapter release switch is disabled again. The next natural
`forecast-json.service` run is scheduled for 11:20 MDT. The migration is not
fully verified until that run posts a new forecast series and JDBC persistence
retains all ten member histories without a cutover gap. Keep both the stopped
registry backup and full recovery point until that gate passes. The isolated
recovery test did not validate physical hardware or an atomic whole-host
snapshot.
