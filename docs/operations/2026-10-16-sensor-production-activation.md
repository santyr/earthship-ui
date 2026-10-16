# Production sensor software activation — 2026-10-16

The owner explicitly authorized production activation and migrations in this
session. The software backend is active from source commit
`2deca464ac8a3c3a89cdaf6e4f8e014b42f16ac9` on PR #30. The PR remains open;
no merge was performed. The active console checkout's concurrent changes were
not edited. Dashboard source remains in the PR; the new production Items and SSE
boundary are ready for that frontend integration.

## Activated resources

- Running containers: `earthship-sensors-chirpstack-1`,
  `earthship-sensors-redis-1`, `earthship-sensors-ingest-1`.
- ChirpStack4.19.2 uses the existing PostgreSQL16 instance, a new isolated
  `earthship_chirpstack` database/owner, and required `pg_trgm`/`hstore` extensions.
  PUBLIC database access is revoked. Management binds only `127.0.0.1:18085`.
- Dedicated authenticated Redis7.4.2 persists AOF in the named
  `earthship-sensors_redis_data` volume, published only on `127.0.0.1:6394`.
- New `earthship_observations` schema in the existing `openhab` database is bound
  to `production`. The `earthship_sensor_writer` runtime role has append/select
  rights on originals/observations/seen, state upsert rights, and metadata read.
  It cannot create schema objects or update/delete originals. Existing JDBC and
  thermal schemas were not migrated or backfilled.
- Existing Mosquitto remains on1883. New `earthship_sensor_*` accounts have
  service-specific ACLs. The OpenHAB and health accounts are read only; ingestion
  reads the exact production application and writes only sensor presentation.
  No simulator account was provisioned. Existing password hashes and existing
  users' prior unrestricted access were preserved. Future broker account additions
  must include explicit ACL entries; the broker now has an ACL file.
- Inbound-only providers were hot loaded into `/etc/openhab`:
  `items/earthship-sensors.items`, `things/earthship-sensors.things`, and
  `automation/js/earthship-sensor-supervision.js`. There are three new Items,
  two new Things, and a supervision rule with an empty physical-device policy.
  Existing MQTT/JSONPATH/REGEX/JS Scripting addons were already installed.
- A new private production tenant/application was created through the pinned
  authenticated ChirpStack API. The default administrator password was rotated;
  the old default was explicitly verified to fail. Credentials are root-readable
  in `/etc/earthship-sensors/admin.json`, not in this repository.
- The actual production registry is private and **empty**. Its application UUID
  is the real newly created ChirpStack application, not the example UUID.
  No contact assignments, synthetic devices, join keys or fake readings were
  installed. US915 FSB2 is configured, not yet radio qualified.

## Paths and repeatable operations

Docker is installed through Snap. Its client namespace cannot read an arbitrary
host `/etc` Compose file. The protected Docker data location is therefore:

```
/var/snap/docker/common/earthship-sensors/
  private/                           # 0700 root; /etc/earthship-sensors symlink
    compose.yaml
    registry.json
    ingest.json
    chirpstack/
    redis.conf
    admin.json
    deployment.json
    activation-verification.json
    openhab-provider-manifest.json
  releases/2deca464ac8a/              # exported pinned service source
```

Service JSON is0600 and owned by the corresponding non-root container UID10001.
Redis configuration/registry files are0644 inside the protected parent for direct
bind mounts. No secret or private inventory is tracked. Source code directories
inside the image must be0755; secrets keep their restrictive modes. The first
export inherited a restrictive umask and failed non-root imports. Correcting
source modes, rebuilding without cache, and verifying `python -m
services.lorawan.runtime --help` as the image's normal user resolved this before
successful startup. Use umask022 for source export/build and0700/0600 explicitly
for private provisioning.

`deploy/lorawan/compose.thinkcentre.yaml` records the activated non-secret host
layout. It uses the same digest-pinned images as the qualified deployment and
rotating container logs. The ingester and Redis have health checks. ChirpStack
health is reported through the ingester's local HTTP probe; authenticated API,
region and actual database initialization were separately verified.

