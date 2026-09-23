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

Syntax and bridge reference conventions were checked against the
[official openHAB Thing file documentation](https://www.openhab.org/docs/configuration/things).
The binding's [own configuration documentation](https://github.com/obones/openhab-binding-openmeteo)
describes the dynamic forecast/AQI channel groups and current-data options.
