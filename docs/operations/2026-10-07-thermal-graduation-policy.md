# Versioned numerical graduation policy

`earthship-thermal-graduation-policy/v1` fixes the candidate artifact, publication
runtime, initial sensor epochs, supported thermal regimes, development interval,
untouched holdout interval and prospective interval before release evaluation.
It accepts no active override. Original training dates remain visible.

The derivation retains the original development baseline errors. Validation
recomputes the complete policy and its digest; edited error caps, support floors,
allowable baseline loss, candidate identity or declaration timing refuse. Raw
source qualification and immutable registration are separate mandatory steps.
No genuine production policy has yet been registered from the legacy incomplete
origin captures.

## Numerical rules

For each declared horizon and regime, the policy derives:

- MAE and RMSE caps from the better development baseline for each metric;
- a signed-bias cap from baseline bias and its development uncertainty;
- interval-width cap from twice the smaller baseline 90th absolute-error quantile;
- independent support from the larger of twice the active parameter count and
  the sample size implied by 95 percent precision of a 90 percent coverage rate
  to ten percentage points. The current rule yields at least 35 independent days.

The deterministic sampling rule chooses UTC non-overlapping windows, then the
first issue per Denver local day. It is applied to development threshold derivation
and evaluation; additional same-day rows cannot inflate statistical sample size.
Raw pair, non-overlapping window and independent-day counts remain distinct.

The statistical assessor requires an upper one-sided confidence limit below
zero for paired absolute-error differences against both persistence and recent
cycle. It permits no positive loss tolerance. The confidence calculation follows
[the Student mean confidence interval](https://www.itl.nist.gov/div898/handbook/eda/section3/eda352.htm).
The family budget covers both baselines, both evaluation sets, every horizon and
the overall plus declared-regime comparisons.

Prediction interval coverage uses the [Wilson interval for a proportion](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm)
and checks the declared 90 percent nominal coverage; width is assessed separately
so very broad intervals cannot gain eligibility merely from high coverage.

## Lifecycle and authority

The final holdout stays immutable. Freshness is assessed from new qualified
prospective outcomes within the preceding 24 hours, without rewriting artifact
creation/training dates or moving the holdout. Both holdout and prospective
scores must pass overall and by declared regime. Overlap between the evaluation
sets is explicitly counted, never presented as additional independent evidence.

Statistical success alone produces **no release authorization**. Original source
qualification, immutable policy registration, actual conditioning/block-refit
stability, physical constraints, runtime/epoch compatibility, current inputs,
publication and rollback gates must also pass. Action evidence is not evaluated
by this statistical component and remains a separate advisory-stage requirement.
There is no automatic actuation.

Thirty-two focused policy/statistics tests passed under the local CPU/memory
limits. They include baseline losses/ties, bad calibration, broad intervals,
mixed revisions, epoch changes, overlapping/dense rows, stale prospective scores,
incomplete holdout and policy tampering. Full suites run remotely in CI.
