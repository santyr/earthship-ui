# Task 2 report: append-only PostgreSQL action journal and local THERMAL ingestion

Status: implemented, verified, and committed as `d39b8df feat: add append-only thermal action journal`.

## Implementation

- Added an explicit `migrate()` setup path that creates only the application-owned `thermal_intel` PostgreSQL schema, `message_receipts`, `action_events`, and `mode_events`.
- Added receipt-key uniqueness and SHA-256 payload digests. Exact-byte replays are no-ops; reuse of a key with different bytes raises `IdempotencyConflict`.
- Added one-transaction mixed action/mode batches, stream-specific deferrable supersession foreign keys, unique direct supersession, `TIMESTAMPTZ` columns, correction-aware reads, deterministic ordering, and prior-mode carry-in for bounded mode reads.
- Added database append-only triggers on all three tables. Setup revokes public access and grants a supplied runtime role only schema usage plus table `SELECT` and `INSERT`; it explicitly revokes `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`, and `TRIGGER`.
- Added the frozen `ParsedThermalMessage` and closed `THERMAL` parser. It enforces the exact header/field set, 4096 UTF-8-byte bound, timezone-aware timestamps, deterministic event/interval IDs, exact mode/state normalization, overnight local intervals, and DST fold/gap rejection in `America/Denver`.
- Added the local-only `thermal_intel.py journal` command. It reads a complete UTF-8 file, obtains its DSN only from `THERMAL_DATABASE_URL`, appends the parsed action/mode tuples atomically, reads them back, and prints compact JSON. It exposes no transport, Nostr, OpenHAB command, generic execution, advisory, or actuation arguments.

## Files

- `openhab/scripts/thermal_model/journal.py`
- `openhab/scripts/thermal_model/actions.py`
- `openhab/scripts/thermal_intel.py`
- `openhab/scripts/test_thermal_journal.py`
- `openhab/scripts/test_thermal_actions.py`

## TDD evidence

Initial RED, before production modules existed:

```text
$ pytest -q openhab/scripts/test_thermal_journal.py openhab/scripts/test_thermal_actions.py
ERROR openhab/scripts/test_thermal_journal.py
ModuleNotFoundError: No module named 'thermal_model.journal'
ERROR openhab/scripts/test_thermal_actions.py
ModuleNotFoundError: No module named 'thermal_model.actions'
2 errors in 0.09s
```

First PostgreSQL GREEN iteration reached the real database boundary: `22 passed`, with three failing assertions. Review showed those failures were test-spec issues: unrelated shared-fixture rows in an unfiltered range, PostgreSQL's specific exception subclass for SQLSTATE `55000`, and a stop correctly moved to the following non-ambiguous local day. After narrowing those assertions:

```text
$ pytest -q openhab/scripts/test_thermal_journal.py openhab/scripts/test_thermal_actions.py
25 passed in 2.39s
```

Self-review recovered the exact retained shade alias map from the approved pre-PostgreSQL plan. A second RED proved `open-day` was not normalized and `open-night` was rejected:

```text
$ pytest -q openhab/scripts/test_thermal_actions.py
2 failed, 16 passed in 0.04s
```

After the minimal state-map correction:

```text
$ pytest -q openhab/scripts/test_thermal_actions.py
18 passed in 0.02s
$ pytest -q openhab/scripts/test_thermal_journal.py openhab/scripts/test_thermal_actions.py
26 passed in 2.41s
```

## Ephemeral PostgreSQL proof

The integration fixture launches `postgres:16` with a UUID-named Docker container, a loopback-only randomly assigned host port, random test-only administrator/runtime passwords, and a UUID-suffixed runtime role. It waits for that new instance, creates the role, runs the migration twice to prove repeatability, and passes only the generated ephemeral DSNs to tests and CLI subprocesses. It never reads `THERMAL_DATABASE_URL` from the host and therefore cannot select the production database. Cleanup force-removes only the UUID-named container created by the fixture, including on failures.

Verified after tests:

```text
$ docker ps --filter 'name=thermal-journal-test-' --format '{{.Names}}'
# no output
```

