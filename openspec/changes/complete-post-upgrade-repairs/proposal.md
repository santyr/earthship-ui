# Proposal

## Why

The OS and PostgreSQL upgrade exposed radio, forecast, analytics, and UI failures.
Several repairs are implemented, but forecast publication, complete runtime
qualification, and final integration are still unproven. Finish the authorized
repair scope using OpenSpec without discarding working changes or prior evidence.

## What Changes

- Make OpenSpec the active project workflow; stop using Superpowers.
- Preserve the delivered clock/date layout and restore missing current UI data.
- Complete native forecast/scoring compatibility, performance verification,
  coherent deployment, and subsequent scheduled operation.
- Verify the RTL-SDR-to-OpenHAB-to-UI data path, Bedroom mapping, Wi-Fi, and host
  error corrections with actual runtime evidence.
- Complete the full private sensor integration workload and cleanup checks.
- Reconcile analytics provenance and PostgreSQL compatibility, then integrate the
  qualified changes without overwriting unrelated main-checkout work.

## Capabilities

### New Capabilities

These are the first OpenSpec definitions of existing recovery requirements.

- `sensor-data-continuity`: Weather reception, sensor identity, freshness, and
  delivery through OpenHAB and the UI.
- `native-forecast-lifecycle`: Dense input handling, retained scoring, publication,
  coherent activation, cleanup, and scheduled model refresh.
- `dashboard-data-presentation`: Current UI data, the requested clock/energy
  layout, analytics provenance, and route-level behavior.
- `post-upgrade-runtime-qualification`: Host checks, maintained test coverage,
  complete sensor integration, and evidence-preserving final integration.

### Modified Capabilities

None; this project has no existing OpenSpec capability specifications.

## Impact

Earthship UI and its runtime worktrees; OpenHAB and RTL-SDR ingestion; native
thermal and household forecasts; Solar_PV analytics; user services and timers;
deployment documentation. Equipment actuation and retired Lightningd remain
outside this change. Existing production data, private configuration, and
immutable releases must be preserved.
