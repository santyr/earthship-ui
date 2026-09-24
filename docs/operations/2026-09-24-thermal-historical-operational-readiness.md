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
predictions; action reconstruction and dynamics remain confounded. No
captured 24-hour target had matured. The natural 07:55 publication exited
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
