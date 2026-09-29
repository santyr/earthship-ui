# Thermal historical versus operational readiness — September 24

Read-only checkpoint updated after the natural September 24 trainer completed
at 08:42 MDT. The accepted artifact is trained through September 24 12:50Z
with code revision `507748cee9ca`. Its `promotion.eligible=true` is
**internal shadow-artifact acceptance**, not approval to enable advice:
`shadow_only=true` remains an
explicit invariant. The operator-approved provisional gate allows 24-hour
model MAE up to 0.5°F above same-fold persistence to collect divergence data.

| Historical 24-hour air MAE | Model | Persistence | Recent-cycle |
| --- | ---: | ---: | ---: |
| Overall, 119 paired folds | 2.179°F | 1.690°F | 1.834°F |
| Warm, 46 | 1.927°F | 1.734°F | 1.764°F |
| Winter, 46 | 2.375°F | 1.759°F | 1.978°F |
| Shoulder, 27 | 2.272°F | 1.497°F | 1.708°F |

Thus the model was worse than persistence in every scored regime; the overall
0.489°F deficit only just fits the 0.5°F provisional tolerance. The separate
capture-qualified operational score after today's 07:55 shadow publication
has eleven non-overlapping one-hour targets at model/persistence MAE
1.3448/0.5073°F. All eleven model errors are negative; paired outdoor
forcing bias is +3.2327°F. Eight overlapping six-hour targets also all err
low, model/persistence MAE 4.1949/2.3400°F, with paired outdoor forcing bias
+2.8500°F. Only two six-hour targets are independent (4.9995/3.1500°F).
This pattern does not isolate weather forcing as the cause of low indoor
predictions; action reconstruction and dynamics remain confounded. At 10:05
MDT, the first captured 24-hour target matured: the September 23 09:50 MDT
publication predicted today's 10:00 MDT hallway temperature 6.286°F below
the qualified outcome, while same-origin persistence was 0.54°F above it.
The 10.414°F prediction interval missed; paired outdoor forecast error was
+1.64°F. This is one independent operational pair, not a root-cause estimate,
but it is adverse evidence for shadow exit. Twelve later captured 24-hour
targets were still immature. The natural 07:55 publication exited
zero and remained low-confidence shadow with no candidate because the
minimum modeled improvement was not met. The daily trainer later exited
successfully and reported an internally promoted artifact, but the new
artifact still records `shadow_only=true`, the same 119-fold 24-hour air
comparison (model 2.1785°F versus persistence 1.6899°F), and zero confirmed
action-evidence evaluation targets. Training completion does not satisfy the
operational shadow-exit gate.

This evidence supports continued historical tuning but not shadow exit.
Before fitting an operational correction, freeze chronological training,
validation and untouched later test periods; use exact as-issued weather
forcing and qualified indoor outcomes; compare against both same-origin
persistence and recent-cycle baselines; and obtain real shade/vent action-state
provenance (or a genuinely qualified passive interval). Reconstructed actions
cannot be silently relabeled as observed. Keep the existing advisory/action
authority unchanged while these data and accuracy gates remain open.

At 11:45 MDT, the bounded read-only strict scorer was rerun against the
September 23 15:45Z onward persisted publications, requiring each exact private
forcing archive and qualified later temperature receipts. Thirteen
non-overlapping one-hour pairs scored model/persistence MAE **1.2166/0.4846°F**;
all thirteen model errors were low and their nominal intervals covered all
thirteen outcomes, though the intervals averaged 10.4138°F wide. Ten
overlapping six-hour pairs scored **3.8390/1.9980°F**; only three disjoint
windows remain and score **4.1417/2.5200°F**, with two of three intervals
covering. All ten six-hour model errors were low, while their paired outdoor
forecast errors had mixed signs. The 24-hour set still has only the one
adverse mature captured pair described above; twelve targets are not due.
The one-hour sample spans two artifact revisions (twelve old, one current),
and all scored outputs remain low-confidence. These observations strengthen
the no-graduation decision but do not isolate a causal coefficient or provide
an untouched seasonal validation set. This scoring checkpoint did not trigger
the publisher or write outcomes.

The next natural shadow timer fired at 11:56 MDT and exited zero. Its live
`Thermal_Model_JSON` has a 17:56:11.975024Z decision time, accepted revision
`507748cee9ca`, `status=shadow`, low confidence and no candidate schedule.
The strict archive verifier accepted its exact matching private forcing
capture with 240 forecast rows. The timer rescheduled for 13:56 MDT. This
closes a current-artifact publication/capture check, not its future outcome
scores, action provenance, seasonal holdout or shadow-exit criteria.

