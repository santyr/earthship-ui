# Dooya shades: Earthship UI and thermal-learning handoff

## Ownership and present state

The transport adapter remains in the separate
[`santyr/dooya_blinds_openhab`](https://github.com/santyr/dooya_blinds_openhab)
repository (reviewed at `88e09b0`); do not vendor its Python code into this UI.
Its `docs/CODEX_HANDOFF.md`, `docs/MQTT.md`, and `docs/DEPLOYMENT.md` are the
commissioning authority. It targets the existing OpenHAB host and publishes
per-shade MQTT reports; 0 means open and 100 means closed. It has simulated
tests, but has not been commissioned against household hardware.

The operator confirmed September 27 that the 26 shades have **not arrived**.
Read-only host inventory found Mosquitto active and an ONLINE OpenHAB MQTT
broker Thing, but no Dooya/shade control Items; the existing `Moon_ShadeLengthRatio`,
`Sun_ShadeLengthRatio`, and Living Office sensor Items are unrelated and must
not be bound as motor positions. This inventory does not qualify an
authenticated adapter connection or broker security; preserve existing broker
configuration and clients. No broker, Thing, Item, service, motor or rule was
changed for this UI foundation.

## Earthship UI foundation

`src/screens/Shades.svelte` adds a sixth primary page with
26 numbered slots, 13 per view, sized for Lenovo Tab M9 1340×800 and the
1280×720 laptop floor. No location names or RF IDs are guessed. The page has
no movement controls and adds no POST route. Slot mapping lives in
`src/lib/shades/catalog.js`: after commissioning, set each slot's label and
the exact OpenHAB Rollershutter position, availability, and diagnostic-state
Item names. Do not mark a slot mapped from a partial pair.

For display, a position is accepted only when OpenHAB is live, availability is
ON, the adapter JSON is schema 1, `source=motor_report`, `stale=false`, its
original `report_received_at` is at most 30 minutes old, and the scalar
Rollershutter position matches the JSON reported position. NULL/UNDEF,
cache/acknowledgement, future or expired reports, mismatches and an offline
service display as unavailable—not 0% or completed motion. This conservative
UI check is not itself a durable training receipt.

## Observation and learning path

The purpose of the 26-shade data is to learn when opening or closing a
particular window helps heat or cool the Earthship by season, sun position,
time and environmental conditions. The next implementation stage belongs in
the Earthship thermal data pipeline, after one-shade hardware qualification:

1. Record each *motor Report* with shade ID, reported position (including
   intermediate percentages), original adapter reception time, OpenHAB/JDBC
   persistence time, source/provenance, freshness and service/bridge epochs.
   Persist OFFLINE, UNDEF and telemetry gaps as barriers. Commands, bridge
   cache and acknowledgement events are separate evidence, never observed
   positions. Change-only positions need held-state carry only within a
   qualified, covered interval; never infer a transition time from a later
   periodic re-publication.
2. Inventory each shade's window/zone, orientation, glazed area and any
   effective inversion. Join qualified position intervals as-of each model
   origin with indoor/outdoor temperature, solar radiation, cloud/weather,
   season, time, existing vent/shade actions and other thermal disturbances.
   Historical corrections must not leak future knowledge into earlier folds.
   Missing shade coverage must remain unknown rather than assuming all open or
   all closed.
3. Evaluate shade-specific or area-weighted solar-gain and insulation effects
   chronologically against the existing persistence and thermal baselines,
   stratified by heating/cooling season and daylight/night. The current model
   has one coarse `indoor_shade_closed` feature from manual action history;
   do **not** silently map 26 motor reports into that binary feature or treat
   correlation with weather and human decisions as a proven causal benefit.
4. Run any future policy in shadow first. Require measured per-shade outcomes,
   confidence and coverage gates, manual override/hold, explicit command
   ownership, bounded group staggering, stale-report refusal, non-retained
   commands, and supervised single-shade trials before any automation.
   Thermal-model shadow exit and shade-control activation are separate gates.

The adapter's handoff identifies additional prerequisites: real protocol and
percentage validation, post-command Report correlation, broker/bridge/restart
resilience, correct physical direction and limits, and all-shade inventory.
Neither this page nor this handoff changes those requirements.

## Source verification

The Earthship UI suite passed 1,754 unit tests in 115 files and the production
build completed. Browser tests passed for the Shades, Controls, Weather and
Earthship layouts (9 tests), including 1340×800 and 1280×720. The shade tests
checked both 13-slot views, viewport containment and zero command requests.
These checks use fixtures and prove no physical shade behavior.