The PostgreSQL tests prove:

- exact replay returns `1` then `0`, while different payload bytes under the same receipt key are rejected;
- a failed mixed batch rolls back its receipt plus all action/mode rows;
- action and mode correction foreign keys are stream-specific, originals remain stored, and reads return only effective leaves;
- bounded mode reads include the last effective mode before `start`;
- timestamp columns are PostgreSQL `timestamp with time zone` and aware datetimes round-trip;
- the runtime role has `SELECT`/`INSERT` but not `UPDATE`/`DELETE`;
- runtime mutation fails by privilege and owner mutation fails through the append-only trigger;
- one CLI message inserts an action/mode batch and an exact replay reports `inserted: 0`.

## Final commands and results

```text
$ git diff --check
# exit 0, no output

$ pyflakes openhab/scripts/thermal_model/actions.py openhab/scripts/thermal_model/journal.py openhab/scripts/thermal_intel.py openhab/scripts/test_thermal_actions.py openhab/scripts/test_thermal_journal.py
# exit 0, no output

$ python3 -m py_compile openhab/scripts/thermal_model/actions.py openhab/scripts/thermal_model/journal.py openhab/scripts/thermal_intel.py openhab/scripts/test_thermal_actions.py openhab/scripts/test_thermal_journal.py
# exit 0, no output

$ pytest -q openhab/scripts/test_*.py
64 passed in 2.57s

$ git diff --cached --check
# exit 0, no output

$ git commit -m "feat: add append-only thermal action journal"
[rc-thermal-shadow-foundation d39b8df] feat: add append-only thermal action journal
5 files changed, 1115 insertions(+)
```

## Self-review

- Transactionality: receipt insertion and every action/mode row share one connection transaction; the deferred FK failure test proves full rollback at commit.
- Replay behavior: the receipt row is the uniqueness boundary, allowing action and mode rows to share one key. Same-key/same-digest is a no-op and same-key/different-digest fails closed.
- Timezone/DST: all API timestamps must be aware; interval clocks use the received date converted to `America/Denver`; non-later stops move one local calendar day; ambiguous folds and nonexistent gaps are rejected instead of guessed.
- Secret safety: no DSN or credential is hardcoded, printed, included in receipts, or committed. The CLI reads only `THERMAL_DATABASE_URL`. Tests generate isolated throwaway credentials.
- Parser grammar: only the approved fields are accepted. `fall-charge` becomes `fall_charge`; `open-day`/`open-night` become `open`; invalid/duplicate/unknown/oversized inputs fail closed.
- Append-only enforcement: runtime grants omit all mutation privileges and database triggers reject owner-level row updates/deletes. No code path deletes or updates journal data.
- Authority boundary: no production OpenHAB database was contacted, no OpenHAB persistence table was referenced, and no Nostr transport, OpenHAB write, advisory, or actuation path was added.

## Concerns

No implementation blocker. Production schema/role creation and the live `THERMAL_DATABASE_URL` remain intentionally deferred to the later explicit operator-approval deployment gate. The local test harness requires Docker and the official `postgres:16` image; it fails rather than falling back to SQLite or production.

---

## Review correction round: supersession integrity and cycle guards

### Findings fixed

- Action corrections now preserve action kind at the PostgreSQL boundary. `action_events` has a deferred composite foreign key `(supersedes, action) -> (event_id, action)`, backed by a unique `(event_id, action)` constraint. A `kiva` event cannot supersede a `vent` event even if application validation is bypassed.
- Both action and mode streams now have deferred constraint triggers that traverse the supersession ancestry at transaction commit and raise SQLSTATE `23514` on any direct or longer correction cycle. Legitimate acyclic chains remain accepted.
- The append-only privilege/trigger regression now inserts its own dedicated action row before attempting runtime `UPDATE` and owner `DELETE`; it passes when selected alone and the owner operation necessarily reaches the trigger.
- The explicit migration upgrades the earlier Task 2 schema by replacing its action `supersedes` foreign key with the composite constraint, and remains repeatable when called twice.

