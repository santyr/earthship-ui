# Task 1 Report: Lock the shared schemas and safety contract

## Implementation

Implemented the immutable thermal model data contracts in `openhab/scripts/thermal_model/schema.py` and package marker in `__init__.py`. The module defines the exact sensor item constants, action kinds, source precedence weights, frozen records (`ActionEvent`, `ModeEvent`, `ThermalSample`, `DynamicsModel`, `BehaviorModel`, `ThermalArtifact`, and `ShadowOutput`), serialization, and fail-closed `validate_shadow_output()` enforcement for version-1 shadow output with no unknown actuator/live fields. Added the specified focused contract tests in `openhab/scripts/test_thermal_schema.py`.

## TDD evidence

### RED

Command: `pytest -q openhab/scripts/test_thermal_schema.py`

Result: collection failed as expected with `ModuleNotFoundError: No module named 'thermal_model'`, because the schema package did not yet exist.

### GREEN

Command: `pytest -q openhab/scripts/test_thermal_schema.py`

Result: `2 passed in 0.01s`.

Relevant full baseline: `pytest -q openhab/scripts` -> `37 passed in 0.05s`.

## Self-review

Reviewed scope, exact constants and weights, frozen dataclass declarations, shadow-only status validation, unknown-field rejection, and `git diff --check`. Only the three Task 1 files were staged and committed. The worktree is clean after commit `808b69a` (`feat: define thermal model data contracts`).

## Concerns

No concerns within Task 1 scope. Validation intentionally enforces the currently specified top-level schema only; deeper payload semantics belong to later tasks.


## Review fix: glazing observation naming and persistence preference

Renamed `DynamicsModel.glazing_coefficients` to `glazing_observation_coefficients` in the production schema and mirrored plan contract, making clear that south glazing is an auxiliary observation rather than a third thermal state. Added the approved Global Constraints note: prefer OpenHAB-backed persistence whenever it preserves required semantics; justify any local store. No storage implementation was changed.

### Fix TDD RED

Command: `pytest -q openhab/scripts/test_thermal_schema.py`

Result: `1 failed, 2 passed`; the new test failed because the old field remained and `glazing_observation_coefficients` was absent.

### Fix GREEN

Commands: `pytest -q openhab/scripts/test_thermal_schema.py` -> `3 passed in 0.01s`; `pytest -q openhab/scripts` -> `38 passed in 0.06s`.

Files changed: `openhab/scripts/test_thermal_schema.py`, `openhab/scripts/thermal_model/schema.py`, `docs/superpowers/plans/2026-08-13-rc-thermal-shadow-foundation.md`, and this report.

Self-review: verified the old field is absent from the dataclass, the new name is present, the plan wording is limited to a persistence preference, no Task 2 storage work was introduced, and focused/baseline tests pass. No concerns.


## Review fix: PostgreSQL thermal-action journal decision

Updated the authoritative thermal-model spec and implementation plan to replace the planned SQLite action journal with append-only PostgreSQL tables in a dedicated `thermal_intel` schema inside the existing local OpenHAB `openhab` database. The documentation now binds Python `psycopg2`, PostgreSQL 16, `THERMAL_DATABASE_URL`, a least-privilege runtime role, `TIMESTAMPTZ`, transactional batches, unique receipt keys, correction/supersession foreign keys, append-only privileges/guards, ephemeral PostgreSQL integration tests, and deployment-time schema/role setup only at the later explicit live-approval gate. OpenHAB-generated persistence tables remain untouched; local model artifacts/backtest reports remain reproducible service artifacts. The rationale records why OpenHAB Item time-series persistence alone cannot enforce atomic batches, idempotency, or correction links.

Files changed: `docs/superpowers/specs/2026-08-13-rc-thermal-model-design.md`, `docs/superpowers/plans/2026-08-13-rc-thermal-shadow-foundation.md`, and this report. No production code changed.

Checks:

