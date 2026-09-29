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
One additional test used Solar_PV's disposable PostgreSQL fixture to exercise
the actual three-table SQL with a restricted reader: partial positions joined
at their stored times, an oversized diagnostic became a barrier, revoking one
table's SELECT withheld the entire result, and every reader connection closed.
The fixture container and volumes were removed by the harness; no household
database or shade hardware was used.

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
and one per room group. The drawn window approximates the actual 32:88
width-to-height ratio at 26×72 CSS pixels. On the 1340×800 Lenovo canvas,
each card is capped at 72 CSS pixels wide, with full visible room and shade
labels; the four groups remain on the two established views. The group display shows a single
percentage only when every member has the same fresh qualified motor report;
mixed or missing members never produce a fabricated aggregate position. All
sliders and open/close buttons remain disabled until hardware commissioning and
a reviewed command owner exist. Browser regressions at 1340×800, 1280×720 and
900×800 passed with zero movement requests, no room-label truncation, no horizontal
overflow, and all 27 individual plus four group sliders present across views.
The September 28 tablet-width correction keeps each zone on a single row down
to 700 CSS pixels. At 700–899 pixels the cards, window outlines and sliders
are narrower; the five-column wrap now begins only below that range. A short
landscape viewport can scroll within the Shades page to reach both complete
zones, while 800×600 and the documented 1340×800 Lenovo canvas show both zones
without scrolling. These are CSS viewport checks, not a physical-device signoff.
The later September 28 compactness pass reduces the card cap from 58 to 52 CSS
pixels at the 1340×800 Lenovo reference viewport, and to 46 CSS pixels at
700–899 pixels. The individual window outline and vertical slider remain
separate. Six focused browser cases pass across the five landscape sizes and
the short-tablet scroll case; physical Lenovo readability still needs operator
confirmation.

The September 29 tablet-control refinement lets the individual and room-group
vertical tracks use the available card height instead of the old 50–55 CSS
pixel cap. On the primary 1340×800 Lenovo viewport, browser checks now require
at least 120 CSS pixels of slider travel; the 1280×720 laptop floor requires at
least 95, and compact 700–899-pixel landscape views at least 75 without page
overflow. A separate, narrow all-27-shades column spans both visible room
rows, providing one master percentage display and vertical slider in addition
to the existing per-zone and individual sliders. Mixed or unreported positions
show no fabricated master percentage. All controls remain disabled until
commissioned; the all-shades slider does not submit movement commands.
For eventual touch operation, a slider is a useful quick approximate control,
but not a sufficiently precise *sole* percentage setter on a narrow tablet
card. Keep the visible percent readout and open/close buttons; commissioning
should test touch/assistive interaction and provide an explicit exact-percent
or small-step adjustment path before enabling movement. A master adjustment
also needs the command owner's reviewed staggering and per-motor report checks.
This is a UI decision, not permission to energize the motors.

## Planned fine control and voice operation (not enabled)

Keep the vertical sliders for quick approximate adjustment, and add paired
**Open +5%** and **Close -5%** buttons beside each individual, zone, and
all-shades control. The step is five percentage points of *percent open*,
clamped to 0–100; provide an exact-percent entry for targets that the slider
cannot set reliably by touch. Retain separate **Open fully** (100% open) and
**Close fully** (0% open) actions, so a nudge is never confused with an endpoint
command. Each control must show the requested target and the subsequent
reported position separately. If any member's report is missing or mixed, do
not manufacture a group starting percentage; the command owner must require an
explicit absolute target or decline a relative group step. Tablet touch size,
keyboard and assistive operation require physical Lenovo acceptance testing.

Voice should support open, close, stop, and absolute percent-open positions for
individual shades, named zones, and all shades. Proposed unambiguous forms are
"Open Kitchen shades fully", "Close Living Room shade 2", "Set all shades to
76% open", and "Set Kitchen shades to 25% open". A spoken "close ... to 45%"
means a target of **45% open**, not 45% closed or 45 points of travel; if the
recognizer cannot preserve that meaning, ask for clarification and do not move.
"Living Room shades 2 and 5" refers to within-zone aliases only after their
physical inventory is assigned. A multi-shade arbitrary subset in one
utterance is *not* assumed to work with an off-the-shelf smart-home skill;
predefined named subgroups or a reviewed interpreter would be needed. A
command like "Open all shades 76%" should be accepted only if the selected
voice provider demonstrably maps it to 76% open in an attended one-shade test;
otherwise use the explicit "Set ... to 76% open" form.

