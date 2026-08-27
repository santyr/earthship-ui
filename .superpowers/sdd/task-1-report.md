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