At 12:05 MDT, the next captured 24-hour target passed the scorer's five-minute
maturity margin. Its September 23 11:51 MDT publication missed the qualified
hallway outcome by **−7.565°F**, versus **+0.18°F** for same-origin
persistence. The 10.414°F model interval missed; archived outdoor forcing
was **4.02°F cooler** than the qualified outdoor outcome, opposite the sign
of the first 24-hour pair's outdoor error. Both 24-hour model errors are low,
both intervals miss, and their overlapping windows leave only **one**
non-overlapping selection. The paired two-publication MAE is 6.9255°F for
the model versus 0.36°F for persistence; it is diagnostic, not two independent
days or a validated coefficient correction. Twelve captured 24-hour targets
remain immature. Shadow-only and existing advice/control authority remain
unchanged.

At 16:55 MDT, the same bounded capture-strict scorer was rerun read-only
from September 23 15:45Z. Four captured 24-hour targets had matured under
the previous `c87551f92f02` revision. All four model errors were low
(−6.286, −7.565, −5.977 and −5.548°F), and all four 10.414°F nominal
intervals missed. Their overlapping MAE was 6.344°F versus 1.35°F for
same-origin persistence; greedy non-overlap still selected only one target
(6.286 versus 0.54°F). The paired outdoor forecast errors changed sign
(+1.64, −4.02, −4.10 and −3.40°F), so weather error alone does not explain
the shared low indoor miss. Twelve newer captured 24-hour targets remained
immature. This is stronger adverse diagnostic evidence, not four independent
days or an identified calibration offset.

The refreshed one-hour set has 15 disjoint pairs, model/persistence MAE
1.2254/0.444°F. Only three use the current `507748cee9ca` artifact;
their MAE is 1.063/0.300°F. The six-hour set has 13 overlapping pairs;
four disjoint pairs have MAE 4.0977/2.295°F. Only one six-hour pair uses
the current artifact (3.966/1.62°F). All scored publications remain
low-confidence. The latest natural shadow service exited zero and its
15:57 MDT output still reports `shadow` with no candidate schedule. Continue
capture and independent current-revision scoring; do not fit from these
overlapping warm-season targets or change advisory/control authority.

## September 27 read-only operational checkpoint

The natural September 27 06:50 trainer exited successfully at 08:01, but this
is still internal shadow-artifact promotion, not approval for advice or
actuation. The capture-strict scorer now has 48 independent one-hour pairs
(model/persistence MAE 1.1113/0.5100°F), 15 non-overlapping six-hour pairs
(3.4504/3.1680°F), and four non-overlapping 24-hour pairs
(4.1582/1.4850°F). All scored publications have low confidence. The 37
overlapping 24-hour pairs are not 37 independent days; their MAE is
3.8614/1.5519°F. Approved numerical operational graduation thresholds and
confirmed action-outcome scoring are still absent. Shadow-only remains the
correct state.

The operator reported that vents stayed closed on the nights of September
23–25 and that no venting was planned for September 26. Treat these reports as
diagnostic context, not signed action-history or training labels. A read-only
replay of the exact September 26 16:08:50Z forcing archive and the matching
`01b0eda24b6e` accepted artifact reproduced the entire published hourly
trajectory exactly. Its published baseline assumed venting from September 26
18:45 to September 27 10:00 MDT. With only the vent schedule set to closed,
keeping the same as-issued weather, initial state, shade schedule and dynamics,
the September 27 10:00 hallway prediction rose from 64.535°F to 65.344°F.
The qualified outcome was 69.44°F: the closed-vent counterfactual still missed
low by 4.096°F, versus 4.905°F for the issued forecast. This one replay
shows the vent assumption contributed about 0.809°F but does not explain most
of that miss. It is not a causal training label, a broader vent calibration,
or evidence to relax the shadow gate. Investigate model dynamics and forcing
with chronological held-out data and confirmed actions before changing the
baseline or promotion policy.

## September 27 lead-time diagnostic

A fresh read-only `--require-capture` score paired exact private forcing
archives with qualified later indoor outcomes. The greedy non-overlapping
windows score as follows; these are mixed artifact revisions and warm-season
observations, not a randomized or untouched validation set.

