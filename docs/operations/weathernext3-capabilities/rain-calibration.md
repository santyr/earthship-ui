# Rain comparison and occurrence/amount experiment

The [frozen protocol](rain-calibration-protocol.json)
retains the original evaluation policy's wet-threshold and support rules. The [actual interval experiment](rain-experiment.json) now contains matched
continuous-depth scores, timing diagnostics and original-source replay. All
37 outer candidate-fit attempts correctly refused because their historical
original decisions preceded actual acquisition of the retained labels. Synthetic
tests exercise supported fitting and scoring. Current production rain
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
The actual collection retained 217 original counter acquisitions: 200 qualified
continuous intervals and 17 gap/restart refusals. All three heads were rederived
from the complete original Google capsules for 375 mature forecasts. Thirteen
forecast scopes yield 97 independent target-and-scope pairs, of which 80 match
qualified observations in twenty measurement cohorts. These counts are not a
pooled independent sample size. Every scope preserves its original availability
basis, grid, interval, lead, gauge policy and receiver epoch. Local-calendar,
rolling and remaining-day results remain separate.

The final-third assignment is frozen from original independent forecast dates
before missing heads, unavailable labels or measurement epochs partition the
sample. All eighty original experimental prediction records and all thirty-seven
fit refusals replay exactly with their literal 415-file producing package. Six
older gain models also reproduce under their three original producer packages,
retaining their v1 coefficients and identities. Five original forecasts have an
applicable earlier gain prediction; unsupported duration, timezone or availability
retains an explicit refusal. No coefficient is refitted during outcome scoring.
The largest scope used 22,032,186 original bytes and 46.95 seconds, within the
frozen 48 MiB and 120-second experiment bounds.

Separate read-only queries retained all 312 predeclared hourly windows: 309
qualified and three refused. Every one of the 97 preselected target-and-scope
pairs has a timing result or explicit refusal. Eighty have complete coherent
hourly support; twenty-nine support a nonzero counter-depth centroid diagnostic.
Zero depth and tied peaks never invent a peak time or a probability. All
seventeen timing batches replay exactly with independent point checks.

There is still no source-bound independent resolution document, so occurrence
classes, wet-event selection, probability calibration and physical gauge accuracy
remain unsupported. All local candidates and alternative raw-head selections
remain unselected with `insufficient_evidence`; the raw production rain is
retained. Retrospective comparisons are explicitly not as-issued skill.

The future queue now retains literal originals and producing bytes, requires
actual byte-confirmed cache emission before scoring, handles delayed maturity,
receiver-epoch changes, retries, preview and restart recovery without fitting.
Its originals share the existing private shadow capacity guard: 2 GiB and
10,000 original objects, with a separate 64 MiB SQLite index. No evidence is
pruned to make room. New v2 current views live for at most six hours and never
beyond an original source initialization plus 24 hours; v1 views retain their
original two-hour lifetime.

The source-pinned, default-off producer accepts explicit local archive/state,
measurement policy, cutover, optional independent-resolution evidence and literal
model catalogs. It reads the actual current counter receipt before making its
decision. Unknown or stale counter context preserves raw heads and withholds
unsupported local predictions. It chooses the latest declared eligible original
for each exact interval before checking head completeness; a newer short profile
cannot hide older long-range coverage or substitute an older successful head.
It performs no collection, fitting, selection or hardware action. One confirmed
emission is allowed per source/catalog/current measurement generation. The
publication lock rechecks that generation before replacing the cache; a repeated
attempt reports original cache freshness without renewing the issue clock.

The existing monitor owns delayed outcome acquisition. Rain reserves at most
eight of its existing 64 observation reads, including partial-failure attempts;
owner deadlines still propagate. Full detailed comparisons live in a separate
bounded performance report, while the core report carries a small status summary.
Original measurement policy, cutover, resolution, epoch, interval, native grid,
availability basis and local/gain/producer identities remain distinct.

A real local-only prospective lifecycle retained 28 complete future intervals
from two current native originals, covering local-calendar, rolling-24-hour and
remaining-day targets. Exact cache bytes and the original emission were confirmed.
A separate repeated process reused that emission without state or clock changes;
an index rebuild recovered the same originals and confirmed 28 pending targets,
with zero premature observation queries. These are genuine future shadows in a
private verification namespace. The optional producer is not installed in
production yet; the integrated rollout remains Task 11. This lifecycle uses a
fresh literal producing package and does not repin the historical experiments.

The [Task 9 verification record](task9-verification.json) binds the final source,
complete affected backend gate, original science replay proofs and this lifecycle.
Physical gauge calibration and local probability qualification remain unsupported.
Rainfall information does not authorize cistern-availability calculations or
hardware actions.

The [installed gathering audit](station-ingestion-audit.md) verifies the RTL-SDR
decoder against manufacturer documentation and records confirmed legacy
derivation and counter-recovery defects. Its raw-versus-derived distinctions
govern which observations may enter the calibration experiment.