### RED evidence

Regression command, run before changing `journal.py`:

```text
$ pytest -q openhab/scripts/test_thermal_journal.py -k 'preserve_action_kind or correction_cycles or legitimate_action_correction_chain or database_guards'
FFF..                                                                    [100%]
FAILED test_action_correction_must_preserve_action_kind
E Failed: DID NOT RAISE <class 'psycopg2.errors.ForeignKeyViolation'>
FAILED test_action_correction_cycles_are_rejected_at_commit[cycle-two-receipt-links0]
E Failed: DID NOT RAISE <class 'psycopg2.errors.CheckViolation'>
FAILED test_action_correction_cycles_are_rejected_at_commit[cycle-three-receipt-links1]
E Failed: DID NOT RAISE <class 'psycopg2.errors.CheckViolation'>
3 failed, 2 passed, 7 deselected in 2.13s
```

Expected reasons:

- Cross-kind RED: the old single-column foreign key verified only that `supersedes` named some action row, so `kiva -> vent` committed.
- Two-node cycle RED: deferred foreign keys allowed `A -> B -> A`; no database guard inspected the graph at commit.
- Longer-cycle RED: the same gap allowed `A -> B -> C -> A`, hiding all three rows from correction-aware reads.
- The two passing tests were intentional controls: a legitimate three-row correction chain already committed and resolved to its leaf, and the revised self-contained append-only guard exercised its dedicated row.

### GREEN evidence

```text
$ pytest -q openhab/scripts/test_thermal_journal.py -k 'preserve_action_kind or correction_cycles or legitimate_action_correction_chain or database_guards'
.....                                                                    [100%]
5 passed, 7 deselected in 2.08s

$ pytest -q openhab/scripts/test_thermal_journal.py::test_runtime_role_is_least_privilege_and_database_guards_are_append_only
.                                                                        [100%]
1 passed in 2.03s

$ pytest -q openhab/scripts/test_thermal_journal.py openhab/scripts/test_thermal_actions.py
..............................                                           [100%]
30 passed in 2.73s

$ git diff --check
# exit 0, no output

$ pyflakes openhab/scripts/thermal_model/journal.py openhab/scripts/test_thermal_journal.py
# exit 0, no output

$ python3 -m py_compile openhab/scripts/thermal_model/journal.py openhab/scripts/test_thermal_journal.py
# exit 0, no output

$ pytest -q openhab/scripts/test_*.py
....................................................................     [100%]
68 passed in 2.79s

$ docker ps --filter 'name=thermal-journal-test-' --format '{{.Names}}'
# no output
```

All database tests again used UUID-named, loopback-only ephemeral `postgres:16` containers with generated credentials. No production DSN was read, and cleanup left no container running.

### Files changed

- `openhab/scripts/thermal_model/journal.py`
- `openhab/scripts/test_thermal_journal.py`
- `.superpowers/sdd/task-2-report.md`

### Self-review

- Same-kind integrity is relational, deferred, and transactional; it does not depend on the Python caller or read-path filtering.
- Cycle checks execute as deferred PostgreSQL constraint triggers, so complete multi-row batches are visible before validation and any exception rolls back the receipt and every event in the batch.
- The recursive queries track visited IDs and stop after detecting a repeated ancestor, avoiding infinite recursion even for a malformed pre-existing graph.
- Both action and mode streams receive cycle protection; the action stream additionally enforces physical action-kind equality.
- Direct self-supersession remains rejected by the existing row check, while two-node and longer cycles are rejected by the new commit-time guards.
- The valid three-row regression proves the guards do not reject ordinary correction chains and effective reads still return the final leaf.
- The runtime role remains `SELECT`/`INSERT` only. Append-only triggers, atomic batches, idempotency behavior, DSN handling, production-fallback protections, parser grammar, and no-actuation boundary are unchanged.

### Concerns

No implementation blocker. Production schema/role migration remains deferred to the explicit operator-approved deployment gate. As before, PostgreSQL integration tests require Docker and `postgres:16` and fail rather than falling back to SQLite or a live database.
