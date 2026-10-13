# Distributed sensing validation receipt — 2026-10-13

Implemented in isolated branch `feat/lorawan-sensors-20261013` from merged
`origin/main`3d118d6. Main checkout's concurrent changes were not edited.
PR #3's architecture and the current implemented household foundation were reviewed;
PR #29's household delivery changes remain independent.

| Classification | Delivered result |
|---|---|
| Implemented and tested | Transport-independent registry/types; documented LoRaWAN decoder profiles; transactional append-only originals, persistent ordering and state; private deployment/config generators; inbound OpenHAB Items and supervision; tablet UI on existing REST/SSE; history/health; explicit optional canonical snapshot attachment |
| Simulated |15 independent openings plus gate;5 environmental devices/7 readings; joins, contact changes, battery warning, tamper, duplicate/order/corrupt events; deterministic replay; outages/recovery; nonlinear water calibration examples |
| Hardware dependent | Purchased RAK5146 enumeration, USB HAL/reset/power, antenna and regional mask, radio joins/uplinks/downlinks, real sensor polarity/firmware, battery life and distant-gate coverage |
| Future planned | Real water/environmental instrumentation; calibrated usable volume/consumption; security policy and alerting; greenhouse analytics; ventilation model evaluation/training |
| Remaining risks/limits | Radio delivery and latency unqualified; unsupported payload modes fail closed; duration is censored supervised estimate; UI history is bounded; HTTP presence alone does not qualify ChirpStack migrations; larger household observation collections need separate size qualification |
| Authorization required | Production accounts/ACLs/schema/extensions; new service activation; OpenHAB provider installation; gateway/device commissioning; any future model, notification or control change |

## Tests and measured behavior

- **Frontend:**147 files,2238 tests passed (`npm test`). Existing frontend regression
  suite is included, with the route contract updated for the additive sensor page.
- **Python:**78 passed,11 container tests skipped in the ordinary unit command. This
  includes new sensor contracts and existing household evidence/snapshot/replay tests.
  Existing household tests need `/home/sat/Solar_PV/analytics/src` on PYTHONPATH,
  as in the repository's existing CI dependency setup.
- **Actual containers:**11 passed with `SENSOR_INTEGRATION=1`. Tests exercised
  real Mosquitto, PostgreSQL16, OpenHAB5.2.1 and isolated ChirpStack4.19.2.
  Verified16 independent contacts, environmental data, OpenHAB contact/battery Items,
  history, actual simulator command, retained live-input rejection, persistent
  restart, queued delivery during ingestion stop, broker restart, database-failure
  redelivery, runtime raw-history write denial, observer publish denial,
  `pg_dump`/`pg_restore` and supported ChirpStack gRPC-web login.
- **Browser:**2 passed at1340×800 and1280×720. Real OpenHAB SSE changed visible
  state without refresh; all15 opening cards fit; no main-screen scrolling/horizontal
  overflow; private configuration requests returned403. Screenshot:
  `docs/screenshots/sensors-simulation-1340x800.png` (explicit synthetic data).
- **Build:**`npm run build` passed. Existing large-bundle advisory remains; no new
  model behavior or production source/configuration was changed to address it.
- **Deployment:**both Compose files parse. A separate clean disposable PostgreSQL
  volume successfully initialized the generated schema/environment and required
  ChirpStack `pg_trgm`/`hstore` extensions, then was removed. Fresh protected-staging provisioning and0600 service-file
  permissions were also verified. All service images and
  the Python base image are pinned by digest. The pinned Basic Station image is
  AMD64; its vendor CoreCell profile was extracted/rendered without starting a
  forwarder or attaching hardware. Inspection corrected its configuration schema
  and confirmed writable startup reset-helper requirements.

Two additional sampled transitions measured **106.76ms** and **105.08ms** from
synthetic MQTT publish to matching OpenHAB Contact and view state. Browser tests
asserted complete publish-to-visible-update within5seconds. These measurements
include local software processing/test observation and establish no physical
LoRaWAN delay or guaranteed delivery bound.

One development resource sample showed ingestion17MiB, Mosquitto1.5MiB,
ChirpStack34MiB and isolated OpenHAB645MiB. Snapshot idle CPU was approximately
0.01%,0.05%,0.23% and0.15% respectively. This is a single local sample, not a
long-run capacity/load qualification. At least16 simultaneous logical contacts
and their transition burst were tested.

## Independent review and recovery corrections

Independent read-only review and re-review found and corrected simulator join
handling, equal-timestamp deterministic ordering, missing-frame/status barriers,
old-evidence withdrawal, MQTT session persistence, retained-flag handling, canonical
provider imports, sensor removal projection and snapshot-time communication expiry.
Regression tests reproduce those failures. Final focused re-review passed42 tests
before the additional tested vendor-profile renderer; no remaining important
blockers were reported in that reviewed scope.

Credentials were moved into the already Vite-denied `.superpowers` staging path,
protecting the active checkout before this feature is deployed.

Originals remain append-only under the runtime role. Synthetic and production
journals have explicit environment bindings. The optional household adapter requires
matching registry and source epochs, exact original/collector digests, commissioning,
current supervision and clock reassessment. It returns unavailable for synthetic,
expired, missing or withdrawn evidence. Existing live pipelines never call it.

## Production state and cleanup

Read-only systemd verification showed OpenHAB still active from October10,
Mosquitto/PostgreSQL/RTL weather still active from October7. No production restarts,
MQTT policy changes, schema migrations, sensor writes, actuator commands, model
training or control/forecast changes were performed.

Owned development containers are stopped after qualification. Their private
credentials and persistent synthetic history remain in ignored local staging for
an optional demonstration. The separate clean-initialization test database/volume
was removed. No physical gateway service was started. The pull request is for
review and must not be merged automatically.
