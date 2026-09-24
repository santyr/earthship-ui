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
