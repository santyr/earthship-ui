# Task 7 report: offline thermal training and shadow prediction

## Status

Implemented and verified dependency-injected offline training, chronological
backtesting, and bounded local-only thermal shadow prediction. OpenHAB JDBC
history, the weather forecast, and the application journal remain read-only
inputs. No publishing, advisory, command, or actuation surface was added.

## Delivered

- `run_training` reads the exact `THERMAL_ITEMS`, effective journal events and
  modes, builds the canonical dataset, fits Task 4/5 models, evaluates with the
  Task 6 chronological evaluator, persists the backtest report before candidate
  validation or promotion, and assembles the exact Task 6 manifest contract.
- Promotion refusal raises `TrainingRefused` with durable report evidence and
  CLI `train` exits nonzero with explicit reasons. `backtest` persists only its
  local report.
- `run_shadow` loads only the accepted Task 6 artifact and additionally rejects
  future-dated artifact creation/training timestamps. Older valid artifacts
  remain usable at low confidence; model and training-data ages are disclosed,
  with a neutral missed-daily-cadence reason rather than an invented expiry.
- Critical hallway, mass, outdoor, and radiation readings require timezone-aware
  timestamps, physical ranges, and age no greater than 20 minutes. Glazing is
  optional and may be null. Missing, stale, future, non-finite, corrupt, or
  incompatible inputs fail soft to `unavailable` with an empty schedule.
- Timestamped hourly temperature and radiation are piecewise-linearly
  interpolated onto elapsed five-minute instants; cloud/weather, wind, and mode
  are held within their source hour. Duplicate/gapped/naive rows and any need to
  extrapolate are rejected. DST fallback is covered explicitly.
- Forecasts require at least 24 available hours and may shorten to the final
  timestamp through 72 hours while reporting `availableHours`.
- Warm baselines repeat the Task 5 nightly vent window across the full horizon.
  Candidate schedules remain null unless the Task 5 search returns an improved
  bounded candidate and every repeated vent window is physically valid.
  Boosted airflow is inherited only from Task 5 behavior evidence.
- Shadow JSON is version 1 and always `status=shadow`; it has the exact bounded
  top-level schema, no commands, at most 73 exact local-hour trajectory points,
  at most 25 observations, a closed action-marker vocabulary, prediction
  intervals, explicit provenance/ages, and a strict size below 16 KiB.
- Confidence never exceeds `low`. Confirmed action labels require confirmed
  evidence in both training and evaluation; no same-fold residual inference was
  added.
- CLI vocabulary is exactly `journal`, `train`, `backtest`, and `shadow`.
  `shadow` atomically writes only local JSON and there is no `--publish` flag.
- `forecast_intel.py` remains byte-identical.

## TDD evidence

1. RED: the initial focused test collection failed with
   `ModuleNotFoundError: No module named 'thermal_model.pipeline'`.
2. The first implementation run exposed seven failures across orchestration,
   output, and CLI seams; fixes brought the initial focused set to `20 passed`.
3. Additional authority probes failed for accepted-artifact unavailability and
   explicit JDBC service selection before both were fixed.
4. Final self-review probes first failed seven cases covering DST fallback,
   recurring nightly venting, and physical input ranges; the targeted rerun was
   `7 passed`, and the complete focused suite was `26 passed in 4.36s`.

## Verification

- `pytest -q openhab/scripts/test_thermal_pipeline.py`
  - `26 passed in 4.36s`
- `pytest -q openhab/scripts/test_thermal_*.py openhab/scripts/test_forecast_intel.py`
  - `259 passed in 23.16s`
- `python3 -Werror -m py_compile` on the Task 7 source/test files: clean.
- `pyflakes` on the Task 7 source/test files: clean.
- `python3 openhab/scripts/thermal_intel.py --help`: only `journal`, `train`,
  `backtest`, and `shadow` are exposed.
- `git diff --check`: clean.
- `git diff --exit-code -- openhab/scripts/forecast_intel.py`: clean.
- Production scan for OpenHAB writes, `sendCommand`, `--publish`, actuation,
  advisory item names, and causal wording: no matches.
- Independent frozen-diff security review: all three files completed with
  `no_issue_found`; canonical scan contract sealed successfully. Readable report:
  `/tmp/codex-security-scans/earthship-ui/32286b4_20260813-mN7KAt/report.md`.

## Self-review and concerns

Dependency injection, refusal persistence/order, exact manifest keys, accepted
artifact selection, timezone/freshness/interpolation, schema/size bounds,
fail-soft behavior, action evidence, causal wording, and write/authority surfaces
were reviewed against the Task 7 brief. No live artifact was trained and no live
shadow was generated because that would require site histories, journal state,
and forecast/runtime dependencies; this task's deterministic tests exercise those
boundaries without mutating them.
