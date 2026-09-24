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
an untouched seasonal validation set. The next natural shadow publisher is
scheduled for 11:55 MDT; this checkpoint did not trigger it or write outcomes.
