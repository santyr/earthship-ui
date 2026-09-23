# Thermal v5 exploratory historical blend audit

The refused v5 candidate is archived privately under
`/home/sat/.local/state/thermal-intel/qualification-runs/thermal-v5-qualification-AsBEbyXN`.
This audit used its immutable `backtest-report.json` (SHA256
`dbcff6e3a03376a7229285a9869632cf05a32b61d1c90764f4dbd36ac1760128`),
not the production model. Each `prediction_record` stores signed model,
persistence and recent-cycle errors against the observed target.

For each horizon, sort records by forecast origin, use the first 67% to select a
single model weight from 0.00 through 1.00 in 0.05 steps by mean absolute error,
and report the remaining 33% once. The blended error is
`weight * model_error + (1 - weight) * persistence_error`. No offset or regime
parameter was fitted. This is a descriptive chronological split of a previously
inspected report, **not** an untouched final test or origin-time operational
forecast replay.

| Horizon | Earlier/later origins | Selected model weight | Later blend MAE °F | Later raw model | Later persistence | Later recent cycle |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 h | 190/94 | 0.65 | 0.354 | 0.648 | 0.985 | 0.384 |
| 6 h | 181/90 | 1.00 | 1.579 | 1.579 | 5.689 | 1.283 |
| 12 h | 161/80 | 0.95 | 1.924 | 1.865 | 6.025 | 1.532 |
| 24 h | 79/40 | 0.35 | 1.430 | 2.110 | 1.639 | 1.733 |
| 48 h | 25/13 | 0.10 | 1.739 | 1.485 | 2.008 | 1.626 |

The 24-hour later segment consists entirely of 40 warm-regime origins starting
June15. Its 0.35-weight blend improved on persistence in this exploratory
segment, but this does not establish winter or shoulder transfer. The earlier
segment contains 46 winter,27 shoulder and6 warm origins. The 48-hour segment
is too small and its selected blend was worse than the raw model later on.
Do not fit separate regime weights from these counts or change promotion gates
to accommodate the result.

The report's physical evaluation uses observed future weather/action forcing,
not the forecasts actually available at each origin. Its historical action
labels are reconstructed, with zero confirmed-action training/evaluation rows.
Therefore the apparent 24-hour gain identifies an ensemble hypothesis to test,
not a qualified advisory release. Next: freeze the proposed blending rule on
earlier data, evaluate with archived origin-time weather forecasts and
receipt-qualified initial states, reserve prospective observations (including
winter), then score confirmed actions and outcomes. Any blend used in the gate
must also be applied to the published trajectory and daily extrema; evaluation
only correction would repeat the parity defect already repaired in v5.
