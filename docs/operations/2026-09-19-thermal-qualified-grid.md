# Qualified temperature grid foundation

## Verified implementation

`weather_temperature_reader.select_temperature_grid` resolves up to 289 ordered
targets over one elapsed day using one pass over at most 10,000 snapshots.
Single-target selection now delegates to this same engine. Every target retains
the original receipt and persistence timestamps, expiry, epoch and snapshot hash;
an absent/expired/invalid value is `None`, never an invented observation.

`weather_temperature_history.fetch_temperature_grid` uses one dedicated read-only
repeatable-read connection for the whole batch, with the existing query/lock
timeouts, validated Item mapping, original carry row and bounded payloads.
It closes on success and failure. Query failure refuses the entire batch without
exposing database details. Existing hourly callers retain their single-target API.

The full barrier chain is evaluated before each target. Independently slicing
history to each target's TTL window is unsafe: repeated restored old receipts
can propagate an invalidation barrier from before that window. The new regression
requires this chain to remain invalid until an actually newer receipt arrives.

## Evidence

- Before implementation, the new tests could not import the missing batch API.
- Focused reader/history/hourly tests: 81 passed.
- Complete Python suite: 1,047 tests and42subtests passed; one expected optional
  PostgreSQL integration skip. The live restricted-role read below separately
  exercised the actual production JDBC mapping and persisted envelopes.
- Independent comparison against the original committed reader: 6,300 matches
  across 300 deterministic histories containing invalid, malformed, restored,
  regressing and fresh receipts. This is not a comparison against the refactored
  single-target wrapper.
- A full-day fixture has 2,881 snapshots and 289 targets. Each snapshot is parsed
  exactly once; all healthy targets qualify.
- Live read-only verification used the existing `weather_temperature_reader`
  role and approved policy file. Twelve five-minute targets from
  `2026-09-20T00:30:00Z` through `2026-09-20T01:25:00Z` qualified for each of
  outdoor206, indoor235 and north-wall193 (36 of36). Original stored timestamps
  preceded or equalled every target and all targets preceded receipt expiry.

No runtime files, service configuration, privileges, learned artifacts or sensor
history were changed. This is a reader foundation, not deployed thermal integration
or evidence that any model has learned from the new grid.

## Required next integration

1. Route thermal air/mass/outdoor temperature history to the qualified grid at an
   explicit aligned cutover. Keep pre-receipt numeric history separately identified;
   do not label the existing 400-day training archive as receipt-qualified.
2. Emit a deliberate invalid barrier for every unqualified grid target. Do not
   let the dataset's numeric interpolation/hold policy refill those gaps. Prevent
   mixed pre/post-cutover buckets from masking the boundary barrier.
3. Preserve receipt provenance, policy identities, cutover and qualified/missing
   counts in training evidence. Raw north-wall temperature remains an observation
   feeding the existing latent-mass observer, not direct thermal-mass truth.
4. Bound database work and process runtime across the training window; ensure
   unavailable qualified history cannot silently fall back to numeric history.
5. Keep glazing, optional living-office and radiation policies explicit: the three
   temperature receipts do not prove those fields' health. Retain the approved
   astronomical-night radiation reconstruction contract.
6. Validate current/shadow inputs against the same source-receipt semantics.
   A REST Item update timestamp alone is not necessarily a sensor receipt.
7. Test cutover, expiry, restart, unchanged-but-healthy values, invalid gaps,
   recovery and source identity, then deploy with exact-version checks and a
   preserved accepted-model rollback. Do not force training or manufacture data
   merely to obtain a success receipt.
