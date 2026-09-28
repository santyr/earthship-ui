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

## September 28 read-only extension

After the September 26 target window completed, the existing restricted
atomic-SoC assessor measured an 84% minimum for the night ending September
27. The as-issued September 26 trough forecast was 73%, an 11-point low miss.
The natural September 27 producer log scored its September 26 PV prediction
of 7.30 kWh against 8.30 kWh from the daily Item. A separate read-only check
of the directly Modbus-linked
`MPPT60_Native_EnergyFromPV_Today_Wh` history found a September 26 maximum of
8,298 Wh, exactly matching the derived Item's 8.298 kWh maximum. Across
September 20–26, the native and derived daily maxima matched at the Wh level
and neither queried series contained duplicate timestamps. The native Item's
link is `modbus:data:9eb978a141:mppt60Energy:energyFromPVTodayWh:number`;
the derived kWh Item has no direct channel link. These are corroborating
counter histories, not source-bound freshness receipts: each history had a
roughly five-hour maximum gap overnight, which cannot distinguish unchanged
counter state from missed source polls.

Even if the extra 0.998 kWh all became stored charge at 95% efficiency, it
would add only about 4.6 SoC points to a 20.48 kWh bank, leaving at least
about 6.4 of the 11 missed points outside that simple PV-only explanation.
This is a diagnostic upper-bound calculation, not a causal allocation. The
natural producer classified the day as demand-limited and updated `d_direct`,
not the already capped `k_res`. The September 26 night is not added to the
frozen-outcome table above until the ordinary selection/assessment path stores
it. Next evidence work is a source-bound PV poll receipt with restart-safe
coverage, followed by chronological PV/dusk/trough calibration; no live
coefficient, forecast, alert threshold or DM behavior changed here.

## Source-only PV acquisition candidate

The live MPPT energy data Thing, its 30-second poller and TCP bridge were all
ONLINE at the September 28 read-only check. `openhab/transform/mppt60_pv_day_observation.js`
and the disabled `openhab/mppt60-pv-day-evidence-resources.json` candidate
prepare a separate, read-side String observation on that exact native Wh
channel. The source-only rule requires the original source-attributed
`ItemStateEvent`, all three Things ONLINE and a post-start/post-recovery
receipt; it expires a receipt after three poll intervals, rejects invalid or
replayed Wh values, and proposes explicit immutable JDBC snapshots with
sequence/epoch barriers. Candidate Item and JDBC files live under
`openhab/candidates/`; the canonical live `jdbc.persist` and all installed
Items, links, Things, rules and forecast code remain unchanged. Focused PV
and adjacent inverter tests pass. This is **not** an active PV evidence stream
or a qualified daily total. Before deployment, it needs isolated OpenHAB
runtime and persistence/rollback qualification, natural unchanged-value poll
verification, a strict historical day reader, and a reviewed activation.

The September 28 isolated OpenHAB 5.2.1 attempt remains **inconclusive**.
The qualifier was extended to stage the PV candidate in a networkless,
read-only container with a private tmpfs and no host bindings. Two initial
PV runs registered the rule but Graal reported that JavaScript was not
initialized before its body ran. The previously qualified inverter rule
passed as a control in the same harness. A follow-up run deferred loading the
PV transform-linked Item until after scripting-bundle activation, but that
isolated boot left the bundle `Waiting` before the observation Item was
installed. These are runtime-bootstrap
failures, not evidence that the PV rule body executes correctly or incorrectly.
All owned containers and their tmpfs state were removed. The qualifier now
distinguishes the two candidates and captures bundle/body diagnostics; do
not activate the PV resources until a deterministic isolated run, persistence
exclusion/rollback and natural source-event checks pass.

A separate source-only pure reader in `openhab/scripts/pv_day_evidence.py`
now parses exact native-Wh receipts and calculates a completed local day's
counter maximum only with source-qualified coverage of at least 99.5%, a
fresh terminal poll, contiguous sequences within each epoch, explicit
restart barriers and no counter decrease outside a brief midnight reset.
It fails closed on duplicate/out-of-order rows, missing sequence numbers,
malformed evidence, incomplete days, long outages or excessive row volume.
Fifteen focused tests cover those boundaries, including 23- and 25-hour DST
days. No JDBC table resolver, database read, learning update or live producer
calls this reader yet; its threshold and boundary assumptions still require
validation against natural receipts after a reviewed activation.

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

## September 27 qualified overnight-drop diagnostic

