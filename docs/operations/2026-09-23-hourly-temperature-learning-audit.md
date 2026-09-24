# Natural qualified hourly temperature learning audit

Read-only live audit on September 23, 2026, after the qualified hourly cutover.
The installed `forecast-intel.service` retains its 06:40 daily schedule with
`HOURLY_TEMP_QUALIFIED_ENABLE=1` and the approved cutover
`2026-09-20T00:30:09Z`. Hourly refers to the forecast target resolution, not
an hourly service timer. The installed worker's hourly seed, scorer, display
correction and payload builder match repository source by parsed AST; both
installed Kalman constants match too.

The private pre-cutover model snapshot held 535 aggregate local-hour bucket
updates. Live state now holds 590, and contains 55 distinct qualified evidence
receipts: 24 September 21 targets, 24 September 22 targets and seven early
September 23 targets (Denver dates). Each of the 24 bucket count increases
equals its own qualified-receipt count. Every receipt passed aware-time,
cutover, capture-before-target, receipt/persistence/expiry chronology, finite
value and digest-shape checks. Replaying the published Kalman update from the
pre-cutover snapshot reproduces every live bucket's bias, variance and count
exactly. This verifies natural learning without resetting or relabeling the
legacy model history. No synthetic receipt or model write was made.

For an observational *pre-update* comparison, each saved target was scored
using the bias available before that target's learning step. Every pre-cutover
bucket already had at least 22 updates, so the published hourly correction's
count-based weight was 1. The rule correction was the rounded, bounded
negative prior bias. The payload builder also requires finite daily high and
low values; those per-origin inputs are not stored in these receipts, so this
is an evaluation of the correction rule, not proof that every historical UI
payload displayed it. This comparison uses only the 55 saved qualified
targets, not an untouched holdout or a seasonal validation set.

| Qualified measured-temperature slice | Targets | Raw MAE °F | Rule-corrected MAE °F | Raw bias °F | Rule-corrected bias °F |
| --- | ---: | ---: | ---: | ---: | ---: |
| All | 55 | 3.1825 | 3.0607 | −0.3207 | −1.7953 |
| Below 50°F | 5 | 5.0960 | 1.0840 | +5.0960 | +0.9160 |
| Below 60°F | 23 | 3.4252 | 2.1000 | +2.9922 | −0.7817 |
| At least 60°F | 32 | 3.0081 | 3.7513 | −2.7019 | −2.5237 |

The correction helped this small cool subset but worsened absolute error for
the warmer subset; its overall improvement is slight. The five sub-50°F
targets still overpredicted on average after correction. These targets span
only a short late-September interval and are not independent weather regimes.
This does not justify a colder-regime gain, a seasonal claim, discarding the
legacy model, or changing published temperatures. Continue qualified receipt
collection and evaluate an origin-frozen candidate on later, independent
cool/warm windows before changing correction weights or thresholds.
