# Thermal v5 qualification — refused candidate

Source revision: `e7dd34e`. This run does not deploy the v5 runtime or replace
production artifacts. The existing shadow runtime/model pair stays authoritative.

## Isolated run

Started one transient user unit `thermal-v5-qualification-AsBEbyXN.service`.
Invocation ID: `84500d12f3384d37b1c0e2cede705be7`.
Private workspace: `/tmp/thermal-v5-qualification-AsBEbyXN` (mode0700).
Source is a `git archive` snapshot, not the changing main worktree. The command
is `thermal_intel.py train`, with explicit private `models` output directory and
the production artifact's exact time range:
`2025-08-16T12:50:29.206945Z` through `2026-09-20T12:50:29.206945Z`.

The unit reads the existing private environment file without copying credentials
into this repository. Qualified-temperature enable/cutover/policy/database config
match the production trainer drop-in. PostgreSQL sessions request read-only
transactions and a30-second statement timeout. Training uses historical OpenHAB
GETs and journal SELECTs; it does not invoke shadow publication or action commands.
CPU is limited to one core, numerical libraries to one worker, memory to2GiB,
runtime to3hours, and scheduling nice10. Output goes to a private `run.log`.

The production scheduled trainer was inactive at launch; its next timer was
September21 at06:50MDT. The isolated run finished on September20 at about
20:06MDT with exit status1 and a refusal receipt:
`{"reasons":["air_24h_beats_persistence"],"status":"refused"}`.
Its private model directory contains `candidate.json` and `backtest-report.json`,
but no `accepted.json`. On September23 the exact candidate/report bytes passed
the read-only v5/v3 schema and metric-consistency audit using
`scripts/audit-thermal-graduation.py --model-dir /tmp/thermal-v5-qualification-AsBEbyXN/models --artifact candidate.json`.
SHA256: candidate `c4791b12e8fd53d0aa330f231791a368f2df9be339205ff371c03c15065b1905`;
report `dbcff6e3a03376a7229285a9869632cf05a32b61d1c90764f4dbd36ac1760128`.

At 24 hours, model air MAE was 2.470023°F versus persistence 1.689895°F
on 119 scored origins. The 24-hour gate failed; other structural gates passed.
The candidate is shadow-only and was not promoted. The 1, 12, 48 and 72-hour
horizons also failed to beat persistence; only the 6-hour horizon beat both
persistence and the recent-state baseline. Confirmed-action training and
evaluation counts were both zero, so this run does not qualify action advice.
Retain the private report for diagnosis, then remove the owned temporary source
and transient unit after evidence is archived. Do not loosen the gate to accept
this candidate.

## Historical evidence boundary confirmed from source

- `pipeline.run_training` discards `forecast_reader`. `_read_authorities` reads
  sensor history and effective journal events; the evaluator passes held-out
  sample rows directly to `dynamics.simulate` as weather/action forcing.
- The physics simulation advances its own air/mass states, but its outdoor
  temperature, radiation and action inputs come from those historical future
  rows. This is a conditional physical-model hindcast, not origin-time forecast
  accuracy. Removing residual blending does not remove this distinction.
- `journal.effective_events/effective_modes` resolve present-day supersession
  using effective timestamps without an origin-time `received_at` cutoff.
  Retrospective corrections can therefore differ from knowledge at issuance.
- Legacy dataset preprocessing interpolates between bracketing observations
  before chronological folds are split. A training-row timestamp before the
  origin alone does not prove every input used to construct it was then known.
- Daily origins maximize subsequent continuous coverage. This is a useful
  retrospective coverage rule, not an unbiased fixed-time operational schedule.

Keep the physical hindcast for diagnosing model fit. Qualify operational advice
separately with immutable origin-time weather forecasts, receipt-qualified
initial states, origin-available modes/actions, and later scored outcomes.
Do not represent this run as an untouched operational holdout, confirmed causal
benefit, or proof that historical action labels are trustworthy. Before tuning,
reserve a separate chronological validation/test protocol and verify its
preprocessing and correction cutoffs at the input boundary.
