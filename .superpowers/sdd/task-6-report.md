# Task 6 report: atomic artifacts and chronological evaluation

## Status

Implemented and verified the versioned local artifact registry and strictly
chronological walk-forward evidence layer. This task performs no PostgreSQL,
OpenHAB, network, advice-graduation, command, or actuation writes.

## Delivered

- `ArtifactRegistry` writes `candidate.json`, `accepted.json`, and
  `backtest-report.json` through a sibling `.tmp`, file `fsync`, `os.replace`,
  and parent-directory `fsync`.
- Temporary writes use `O_NOFOLLOW`; candidate symlinks are rejected. Corrupt
  accepted artifacts are timestamp-quarantined and fail closed.
- JSON loading reconstructs `DynamicsModel`, `BehaviorModel`, nested tuple
  coefficients, and `SeasonalActionVocabulary` with type fidelity.
- Validation covers `earthship-thermal-model/v1`, UTC chronology, exact item
  identities and units, SHA-256 dataset digest, code revision, provenance
  counts, fit diagnostics/constraints, recursive numeric finiteness, and Task 4
  physical/stability validation.
- Promotion recomputes the only provisional gates: valid physics, finite
  metrics, at least two scored folds, and lower 24-hour air MAE than
  persistence. It requires `shadow_only=true` and defines no graduation gate.
- Walk-forward origins advance one America/Denver local day after at least 14
  elapsed training days. Every fold records boundaries with
  `train_end < prediction_start`; horizons 1/6/12/24/48/72 hours are included
  only when every required future five-minute sample exists.
- Reports include air/mass MAE, RMSE, and bias by horizon; warm/winter/shoulder
  and action-provenance splits; hallway extrema, peak timing, morning mass;
  progressive prior-fold prediction-interval coverage; behavior
  precision/recall/timing where labels exist; persistence, prior-only
  seven-cycle median, and the existing 90/95 F plus 92 F streak classifier.
- Report generation is deterministic from input data; no wall-clock value is
  included in evaluation output.

## TDD evidence

1. RED: focused collection failed with missing `thermal_model.artifacts` and
   `thermal_model.evaluation` imports.
2. GREEN: the two core atomicity/quarantine/leakage tests passed (`2 passed`).
3. RED/GREEN increments covered missing report persistence, untrusted promotion
   booleans, numeric type fidelity, and temp/candidate symlink traversal.
4. Expanded evaluation RED/GREEN covered metrics, baselines, provenance/regime
   splits, missing horizons, deterministic output, behavior labels, threshold
   boundaries, physical refusal, and shadow-only gates.

## Verification

- `pytest -q openhab/scripts/test_thermal_artifacts.py openhab/scripts/test_thermal_evaluation.py openhab/scripts/test_thermal_dynamics.py openhab/scripts/test_thermal_behavior.py`
  - `82 passed in 13.91s`
- `pytest -q openhab/scripts`
  - `176 passed in 16.77s`
- `pyflakes` on all four Task 6 source/test files: clean.
- `python3 -m py_compile` on all four Task 6 source/test files: clean.
- `git diff --check`: clean.

## Concerns and handoff

No live artifact was trained or promoted. Task 7 must assemble the artifact
manifest with exact units, fit diagnostics, constraints, provenance counts,
and the canonical dataset digest before `save_candidate`; validation will
refuse incomplete evidence. Prediction-interval coverage is explicitly
calibrated only from earlier fold errors and remains evaluation evidence, not a
graduation threshold.