For an operator with Docker access, read status/logs using the tracked host file:

```bash
docker compose -f deploy/lorawan/compose.thinkcentre.yaml ps
docker compose -f deploy/lorawan/compose.thinkcentre.yaml logs --tail 50 ingest
```

The private deployment also contains the same Compose definition and root-only
provisioning/management/verification helpers from this cutover. Helpers that
create accounts or bootstrap ChirpStack are deliberately one-time operations;
never rerun them as credential rotation. Registry changes require validation,
matching inbound OpenHAB definitions, and restart of only the new ingester.
No existing OpenHAB restart is needed for file-provider changes.

Docker's daemon is enabled at boot. New services use `restart: unless-stopped`.
The manually stopped state remains intentional; restore with `up -d --no-build`
against the tracked host file. Management access is local or through an SSH
forward, for example `ssh -L 18085:127.0.0.1:18085 <server>`.

## Verified outcome

At16:09UTC the ingester and Redis were healthy, ChirpStack was running, and:

- `Earthship_Sensor_Service=online` and both new MQTT Things were ONLINE.
- The view was fresh, identified `production`, reported MQTT connected and local
  ChirpStack HTTP responding, and contained zero registered devices.
- The actual authenticated OpenHAB SSE stream emitted a new sensor-view event
  without any synthetic sensor stimulus.
- Raw events, observations, state rows and seen-event rows were all zero.
- Direct database privilege checks denied runtime CREATE and raw UPDATE/DELETE.
- A non-retained inert MQTT qualification publish by the OpenHAB account received
  MQTTv5 `Not authorized`; no observation or actuator topic was published.
- The new ingester alone was restarted; it recovered healthy with the same
  production binding, fresh view, and empty journal.
- All pre-existing OpenHAB Item names, Thing UIDs and rule UIDs remained present.
- OpenHAB still had its October10 start time; Mosquitto and PostgreSQL retained
  their October7 start times. Mosquitto was reloaded, not restarted. Zigbee,
  RTL-SDR, water/energy controls and live forecast code were not reconfigured.

All checks on PR #30's deployed source commit had completed successfully before
activation, including the broader existing repository regression suite.

## Backup and rollback

Pre-change broker configuration/password hashes, PostgreSQL roles and the existing
OpenHAB database schema are saved under root-only:
`/var/backups/earthship-sensors/20261016T160349Z/`.
Post-activation custom-format dumps of the new observation schema and ChirpStack
database are in its `after-activation/` directory. `pg_restore --list` succeeded
for both; SHA256 manifests are recorded. This checks archive readability, not a
new full restore rehearsal; the isolated development restore test remains the
prior restore qualification. Protect/encrypt any off-host backup copies.

To roll back the new runtime, stop only the three services in the tracked host
Compose file. Keep databases/volumes for evidence and do not run `down -v`.
The service LWT and view expiry withdraw availability; no contact is set CLOSED.
Remove only the three installed sensor providers (rule first) after checking their
hashes against the private ownership manifest. Do not alter unrelated providers.
Revoke the new writer's schema privileges if retiring the integration; retain
originals rather than dropping the observation schema. Restore pre-change broker
files only if no later broker changes exist; otherwise surgically remove the new
accounts/ACL entries. Reload Mosquitto and verify existing clients. No OpenHAB or
PostgreSQL restart is required. Never replace a whole live database from the
schema/role backups.

## Hardware and remaining deployment boundaries

No RAK5146 enumerated during this cutover. Neither Basics Station nor Gateway
Bridge is running. Physical gateway identity, USB reset/power, antenna, regional
mask, sensor joins/polarity/firmware, and distant-gate coverage remain commissioning
steps. No simulation traffic was injected into the production journal. There is
no new model training, snapshot consumer activation, notification policy or
actuator authority. The ventilation dashboard is delivered in the open PR and
has not replaced the concurrently edited active frontend checkout.
