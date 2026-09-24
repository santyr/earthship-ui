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

## Archived origin-time forecast prerequisite

Solar-PV already stores immutable hourly temperature, radiation, wind and
weather-code forecasts in `energy_analytics.forecast_snapshots`. Read-only
inventory on September23 found 299 distinct issuances from August20 through
September23, with roughly 232 hourly targets in the latest issuance. The table
also records `captured_at`, which is essential: its median lag after `issued_at`
for hourly temperature was about71minutes, with a maximum around2hours.
Selecting only `issued_at <= origin` can therefore use a forecast not yet
available to the household.

In a September22 15-minute grid of97 origins, Solar-PV's former historical
feature query selected49 hourly temperature snapshots whose `captured_at` was
later than the origin. The corrected query selected an earlier captured snapshot
at all49 origins; none became unavailable in that sample. Solar-PV commit
`64460be` adds `captured_at <= origin` for hourly temperature, matching radiation
and daily PV, and for replayed UI forecast reads. All758 Solar-PV tests passed;
a read-only live four-row feature read succeeded. This repairs the feature export
contract, not thermal backtesting itself.

Thermal operational replay must select a complete, single issuance only when
both issue and capture times precede the origin. Its initial indoor state and
action timeline need their own origin-time receipt cutoffs. The present archive
spans only late summer and early fall, so it cannot qualify winter advice or
replace a prospective seasonal holdout.

Source-only `thermal_model/forecast_history.py` now provides that bounded
read-only weather selection primitive. It requires one complete issuance for
every hourly bracket target, checks both issue and capture cutoffs, and returns
no forecast when the available snapshots cannot cover the requested horizon.
The query runs in a dedicated read-only repeatable-read transaction with a row
limit. Seven focused tests pass, including a late-captured newer issuance and
an incomplete-issuance case. A read-only live 24-hour lookup returned26 hourly
bracket rows from the September23 13:15:49Z issuance, captured by14:10:07Z.
The reader is not yet wired into thermal evaluation or publication; no model
score, accepted artifact or advice changed.

`thermal_model/operational_origin.py` now combines one complete archived
forecast with the existing receipt-qualified indoor, north-wall and outdoor
temperature readers at the same five-minute origin. It refuses missing or
post-origin receipts and an incomplete forecast bracket. A live read-only
assembly at September23 14:45Z found all three qualified receipts and26
captured forecast hours from one issuance. Its action knowledge is explicitly
`not_qualified`; it does not simulate, score or publish an advisory. Twelve
focused archive/assembly tests pass. The subsequent action-as-of/persistence
census is recorded below; physical-model outcome scoring remains open.

## Read-only operational-origin persistence census, September 23 evening

`scripts/audit-thermal-operational-origins.py` now connects the existing
capture-safe forecast, qualified-temperature and optional restricted
action-journal readers. It scores only same-origin indoor persistence, never
the physical model or an action benefit. The CLI bounds its elapsed origin
window to 14 days and 96 origins and refuses naive/off-grid timestamps.
Twenty-four focused audit/reader tests pass. It uses separate restricted
connection paths for the forecast archive and thermal action journal;
credentials are neither printed nor committed.

At six-hourly origins from September20 00:00Z through September23 00:00Z
(end exclusive), the live read-only 24-hour census found 11 qualified pairs
among 12 origins. One origin lacked a qualified initial indoor-air receipt.
The same-origin persistence MAE was **2.0782°F** on those 11 *overlapping*
pairs. A repeated run with the restricted action journal returned the same
forecast digests, coverage and error. It found mode knowledge for all 11
paired origins but complete action knowledge for **zero**: every origin had
two known actions and lacked `indoor_shade` and `vent`. The action snapshot
records what had been received by the origin, not whether an action actually
occurred. No action state was imputed from current telemetry or a later DM.

This establishes a reproducible historical persistence comparator and a
concrete action-coverage gap. It does **not** make the v5 physical backtest
operational, furnish an untouched validation set, justify thermal coefficient
tuning, or move the production model out of shadow. Next model replay must
fail closed on missing action forcing or restrict itself to a separately
qualified passive interval, then use prospective confirmed actions and
held-out outcomes for release evidence.

At September 23 23:04 MDT, one additional six-hour-grid origin at
September 23 00:00Z had a matured qualified 24-hour indoor target. Its
same-origin persistence absolute error was 1.98°F, with captured forecast
digest `ff29774353131ec9f0a714f0a7027694a3a50d4bf8c408e355db8ebaeb98f117`.
This read used no action-journal credential, so its action knowledge is
explicitly unqualified. It is an extra historical baseline observation,
not a physical-model or action-benefit score.
