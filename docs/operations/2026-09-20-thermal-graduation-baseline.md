# Thermal graduation baseline audit — September 20, 2026

Task99 remains in progress. This is a descriptive audit, not new release
thresholds, a promotion, or evidence of causal benefit from advice.

## Reproducible evidence

Run `python3 scripts/audit-thermal-graduation.py`. The utility reads the accepted
artifact and backtest report, validates both without loading the mutable model
registry, requires matching metrics and refuses files changed during the read.
It does not train, publish, quarantine artifacts, query the database or control
equipment. Five tests pass in `scripts/test_thermal_graduation_audit.py`.

Audited private model directory: `/home/sat/.local/state/thermal-intel/models`.
The accepted model was trained through `2026-09-20T12:50:29.206945Z`; the report
covers `2025-08-16T12:55:00Z` to `2026-09-20T12:55:00Z`.

- accepted.json SHA256: `40a48cf6e491054a83b2577c2974a5a65ec37e8c8298f0e36613238ce4201e18`
- backtest-report.json SHA256: `4927326feed6c47c710d9fb488654b26c14e68879dd5bb361936b7c9033fdc5b`

## Forecast evidence

Air-temperature mean absolute error, Fahrenheit; lower is better. Coverage is
the observed fraction inside nominal 90% backtest intervals, not a confidence
statement about the coverage estimate. Long horizons have limited support.

| Horizon | Model MAE | Persistence MAE | Recent-cycle MAE | Scored targets | Interval coverage (targets) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1h | 0.687 | 1.249 | 0.471 | 284 | 92.9% (283) |
| 6h | 1.682 | 6.572 | 1.639 | 271 | 88.1% (270) |
| 12h | 2.317 | 7.178 | 2.089 | 241 | 91.3% (240) |
| 24h | 2.179 | 1.690 | 1.834 | 119 | 81.4% (118) |
| 48h | 2.322 | 1.453 | 1.550 | 38 | 72.2% (36) |
| 72h | 4.194 | 1.171 | 1.712 | 15 | 46.2% (13) |

No reported horizon strictly beats both baselines. At 24h, model MAE exceeds
persistence in all three reported regimes: shoulder 2.272 versus 1.497 (27
targets), warm 1.927 versus 1.734 (46), winter 2.375 versus 1.759 (46).
Air bias is +0.524F at 24h, +1.214F at 48h and +3.074F at 72h.

The accepted `air_24h_beats_persistence` gate has a misleading name: the approved
shadow-only policy permits MAE up to 0.75F worse than persistence. Thus its true
value does not contradict these errors and does not qualify advisory release.
`shadow_only` remains true and `graduation_thresholds` is null. Preserve the
approved shadow tolerance; do not silently redefine it as a release criterion.

Confirmed action evidence has zero training rows, zero evaluation targets and
zero disjoint folds. Historical reconstructed labels do not establish confirmed
ventilation/shade outcomes or causal benefits. Data coverage and receipt-qualified
provenance still need separate assessment; a 400-day date range is not proof of
400 complete or qualified days.

## Discovered evaluation/runtime mismatch

Current repository `thermal_model/evaluation.py` applies
`_shrunk_prediction(raw, origin) = 0.85 * raw + 0.15 * origin` before recording
air and mass horizon errors. In contrast, `pipeline.py::_simulate_schedule`
returns the raw physical simulation; `_trajectory` and summary high/low use
those raw states without this blend. Its interval margin uses the artifact's
24h backtest RMSE and coverage, which were scored on blended errors.

Consequently these backtest metrics cannot directly qualify the displayed raw
trajectory or its interval calibration. This is a source-path finding, not a
new live-output replay. Weather and action forcing differences between historical
evaluation and operational forecasting also still require examination.

Before parameter tuning, define and test one forecast-output contract across
evaluation, candidate scoring and publication, including interval calibration.
Do not simply blend the displayed line while leaving advisory scoring and
physics validation inconsistent. Any changed model/evaluation semantics need a
versioned artifact boundary and fresh backtest evidence, not reuse of this
accepted report. No runtime semantics or accepted artifact were changed here.

## Next work

1. Resolve output-contract parity and audit origin-time weather/action inputs;
   distinguish conditional historical simulations from operational forecasts.
2. Diagnose the live no-candidate reason with a read-only input replay and
   rejection counts. The generic reason alone does not identify the cause.
3. Audit confirmed action collection and outcome attribution, then conduct
   bounded historical tuning with chronological validation and an untouched
   final holdout. This report is exploratory evidence, not that final holdout.
4. Derive and review graduation thresholds only after comparable evidence exists.

See [the full graduation workstream](thermal-model-graduation.md). Other
Earthship/OpenHAB requirements remain in the outstanding-work tracker.
