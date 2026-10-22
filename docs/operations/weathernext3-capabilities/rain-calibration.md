# Rain comparison and occurrence/amount experiment — implementation in progress

Task 9 is in progress. The [frozen protocol](rain-calibration-protocol.json)
retains the original evaluation policy's wet-threshold and support rules. No Task 9
final outcome evaluation or candidate fitting has occurred. Current production rain
is retained; this document does not select a product or qualify a probability.

The comparison keeps total, IMERG and experimental precipitation heads separate
and uses the same complete target coverage for all three. Local-calendar days,
rolling 24-hour intervals and complete remaining-day hours have distinct identities.
Original means can supply interval totals. Marginal quantiles and hourly
probabilities cannot be added to create interval quantiles or probabilities.

The one challenger uses a ridge logistic occurrence model and a conditional
positive-amount model with training-only smearing. Its probability refers to the
named interval meeting its declared gauge-based wet-event threshold. The
below-threshold component retains a training-only trace mean, so measurable small
accumulations are not silently treated as exact zero rainfall. A range crossing
the event threshold is ambiguous. Missing independently evidenced resolution,
insufficient wet/dry classes, absent independent wet events or an unseen context
withholds the local model. Raw continuous-depth comparisons can still be reported
when their native source evidence qualifies.

The daily model's six wet/six below-threshold minimum supplies 12 distinct targets
within the already frozen 28-day training window. This applies the evaluation
protocol's rain-specific class rule; requiring the generic 48-target minimum for
one daily target per date would contradict that window. The original three-wet-
event minimum, held-out local-date blocks and 3%/5% selection/regression rules are
preserved. One bounded method is used, with no hyperparameter search.

Decoder specifications do not substitute for local measurement-resolution evidence.
The [upstream Fine Offset decoder](https://github.com/merbanan/rtl_433/blob/master/src/devices/fineoffset.c)
distinguishes WH24 and WH65 rain-counter scaling. The local reader accepts both
model labels, so a hardware label alone cannot establish the locally measured
resolution or physical rain calibration. Original source-policy and acquisition
identities must accompany any evidence used to instantiate the threshold rule.

Source-bound interval forecasts and counter observations now replay their literal
originals. The shared native counter kernel supports explicit rolling and partial
intervals while preserving the existing daily reader output and refusal rules.
Resolution declarations require a matching sensor/policy, actual availability and
at least three consistent independently counted tip trials. Missing or invalid
resolution evidence withholds the occurrence label while preserving qualified
continuous-depth diagnostics. This declaration does not qualify physical gauge
accuracy. Source-availability timestamps come from acquisition completion, not
from the last old database row. Forecast completion at or after the target start
cannot enter a complete-interval comparison.

Remaining work includes the two-part fitter and original prediction scoring,
matched actual collection and experiments,
retained prospective evidence/pending status, integration tests and disposition.
Rainfall information does not authorize cistern-availability calculations or
hardware actions.
