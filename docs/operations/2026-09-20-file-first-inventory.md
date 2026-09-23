# File-first migration inventory boundary

Live registry read on September 20, 2026, after the first Item transfer:

| Resource | Managed | Non-managed | Verified file-owned |
| --- | ---: | ---: | ---: |
| Items | 427 | 1 | 1 |
| Things | 84 | 0 | 0 |
| Rules | 35 | 0 | 0 |
| Item/channel links | 261 | 0 | 0 |

`openhab/scripts/config_inventory.py` reproduces this registry graph through GET
requests only. The first run found no duplicate identities, unresolved Item/group,
Thing/bridge or Item/channel link references, or discrepancies against the current
ownership manifest. This is structural evidence, not proof of control safety.
Six unit tests cover omission of sensitive values, graph references, provider
ambiguity, ownership drift, duplicates and absent declarations.

Follow-up inventory adds Thing, channel and link configuration **key names only**.
Eight tests now cover value omission and absent configuration. Live readback still
has the same counts and no structural issues. Eleven links have configuration;
their keys include `profile` and `function`, so migrating links without their
private value review would lose behavior. Thing configuration includes credential
fields (API keys, passwords and Zigbee network/link keys). Values were neither
printed nor exported. A blanket Things-to-Git export is therefore inappropriate;
secret-bearing resources need private provisioning or documented exceptions.

The installed `/usr/share/openhab/runtime/bin/backup` was inspected, not executed.
Its `--noninteractive` mode writes an archive under `/etc/openhab/html`, which is
unsuitable for credential-bearing recovery material. Its normal mode copies live
configuration/userdata and is not an atomic snapshot or proof of clean restart.
Any future use must have dedicated private staging and destination paths; external
PostgreSQL, systemd configuration and learned artifacts still require separate
coverage. No backup or production configuration was changed by this inspection.

## Remaining migration scope

September 23 live refresh: the read-only extended inventory reports 422 managed
and seven non-managed Items, 81 managed and three non-managed Things, 261
managed and one non-managed link, 35 managed rules, one non-managed JDBC
strategy, and zero structural/ownership issues. It also sees 18 add-ons, 12 UI
pages and 15 transformations. This is still non-atomic and not a restore export.

The next staged observational candidate is `Current_US_AQI`. Its live managed
definition is a Number labeled “Current US AQI,” category `airquality`, with a
`Measurement` tag and a single managed link to the file-owned OpenMeteo AQI
Thing. A prepared Git source preserves those identifiers and passed the
installed OpenHAB 5.2.1 Item grammar and a focused source test. It is **not**
installed or declared file-owned: provider/link behavior, state recovery,
JDBC continuity and rollback still need isolated qualification and an attended
cutover. No second Item/link provider was created.

14:16 MDT extension: `config_inventory.py --extended --summary` now also
verifies explicit link ownership and inventories 18 installed add-ons, 12 UI
pages and 15 registered transformations without reading their settings into
output. Ten tests pass, including secret-value exclusion and link ownership
drift/absence. The live core graph has 427 managed plus two file Items, 261
managed plus one file link, 84 Things and 35 rules, with no detected issues.
This does not establish additional provider transfers, script dependency
resolution, complete filesystem coverage or restore qualification.

1. Review each observational Item's metadata, link profiles, state restoration,
   writer and consumers before selecting further transfers. A String Item is not
   inherently safe: it may carry safety observations or operator commands.
2. Inventory Thing configuration and binding-specific secret dependencies before
   generating text definitions. Preserve UIDs, channels, bridges and polling
   parameters. Do not combine Modbus bridges as an incidental migration change.
3. Inventory rule scripts, triggers, dependencies and runtime/cache ownership.
   Registry graph checks cannot resolve code-generated Item names. Preserve pump
   timing and fail-closed controls; qualify restore/restart/rollback before moving
   protected resources. No duplicate active rule or competing timer is acceptable.
4. Inventory persistence strategies, transformations, UI pages, add-ons, exec
   scripts and external systemd publishers. Determine the supported declarative
   source or reproducible managed exception for each. Existing registry totals
   do not include these resources and must not be called a complete inventory.
5. Establish protected backups for credentials, userdata, PostgreSQL history and
   learned models, then rehearse clean-system restoration. Git definitions alone
   cannot recover the running installation. Temporary cutover receipts are not
   a substitute for durable backups.

No additional live provider transfer occurred during this inventory. Task 82
remains held; feeder work owned by another agent is not included in this change.

## Persistence and backup follow-up

Live `/persistence` reports only JDBC. `/persistence/jdbc` is managed and has three
entries: global everyChange/restore excluding `Power_Evidence_JSON`, group
`gForecast*` forecast/everyChange, and explicit power-evidence restore. There are
no aliases, custom cron strategies or filters. Prepared `jdbc.persist` matches
the live DTO through a closed, tested renderer. It is not installed; managed
ownership remains unchanged. Existing change-only semantics must be preserved.

The weekly `energy-backup-check.service` still reads the August 20 full-database
manifest. Its September 20 03:31 run reported `fresh:false`, `readable:true`,
`restore_verified:true`, `off_host:false`, `disaster_recovery:false`, Actionable.
Systemd success is expected because exit statuses 10/20 are accepted; it does not
mean backup coverage is healthy. The recent September 20 restore rehearsal is
only `energy_analytics`, not public telemetry, thermal models, configuration or
credentials. Substituting that manifest would narrow the monitored recovery
scope, so the reference was intentionally not changed. A refreshed full restore
point is still needed; the off-host destination remains explicitly deferred.
