# Suggestion refresh cadence

The existing household cycle generates advice every five minutes. The UI follows
atomic publication through `/api/household-advice-events`, with one shared
five-minute fallback read. Opening a page, returning to it, reconnecting, and
recording human feedback or observed state request an immediate read. Notifications
only read existing results; they do not execute models or device commands.

Suggestions show their original evaluation age in the header and the evaluation
time in details. A failed refresh retains the previous validated report, marks the
view stale and removes actionable controls until a successful read. Human state
declarations continue to invalidate older recommendations for the same target.
Expiry is clock driven even without a new message. The server releases its single
state-directory watcher and heartbeat when the final subscriber disconnects or
the server shuts down; browsers release subscriptions and timers on teardown.

Input freshness is distinct from generation cadence. Actual temperature receipts
have a two-minute validity and can expire sooner than the next household issue.
The UI labels those comparisons stale; it does not stretch source expiry or
change recorded observation/evaluation times. Keeping a dated last suggestion
visible is historical context, not proof of current valid evidence. Any future
change to decision validity requires its own explicit contract and qualification.

This cadence follows the read-only winter/summer analysis retained in
`artifacts/indoor-thermal-inertia-20261029.local/REPORT.md`. Numerical models,
receiver policy, forecast schedules and equipment-control permissions are unchanged.

Deployed 2026-10-29: `artifacts/suggestion-refresh-20261029.local/ui-release-suggestions-20261029-a03`.
Signed source: `0b52dc1`, branch `fix/suggestion-refresh-20261029`.
Detailed qualification, original failures, deployment and guarded rollback are
recorded in `openspec/changes/align-suggestion-refresh-cadence/evidence.md`.
Live publication verification is recorded separately in
`artifacts/suggestion-refresh-20261029.local/live-suggestions.json`.
