# Model evaluation contract v2

Declared before the consolidated reassessment or any new selection. This contract is implemented as `weather_learning.performance.EVALUATION_CONTRACT`; its canonical identity accompanies each new score/work key. Old evaluation reports and original numerical producers retain their original versions. Changing a diagnostic does not grant release or actuator authority.

## Targets, population and clocks

Temperature is an instantaneous station-head temperature in °C, with source grid/product, original issue/snapshot, target time, actual local receipt, sensor epoch and measurement-policy identity. The prospective monitor retains its predeclared first original issue per local issue date and sparse native-hour offsets; it scores only targets actually present, through the maximum actually issued336h. This sampled operational series is distinct from every UI publication and retrospective historical experiments. No current coefficients recreate absent old predictions.

Pending work survives report windows. Seven days after target maturity is the explicit observation-arrival allowance; work is attempted in bounded batches with durable completion before progress, idempotent evaluation keys, and named not-yet-observable/quality-withheld/missing-original/unrecoverable states. The report shows seven days of target outcomes, not seven days of issue creation. Original predictions are never deleted to fit queue capacity.

Wind is the hourly mean of the local station, compared with original issued trapezoidal native point-wind forecasts and the originally used gain; numeric station health remains unqualified. Irradiance is ending-hour mean local lux-derived exposure proxy, separate from physical GHI/direct components. Rain keeps native hourly/UTC-aligned24h and Denver-calendar accumulation targets distinct; dry/wet and uncertain-boundary evidence are separate. PV labels are uncensored controller-input proxies; available array DC, captured controller energy, AC load and nominal SoC scenarios remain different targets. Thermal air and mass have separate losses and recorded action regimes.

## Matching, weights and support

Each head-to-head comparison uses the identical original issue, source grid/product, target time/interval, observation identity and policy/epoch. Raw-all diagnostics, candidate-available scores plus their matched raw baseline, and original-correction-or-raw-fallback policy scores are separate at aggregate/horizon/month/cohort levels. Missing/invalid observations are withheld, never zero. Empty metrics are null. Counts identify issued/matured/qualified/corrected/fallback/withheld populations under the declared sampling policy.

Prospective temperature metrics give each Denver target date equal mass, each distinct measured target equal mass within its date, and each distinct original forecast equal mass within its measured target. MAE/RMSE/signed bias and weighted95th absolute error use those same weights. A count of dates is not an assertion of independent weather events. Record forecast pairs, unique measured targets, dates and temporal blocks separately. Repeated identical evaluation identities collapse exactly; conflicting results or observation identities reject.

The consolidated fitting review will use unique-measured-target mass spread across distinct original forecast pairs, and scale regularization by that mass rather than acquisition row count. A24-target prior must remain24target units when identical targets acquire a second forecast. Denver dates govern support; deliberately UTC-defined accumulation targets retain that definition. New fitting schemas are required; existing fitted bytes retain original interpretation.

## Cohorts and qualification

Policy cohorts preserve variable/period/target definition, provider grid/product, timezone, observation policy/epoch, numerical producer, correction method, training-policy and selection-policy identities. Artifact diagnostics add the exact fitted-model identity. A pooled method/policy metric cannot be attributed to its newest artifact. Legacy original issues lacking retained method/policy provenance are explicitly unidentified and cannot establish qualification of today's procedure. Exact original predictions may still be diagnosed.

The original public shadow payload v2 remains compatible. New weather-performance reports are v2 and older reports remain original artifacts. Retrospective comparisons, artifact diagnostics and versioned operational policy performance are labeled separately. Generic `calibration_qualified`, `release_authorized` and `automatic_actuation` remain false. Point clipping bounds are not confidence intervals; no new probabilities or model families are introduced.

## Frozen reassessment procedure

Use original as-issued predictions first. Repaired-kernel/weight refits are separate artifacts compared with raw/physics and the retained incumbent on identical later targets. At every retrospective fitting origin admit only outcomes available by fitting; retain original preprocessing, parameters and source clocks. Earlier inspected holdouts are development data. Use chronological inner selection and later outer/original-as-issued assessment where available; otherwise report the precise evidence gap. No additional data availability is fabricated.

Primary point loss is matched MAE, with RMSE, signed bias, tail errors and coverage required. Selection requires improvement against both raw and incumbent on the same declared cohort without material predeclared regime regressions; inconclusive/losing candidates retain the incumbent. Practical thresholds and regression tolerances must be recorded for the actual family before selecting, never tuned on the final outcomes. Preserve daily-demand/nominal-storage choices unless matched evidence changes them.

For uncertainty, keep all predictions sharing an observation together; use temporal/target blocks reflecting forecast horizons and measured residual dependence. Report block-length sensitivity when few independent blocks exist. No universal calendar waiting rule or significance claim from tiny support. Qualification records distinguish source-valid, fitted, provisional-serving-admitted, retrospective comparison, prospective skill, distribution calibration and actuator authorization.

Implementation status and family-specific executed evidence remain in [requirements](requirements.md), [verification](verification.md) and [qualification](qualification.md); this specification alone is not completion evidence.

## Executed engineering criteria and correction diagnostics

Before reassessment, the retained policy remains the default. An existing-family replacement would need at least1% matched-target MAE improvement against both raw and incumbent and no greater than5% lead/regime MAE regression where there are at least24unique targets and2Denver dates. Smaller strata are diagnostic. These are provisional engineering criteria, not physical/release qualification. No candidate was selected or deployed. All previously inspected holdouts remain development data.

The separate correction evaluator is version2: equal target dates, measured intervals and original forecasts, with matched correction/raw, raw-all and correction-or-raw fallback metrics at horizon/month/regime and artifact/procedure levels. Complete future-hour outcomes must be available between interval end and end+7days; later processing of timely retained evidence is allowed. Its private durable scores and originals remain immutable. Public detail is capped at64KiB with explicit cohort omissions; the complete records remain private. Missing/corrupt dependencies defer their own work without blocking independent targets. All label readers share the existing90-second deadline and64-label job budget, including legacy solar/rain reads.

Original wind/native historical training-window policies are not reconstructed from current configuration. Known method/source/selection identities are retained prospectively; absent training/grid/selection provenance remains null and the separate procedure series is labeled partial/unidentified. Such support does not qualify the current procedure or newest artifact. Native proxy replay uses the original external producer pin and actual delivery, never current-model backcasts.
