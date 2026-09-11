# Temperature evidence target-time reader

`weather_temperature_reader.py` implements a pure selector for future hourly
temperature scoring. It performs no I/O, learned-state write, model update or
fallback to the legacy temperature series. forecast_intel.py remains unchanged.

## Whole-snapshot persistence contract

Persist the complete version1 `/temperature_evidence` JSON envelope in an
additive String Item, not just `records.indoor.temperatureF`. Preserve its
streamEpoch and all named record/null entries. A restarted collector's null
record is an explicit unknown barrier inside this JSON, not an omitted numeric
sample. This refines the earlier generic proposal for additive String Items;
it does not create or activate an Item in production.

The caller supplies ordered pairs of original persistence timestamp and raw
whole-envelope JSON, a target, assessment time, explicit queried history start,
stream name and reviewed TemperaturePolicy. The query must completely cover at
least one policy-validity interval before target, plus original carry when
available. The selector checks the declared window but cannot prove database
query completeness by inspecting a caller-supplied list. Do not relabel carry
timestamps or use a numeric/nearest-change query as its adapter.

At most10,000rows and8,192UTF-8bytes per snapshot are accepted. Duplicate JSON
keys, nonfinite constants, unknown envelope/record fields, wrong version,
model/ID/field/epoch mismatch and invalid timestamps cannot qualify a sample.
The selected field must match an explicit Fahrenheit range and bounded validity
policy. A valid receipt has receivedAt=recordedAt, no later than its persistence
timestamp; the target must be elapsed at assessment and fall in the half-open
receivedAt..validUntil interval.

## Selection and barriers

Only snapshots persisted at or before target are eligible. The latest such
snapshot controls the result; invalid, malformed, missing-stream or null
records cannot be skipped in favor of an older valid reading. Post-target
snapshots never qualify, even if temporally closer. Identical persisted rows
are tolerated; conflicting equal-time or out-of-order rows fail closed.

After an invalid/unknown barrier, a new receipt must be later than that barrier's
persistence timestamp. A failed attempt to republish older evidence is itself a
barrier. Epoch changes require a new receipt after the prior epoch's last
snapshot. Same-epoch receipt regression or conflicting values/expiry at the
same receipt time are invalid barriers. These rules are intentionally
conservative when publication latency makes ordering ambiguous: missing is
preferable to silently reviving restored or conflicting evidence.

The result includes temperatureF, original receivedAt, validUntil, storedAt,
streamEpoch and SHA-256 of the exact raw snapshot. It is measurement evidence,
not a reward, threshold decision, successful source-health audit or permission
to modify controls. A constant value with current qualified receipt evidence
can be selected without requiring a nearby numeric change.

## Verification and remaining work

27selector tests cover constant-state selection, post-target rejection, exact
expiry, invalid/unknown/malformed/wrong-ID barriers, failed revival, restart,
receipt regression/conflict, schema and identity drift, finite/range/TTL checks,
future receipts, row bounds/order/conflicts, duplicate JSON keys and actual
elapsed time through Denver's repeated autumn hour. Combined with95source,
collector, configuration and relay cases:122focused tests passed.

No production history is available for this new envelope yet. The bounded
persistence fetch adapter, original query/carry provenance, natural collector
and expiry/restart qualification, policy cutover bookkeeping and actual hourly
scorer integration are still required. Legacy hourly history/model state is
not reset or relabeled. Indoor sensor ownership confirmation remains pending.

## Bounded JDBC adapter

`weather_temperature_history.py` fetches one elapsed target from the exact
proposed Item Weather_Temperature_Evidence_JSON. Its connection factory must
return a new dedicated psycopg2 connection with bounded connection timeout;
the adapter contains no credentials, fallback Item or automatic live caller.
It refuses an active transaction, configures read-only repeatable-read and
verifies both properties inside the transaction. Statement/lock/idle deadlines
are2s/1s/5s. It closes the dedicated connection without committing.

Within that stable snapshot it resolves one exact Item mapping (LIMIT2), derives
the table identifier only from a validated nonnegative integer, reads original
carry before target-minus-policy-validity, and all rows through the target
inclusive. Values remain raw text; oversized values become explicit NULL
barriers rather than disappearing. Queries use a10001row sentinel; more than
10000combined rows, bad carry or out-of-window rows refuse qualification.
Database/permission/timeout/mapping failures yield a constant sanitized
TemperatureHistoryUnavailable error, never a partial daily/hourly value.

Fifteen adapter tests plus27reader tests pass. A separate real PostgreSQL case
uses Solar_PV's explicit disposable-only advisory_db fixture: fresh
postgres:16 container, generated credentials, no external DSN fallback and
cleanup of only that fixture. It verifies exact raw reading, carry preservation,
post-target exclusion, invalid/oversize barriers, fresh recovery, SELECT denial,
duplicate mapping and an actual access-exclusive lock timeout. All43tests pass
in3.41seconds with that fixture enabled. The rest of the95focused weather-source
tests remain the previously verified baseline; no full-script result is claimed
for the new adapter yet.

Reproduction from the reader worktree:

```sh
PYTHONPATH=openhab/scripts:/home/sat/earthship-ui/.worktrees/advisory-trough-assessment/analytics/tests:/home/sat/earthship-ui/.worktrees/advisory-trough-assessment/analytics/src python3 -m pytest -q --tb=short openhab/scripts/test_weather_temperature_history_postgres.py openhab/scripts/test_weather_temperature_history.py openhab/scripts/test_weather_temperature_reader.py
```

Without the explicitly supplied disposable fixture the PostgreSQL test skips;
it never substitutes the OpenHAB production connection. Installed Item/table,
natural receiver publication, production read-only role/factory wiring and
bounded multi-target scorer scheduling/cutover remain to be implemented and
qualified. No OpenHAB contract, production table, scheduler or learned state
was modified by this adapter implementation.
