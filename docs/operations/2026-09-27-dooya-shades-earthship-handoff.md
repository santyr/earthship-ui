# Dooya shades: Earthship UI and thermal-learning handoff

## Ownership and present state

The transport adapter remains in the separate
[`santyr/dooya_blinds_openhab`](https://github.com/santyr/dooya_blinds_openhab)
repository (reviewed at `88e09b0`); do not vendor its Python code into this UI.
Its `docs/CODEX_HANDOFF.md`, `docs/MQTT.md`, and `docs/DEPLOYMENT.md` are the
commissioning authority. It targets the existing OpenHAB host and publishes
per-shade MQTT reports; 0 means open and 100 means closed. It has simulated
tests, but has not been commissioned against household hardware.

The operator confirmed September 27 that the 27 shades have **not arrived**.
Read-only host inventory found Mosquitto active and an ONLINE OpenHAB MQTT
broker Thing, but no Dooya/shade control Items; the existing `Moon_ShadeLengthRatio`,
`Sun_ShadeLengthRatio`, and Living Office sensor Items are unrelated and must
not be bound as motor positions. This inventory does not qualify an
authenticated adapter connection or broker security; preserve existing broker
configuration and clients. No broker, Thing, Item, service, motor or rule was
changed for this UI foundation.

## Earthship UI foundation

`src/screens/Shades.svelte` adds a sixth primary page with 27 numbered slots,
sized for Lenovo Tab M9 1340×800 and the 1280×720 laptop floor. The owner
confirmed Kitchen 1–8 and Living Room 9–17 on the first view, Bathroom 18–22
and Bedroom 23–27 on the second. Cards and zone controls use room names so
operators never need to infer the zone from a number. No individual window
location or RF ID is guessed. The page shows percent **open** as
`100 - reported_position`, while preserving the adapter's 0=open, 100=closed
contract. Slider presentation and all/zone open/close controls are present but
disabled; no movement POST route exists yet. Enabling them requires an owner
path that serializes/group-staggers commands and verifies post-command motor
Reports under supervised commissioning. Slot mapping lives in
`src/lib/shades/catalog.js`: after commissioning, set each slot's label and
the exact OpenHAB Rollershutter position, availability, and diagnostic-state
Item names. Do not mark a slot mapped from a partial pair.

For display, a position is accepted only when OpenHAB is live, availability is
ON, the adapter JSON is schema 1, `source=motor_report`, `stale=false`, its
original `report_received_at` is at most 30 minutes old, and the scalar
Rollershutter position matches the JSON reported position. NULL/UNDEF,
cache/acknowledgement, future or expired reports, mismatches and an offline
service display as unavailable—not 0% or completed motion. This conservative
UI check is not itself a durable training receipt. An unavailable position
has no slider thumb or fabricated percentage.

## Observation and learning path

The purpose of the 27-shade data is to learn when opening or closing a
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
   periodic re-publication. Store both raw percent-closed and derived percent-
   open so the UI and model share an unambiguous conversion; a partial position
   is not forced into a binary open/closed class.
2. Inventory each shade's window/zone, orientation, glazed area and any
   effective inversion. Join qualified position intervals as-of each model
   origin with indoor/outdoor temperature, solar radiation, cloud/weather,
   season, time, existing vent/shade actions and other thermal disturbances.
   Historical corrections must not leak future knowledge into earlier folds.
   Missing shade coverage must remain unknown rather than assuming all open or
   all closed. The existing Hallway temperature Item is the Kitchen-area
   reference and a *provisional proxy* for Living Room and Bedroom. Bathroom
   has no qualified temperature source yet. The catalog labels these distinct
   roles; future in-zone sensors replace proxies prospectively, preserving
   historical source provenance. Do not claim Bathroom thermal outcomes from
   the Hallway series or silently label proxy measurements as direct.
3. Build time-weighted percent-open intervals only within qualified source
   coverage. Pair each room's interval with its labeled temperature source and
   delayed temperature outcomes; test solar-gain effects in daylight and
   insulation effects at night, conditioned on season, sun angle, outdoor
   weather and other actions. Evaluate shade-specific or area-weighted effects
   chronologically against persistence and thermal baselines, with held-out
   origins and no future report leakage. A proxy sensor is lower-quality
   evidence, not a direct room outcome. The current model
   has one coarse `indoor_shade_closed` feature from manual action history;
   do **not** silently map 27 motor reports into that binary feature or treat
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

## Source-only motor interval foundation

`openhab/scripts/thermal_model/shade_observations.py` now accepts one shade's
already-joined, chronological diagnostic JSON, availability, scalar-position
and persistence-time rows. It requires a matching fresh `motor_report`, keeps
the original report timestamp, derives percent open without binarizing partial
positions, and emits only intervals knowable after their persistence time.
Repeated publications of one report do not refresh its 30-minute limit;
offline, unknown, malformed, stale, cache-only, scalar-mismatched and
out-of-order rows break coverage. A prior valid report can carry into a later
window only until its original expiry. Queries are capped at 10,000 rows and
two days per call; even a streaming input stops after one over-limit row.
Twelve focused tests and all 703 thermal Python tests pass.

This pure reader does **not** query JDBC, prove the three Item histories share
an atomic observation boundary, collect hardware events, join temperatures,
fit a model, publish an advisory, or command a motor. Those stages require the
installed inventory and natural report evidence. In particular, the existing
coarse `indoor_shade_closed` feature remains unchanged.

The next source-only step joins separately persisted diagnostic, availability
and scalar-position Item changes at their actual persistence timestamps. It
allows at most one pre-window carry per Item, admits no future rows, and refuses
more than 10,000 total changes. A cross-Item timestamp tie is a coverage
barrier, not proof of atomic publication; an offline-to-online transition
requires a later diagnostic before position coverage resumes. A scalar value
arriving after a motor diagnostic starts coverage only when that scalar was
stored, with no backdating. Seventeen focused shade tests and all 708 thermal
Python tests passed at that checkpoint.

`openhab/scripts/thermal_model/shade_history.py` now supplies the source-only
JDBC acquisition boundary. It requires three exact, distinct commissioned Item
names, resolves their unique IDs inside a dedicated read-only repeatable-read
transaction, and bounds the combined original history to 10,000 rows over at
most two elapsed days. It retains one pre-window carry per Item and NULL or
oversized values as barriers, then applies the same change-only join and
motor-report qualification. Queries do not extend past the explicit as-of
origin. Fourteen new focused tests cover mapping, transport, row bounds,
partial percentages, cross-Item ordering and future-origin refusal; all 723
thermal tests pass. This is not a configured production reader: there are no
commissioned Item names or restricted grant yet, and real Report continuity,
temperature pairing and chronological learning remain separate gates.

## Source verification

The revised 27-slot, zone-paired version passed all 1,755 UI unit tests in
115 files, the production build and nine affected browser checks at 1340×800
and 1280×720. The tablet browser confirmed both view layouts, disabled
all/zone controls and zero command requests. A read-only visit to the running
local `#/shades` route then showed Kitchen/Living Room with 17 cards,
Bathroom/Bedroom with 10, `27 planned · 0 mapped · 0 reporting`, disabled
all-shade control, zero non-GET requests and no page errors. These checks prove
UI deployment, not physical shade behavior or Dooya adapter installation.

The September 27 vertical-control revision adds one percentage track per shade
and one per room group. The drawn window uses the actual 32:88 width-to-height
ratio at 32×88 CSS pixels. On the 1340×800 Lenovo canvas, each card is capped
at 88 CSS pixels wide, with full visible room and shade labels; the four
groups remain on the two established views. The group display shows a single
percentage only when every member has the same fresh qualified motor report;
mixed or missing members never produce a fabricated aggregate position. All
sliders and open/close buttons remain disabled until hardware commissioning and
a reviewed command owner exist. Browser regressions at 1340×800 and 1280×720
passed with zero movement requests, no room-label truncation, no horizontal
overflow, and all 27 individual plus four group sliders present across views.
