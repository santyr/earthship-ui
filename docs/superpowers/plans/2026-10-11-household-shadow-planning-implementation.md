# Household hard constraints, arbitration and sealed shadow planning

Approved basis: PR #3 phases5–7. Inline test-first implementation, one final stage review. Full goal remains unchanged; source expansion and qualification are tracked separately.

Implement pure hard constraint evaluation from frozen snapshot, typed intents, explicit coordination evidence and immutable policy. Unknown evidence blocks optional proposals. Owner availability, cooldown/curfew, lockout and manual override facts must retain original digests and clocks; booleans alone do not qualify a fact. Snapshot/intent source freshness is rechecked at the decision clock. Battery reserve uses an explicit frozen baseline lower bound and cumulative effects; absence stays unknown.

Implement deterministic exhaustive arbitration over at most eight typed candidates. Hard failures/unknowns are excluded before scoring, including pair conflicts and cumulative reserve. Same owner requests are mutually exclusive at this coordination boundary. Utility components use explicit versioned units and bounded weights; no hard rule has a penalty coefficient. Explain accepted/rejected/deferred/superseded/unknown decisions in shadow scope, with stable reason codes.

Seal complete bounded plan inputs and outputs: snapshot, registry, intents, coordination originals, policy, model/forecast references, candidate checks, objective decomposition and selected plan. Replay must rederive decisions identically without transport. Compare no optional action and greedy baselines; actual household/current-owner policy remain unavailable unless original evidence is provided. No notifications, Item publication, request construction or actuators.

Tests cover stale/missing/forged clocks, wrong identity, hard rule dominance despite large utility, pair conflict, cumulative reserve, deterministic ordering/ties, exhaustive optimum, sealed replay tampering and input mutation. Local scopes: CPU20%, memory256MiB, swap0, tasks24, serial, one numerical thread. No new solver dependency or services.
