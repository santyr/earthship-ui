# Retained scoring deadline and learned-PV progress

Read-only diagnosis on October 16 separates an old native worker failure from
current production feedback and the optional captured-PV queue. No production
job was manually started, source query issued, limit changed or model fitted.

## Historical native deadline

The scheduled 08:06 MDT slot selected the sealed
`actual-review-fixes-20261014/final` archive through the effective native-only
dispatch, which retains 41 historical stages. The archive deployment is
`bbc998aea1f95ae1e2f68665508f3f1e7570c65e2ff99e6d069842f2d1819f65`.
The dispatch, manifest and both source hashes were independently checked.

The retained outer `household_forecast_score.py:71` sets a 50-second deadline;
line 98 raises `score lifetime elapsed`. Its original `native_thermal_live.py:446`
sets another 50-second deadline, checked at line 449. The normal failed
invocation's journal records `score_withheld`, `deadline`, outer source line98
at 2026-10-16T14:06:53.507091Z. Current resource/pressure adapters intentionally
preserve archived source and do not change either local clock.

The current coordinator has a 120-second useful-work budget and the effective
service timeout is 130 seconds. Thus extending only the systemd timeout, or only
the archived outer guard, cannot resolve this mismatch. The archived inner
function belongs to the original model runtime; silently editing its sealed
source or substituting a clock would invalidate the claimed execution identity.
The existing practical-budget and continuity documents explicitly retain this
historical-worker limitation. The operator approved moving historical orchestration outside the model while
preserving the archived numerical functions/receipts and current operational
deadlines. Implementation and verification follow below; production activation
is recorded separately.

Current-model scoring completed naturally at08:11 and08:21 MDT; the latter
finished08:21:28 with exit0. Independent battery/load/PV scoring completed at
08:18:31 with exit0. This is a historical-worker issue, not evidence that all
production scoring is blocked. Scheduled legacy-v1 workers were already retired;
their old pressure refusal is no longer an active deployment blocker.

## Learned-load captured PV

At14:16:49Z the private captured-PV and solar indexes each retained24 selected
hourly origins. The first learned-load origin at13:00:15Z is present and unscored;
its absence is not caused by losing the source forecast. Two horizons were due
at14:05:15Z: the08:00:15Z origin's6-hour result, then the13:00:15Z origin's1-hour
result. They have equal maturity, so the producer's existing original-hour tie
break selects the older origin first. Each normal opportunity processes exactly
one due horizon. The14:18:31Z publication still has zero learned-PV pairs while
this earlier horizon advances. The next normal08:28:20MDT opportunity is the
expected opportunity for the learned origin if admission and source coverage
succeed; that expectation was not a completed score or a guaranteed schedule.
The actual08:28 opportunity returned `captured_PV_scenario_or_reference_unavailable`
for the newest scenario, while the learned-load AC/SoC report refreshed. The PV
report therefore remains at14:18:31Z. The first learned-PV original is still
retained, but a subsequent unavailable current reference is an additional
producer admission obstacle. The queue ordering alone does not explain this
later publication gap; resolving that separate fallback behavior is not part
of the retained thermal deadline correction.

No sample was replaced, prioritized by its measured outcome or backfilled with
a later load model. No scheduler or queue policy changed. A nonfuture
`next_mature_at` means overdue queue work remains; it does not mean the learned
forecast has not matured. The same-issue learned-load AC/SoC outcome already has
one matched pair, now independently reproduced through the exact deployed CLI
from its retained raw originals, with network forbidden. That separate result
still does not establish captured-PV accuracy, independent-day skill or causal
action effects.

Private sanitized diagnosis and replay proof are under
`.superpowers/sdd/2026-10-12-household-common-cycle/native-score-progress-20261016/`.
The approved read-only per-intent assessment remains deployed; all families stay
unqualified. Full PR #3 remains incomplete, with actuator translation disabled.


## Approved implementation and original-output verification

`household_retained_native_score.py` now owns the operational historical loop
outside the fitted runtime. The current worker verifies this helper against its
explicit SHA before loading it and on every guard. Archived source files, their
manifest, imports and model/runtime bindings remain original. Native historical
workers use the archive's original source score, completion, query, retry and
report functions; the archived outer/inner orchestration functions are not run.
Legacy file-only workers retain their original entrypoint.

The current parent passes its absolute monotonic deadline through `exec`.
Admission, model reads, score construction and final verification all consume
that same budget; the child cannot extend it past120 seconds from its own start.
The existing absolute forecast preparation boundary, exclusive lock, shared
pool/zero worker swap, pressure checks and original configuration/source checks
remain. No scheduler, numerical runtime source, candidate or original receipt
changes are required. Older archive report conventions are preserved.

Genuine fixture regressions compare the complete saved source score with an
independent full original replay after a simulated76 seconds; they also verify
that expired admission cannot renew the budget and that configuration, pressure,
forecast-window and archive changes still refuse success. The existing retained
slot test was stale after the prior native-only cutover: it sampled two history
slots20 minutes apart, selecting the same entry. It now exercises successive
native history slots6/16 and the correct reserved minute. Dispatch tests check
the inherited deadline explicitly.

At2026-10-16T14:35:17Z the new coordinator independently reproduced a completed
production score from the exact oldest50-second archive, using its original
model87896dd2, runtime95293950 and original raw query packets. Full source score
`e09ea835448a821989101f6442fcfeac4441042cf6c7bc011ff6ff91986aa230`
is identical. All38 pinned input files stayed unchanged. Replay took10.089 seconds
with network forbidden and all output redirected to a private evidence directory.
It created no new live outcome, forecast or fit. This verifies numerical/source
parity for that retained original; production backlog latency is not inferred
from a one-score replay.


Validation before review:99 affected score, source/completion/report, pressure,
dispatch, family and model-identity tests pass in77.72seconds. A separate adjacent
batch passes64 tests with one explicitly gated resource smoke skipped; running
that exact smoke inside the actual shared pool then passes. Deployment/daily
integration and focused guard/dispatch checks pass41 tests. These are separate
batches with overlap, not a sum of distinct cases. Original-output offline replay
above uses the production archive, independently of synthetic fixture timing.


## Production activation

The single immutable review of source1a3d5d8 found no Critical, Important or
Minor issues and requested no correction. Independent Gitleaks8.30.1 default
rules, no suppression and full redaction report zero findings for the committed
change. GitGuardian's large-PR skip is not represented as a clean scan.

The owned unchanged-model activation completed at2026-10-16T14:46:49Z,
deployment097e4f75. Complete model284139ee, trained through2026-10-16T06:00Z,
remains byte-identical. No fit, fresh forecast, serving qualification probe or
explicit service restart was run. The transaction waited for idle workers,
quiesced the existing timers, verified the generation and restored those timers.
Readback at14:47:24Z verifies all five owned files, effective shared launchers
and deployment pins, all three active timers and the existing score calendars.
UI, model and forecast returnHTTP200/provisional. Shared6GiB maximum/5GiB high,
zero worker swap,256 tasks and8core-equivalent ceiling are unchanged. The clean
idle daily checkout now selects1a3d5d8 with unchanged daily unit bytes; training
was not started.

The original50-second archive's next scheduled selection is18:06UTC
(12:06MDT) in the42-entry history rotation. Its network-denied original-output
parity is verified above. End-to-end production backlog latency for that exact
selection remains pending its normal job; no manual score was triggered to
replace that evidence. Current-model/other natural jobs and post-activation
publication observations are recorded separately. Full PR #3 qualification,
physical/action effects and owner integration remain incomplete. Actuator
requests stay disabled.
