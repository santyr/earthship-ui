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

## Blocking-review hardening wave (2026-08-13)

### Exact RED evidence

- Review probe collection: `pytest -q openhab/scripts/test_thermal_artifacts.py openhab/scripts/test_thermal_evaluation.py` -> `24 failed, 24 passed in 4.13s`. Failures covered semantic metric bounds/types, explicit `shadow_only`, exact Task 4/5 contracts, accepted-artifact revalidation, invalid UTF-8, unique atomic-write races, corrupt-reader/promoter locking, and target-aware interval history.
- Quarantine reservation probe: `pytest -q openhab/scripts/test_thermal_artifacts.py -k quarantine_destination_is_reserved_with_o_excl` -> `1 failed, 38 deselected in 0.16s`; no `O_EXCL` reservation was observed.
- Seasonal ordering probe: `pytest -q openhab/scripts/test_thermal_artifacts.py -k behavior_seasonal_modes_use_canonical_order` -> `1 failed, 39 deselected in 0.17s`; reversed canonical modes were accepted.

### GREEN implementation and evidence

- Promotion and accepted loading now independently revalidate schema, recursive finite/type semantics, exact item/unit/digest/revision/ranges, complete Task 4 diagnostics and named constraints, Task 4 physics/stability, exact Task 5 features/transitions and canonical seasonal vocabulary, explicit `shadow_only=true`, and recomputed provisional gates. Negative error magnitudes, out-of-range coverage, boolean numerics, negative/non-integer counts, and negative timing errors fail closed.
- Unique sibling `mkstemp` files are file-fsynced, atomically replaced, and followed by directory fsync. A per-registry advisory lock covers accepted read/diagnose/quarantine and promotion. Quarantine uses a unique `O_EXCL` sibling, copies from an inode-verified descriptor, fsyncs it, rechecks the accepted inode, then unlinks and fsyncs the directory. Invalid UTF-8 and JSON/schema/semantic corruption retain exact evidence and raise `ArtifactUnavailable`.
- Every scored error record now retains `origin_at` and `target_at`. Interval calibration at an origin includes only same-horizon errors with `target_at <= origin_at`, so overlapping 48/72-hour daily origins cannot use outcomes that have not occurred.
- Focused artifact/evaluation: `50 passed in 3.82s`.
- Focused artifact/evaluation/dynamics/behavior: `107 passed in 15.20s` before the two final hardening probes; rerun below records the final total.
- Static checks (`pyflakes`, `py_compile`, `git diff --check`) are clean before the final baseline run.

### Final verification after hardening

- Nested semantic-type probe: `pytest -q openhab/scripts/test_thermal_artifacts.py -k "metric_semantics and not numeric_types"` -> `1 failed, 6 passed, 34 deselected in 0.23s` before the scalar-key fix; the string interval fraction was incorrectly accepted.
- `pytest -q openhab/scripts/test_thermal_artifacts.py openhab/scripts/test_thermal_evaluation.py openhab/scripts/test_thermal_dynamics.py openhab/scripts/test_thermal_behavior.py` -> `110 passed in 15.11s`.
- `pytest -q openhab/scripts` -> `204 passed in 17.98s`.
- No PostgreSQL/OpenHAB/raw-store writes, advice graduation, commands, publishing, or actuation were added.
