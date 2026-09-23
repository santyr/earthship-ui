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
The legacy live v4 shadow command timestamped `generatedAt` at command start,
before its direct Open-Meteo fetch completed. Persistence confirms delivery
before each scored target, but this audit cannot claim the exact weather forcing
was known at the printed legacy `generatedAt` to the second. On September 23,
the compatible installed v4 publisher received a narrow post-input timestamp
and private forcing-capture backport; its first verified archive is documented
in [the live activation receipt](2026-09-23-thermal-forcing-capture-live.md).
No archive was retroactively manufactured for historical publications.

The audit now accepts `--require-capture`, which verifies an exact private
archive and persisted-output digest before scoring a mature pair. At 09:57 MDT,
strict mode found 31 mature legacy publications without captures and 14 targets
not yet due, so it correctly emitted **zero capture-qualified scores**. The
non-strict observational score remained 31 pairs, model MAE 2.4565°F versus
same-origin persistence 2.0265°F. Capture-qualified scoring must wait for the
first archived 24-hour target to mature; missing archives remain explicit gaps.

The scorer now also accepts explicit 1, 6, 12 and 48-hour diagnostic horizons;
the default and graduation-relevant 24-hour selection are unchanged. At
11:21 MDT, `--since 2026-09-23T15:45:00Z --require-capture --horizon-hours 1`
read two persisted publications. The 15:48:53Z legacy publication correctly
counted as missing a forcing capture; the 15:50:54.866271Z captured publication
scored one qualified indoor target. Its 1-hour model absolute error was
**1.541°F** versus **0.540°F** for same-origin persistence. The published
interval contained the outcome but was 10.414°F wide. Both publications'
24-hour targets were not yet due. This first exact-forcing point is a useful
early diagnostic, not a trend, independent-day sample or shadow-exit pass.
The strict scorer now also pairs the exact captured hourly outdoor forcing with
a separately qualified outdoor receipt at the same target. For this one point,
the captured outdoor forecast was 70.6°F versus 65.48°F observed, an error of
+5.12°F; the indoor shadow prediction erred −1.541°F. Opposite signs on one
sample do not establish causation or rule out weather influence. Missing
outdoor receipts or a missing exact forcing target remain explicit diagnostic
gaps and do not turn a valid indoor score into a fabricated weather score.

This live score does not support shadow exit: overall near24-hour
MAE trails persistence by0.4300°F, and interval coverage is below the nominal
90% on this small overlapping sample. The next modeling work should diagnose
why current revisions overpredict cooling or miss stable-temperature regimes,
then score any candidate against chronological, capture-safe, revision-specific
holdouts. Do not change the live output contract or graduate advice from this
exploratory audit.

An exploratory forcing-source check paired the same31 target hours with the
latest complete Open-Meteo archive issuance captured no later than each shadow
publication. Against qualified outdoor-temperature receipts, that archived
forecast had MAE2.456°F and signed bias−1.166°F. The signed outdoor-weather
and indoor-shadow errors had correlation−0.174. The archive may not be the
exact weather sequence consumed by the historical publisher, so this does not
attribute the indoor error to weather or exonerate it; capturing the actual
forcing digest/provenance in a future versioned publication is the next
diagnostic prerequisite before changing model physics or weather correction.
