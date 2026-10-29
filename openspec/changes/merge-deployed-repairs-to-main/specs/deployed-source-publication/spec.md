## ADDED Requirements

### Requirement: Publish verified deployed component sources
Remote main SHALL contain the active verified UI, suggestion, native forecast, sensitivity, sensor component and supporting deployed source corrections with recorded release provenance and relevant validation.

#### Scenario: Component sources differ across releases
- **WHEN** separately deployed components have different qualified source authorities
- **THEN** integration preserves each active component's source rather than substituting an entire unrelated release tree
- **AND** source equality and any required merge resolutions are recorded

### Requirement: Preserve running installations and dirty work
Publication SHALL use isolated integration checkouts and normal Git updates while preserving private configuration, dirty work, original indexes and running release selections.

#### Scenario: Remote main is updated
- **WHEN** qualified integration commits are pushed
- **THEN** exact remote commit identities are verified
- **AND** active services and dirty original checkouts remain unchanged by the publication
