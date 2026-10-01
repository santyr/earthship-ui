# `gForecast` attended cold cutover — verified receipt

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

The natural OpenMeteo binding refresh at 11:17:49 MDT—not the separate
`forecast-json.service` JSON refresh at 11:21—published all ten expected
48-hour/7-day time series as `ItemTimeSeriesUpdatedEvent` events. Read-only
JDBC readback retained IDs 563–572 and showed 48 contiguous hourly targets
from September 24 17:00Z through September 26 16:00Z for each hourly member,
and seven contiguous daily targets from September 24 through September 30 for
each daily member. The four hourly tables advanced from 726 to 727 cumulative
rows across the natural refresh; the daily tables retained 40 rows each as
their same-day target timestamps were refreshed. PostgreSQL MVCC row markers
corroborate new writes: the seven current `Forecast_Daily_High` targets have
`xmin` 286630672–286630678, while the prior September 23 target remains at
286153133; the other sampled daily tables and the new hourly horizon likewise
carry the new transaction range. The Group is still
file-owned with ten file-owned members/links, the OpenHAB ownership inventory
has zero issues, and OpenHAB remains active. The independent 11:21 JSON
refresh also exited successfully and re-armed its timer, but was not used as
evidence for the Group's series gate.

The ownership manifest is now `file`/`verified`; the attended restart adapter
remains re-locked with `RELEASE_READY = False`. The stopped registry backup
and full recovery point are retained. This verifies the provider and natural
series/JDBC continuity, not physical hardware recovery or an atomic
whole-host snapshot.

## September 30 current-state follow-through

At `2026-10-01T00:41:26.830777Z` (September 30 18:41 MDT), a fresh read-only
check confirms the Group, all ten exact members and their ten links remain
non-managed, declared file/verified. Group type/label/tags/metadata/membership
match the qualified definition. Canonical sources match deployed files exactly:

| Item source | SHA-256 |
| --- | --- |
| `items/forecast-group.items` | `a9816041107155acbaa7683208a32d82a0d31a5698e53e4400209b1cd6146506` |
| `items/openmeteo-forecast-temperature.items` | `10d702cba64f1bca213f4db9229107ed04bd12db5d28448026fe9200f118e9fc` |
| `items/openmeteo-forecast-meteorology.items` | `b47c97c492206a51c05d5ea75b86c5be24390268a589dd0db90daaf11f64df5a` |
| `items/openmeteo-forecast-daily.items` | `9f1236706f3e33748e9a6069ce01fe44dfebc111d699bbaa6c34f4f77f957fea` |

Bounded JDBC REST reads find 48 unique contiguous one-hour targets in each
hourly member (`00:00Z October 1` through `23:00Z October 2`) and seven unique
contiguous daily targets in each daily member (`00:00Z October 1` through
`00:00Z October 7`). These are UTC target timestamps, not an inference of
weather issue time or forecast accuracy. The previous September 24 event/JDBC
receipt remains the natural post-cutover writer evidence.

The current registry inventory has zero issues: 382 managed / 62 non-managed
Items, 80 / 5 Things, 37 / 5 rules and 246 / 21 links. Separate live readback
also confirms the JDBC persistence provider is non-managed, declared
file/verified and its strategy file matches canonical source bytes exactly.

The current execution queue had mistakenly described `gForecast` as still
managed. That entry is corrected. **Do not repeat this cold cutover or ask for
another `gForecast` restart.** Remaining managed-resource migration and general
protected-control/whole-host recovery are separate outstanding work. This
follow-through changed no production configuration, Item, control or service.
