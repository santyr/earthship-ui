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

## Blocking review remediation wave (2026-08-13)

### Findings closed

- Candidate semantics are now null unless Task 5 returns a structurally
  different, physically valid schedule whose modeled improvement reaches
  `MINIMUM_IMPROVEMENT`. `protocol_constraint`,
  `minimum_improvement_not_met`, `no_valid_candidate`, structural equality,
  and post-expansion physical rejection retain the baseline with a null
  candidate and exactly zero effect.
- `validate_shadow_output` now validates the complete exact v1 tree: top-level
  and nested key sets; strict non-boolean finite numerics; aware chronological
  timestamps; model/current/forecast/schedule/confidence/provenance/reason
  vocabularies; 73-point trajectory and 25-point observation bounds; monotonic
  rows; exact local-hour trajectory timestamps; closed action markers; ordered
  uncertainty intervals; candidate-null/effect invariants; confidence/source
  agreement; unavailable/available invariants; and compact JSON below 16 KiB.
  Both construction and atomic writing invoke this validator.
- CLI shadow input failures from site/current JDBC reads, forecast retrieval or
  parsing, and accepted-artifact loading now atomically replace any prior output
  with a valid unavailable v1 payload, empty schedule, and explicit reason.
  They print the unavailable payload to stderr and return nonzero. The default
  invocation still writes the standard local shadow path and has no publish
  option.
- Walk-forward evaluation now records exact action-provenance counts separately
  for every fold's training rows and held-out horizon targets. Metrics summarize
  confirmed training rows, confirmed evaluation targets, and folds where both
  are strictly separated by the origin. Shadow labels become `confirmed` only
  when that disjoint-fold evidence is present; whole-dataset manifest counts can
  no longer satisfy confirmation.
- Task 6 artifact/report validation accepts only the exact action-evidence shape
  and requires the per-fold provenance split for newly persisted v1 reports.

### Exact RED evidence

- Candidate-null regressions: `3 failed, 60 deselected in 1.48s`; cold-cloudy
  protocol, minimum improvement, and structurally equal search results all
  incorrectly exposed the baseline as a candidate.
- Provenance regressions: `3 failed, 2 passed, 35 deselected in 2.42s`; folds
  lacked separate provenance evidence and heldout-only/overlapping evidence
  incorrectly produced `confirmed`.
- Task 6 evidence contract: `1 failed, 70 deselected in 0.21s`; the exact new
  `action_evidence` field was rejected as unknown before validation support was
  added.
- Deep shadow schema: `15 failed, 1 passed, 5 deselected in 0.06s`; every
  malformed nested payload was accepted by the former top-level-only validator.
- CLI fail-soft replacement: `3 failed, 30 deselected in 0.21s`; current and
  forecast failures escaped without writing, while artifact unavailability
  wrote a payload but incorrectly returned success.

### GREEN evidence before final commit

- Candidate-null focused set: `3 passed, 60 deselected in 1.37s`; direct Task 7
  minimum-improvement, winter-protocol, and structural-equality output checks:
  `3 passed, 32 deselected in 0.62s`.
- Disjoint provenance focused set: `5 passed, 35 deselected in 2.38s`; real
  evaluator training-only, heldout-only, and both-disjoint cases:
  `3 passed, 10 deselected in 0.41s`.
- Deep schema plus pipeline: `51 passed in 5.36s`, then `54 passed in 5.32s`
  after strict chronology/list and confidence/provenance alignment hardening.
- CLI current/forecast/artifact replacement: `3 passed, 30 deselected in 0.16s`.
- Combined pipeline/schema/evaluation/behavior/artifact contract suite:
  `174 passed in 22.06s`.
- Complete thermal plus forecast baseline before the two final direct candidate
  regressions: `287 passed in 27.31s`; the final post-report run is recorded in
  the commit handoff.
- `pyflakes`, warning-as-error `py_compile`, `git diff --check`, CLI help, and
  the tracked `forecast_intel.py` invariant were clean. Production scans found
  no OpenHAB write, `sendCommand`, publish flag, command item, advisory item, or
  causal-claim sink.

### Remaining concern

No live OpenHAB, PostgreSQL, forecast service, model registry, or actuator was
mutated. Runtime failure behavior is proven through injected CLI tests that
start with stale local output and verify its atomic replacement; live transport
smoke remains intentionally out of scope for this read-only/offline task.

### Final event-identity hardening and verification