The installed forecast's `overnight_drop_samples_pct` are currently calculated
as `99 - qualified trough`, a *proxy* rather than a measured dusk-to-trough
decline. A restricted, transaction-read-only query used the same atomic SoC
evidence, physical-bank epoch, completed-night window and coverage assessor as
the forecast's qualified trough reader. It additionally required a valid SoC
interval at exactly 20:00 local, the trough-window start. All six September
21–26 prediction-day nights qualified at 99.85–99.99% coverage:

| Prediction day | 20:00 / trough SoC | Observed 20:00-to-trough drop | Current 99-to-trough proxy |
| --- | ---: | ---: | ---: |
| Sep 21 | 96 / 84% | 12 pp | 15 pp |
| Sep 22 | 96 / 83% | 13 pp | 16 pp |
| Sep 23 | 97 / 83% | 14 pp | 16 pp |
| Sep 24 | 92 / 77% | 15 pp | 22 pp |
| Sep 25 | 96 / 84% | 12 pp | 15 pp |
| Sep 26 | 97 / 84% | 13 pp | 15 pp |

For the September 25 and 26 as-issued origins, substituting the prior three
qualified 20:00 drops while leaving their issued dusk estimate and cloud
penalty unchanged would raise the rounded trough forecasts from 63 to 65%
and from 73 to 77%, respectively. The corresponding measured troughs are
84% on both nights. The September 27 issued 71% would become 75%, but its
outcome is not complete. This is a component counterfactual, **not** an
accepted forecast replay or a policy change: 20:00 is not necessarily solar
dusk, earlier evidence may include later-arriving rows, and the PV/dusk
residual remains large. No live coefficient, numerical forecast, DM policy or
learned state changed.

The local OpenHAB REST persistence response repeated one identical timestamp
on each of the Sep 24 and 25 nights. The strict evidence sequence correctly
refused those REST series; no sorting or deduplication was used to make them
qualify. The figures above instead come from the existing restricted JDBC
reader, which returned original ordered evidence. A source-only pure helper
`qualified_night_start_drop` now refuses a missing 20:00 sample even when
the rest of a night passes 90% coverage and bounds a streaming input after
10,001 rows. Eight focused qualified-SoC tests and all 79 adjacent
forecast/SoC tests pass. Before changing the forecast, replay
this candidate with frozen origins, strict as-of receipts and a later held-out
set; evaluate PV, dusk and trough together.

## September 27 origin-as-of replay

The three available qualified-sample origins in the producer's as-issued
private state were replayed against the restricted JDBC atomic-SoC source in a
transaction-read-only session. Each input row was additionally constrained to
its origin's recorded `temperature_issued_at` (06:40 MDT). All nine prior-night
sample sets were already complete at issuance: 890–897 original rows per
night, **zero** rows excluded as later-arriving, 99.845–99.990% coverage, and
each remeasured trough matched the corresponding stored `99 - trough` sample.
No duplicate timestamp was normalized or removed. This validates as-of input
availability for this limited comparison; it does not establish that the
forecast's dusk estimate is accurate.

| Origin | Prior-night observed 20:00 drops (pp) | Issued / replay trough (%) | Direct completed target trough (%) |
| --- | --- | ---: | ---: |
| Sep 25 | 14, 13, 12 | 63 / 65 | 84 |
| Sep 26 | 15, 14, 13 | 73 / 77 | 84 |
| Sep 27 | 12, 15, 14 | 71 / 75 | Pending |

The replay holds each origin's issued dusk estimate and cloud penalty fixed;
only the trailing-drop input changes. It reduces the signed low miss from
21 to 19 points on Sep 25 and from 11 to 7 on Sep 26. The target nights'
measured 20:00 starts were 96% and 97%, respectively, versus the issued
*estimated dusk* values 78.411% and 93.41%. These are different clock points,
so their differences cannot be assigned entirely to a dusk-model error, but
they locate the larger unresolved Sep 25 miss upstream of the corrected drop.
Two completed origins are insufficient to accept a live calibration. Retain
the current numerical forecast while accumulating a chronological holdout and
separately validating the PV/dusk chain and the 20:00-versus-sunset offset.
The source-only night-profile helper now also rejects any supplied persistence
receipt later than its explicit as-of clock, even if that receipt falls beyond
the target night and the assessor would otherwise ignore it. This prevents a
future replay caller from silently admitting post-origin evidence; eight
focused and 79 adjacent forecast/SoC tests pass. No live forecast path calls
this helper yet.
