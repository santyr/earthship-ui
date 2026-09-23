# OpenMeteo Thing file-first preflight

September 23, 2026. Source-only preparation; no live Thing, link, Item,
binding, polling schedule or forecast publisher was changed.

The three managed Things are `openmeteo:openmeteo:local` (bridge),
`openmeteo:forecast:local:site`, and `openmeteo:air-quality:local:aq`.
All three were `ONLINE/NONE`. The two child Things have 12 active managed
Item/channel links between them, including `Forecast_Temp` and
`Current_US_AQI`. The bridge has no populated API key or proxy credentials.
The UI's corrected ten-day forecast is a separate direct Open-Meteo publisher;
this binding still supplies several Item-level weather and AQI channels.

The proposed Git-owned definition is
`openhab/file-config/things/openmeteo.things`. It preserves the three UIDs,
labels, bridge relationship and location currently in the live registry.
Its eight explicit supported overrides plus the installed binding's current
defaults match all non-secret effective live settings recognized by that
binding. Two extra managed forecast keys, `includeTemperatureMin` and
`includeTemperatureMax`, are absent from the installed Thing-type metadata and
from the binding JAR's class constants. They are stale configuration entries,
not supported behavior, and are intentionally not copied into the file.
The existing live coordinates were preserved; no coordinate change was
smuggled into the provider migration. This comparison does not establish
channel runtime equivalence after provider loading.

The installed OpenHAB 5.2.1 Thing DSL parser accepted exactly one bridge and
two Thing declarations and rejected malformed syntax. Run the bounded offline
check with `python3 scripts/check-openmeteo-things-parser.py`. This does not
create a second provider or contact OpenMeteo.

An attempted networkless, disposable clean-image provider boot on September 23
did **not** qualify the provider. The first harness variant hid the image's
required Karaf configuration; a later variant hit an image/host
`no-new-privileges` entrypoint incompatibility. With those harness faults
isolated, the pinned image reached its startup sequence and remained healthy,
but `/rest/things` did not return a successful registry response within the
bounded 180-second observation. The HTTP status was not captured, so neither
Thing creation nor a provider error is inferred. All owned test containers and
their overlays were removed; live OpenHAB and its thermal timer stayed active.
Use the proven restore-based isolated runtime with authenticated REST readback
for the next qualification; do not repeat this bare-image result as a pass.

Before production ownership transfer, qualify the file in an isolated 5.2.1
runtime without duplicate managed UIDs. Require exact Thing UID/config and
linked channel identity readback, all 12 link targets resolved, dynamic
weather/AQI channel presence, rollback to managed ownership, and a clean
restart. Then take a private managed-definition/state backup and execute a
bounded attended cutover without deleting Item or JDBC history. Keep the
current managed Things authoritative until those checks pass.

## Superseding qualification and production transfer

The later restore-based, networkless rehearsal passed every required provider
phase using the pinned OpenHAB 5.2.1 image and the installed OpenMeteo 0.5.0
binding. First file-owned boot, full JVM restart, managed-definition restore,
REST `force=true` managed removal followed by file creation, and the online
file-to-managed REST rollback all produced the same three UIDs, supported
effective configuration, 1/38/12 channel sets, and all 12 Item/channel links.
Normal REST DELETE had returned success without removing the Things while the
networkless handler was awaiting cleanup; immediate force removal was therefore
qualified in isolation. The test container and overlay were removed. No
synthetic weather measurement or external API receipt was claimed.

At approximately **10:51 MDT on September 23**, the attended production
transfer passed its preflight and installed the Git-owned file. A fresh private
rollback snapshot is at
`/home/sat/.local/state/openhab-config-migration/openmeteo-20260923T165101Z`:
directory mode `0700`, REST definition and original Thing/link JSONDB files
mode `0600`. It contains sensitive configuration from other Things and must
not be committed or exposed. The installed `.things` file is mode `0644`,
SHA-256 `2d0f1fc402a23115a54bc0e3ce110eacc4424581903fcaed77f4923535d6b585`,
identical to the tracked source. No OpenHAB JVM restart was made.

Independent REST and filesystem readback at 10:51–10:53 MDT found all three
Things `ONLINE`, `editable:false`, with 1/38/12 channels. Exactly 12 unique
managed links remain, and the live link JSONDB hash is byte-identical to its
private pre-transfer backup. None of the three UIDs remains in managed Thing
JSONDB. `Forecast_Temp`, both bound daily extrema, `Current_US_AQI`, and the
separate direct-publisher `Forecast_10Day_JSON` have valid Item states. The
ownership inventory reports **81 managed / 3 non-managed Things** and zero
structural issues. No forecast or AQI value was manufactured.

At immediate post-cutover readback, no new JDBC row for the bound forecast/AQI
Items had yet appeared after 16:51:01Z. This is a pending natural refresh
check, not a failed binding: the Things were online and their Items retained
valid states. Confirm a new natural update later, including the expected
change-only persistence behavior. Off-host recovery of the private snapshot
remains a separate installation-wide gap.

Syntax and bridge reference conventions were checked against the
[official openHAB Thing file documentation](https://www.openhab.org/docs/configuration/things).
The binding's [own configuration documentation](https://github.com/obones/openhab-binding-openmeteo)
describes the dynamic forecast/AQI channel groups and current-data options.