- Same-event persistence RED: after adding the explicit dataset metadata seam,
  `test_persistent_confirmed_state_does_not_reuse_one_event_across_fold_origin`
  failed because one pre-origin confidence-1 state produced three supposed
  evaluation confirmations. `ThermalDataset` now retains only five-minute rows
  containing actual `nostr_confirmed` or `manual_dm` events; evaluation relabels
  persistent confirmed state without such an event row as unknown action
  evidence. The persistence plus training-only/heldout-only/both-disjoint set is
  `5 passed, 9 deselected in 0.91s`.
- Dataset source binding: the actual-event metadata regression is
  `1 passed, 24 deselected in 0.05s`; photosensor events do not enter the
  confirmed row set.
- Persisted report consistency RED: a mismatched fold summary was accepted
  (`1 failed, 70 deselected in 0.18s`). The registry now recomputes confirmed
  training rows, held-out targets, and disjoint folds from exact fold receipts;
  the corrected probe is `1 passed, 70 deselected in 0.15s`.
- Final expanded focused suite (pipeline, schema, evaluation, behavior,
  artifacts, and dataset): `202 passed in 22.32s`.
- Final complete thermal and forecast baseline: `291 passed in 25.20s`.
- Final warning-as-error compile and `pyflakes`: clean.
- Final CLI help, `git diff --check`, byte-identical `forecast_intel.py`, and
  prohibited OpenHAB write/command/publish/advisory symbol scans: clean.


## Re-review hardening wave (2026-08-13)

### Findings closed

- Reader failure reasons now pass through one bounded normalizer: controls and
  newlines collapse to a single line, each reason is truncated on a UTF-8
  boundary at 256 bytes, at most eight distinct reasons survive, and an empty
  exception gets a stable reason naming the failed site/current/forecast/artifact
  input class. `_unavailable()` guarantees at least one reason, so atomic writing
  can always replace stale output with a valid sub-16-KiB unavailable payload.
- The exact public v1 validator now rejects identical candidates regardless of
  claimed effect; incomplete, reversed, or out-of-horizon vent windows; available
  critical ages above 20 minutes; missing summaries; extrema that exclude the
  emitted trajectory; future observations; and forecast/trajectory/extrema times
  outside the modeled horizon. Reason strings are also exact, bounded, and
  control-free.
- Rich internal schedules are validated before simulation: vent and shade windows
  are paired and ordered within the horizon; airflow levels are closed-vocabulary;
  same-level segments are sorted and nonoverlapping; and boosted segments must be
  nested in a baseline vent window. Invalid candidates become null with zero
  effect, while an invalid baseline fails soft to unavailable.
- Confirmed action evidence now uses ceiling alignment: an event at 00:07 belongs
  to the 00:10 sample, an event exactly at 00:05 remains at 00:05, and an event
  beyond the final dataset sample is excluded. Walk-forward train/evaluation
  membership continues to use these effective sample identities.

### Strict TDD evidence

- Initial combined RED: `10 failed, 15 passed`; malformed cross-field payloads,
  pre-event floor alignment, empty/oversized reader errors, and the missing
  internal schedule validator all reproduced the review findings.
- Bounded CLI reader GREEN: `5 passed`; both `OSError()` and a 16-KiB-plus Unicode
  control-bearing exception replace stale output, validate as unavailable with an
  empty schedule, stay below 16 KiB, return nonzero, and expose no publish field.
- Public schema and construction GREEN: `29 passed`; internal schedule plus
  preserved candidate-null/winter behavior: `5 passed`.
- Event ceiling and confirmed disjoint-evidence GREEN: `5 passed, 10 deselected`.
- Additional RED/GREEN edges: empty artifact context failed then passed with
  `accepted artifact input unavailable`; null summary and summary/trajectory
  containment failed then passed; control-bearing and excessive reason lists
  failed then passed (`2 passed, 24 deselected`).

### Final verification

- Focused pipeline/schema/dataset/evaluation suite: `110 passed in 9.04s`.
- Complete thermal and forecast baseline: `306 passed in 26.02s`.
- `compileall`, `pyflakes`, `git diff --check`, CLI main/shadow help, and
  byte-identical `forecast_intel.py`: clean.
- Prohibited OpenHAB write, command, publish-flag, and mutating HTTP helper scan:
  no matches. The CLI remains exactly journal/train/backtest/shadow and local-only.

### Remaining concern

No live OpenHAB, PostgreSQL, forecast service, accepted registry, or actuator was
mutated. Transport failure behavior is covered through injected CLI-level tests;
intentional live-service smoke remains outside this read-only/offline task.
