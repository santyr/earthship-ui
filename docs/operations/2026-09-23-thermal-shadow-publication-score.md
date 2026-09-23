# Published thermal shadow forecast score — September 23

Read-only live audit using `python3 scripts/audit-thermal-shadow-publications.py`.
No model artifact, journal, OpenHAB state, alert, advice or control was changed.
Four selector/scorer tests cover future outcomes, stale current inputs,
postdated issues and missing qualified outcomes.

The scorer read43 persisted `Thermal_Model_JSON` rows from September20 onward.
It required issue and artifact times no later than persistence, shadow status,
indoor-air and mass ages at most five minutes, and the published hourly point
within30 minutes of issue+24 hours. It paired that point and the same
publication's current hallway temperature with a receipt-qualified indoor
temperature at the target. Twelve targets were not yet due;31 pairs scored.
All31 publications reported low confidence. The target is near24 hours, not
an exact24-hour interpolation.

| Issued UTC day | Pairs | Published model MAE °F | Same-origin persistence MAE °F | Published interval coverage |
| --- | ---: | ---: | ---: | ---: |
| September20 | 12 | 3.2654 | 4.2450 | 75.0% |
| September21 | 12 | 2.2317 | 0.4500 | 91.7% |
| September22 | 7 | 1.4550 | 0.9257 | 100.0% |
| All matured | 31 | **2.4565** | **2.0265** | **87.1%** |

The interval mean width was10.4138°F. The published model's signed bias was
−1.1822°F versus−1.7361°F for the paired persistence baseline. Three code
revisions are mixed: `fa218bd40905` (7 pairs, model2.3960 vs persistence
4.8343°F), `261d0da8b615` (12 pairs,2.6094 vs1.6050°F), and
`c87551f92f02` (12 pairs,2.3388 vs0.8100°F). The newest revision's matured
sample is therefore also worse than persistence; do not average it with prior
revisions to claim a current-model pass.

Publications are roughly two hours apart, so targets and errors overlap. This
is a few warm-season days, not31 independent trials, a winter holdout, a causal
action-benefit study, or an advisory graduation assessment. The published
current value is the model's own baseline and is freshness-checked here; it is
not substituted with a later measurement. The separate
[origin census](2026-09-23-thermal-origin-census.md) uses a different hourly
grid, so its persistence MAE is not directly paired with these publications.

This live score does not support shadow exit: overall near24-hour
MAE trails persistence by0.4300°F, and interval coverage is below the nominal
90% on this small overlapping sample. The next modeling work should diagnose
why current revisions overpredict cooling or miss stable-temperature regimes,
then score any candidate against chronological, capture-safe, revision-specific
holdouts. Do not change the live output contract or graduate advice from this
exploratory audit.
