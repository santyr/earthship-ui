# openHAB Persistence Alert Removal Design

Date: 2026-07-20

## Context

The external openHAB sanity checker currently queries persisted
`DCData_Voltage` history over a 15-minute window. It reports a problem when
fewer than three rows are returned and also reports failures from the
persistence REST query.

openHAB persists these item states only when their values change. A healthy,
stable item can therefore produce few or no rows during the window. Neither a
low row count nor failure of this optional history query reliably identifies a
stalled JDBC or Postgres service. The observed alert at 07:20 on 2026-07-20
recovered on the next run and is a confirmed false positive.

## Scope

Remove all persistence-derived item notifications from the external sanity
checker:

- Do not query `/persistence/items/...` for notification decisions.
- Do not notify based on persisted row counts for any openHAB item.
- Do not notify when an item persistence query fails.
- Silently discard any saved `persist` alert state so removal cannot emit a
  final `recovered [persist]` notification.

Keep all existing non-persistence checks unchanged, including openHAB REST
availability, rule health, current-value ranges, source freshness, and
algorithm cross-verification.

## Implementation Design

Remove the `DCData_Voltage` persistence block from
`/home/sat/openhab/scripts/openhab_sanity_check.py` and update its module
description and numbered check comments so they no longer claim that
persistence flow is monitored.

When state is loaded, remove the legacy `persist` entries from both
`active` and `last_alert` before normal alert and recovery processing. This
migration is silent and idempotent.

The checker will continue to use current item states and explicit last-update
items for safety monitoring. It will not infer item health from the frequency
of persistence records.

## Error Handling

No persistence REST request will be made, so persistence endpoint failures
cannot become sanity-check problems or notifications. Errors from retained
REST, rule, value, freshness, and algorithm checks keep their existing
handling and rate limits.

## Testing

Add a focused regression test for the real checker entry point. The test will
provide controlled responses for required REST calls, capture the resulting
problem set, and fail if the checker requests any
`/persistence/items/...` endpoint or emits a `persist` problem.

Add a state-migration test proving that legacy `persist` entries are removed
without invoking the notification function, while unrelated saved alert state
is preserved.

Run the focused tests first, then the existing openHAB test suite. Finally run
the checker in a notification-disabled test harness to confirm retained checks
still execute without a persistence request.

## Acceptance Criteria

- No persistence row-count notification can be sent for any openHAB item.
- No persistence item-query failure notification can be sent.
- Removing the check cannot send a `persist` recovery notification.
- Existing non-persistence safety notifications retain their behavior.
- Regression tests pass and explicitly protect the all-items boundary.
