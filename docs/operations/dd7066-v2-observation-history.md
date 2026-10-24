# DD7066 v2 received-Report history preparation

This is an uninstalled, source-only acquisition family for the adapter's schema-v2
observations. It does not qualify DD7066 hardware, publish or change a forecast,
replace a model feature, create a training label, collect live data, or enable
movement. Observation stays independent of zone automation preferences and
`OverrideSwitch`; those permissions are not accepted as reader inputs.

The original [`shade_observations.py`](../../openhab/scripts/thermal_model/shade_observations.py)
and [`shade_history.py`](../../openhab/scripts/thermal_model/shade_history.py) remain
byte-identical for their original schema-v1 producer and replay. Their SHA-256
identities are respectively
`a465dc7a269da058355672a3a715344b53023567aaa8776b2f645ff200e7ccd2` and
`5a9aefbbd6378845279ef21ea6db7ebb99f5a5dbb0323032f9e14c4d9f3ed806`.
The original reader explicitly refuses the new schema; there is no compatibility
fallback or reinterpretation of an original producer's receipts.

The new files are
[`shade_observations_v2.py`](../../openhab/scripts/thermal_model/shade_observations_v2.py)
and [`shade_history_v2.py`](../../openhab/scripts/thermal_model/shade_history_v2.py).
`fetch_shade_intervals_v2(connection_factory, *, items, profile, start, end, as_of)`
returns `earthship-dooya-observation-history/v2`, family `dooya_report_receipt`.
Its qualification scope is only `received_report_continuity_only`;
`action_qualified`, `preference_qualified`, and `measurement_time_known` remain
false. No existing thermal producer, dataset builder, model registry or binary
`indoor_shade_closed` feature imports this new family.

Each individual shade needs an explicit private profile containing exactly
`schema="earthship-dooya-observation-profile/v2"`, `shade_id`, `bridge_id`,
`device_id`, `commissioned_epoch`, `source_identity_sha256`, and
`commissioning_ref`. The uppercase device identities, canonical commissioning
UUID and SHA-256 of the compact sorted ASCII identity object must agree. This is
a reference to the actual installation's commissioning record, not evidence that
hardware has been commissioned merely because a profile can be parsed. New
firmware/hardware commissioning must use its actual new epoch. Historical
observations cannot borrow the current mapping's epoch or identity digest.

Eight exact, distinct OpenHAB Item names must be supplied; there are no default
or guessed household Item IDs:

| Role | Original persisted value |
| --- | --- |
| `diagnostic_state` | Adapter schema-v2 shade JSON |
| `availability` | Individual shade `ON`/`OFF` |
| `scalar_position` | Native percent closed, integer 0–100 |
| `service_availability` | Adapter `ON`/`OFF` |
| `bridge_availability` | Bridge `ON`/`OFF` |
| `service_state` | Adapter schema-v2 health JSON |
| `bridge_state` | Bridge schema-v2 health JSON |
| `provider_status` | Actual provider Thing `ONLINE`/other status |

The callable collector software is prepared in
[`shade-provider-history.js`](../../openhab/file-config/automation/js/shade-provider-history.js).
It exports `readShadeProviderHistoryMappings(path)` (read-only file access) and
`registerShadeProviderHistory(api, mappings)`. The separate
[`mapping JSON template`](../../openhab/file-config/shade-provider-history.mapping.example.json)
is an empty array. Its closed entries are exactly `{slot, thingUID, statusItem}`,
with at most 26 slots in 1–26, unique slots/targets, literal exact Thing UIDs and
String targets restricted to `Shade_*_ProviderStatus`. Several logical shades
may share an actual provider UID with distinct status Items. Extra fields,
owner keys/MQTT credentials, duplicate JSON keys, wildcards and arbitrary Item
writes are refused. No default private path, Thing UID or active registration
is supplied.

The separate
[`26 logical Item examples`](../../openhab/file-config/items/shade-provider-history.items.example)
are unlinked String definitions only; the `.example` suffix leaves them outside
normal Item loading. They are proposed logical names, not installed or verified
household resources. No ownership manifest or provider has been transferred.
Future installation must inventory the actual provider Thing, create and verify
its observational Item, and supply the private mapping file. Its selected
`statusItem` is the SQL reader's `items['provider_status']`. The reader profile's
commissioning reference is maintained separately from this credential-free
mapping. Private commissioning mappings must not be replaced with the empty
example as a live installation change.

