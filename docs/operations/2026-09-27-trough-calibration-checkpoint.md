# Trough/PV calibration checkpoint — September 27

Latest extension: the [September 30 true-sunset diagnostic](#september-30-true-sunset-as-issued-component-comparison)
uses original Astro sunset rows and atomic SoC coverage. It confirms that the
morning evening-charge estimate, not just the overnight-drop proxy, dominates
the recent trough underprediction. Earlier checkpoint observations below
remain dated evidence, not current model-promotion claims.

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

This section preserves the pre-activation qualification sequence. The
[September 28 activation receipt](2026-09-28-pv-day-evidence-activation.md)
records the subsequent live observational stream and canonical file ownership.

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

The first September 28 isolated OpenHAB 5.2.1 attempts were inconclusive:
Graal reported JavaScript uninitialized or the scripting bundle stayed
`Waiting`. The networkless, read-only qualifier now stages the Graal language
bundles first and waits for the JavaScript language bundle to become Active
before installing the scripting add-on. That ordering matters because the
add-on creates its shared Graal Engine when its factory activates. Two fresh
PV container boots now compile the rule, register its triggers, return from
`runnow` to IDLE and publish a `source_unavailable` Item receipt. The existing
inverter rule passed as a control under the revised bootstrap. Each owned
container and its tmpfs state was removed. This closes only the isolated
rule-body bootstrap gate; no physical Modbus event, JDBC persistence,
production rollback or natural poll was exercised. Keep production PV resources off
until those remaining gates pass.
The PV JDBC strategy candidate was then rendered byte-for-byte from the
current file-owned live DTO with the PV evidence Item's everyChange exclusion,
its restore-only selector and a complete automatic-persistence exclusion for
the transient observation Item. A networkless OpenHAB 5.2.1 fixture loaded
the exact candidate DTO and completed two file→managed→file roundtrips, each
with observed provider absence between owners. Its owned container and tmpfs
were removed. This qualifies parser/provider ownership and rollback in the
isolated fixture, **not** PostgreSQL write/readback, restore after a new JVM,
or production hot reload. The current live JDBC strategy is unchanged.
A second disconnected OpenHAB 5.2.1/PostgreSQL 16 rehearsal used that exact
candidate through five file/managed provider checkpoints and a new JVM. At
each checkpoint, ordinary PV evidence and transient-observation Item updates
produced no JDBC rows while a change-only positive control and forecast future
series persisted as expected; existing power and AC evidence exclusions
remained intact. A guarded
isolated-only Java probe explicitly persisted one PV row without changing the
Item state. After JVM restart, exactly that PV history row remained and the
evidence Item restored from it; the transient observation still had no JDBC
history, and power, AC, forecast and ordinary history controls also
passed. Four provider handoffs had measured collection gaps rather than
fabricated continuity. Both owned containers and their disposable PostgreSQL
data were removed. This completes isolated JDBC exclusion, explicit-write and
restart/rollback qualification, **not** live Modbus source provenance,
production hot reload, natural polling or a qualified full PV day.

A separate source-only pure reader in `openhab/scripts/pv_day_evidence.py`
now parses exact native-Wh receipts and calculates a completed local day's
counter maximum only with source-qualified coverage of at least 99.5%, a
fresh terminal poll, contiguous sequences within each epoch, explicit
restart barriers and no counter decrease outside a brief midnight reset.
It fails closed on duplicate/out-of-order rows, missing sequence numbers,
malformed evidence, incomplete days, long outages or excessive row volume.
Fifteen focused tests cover those boundaries, including 23- and 25-hour DST
days. At that source-only checkpoint, no JDBC table resolver, database read,
learning update or live producer called this reader; its threshold and
boundary assumptions still required natural-receipt validation.
A source-only `pv_day_history.py` adapter now resolves exactly
`MPPT60_PV_Day_Evidence_JSON` to one JDBC table inside a dedicated
repeatable-read, read-only transaction. It bounds original rows and value
size, refuses ambiguous identity or failed privileges, and feeds the pure
reader without sorting, deduplicating or filling gaps. All 27 adjacent
Python tests pass. A separate disposable PostgreSQL 16 test exercised the
real SQL with a restricted role: one complete synthetic day qualified,
revoked SELECT failed closed, and an oversized persisted value failed closed.
Its owned container and volume were removed. At that test checkpoint, no
production PV Item, table, grant, connection factory or forecast caller
existed. The [September 28 live observation receipt](2026-09-28-pv-day-evidence-activation.md)
records subsequent source-bound activation; it does not qualify a complete
day, create the restricted reader grant or change forecast calibration.

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

## September 30 true-sunset as-issued component comparison

The source-only `sunset_soc_profile.py` now measures a valid atomic SoC at the
original Astro sunset, not an assumed 99% or a fixed 20:00 sample. It requires
the source sunset to have been persisted before sunset, the complete night to
have elapsed at its explicit as-of clock, physical-bank boundaries and at
least 90% canonical **and** sunset-to-11:00 coverage. The sunset-shifted
minimum must equal the existing canonical 20:00-to-11:00 trough; otherwise
the comparison is withheld rather than silently changing the target.
Original sequence ordering, source expiry and barriers are retained. Future
rows, missing sunset coverage, duplicate timestamps, pre-bank data and a
changed minimum refuse qualification. Streaming inputs stop after 10,001
rows; spring/fall DST elapsed-duration tests pass.

Reproduce the actual household read-only comparison:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/experiment-sunset-soc-drop.py \
  --start-day 2026-09-25 --end-day 2026-09-30
```

The actual run at `2026-09-30T22:05:35.318307+00:00` qualified all five elapsed
target nights and their fifteen origin-available prior-night profiles with
zero unavailable cases. Its current as-issued state digest was
`6a0e013b2e479bb6113bda2ac17f3d9cb9e199340b54b46678e3d669c7a38d07`.
Each baseline issue was independently matched to exactly one original
persisted morning receipt by date, issue timestamp and published trough.
The three original sample ending dates and their old `99 - trough` values
were verified, not replaced by today's latest history. Only the drop inputs
changed; each issued dusk estimate and cloud penalty remained fixed.

| Origin | Issued trough | Sunset-drop-only counterfactual | Measured trough | Issued dusk estimate | Measured sunset SoC |
| --- | ---: | ---: | ---: | ---: | ---: |
| Sep 25 | 63% | 64% | 84% | 78.411% | 97% |
| Sep 26 | 73% | 76% | 84% | 93.410% | 99% |
| Sep 27 | 71% | 74% | 80% | 90.716% | 94% |
| Sep 28 | 46% | 48% | 70% | 64.842% | 85% |
| Sep 29 | 53% | 56% | 81% | 71.799% | 98% |

Actual sunset-to-trough drops were **13, 15, 14, 15 and 17** percentage points;
the target sunset-window coverages were 99.990–99.993%. Morning trough MAE
was 18.6 percentage points; the one-component counterfactual MAE was 16.2.
This is a limited diagnostic, not a fitted model, independent skill-validation
set or live-calibration approval. The 1–3-point improvements cannot resolve
the 9–28-point misses. Morning dusk estimates were below measured sunset SoC
by 3.284–26.201 points. They represent an estimated evening state, so this is
a timing-aware diagnostic comparison, not exact causal attribution to PV.
On Sep 25, 28 and 29 the predicted dusk SoC was even below the later measured
overnight minimum. The next priority is the PV/charge-demand-to-evening-SoC
chain, with qualified radiation, demand/curtailment and afternoon discharge
context; do not treat a proxy-drop correction alone as the fix. Keep the
accepted pre-dusk UI choice and preserved morning history/scoring intact.

The restricted `energy_power_reader` already has SELECT on the uniquely mapped
Sun sunset Item 73 and atomic SoC Item 613. It lacks raw-table SELECT for the
morning receipt, so the experiment uses the existing bounded authenticated
OpenHAB original-JDBC receipt reader, not an admin connection or a new grant.
The SQL snapshot is read-only/repeatable-read; source profiles are cached by
night and exact sunset to avoid repeated raw reads. The first attempt exposed
that missing raw privilege; a second exposed the JDBC DateTime value's typed
PostgreSQL representation. Explicit offset-aware datetime support was added
and tested, without guessing epoch units, attaching a timezone to naive data,
sorting or deduplicating receipts. The complete rerun passed.

All **188 affected forecast/SoC/profile/archive tests pass**. No private test
copy, disposable runtime, forecast state update, Item publication, model
coefficient, notification, database grant, unit or production code change was
made. These diagnostic source files need no runtime deployment. Chronological
PV/dusk/trough calibration and adequate seasonal support remain open.

## September 30 qualified charge-time and afternoon-decline targets

The same read-only diagnostic now separately measures the interval from each
original morning origin to its original Astro sunset. `charge_profile` requires
source-bound SoC at both endpoints, at least 99.5% atomic coverage, the current
physical bank and an already-known same-day sunset. It preserves invalid-source
barriers and refuses ambiguous ordering, future rows, oversized input and
incomplete windows. The streaming bound stops at 10,001 observations.

The first 100% timestamp means **first reported full charge**, not the exact
physical event. Already full at the morning origin is left-censored there,
without an invented new full-charge time. No 100% report before sunset is
right-censored at sunset, not silently dropped from the dataset or assigned a
made-up charge time. A first full report exactly at sunset is observed;
reports after sunset cannot change this target. Each result retains its
assessment clock and a digest binding the original rows, endpoints and bank.

The household rerun at `2026-09-30T23:36:59.159744Z` qualified all five completed
days, with zero unavailable cases and unchanged as-issued state digest
`6a0e013b2e479bb6113bda2ac17f3d9cb9e199340b54b46678e3d669c7a38d07`.

| Issue day | Morning SoC | First reported 100% (MDT) | Sunset SoC | Post-full decline | Atomic daytime coverage |
| --- | ---: | --- | ---: | ---: | ---: |
| Sep 25 | 79% | 13:58:10 | 97% | 3 pp | 99.9890% |
| Sep 26 | 85% | 10:23:07 | 99% | 1 pp | 99.9858% |
| Sep 27 | 86% | 10:37:53 | 94% | 6 pp | 99.9868% |
| Sep 28 | 81% | Not reported; censored at 18:49:57 | 85% | Unavailable | 99.9907% |
| Sep 29 | 72% | 12:34:35 | 98% | 2 pp | 99.9899% |

The exact charge-profile digests are, in that order:
`7dc9be5f23dbbbd9f417adc8d9d0a4a00b0f873fe0b4d8f86ed4b64177e2607a`,
`3cc2c293c39c4d9a7c2346d112a0e2a05e435649479a45e72056084008848699`,
`b06a3a5901fb8ff3fb4283a663dfc43ddfa290b73d475c8840ec9dda89238cdf`,
`5d09d10fdf34c63d4dac680ea098ff42f61d2148aff640b7e803cec7c2a72de5`,
`82f43adfa60d0e23ad122028a43a11f873e9dab3a9d8fe790c2d02743e743d3d`.

These targets substantiate the separate charge-to-full and afternoon-discharge
problem: a full-charge milestone cannot substitute for sunset SoC. They do not
establish a scheduling threshold or train a model from five late-September
days. The existing diagnostic command reproduces both targets; later outcome
rows are used only for assessment, never as earlier forecast inputs. Prior-night
reads remain narrowly bounded, and caches include the exact start/sunset to
avoid reusing a short nighttime read as a complete daytime observation window.

All **266 affected forecast, charge/trough, source-reader and archive tests
pass**. No live forecast, coefficient, control, Item, credential, database
privilege or service changed. This pure diagnostic extension is published in
the repo and requires no production-runtime install. Next tuning remains a
chronologically scored joint PV/charge/afternoon/overnight model with qualified
forcing and outcomes, not a proxy-drop-only patch or a claim of seasonal skill.
