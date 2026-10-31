# Native forecast lifecycle

## Purpose

Produce and score household forecasts from complete current observations while
preserving model provenance, bounded execution, and reliable scheduled operation.

## ADDED Requirements

### Requirement: Dense temperature history remains complete
The system SHALL accept the qualified dense source profile without dropping raw
rows, changing receipt clocks, filling missing values, or relaxing the existing
legacy and segmented size, row, segment, and execution bounds.

#### Scenario: A full dense observation window is captured
- **WHEN** valid observations exceed the legacy single-source size
- **THEN** the supported segmented representation retains the complete window
  and replays the full air, mass, and outdoor trajectories with original gaps

### Requirement: Approved source components load coherently
The system SHALL load the exact approved coordinator, reader, model, and archived
dependencies for the selected release and reject mismatched source identities.

#### Scenario: The approved retained coordinator is selected
- **WHEN** scoring loads its approved helper
- **THEN** the real loader succeeds and selects the supported reader without
  substituting a factory or accepting unreviewed helper bytes

### Requirement: Activation preserves the serving family
The system SHALL activate a coherent service family within the original
reservation and safe-window limits and restore the exact required timers and
owner state on success or failure, with equipment actuation disabled.

#### Scenario: Activation fails or is interrupted
- **WHEN** the new family cannot complete activation
- **THEN** the previous valid family and timer state remain recoverable and
  cleanup is verified before another activation is attempted

### Requirement: Publication supplies genuinely current products
The system SHALL publish current household forecast and sensitivity products
with their original issue, preparation, confirmation, and expiry provenance.

#### Scenario: A forecast cycle completes
- **WHEN** valid current inputs produce a confirmed publication
- **THEN** downstream analytics and UI readers can consume matching unexpired
  products without fabricated receipts or extended timestamps

### Requirement: Scheduled refresh works after deployment
The repaired system SHALL complete a subsequent genuine scheduled model refresh,
forecast publication, and eligible scoring cycle using the deployed source.

#### Scenario: The next scheduled opportunity occurs
- **WHEN** the production timers run after activation
- **THEN** actual model, service, publication, and score evidence identifies the
  selected release and demonstrates the resulting behavior