The factory registers actual `ThingStatusChangeTrigger` events plus a startup
reconciliation using the mapped Thing's current registry status. Startup/hot
load first posts `UNDEF` to invalidate restored `ONLINE`; source lookup failure
or unknown status also produces `UNDEF`. An outage event remains an `OFFLINE`
barrier even if the registry has already advanced, while an old `ONLINE` event
cannot override a currently unavailable provider. The only writes are
`postUpdate` on the restricted String targets. There are no commands, timers,
polls, MQTT publications, policy writes or motor operations. The preserved
source `jdbc.persist` wildcard uses `everyChange, restoreOnStartup`; it captures
these transitions once the explicit observation Items and collector are
installed. This is not a claim of JDBC delivery or installed continuity from an
API enqueue: natural event/JDBC readback, reload, outage and restart remain
installation acceptance checks.

Trigger signatures and event fields follow the
[official openHAB JS trigger reference](https://openhab.github.io/openhab-js/triggers.html)
and [official event-property contract](https://github.com/openhab/openhab-js#event-object).
The maintained VM tests in `tests/openhab/shade-provider-history.test.js` exercise
empty defaults, startup/status barriers, shared providers, lookup failure,
strict mapping/type bounds, preserved JDBC source selectors and absence of
commands. Actual runtime installation and persistence remain unqualified.
Missing role mapping fails before SQL; missing provider history withholds every
usable interval while preserving separately labeled original Report
observations. The private Item mapping, installation and actual commissioned
hardware are the remaining dependencies; callable collector software is ready.

The reader obtains one dedicated read-only `REPEATABLE READ` transaction, resolves
all eight exact Item names to unique tables, and reads only `SELECT`, `SHOW` and
transaction-local timeout settings. It closes without committing. A call is
bounded to 10,000 combined source rows, two elapsed days, one pre-window carry
per role and values of at most 8,192 bytes. `end <= as_of` and SQL's exclusive
end boundary prevent later stored rows from rewriting an earlier origin.
Missing/ambiguous mapping, duplicate source timestamps, query/grant failure or
bound violations refuse the complete acquisition. Oversized/NULL values remain
barriers rather than being skipped.

Independent Item writes are not assumed atomic: cross-role timestamp ties and
availability transitions require later diagnostic reconciliation. Current
coverage additionally requires matching adapter session and source generation,
matching original commissioning identity, matching scalar position, usable
stationary-report metadata and health no older than 90 seconds. Original
Report bounds use the recorded adapter-monotonic interval's duration anchored
to the original UTC receipt, capped at 30 minutes. Later publisher/health/cache
clocks never extend that original bound. A repeated Report after an outage or
health gap cannot reopen coverage; a new ordered Report is required.

The separate original observations retain individual partial percentages,
original received/validated times, upstream message ID, adapter session,
source generation, identity digest, commissioning epoch/reference and the first
storage boundary encountered in the bounded read. The upstream timestamp-shaped
ID is a working ordering contract, **not a motor measurement timestamp**.
Physical boot identity, measurement time, delivery age and actor remain unknown.
A target, cache Ack, human command or matched target does not turn the position
into a causal completion, human preference or optimal-action training label.

Maintained regressions live in `test_thermal_shade_observations_v2.py`,
`test_thermal_shade_history_v2.py`, and
`test_thermal_shade_history_v2_postgres.py`. The PostgreSQL test requires the
explicit `advisory_db_fixture` disposable harness and a cached `postgres:16`
image. It has no external/household DSN fallback, verifies all eight real role
queries and repeatable-read behavior during a concurrent fixture update, tests
oversized-value and revoked-SELECT refusal, and closes reader connections. The
provided fixture removes its container; its current `docker rm --force` cleanup
does not request anonymous-volume removal, so volume cleanup is not claimed.
Original v1 unit and PostgreSQL tests
remain part of the regression run. These tests certify synthetic software
behavior only; actual report continuity and physical/DD7066 commissioning stay
separate.
