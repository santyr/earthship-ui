## ADDED Requirements

### Requirement: Read-only seasonal indoor temperature evidence
The analysis SHALL use retained OpenHAB temperature history to compare observed warming and cooling during complete winter and summer months, preserving source timestamps, Item identities, units and response hashes.

#### Scenario: Seasonal comparison is delivered
- **WHEN** available winter and summer records are analyzed
- **THEN** the report provides directional change times, daily coverage, sensor quantization, gap sensitivity and explicit observational limits
- **AND** the report and underlying tables and scientific figures can be reproduced from retained source responses

### Requirement: Preserve the accepted operating cadence
The analysis SHALL leave the accepted five-minute suggestion cadence and production operational configuration unchanged.

#### Scenario: Temperature evidence informs cadence
- **WHEN** the report interprets the observed temperature response
- **THEN** it distinguishes the cadence implication from unproven causal thermal constants and faster-changing nonthermal inputs
- **AND** it makes no production, model, database or equipment-control changes
