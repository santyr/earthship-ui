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
