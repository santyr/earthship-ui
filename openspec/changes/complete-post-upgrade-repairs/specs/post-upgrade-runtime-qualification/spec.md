# Post-upgrade runtime qualification

## Purpose

Demonstrate that the repaired host and application function after the upgrade
without confusing partial checks with verified deployed behavior.

## ADDED Requirements

### Requirement: Host corrections restore normal operation
The repaired host SHALL provide working Wi-Fi and required USB helpers, parse its
service configuration correctly, and have no unexplained system or application
errors attributable to the upgrade.

#### Scenario: Host health is checked
- **WHEN** repairs have been deployed and scheduled services have run
- **THEN** network, package, service, and kernel evidence establishes normal
  operation or identifies each remaining error as unresolved

### Requirement: Maintained tests exercise the intended functionality
The repair SHALL preserve supported unit and integration test discovery and
correct current contracts without removing required tests or treating skipped
coverage as successful qualification.

#### Scenario: A repaired component is tested
- **WHEN** its appropriate checks run
- **THEN** the results identify actual cases, failures, skips, resource outcomes,
  and the source revision they verify

### Requirement: Numerical qualification covers the complete workload
The repair SHALL verify the full retained historical 198-score workload and the
full dense 64-cohort, four-horizon workload under the original execution limits,
with complete replay, independent report comparison, and final source checks.

#### Scenario: A numerical qualification is reported
- **WHEN** the measured coordinator body completes
- **THEN** it includes every required phase within the original deadline using
  production-equivalent path costs, with synthetic and actual acquisition
  evidence identified separately

### Requirement: Sensor qualification covers the complete private stack
The repair SHALL retain the full seven-service sensor stack, eleven Python
integration tests, two real browser tests, and required guardian recovery checks
under their existing resource and cleanup constraints.

#### Scenario: The private integration case ends
- **WHEN** the workload succeeds, fails, or defers
- **THEN** exact owned resources and admission custody are reconciled, production
  containers and volumes are preserved, and only actual completed tests receive
  qualification credit

### Requirement: Final integration preserves unrelated work
The repair SHALL integrate only the qualified changes while preserving unrelated
dirty files, indexes, private configuration, historical evidence, and rollback
material.

#### Scenario: Final integration is prepared
- **WHEN** implementation and runtime verification are complete
- **THEN** the exact integration delta, relevant checks, live readback, remaining
  limitations, and restoration path are reviewable before completion is claimed
