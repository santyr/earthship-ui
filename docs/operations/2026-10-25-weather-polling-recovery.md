# Weather polling recovery, October 25, 2026

The reviewed source configuration reduces both weather HTTP polling intervals
from 30 seconds to 2 seconds. This repairs the avoidable publication tail after
a radio receipt; the strict 120-second source freshness bound remains unchanged.

## Measured defect and scope

Retained October 25 evidence contains a 120.057546-second indoor receipt gap:
one nominal 60-second RF packet was absent, producing a genuine 0.057546-second
receipt expiry. Home uses station quality, whose conservative second-resolution
`radioDecodedAt` deadline expired at 16:55:57Z. The next station-quality Item
snapshot arrived at 16:56:19.807259Z, implying a 22.807259-second unavailable
window, including approximately 22.013570 seconds after the next local receipt.
This is a data-authority inference, not a historical browser capture. Comparable
October 23 windows were approximately 3.2–3.5 seconds; the 30-second poll phase
changed across restarts. Faster polling cannot eliminate genuine RF expiry.

| Source and consumer | Owner and configuration |
| --- | --- |
| `/station_quality` → `WeatherStation_Quality_JSON` → Home indoor tile | Managed `http:url:weatherStationV2`; source recipe `openhab/weather-station-v2-resources.json`, `configuration.refresh: 2` |
| `/temperature_evidence` → `Weather_Temperature_Evidence_JSON` → Bedroom and other receipt consumers | File-owned `http:url:weatherTemperatureEvidence`; `/etc/openhab/things/weather-temperature-evidence.things`, mirrored in `openhab/file-config/things/weather-temperature-evidence.things`, `refresh=2` |

The two paths retain their own epochs, schema, identity, role, validity and source
deadline checks. A fresh receipt on one path does not authorize a substitution
on the other. No held-value cache, UI feature, actuator permission, numerical
model change or freshness extension is introduced. The decoder compatibility
release and isolated current-library environment remain separate and unchanged;
this polling repair does not establish that RF losses have been eliminated.

The [Bedroom relocation boundary](2026-10-24-bedroom-sensor-relocation.md) remains
2026-10-24T23:14:52Z for original receipts from sensor 223. Its hardware epoch,
Bedroom stream and JDBC Item 663 stay stable; older Office Hallway measurements
remain historical and must not become Bedroom training/history.

## Deployment and rollback boundaries

For the managed Thing, capture the complete original DTO privately, then clone
its entire configuration map and change only numeric `refresh` from 30 to 2.
Use the supported authenticated PUT
`/rest/things/http:url:weatherStationV2/config`; read back the effective map,
ONLINE status, enabled state, links and channel identities. Do not edit JSONDB.
The serving successor's `openhab/weather-station-v2-resources.json` is the
existing source asset for this managed configuration. It remains absent from
the primary/Main tree; do not recreate it there. That source manifest remains a
`createOnly: true`, `enabled: false` preparation
recipe with all 14 READONLY data channels intact. **Never reapply that whole
recipe to the existing ONLINE managed Thing.** Preserve its source URL, all
channel transformations, sibling channels, timeouts and other settings.

For the file-owned Thing, preserve original bytes, ownership and mode, then
atomically replace only `refresh=30` with `refresh=2` through the approved
file deployment mechanism. Let the existing OpenHAB file watcher reconcile it;
verify the effective Thing and its READONLY snapshot without creating a
competing managed provider or restarting services. The original migration
`scripts/file_migration_batch.py` pins the original 30-second file hash and will
refuse this changed source. Keep that migration receipt frozen; do not bypass
its guard or use it as the current polling deployment tool.

Rollback only polling: PUT the captured original complete managed configuration
map back to the same `/config` endpoint, and atomically restore the original
file bytes, ownership and mode. Verify refresh 30 for both Things, original
channels/enabled state, ONLINE status and readable snapshots. Leave receiver
epochs, decoder release, persistence, retained history and TTL untouched.

## Resource cost and qualification limits

Station quality generates a new request-time JSON snapshot on every read.
Under the existing JDBC `everyChange` policy, a healthy 2-second cadence projects
43,200 full snapshot rows/day. At the measured approximately 9,781 serialized
bytes per row this is **approximately 403 MiB/day of serialized JSON input**,
versus approximately 26.9 MiB/day at 30 seconds. This is a projection from prior
rows, not measured physical PostgreSQL growth, WAL volume, CPU usage or a load
test. Wire-request multiplicity was not measured; sibling channels also refresh.
Temperature evidence retains its receipt/session timestamps across ordinary
GETs, so its write rate must not be inferred by multiplying the old rate by 15.
Persistence strategy and resource limits remain unchanged.

Healthy 2-second fetch scheduling aims to return the avoidable tail to roughly
the earlier 3-second scale, including source-time conservatism. This is not a
hard latency guarantee: the preserved 3,000ms HTTP timeout already exceeds the
poll period, and timeout/unhealthy scheduling must remain fail closed. Item
events can trigger Home recovery before its ordinary 5-second expiry clock.

Source JSON parsing and exact semantic/text comparisons qualify only these
source settings. Actual recovery qualification must observe both receiver
endpoints, both OpenHAB Items and the real Home indoor tile concurrently,
separating genuine source expiry from receipt-to-published-snapshot delay.
A short all-fresh observation does not establish RF reliability or browser
behavior across a missed packet. Private diagnosis and deployment receipts live
under `artifacts/post-upgrade-repairs-20261024.local/`.

The separate operational receipt
`polling-2s-deployment-20261025T172836Z/deployment-report.json` reports `passed`
for October 25 17:31:26–17:32:02Z: managed config PUT returned 200 and the
file-owned Thing reconciled, with channels, other configuration, source
deadlines and epochs preserved. Its 17 samples observed 17 distinct station
snapshots, maximum station report age 1.1977 seconds, and first-observed
temperature-evidence delivery delays of 3.068 seconds (indoor), 1.943 seconds
(north wall) and 1.851 seconds (outdoor). These are sampled operational delays,
not exact browser repaint times. This 32-second observation includes no actual
browser capture and does not establish missed-packet recovery or RF reliability.
The separate receiver/OpenHAB/Home observation remains required.