| Horizon | Independent pairs | Model MAE | Same-origin persistence MAE | Model signed bias |
| --- | ---: | ---: | ---: | ---: |
| 1 hour | 50 | 1.1875°F | 0.5472°F | -0.9893°F |
| 6 hours | 15 | 3.4504°F | 3.1680°F | -2.7496°F |
| 12 hours | 8 | 3.0833°F | 4.5900°F | -2.7445°F |
| 24 hours | 4 | 4.1582°F | 1.4850°F | -4.1582°F |

The 12-hour model advantage does not override the failed 1- and 24-hour
comparison or low-confidence status. All four independent 24-hour model
errors were low (-6.286, -6.877, -3.021 and -0.449°F), spanning four artifact
revisions. Paired outdoor forecast errors changed sign (+1.64, -0.72, -8.58
and +1.06°F), so a single outdoor-forecast offset cannot explain the common
indoor sign. The eight independent 12-hour targets alternate day/night and
also have mixed outdoor error signs. Investigate accumulated physical-state
drift and action forcing by lead time with confirmed action states and a
chronological holdout; do not fit a global constant correction to these four
overlapping-season days. No model, interval, schedule, alert or control was
changed by this audit.

The September 27 Earthship UI now displays the publisher's validated baseline
vent window as **"Baseline vent assumption · not observed"** (or "No venting
assumed" when its schedule is empty). The live 18:16 shadow output displayed
6:45 PM–7:00 AM as an assumption. This makes the modeled action forcing visible
without turning the operator's closed-vent report into training evidence or
changing the model, schedule, advisory, or shadow-exit gate. Both tablet/laptop
Earthship browser regressions and the live Lenovo-width text-containment check
passed.

## September 27 evening capture-strict rescore

At 18:55 MDT, the existing read-only scorer rechecked exact archived forcing
and qualified indoor outcomes for the four supported lead times. Greedy
non-overlapping pairs remained mixed-revision, low-confidence evidence:

| Horizon | Independent pairs | Model MAE | Same-origin persistence MAE |
| --- | ---: | ---: | ---: |
| 1 hour | 51 | 1.1980°F | 0.5365°F |
| 6 hours | 16 | 3.7555°F | 3.1612°F |
| 12 hours | 8 | 3.0833°F | 4.5900°F |
| 24 hours | 4 | 4.1582°F | 1.4850°F |

The newly matured, *overlapping* September 26 18:10-to-September 27 18:00
24-hour pair missed **high** by 5.678°F, while same-origin persistence missed
high by 1.26°F. It was not selected as a fifth independent 24-hour pair.
That sign reversal makes a global positive offset especially inappropriate;
the independent 24-hour deficit, unverified action states and low confidence
still block shadow exit. No model, artifact, alert, or control was changed by
this rescore.

## September 28 published-model identity check

The capture-strict shadow scorer now separates accepted model instances by
the validated full-artifact SHA-256 in v2 forcing captures. Older captures
without an embedded artifact retain a separate SHA-256 grouping of their
**published model metadata** (`codeRevision`, `createdAt`, `trainedThrough`),
but cannot satisfy an exact-artifact target gate. Previously, revision-only
groups could combine daily retrains that used unchanged code; mixed-instance
skill must not be treated as current-model readiness. An explicit full
artifact digest can be supplied to the read-only scorer, which then uses only
that artifact's independent windows for target skill and confidence blockers.
Overall/revision/metadata groups remain descriptive. No score, however
favorable, bypasses the separate action-outcome and approved-threshold gates.

Around 20:00 MDT, 25 naturally captured one-hour publications separated into
three metadata instances, two of which have full-artifact v2 capture digests.
The live instance, created September 28 12:50:10Z
under code revision `53d96e5e9637`, had six disjoint one-hour pairs:
model MAE 0.352°F versus same-origin persistence 0.000°F. Its validated
captured-artifact SHA-256 is
`f7c85390f842d91685f88592c7b1e50c84805fd662d5fe7562261aa3eb881e17`.
The paired independent comparison has zero model wins, zero ties and six
persistence wins; the mean absolute-error disadvantage is 0.352°F.
Targeted read-only scoring reports inferior skill, low-confidence outputs,
no confirmed-action outcome score and no approved graduation thresholds.
The short window is diagnostic, not a release decision; current status remains
shadow. The next current-instance 24-hour targets have not matured yet.
