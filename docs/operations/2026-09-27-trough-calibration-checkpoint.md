# Trough/PV calibration checkpoint — September 27

This is a read-only diagnostic. The completed-night outcomes came from frozen
`advisory_trough_selection` rows joined to the latest stored assessment under
the configured assessor role. The PV comparison uses the morning producer's
as-issued private state and the next natural run's `MPPT60_EnergyFromPV_Today`
maximum; that Item maximum is not an independent qualified-PV receipt.

| Prediction day | Issued PV / Item maximum (kWh) | Issued / measured trough (%) | Signed trough miss (pp) |
| --- | ---: | ---: | ---: |
| Sep 20 | 8.16 / 7.389 | 84 / 85 | -1 |
| Sep 21 | 7.35 / 7.237 | 77 / 84 | -7 |
| Sep 22 | 7.10 / 7.285 | 76 / 83 | -7 |
| Sep 23 | 3.42 / 6.557 | 59 / 83 | -24 |
| Sep 24 | 2.82 / 4.67 | 58 / 77 | -19 |
| Sep 25 | 5.36 / 8.28 | 63 / 84 | -21 |

The Sep 24 and 25 PV maxima are rounded values from the natural Sep 25/26
forecast-intelligence journals. The Sep 20–23 values were recorded in the
prior [origin-components audit](2026-09-24-trough-origin-components.md).
Sep 26/27 trough target windows are not yet stored as completed outcomes;
do not fill them from a partial window.

The last three PV under-forecasts were approximately 3.137, 1.85 and 2.92
kWh. At the model's 20.48 kWh bank and 0.95 efficiency, these are 14.6, 8.6
and 13.5 SoC points **if** every extra kWh translated linearly into stored
charge. The trough misses were 24, 19 and 21 points; even that optimistic
counterfactual leaves roughly 9.4, 10.4 and 7.5 points unexplained. This is
not a causal decomposition: demand, charging limits, curtailment, SoC
measurement and overnight-drop assumptions can interact.

The live producer's `k_res` is at its configured 1.3 upper bound. Its Sep 24
and 25 natural logs still classified the PV days as resource-limited and
recorded large negative PV errors, yet `k_res` stayed at 1.3. The current
calibration cannot learn beyond that ceiling. However, dividing the six
observed Item maxima by each as-issued radiation sum yields approximately
1.18, 1.26 and 1.30 for Sep 20–22, then 2.45, 2.15 and 2.01 for Sep 23–25.
These are diagnostic ratios, not fitted coefficients or independently
qualified irradiance. A blanket increase of the global gain could damage the
earlier near-accurate days; check forecast cloud/radiation bias and charge
limits by regime before changing its bound. The Sep 27 origin predicts
6.42 kWh PV and 71% trough, with an 86% qualified SoC reference, 90.716%
estimated dusk and 19.667-point estimated overnight drop. Those values are
as-issued diagnostics, not an outcome; no live coefficient, DM threshold,
learned state or alert was changed in this audit.

Next, evaluate a proposed PV-bound or richer site-radiation calibration only
on immutable origins with later qualified PV/SoC outcomes, preserving a
chronological holdout. Score the resulting dusk/trough chain as well as PV,
and separately test the 7–10-point residual before any live numerical change.
Do not use future actual PV to correct a past issued forecast or infer that
removing the gain cap alone fixes the trough.
