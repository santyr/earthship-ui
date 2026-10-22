# Rain comparison and occurrence/amount experiment — implementation in progress

Task 9 is in progress. The [frozen protocol](rain-calibration-protocol.json)
retains the original evaluation policy's wet-threshold and support rules. No Task 9 real-data
final outcome evaluation or coefficient fitting has occurred. Synthetic tests exercise fitting and scoring. Current production rain
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

The installed station is an **Ambient Weather WS-2902**, identified by the user.
The [manufacturer manual](https://ambientweather.com/mwdownloads/download/link/id/567/)
(version 1.12, page 47) specifies nominal rain resolution of **0.01 inch
(0.254 mm)**. The [station context](station-context.json) retains this identity and
reference. If confirmed for the local decoded counter, the frozen two-resolution-
step rule gives a 0.508 mm event threshold, with the existing boundary/resolution
ambiguity band. Manufacturer resolution describes the nominal measurement step;
it does not establish local gauge accuracy or independently measured local
resolution. The current frozen model policy still records that distinction.
Receiver WH24/WH65 decoder aliases no longer leave the physical station model
unknown; its original counter/scaling evidence remains part of verification.

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

The bounded fitter, matched point/event/probability scores, day-block uncertainty,
original prediction records and complete hourly timing helper are implemented.
A 36-day synthetic experiment exercises 12 causal outer fits, using only earlier
acquired training labels; passing its gate means eligibility for review, with no
production selection or probability qualification. Retrospective experiments and
prospective shadows are scored separately. Existing rain gain artifacts apply
only to exact 24-hour elapsed targets under their original timezone contract.

The [complete source inventory](rain-source-inventory.json) freezes 358 native
originals before Task 9 gauge outcomes are collected. Larger archives are retained
in full; each experiment has its own bounded input and runtime allowance.
Remaining work includes target derivation, matched read-only counter collection
and actual experiments, retained prospective pending work, integration tests and
a final disposition.
Rainfall information does not authorize cistern-availability calculations or
hardware actions.

The [installed gathering audit](station-ingestion-audit.md) verifies the RTL-SDR
decoder against manufacturer documentation and records confirmed legacy
derivation and counter-recovery defects. Its raw-versus-derived distinctions
govern which observations may enter the calibration experiment.