- `pytest -q openhab/scripts/test_thermal_schema.py` -> `3 passed in 0.01s`.
- `rg -n -i 'sqlite|thermal-actions\.sqlite' docs/superpowers/specs/2026-08-13-rc-thermal-model-design.md docs/superpowers/plans/2026-08-13-rc-thermal-shadow-foundation.md` -> no matches.
- `rg -n 'PostgreSQL 16|psycopg2|THERMAL_DATABASE_URL|thermal_intel|TIMESTAMPTZ|ephemeral PostgreSQL|atomic multi-event' ...` confirmed all required bindings in spec/plan.
- `git diff --check` -> clean.

Self-review: all affected Task 2 SQL/CLI/default-storage references were replaced, no SQLite action-journal contract remains, no storage implementation was introduced, and the OpenHAB authority/safety boundaries remain intact. No concerns.

---

# 2026-09-05: version-aware forecast capture

Status: DONE_WITH_CONCERNS

## Scope

Implemented only in `/home/sat/earthship-ui/.worktrees/energy-analytics-solar` on
`work/energy-analytics-solar` from base `357b052`. No production database,
OpenHAB, service, scheduler, or deployment mutation was performed.

## Root cause

The consumer used `payload.get("version") != 1`, which rejected the live v2
contract and also treated boolean `True` and float `1.0` as v1 because Python
numeric equality is permissive. Recognized forecast metrics were passed through
`float()`, accepting booleans, numeric strings, NaN, and infinity. Values for
past targets could be skipped before validation.

## RED evidence

Command from `analytics`:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_forecasts.py tests/test_scheduled.py
```

Result: exit 1, `45 failed, 22 passed in 0.37s`. Failures included the expected
v2 rejection (`forecast detail version must be 1`), permissive v1 booleans and
floats, invalid metric acceptance, validation-after-omission behavior, and the
scheduled capture failure-path assertion.

## Implementation

- Supports exactly integer forecast versions 1 and 2.
- Validates v2 correction metadata, method, 24 ordered buckets, counts, and
  finite bounded weights.
- Deep-copies v2 adjustment metadata into provenance; v1 provenance remains
  `{"forecast_version": 1}`.
- Accepts only finite exact `int`/`float` metric values or explicit null,
  rejecting booleans and strings.
- Validates recognized metrics before omitting past targets.
- Preserves issue-time selection, target timestamps, source, metrics, and the
  existing `(source, issued_at, valid_for, metric)` persistence identity.
- Documents only supported v1/v2 input and corrected-value provenance while
  preserving the historical inventory and making no deployment/history claim.

## GREEN evidence

Focused command from `analytics`:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_forecasts.py tests/test_scheduled.py
```

Result after final test addition: exit 0, `68 passed in 0.12s`.

Full suite command, run once before commit from `analytics`:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q
```

Result: exit 0, `192 passed in 0.33s`.

Whitespace verification:

```text
git diff --check
```

Result: exit 0, no output.

## Self-review

Reviewed the complete four-file diff and confirmed:

- malformed payload parsing finishes before persistence is invoked;
- same-day pre-issue summaries are omitted for both versions;
- DST-aware local midnight and aware hourly timestamps are preserved;
- repeated parsing produces unchanged persistence identities;
- input mutation cannot alter captured v2 provenance;
- the existing SQL conflict key and v1 behavior remain unchanged.

## Commit

`8731ff5 fix: ingest corrected forecast detail v2 with provenance`

## Concerns

The environment's `apply_patch` helper was unavailable because its internal
sandbox failed with `bwrap: loopback: Failed RTM_NEWADDR`. After elevated
`apply_patch` failed identically, scoped Python exact-text edits were used as a
fallback and every resulting diff was reviewed. This is an editing-tooling
concern only; tests and Git verification passed.

Fresh real-v2 runtime parsing, service execution, PostgreSQL current-history
confirmation, analytics publication, and deployment are intentionally deferred
to the controller verification/deployment checkpoint and require separate
production authorization.