Out-of-the-box candidates: openHAB's Alexa skill or Google Assistant action
can expose Rollershutter endpoints with open/close and percentages through
myopenHAB. The openHAB Android app can send recognized speech to a rule-based
interpreter, but that route needs command rules and a tap/voice entry point;
it does not establish an always-listening "Computer" wake word on a Lenovo
tablet. Alexa documents "Computer" as a wake word for hands-free Alexa
devices, not a promise for the Android Alexa app. Verify actual Lenovo voice
capture and wake behavior before selecting a provider; cloud exposure and
privacy need operator approval. No voice endpoint may send directly to a raw
all-shades/group Item: all UI and voice requests must pass through the same
reviewed command owner for membership checks, motor staggering, limits,
STOP, post-command Report correlation, and failure handling. Keep every path
disabled until shade hardware, physical direction, inventory, and one-shade
voice percentage tests are complete.

References: https://www.openhab.org/docs/ecosystem/alexa/ ,
https://www.openhab.org/docs/ecosystem/google-assistant/ ,
https://www.openhab.org/docs/apps/android , and
https://digprjsurvey.amazon.com/csad/help/node/201602230 .

September 29 input-path refinement (research, not a provider decision): prefer
a persistent, labelled **Voice command** push-to-talk button in the Earthship
UI left navigation on the Lenovo. Show a clear listening indicator and the
recognized words and target before submission; an uncertain shade name,
percentage or direction must be rejected rather than guessed. The browser
microphone/recognizer and its permission model must be tested on the actual
tablet. The OpenHAB Android app's native voice entry is a possible alternative,
but do not assume its voice button can be embedded in this separate web UI.
Neither choice requires a custom speech recognizer; the web-button path may
still need a small UI-to-OpenHAB command integration. Keep voice input distinct
from authorization to move a motor.
The current `Shell.svelte` uses a 60 CSS-pixel left rail above 900 CSS pixels,
including the 1340×800 Lenovo reference size, and bottom tabs below that
breakpoint. Treat voice as a separate action in the rail, not a seventh page;
choose an accessible header or equivalent action for the bottom-tab layout so
it does not squeeze six existing destinations. Verify touch size and placement
in both layouts before implementation.

Physical Dooya remotes are a **separate direct control path**, outside OpenHAB
and the Earthship UI command owner. Software cannot authorize, delay, or block
their commands. Where the adapter receives their resulting motor Reports, those
reports must update the same per-shade position history and thermal-learning
features, even when OpenHAB issued no command. Attribute a remote origin only
if the adapter actually exposes one; otherwise record `external_or_unknown`,
not an invented person or control source. Reconcile observed remote movement
with pending UI/voice/automation requests and avoid automation immediately
fighting a manual change; the holdoff policy is a commissioning decision. If
the adapter cannot observe a remote-triggered movement, mark position/history
unqualified until a later actual motor report instead of assuming state.

The networked NVIDIA SHIELD is another candidate voice entry point. NVIDIA
documents Google Assistant smart-home control via the SHIELD remote's voice
button; hands-free activation depends on specific controller hardware, so the
actual device must be checked. An OpenHAB Google Assistant endpoint could
receive individual/zone/all commands from it, subject to the same command-owner
and percent-direction tests. This path uses cloud linkage and should remain an
option pending privacy and reliability review, not the assumed architecture.
References: https://support-shield.nvidia.com/shield-tv-user-guide/Google_Assistant_on_SHIELD_TV.htm ,
https://support-shield.nvidia.com/shield-tv-user-guide/SHIELD_Remote-atv.htm ,
and https://www.openhab.org/docs/ecosystem/google-assistant/ .
