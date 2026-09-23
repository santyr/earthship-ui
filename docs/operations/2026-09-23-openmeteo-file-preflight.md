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
Its ten explicit overrides plus the installed binding's current defaults
match all non-secret effective live settings: zero mismatches across the three
Things. The existing live coordinates were preserved; no coordinate change was
smuggled into the provider migration. This comparison does not establish
channel runtime equivalence after provider loading.

The installed OpenHAB 5.2.1 Thing DSL parser accepted exactly one bridge and
two Thing declarations and rejected malformed syntax. Run the bounded offline
check with `python3 scripts/check-openmeteo-things-parser.py`. This does not
create a second provider or contact OpenMeteo.

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
