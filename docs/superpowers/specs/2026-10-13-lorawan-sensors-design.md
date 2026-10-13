# Earthship distributed sensor observation infrastructure

The operator mission authorizes designing and implementing the complete hardware-independent path. Production gateway activation, live OpenHAB changes, forecast changes and actuator authority remain outside this work.

## Architecture

RAK5146 USB SX1303 → local Basics Station → ChirpStack Gateway Bridge → authenticated MQTT → ChirpStack v4 → authenticated application MQTT → Python ingestion → append-only PostgreSQL originals + persistent state → normalized MQTT → inbound-only OpenHAB Items → existing REST/SSE → ventilation screen.

Reuse host Mosquitto and PostgreSQL after attended provisioning; no changes to either host service now. Dedicated Redis belongs to ChirpStack, because the existing container Redis belongs to an unrelated application. Disposable Compose includes its own broker/database/OpenHAB on an isolated bridge with loopback management ports. No physical devices or production credentials are attached. MQTT application injection qualifies the software integration, never the radio path.

## Contracts and ordering

Versioned observations carry device identity, registry binding, semantic state, explicit timestamp basis, battery units, tamper, radio metrics, counters, session, decoder revision, raw SHA256, synthetic provenance and quality. Unknown payloads, unknown identities, malformed timestamps, retained input, conflicting counters and future clocks fail closed and retain bounded originals. Join receipts create session barriers; counter regression never silently resets. Duplicate packets never refresh supervision. Historic datalog remains historic. Contact freshness and communication freshness are separate; status-only packets cannot refresh contact evidence.

Names and locations are commissioning configuration, not permanent invented assignments. Separate simulated and production registries; production defaults to an empty list. Stable Item names derive only from validated logical IDs. Thresholds are explicit per device, with manufacturer defaults documented rather than mistaken for radio qualification.

## History and household integration

Persist raw events, decisions, normalized observations and state transactionally. MQTT publication is a periodically retried projection of committed state, not a second authority. Bounded recent events and daily durations reach the UI through OpenHAB JSON Items. Durations describe supervised estimates with interruptions/gaps, not measured airflow or exact physical transition times.

A pure digest-bound ventilation adapter extends an immutable HouseholdSnapshot only with an explicit opt-in. It recomputes quality at snapshot as_of, requires commissioning/radio qualification, rejects synthetic evidence for household use, and preserves the original parent snapshot. No live pipeline, model, training job, planner or owner rule calls it.

## UI and operations

Tablet-first dedicated Ventilation route: compact overview, 15-card grid, paginated sensor list and history panel. Unknown/stale/offline are distinct from valid closed. Source service expiration and OpenHAB connection status invalidate display counts. Browser reads only existing Item REST/SSE. Optional perimeter organization is observational and never claims alarm certification.

Reproducible pinned images/dependencies, generated private configuration, restricted management ports, topic ACLs, non-admin ingestion database role, bounded logs, health checks, backup/restore/restart runbook, regional FSB alignment, and hardware commissioning acceptance gates are delivered together.

## Expanded mission and transport boundary

The updated mission supersedes the contact-only scope. `services/observations` owns the canonical sensor metadata registry and normalized physical-observation vocabulary. LoRaWAN decoding belongs only in `services/lorawan`. Existing OpenHAB, Zigbee and RTL-SDR integrations retain their existing ingestion and source qualification: explicit adapters accept already-qualified original receipts or OpenHAB evidence and never reread providers during snapshot construction. An Item value alone cannot claim original observation time or household qualification. Derived volume and model outputs have separate schemas and parent evidence, not physical observation roles.

Priority A completes the working contact path. Priority B delivers generic environmental/water contracts, synthetic gate and environmental fixtures, digest-bound read-only HouseholdSnapshot attachment and chronological replay/evaluation scaffolding. Priority C documents instrumentation, calibration, security semantics and future analytics. No production schema migrations, training or control changes. Source mappings and observational capability metadata extend the household evidence boundary rather than changing its existing scalar role registry or control capability registry.

PR #3 is architecture-only and merged at f9ff66f. Current base includes implementation through PR #28. PR #29 is concurrently changing household delivery; this work avoids its pipeline/model/owner files.
