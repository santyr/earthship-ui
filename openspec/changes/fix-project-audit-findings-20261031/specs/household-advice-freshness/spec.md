## ADDED Requirements

### Requirement: Current action text respects retained evidence expiry
The household header SHALL show action text only while the advice and its domain
remain current. Expired advice or a failed refresh SHALL show Awaiting fresh
evidence without extending expiry or removing retained details.

#### Scenario: Provisional advice expires with no new report
- **WHEN** the clock crosses the retained advice validity boundary
- **THEN** the primary header no longer shows the expired action
- **AND** retained evidence remains available in the details

### Requirement: Existing energy scheduling retains its OpenHAB owner
Existing energy schedules SHALL remain owned by OpenHAB without requiring a
second discretionary task profile or duplicating automation.

#### Scenario: No standalone discretionary task is configured
- **WHEN** the household uses its existing OpenHAB energy schedules
- **THEN** advice reports energy scheduling managed by OpenHAB
- **AND** it does not report a missing discretionary-task approval as a blocker
