# Sensor data continuity

## Purpose

Keep weather and temperature observations usable across the receiver, OpenHAB,
and Earthship UI without masking missing or expired measurements.

## ADDED Requirements

### Requirement: Sensor observations reach every consumer
The system SHALL deliver current indoor, Bedroom, north-wall, and outdoor
temperature observations through the receiver, OpenHAB, and Earthship UI.

#### Scenario: A new temperature observation is received
- **WHEN** a supported sensor emits a valid observation
- **THEN** the observation reaches all three layers with its original identity
  and receipt time, within the existing polling and freshness rules

### Requirement: Missing readings remain visible as missing
The system SHALL preserve actual expiry, invalidity, missing values, and stream
changes rather than extending freshness or holding old readings as current.

#### Scenario: A sensor stops transmitting
- **WHEN** its observation expires under the existing policy
- **THEN** consumers report unavailable or stale data rather than a fresh value

### Requirement: Bedroom identity follows the physical sensor
The system SHALL label the relocated Bedroom sensor consistently while retaining
historical sensor identities and persistence history.

#### Scenario: Bedroom data is displayed
- **WHEN** the relocated sensor remains reachable
- **THEN** its observation appears as Bedroom and related documentation describes
  the actual bedroom location without relabeling old stored observations

### Requirement: Continuity claims have bounded observation evidence
The repair SHALL verify continuity with timestamped observations at each layer
and state the observation duration and any errors or gaps.

#### Scenario: A monitoring interval completes
- **WHEN** a receiver-to-UI continuity check finishes
- **THEN** its results include actual new receipts, expiry events, request errors,
  and stream changes without claiming indefinite reliability
