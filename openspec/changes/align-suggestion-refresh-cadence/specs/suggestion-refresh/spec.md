## ADDED Requirements

### Requirement: Five-minute fallback and publication updates
The shared UI suggestion transport SHALL refresh at opening and reconnect, follow actual report publication and human-record changes, and use a five-minute fallback polling interval. Rendering and GET requests SHALL NOT execute models or equipment commands.

#### Scenario: New evaluation is published
- **WHEN** the fixed advice artifact is atomically replaced
- **THEN** subscribers are notified and the shared store fetches the newly published report promptly
- **AND** unsubscribing and server closure release timers, connections and watchers

#### Scenario: Connection is resumed
- **WHEN** a page opens, becomes visible or reconnects
- **THEN** the advice store requests current state immediately without waiting five minutes

### Requirement: Honest retained advice
The UI SHALL preserve the last validated report after an update failure, show its original age and stale state, and suppress actions at their real source or recommendation expiry.

#### Scenario: Source expires before the next generation
- **WHEN** a source-bound suggestion expires
- **THEN** the display identifies the last suggestion as stale without extending or resetting original evaluation or source clocks

#### Scenario: Refresh fails
- **WHEN** a read fails or contains invalid advice
- **THEN** the previous validated report remains available as dated history and the UI identifies the failed refresh
