# Machine learning focus — October 6

The operator stopped migration work and redirected effort to machine learning.
Thermal forecast accuracy is the current priority while the requested track choice
is pending. Existing ventilation handling and the November 1 no-venting default
remain in force.

## Current training and prospective outcomes are separate

The natural training service completed at **07:16:13 MDT**, exit 0, after starting
at 06:50:56. Its accepted file hash is
`16b07d15ac2ec8faa6cddbf55e9eefb2082201e2c04e0a06f773fde8cdfb0ac0`.
Installed revision remains `e32fdb8b785014a43aaf6343eb70bb392a3836789ccb3d8bb0a4f749e5e34fe9`.
This new accepted artifact still uses the legacy three-regime solar feature.
Its historical daily air MAE is **2.17855°F**, versus recent-cycle **1.83416°F**
and persistence **1.689895°F**, on 119 paired comparisons. Daily interval coverage
is 0.81356 versus nominal 0.9. Confirmed-action training/evaluation/disjoint counters
are all zero. These historical numbers do not establish prospective skill for the
new accepted coefficients.

At fixed **13:35:09Z** (07:35 MDT), two independent original-source reads score
12 original publications of the **October5 `bad329e1...` artifact**. Every original
forcing capture is verified; qualified native outcome receipts and seven strictly
prior local-clock cycles supply the comparisons. The two reports match byte-for-byte.
The older published artifact is not replaced with today's accepted coefficients.

| Horizon | Paired outcomes | Model MAE°F | Recent-cycle MAE°F | Persistence MAE°F | Selected windows |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1h | 12 | 0.9102 | 0.4200 | 1.0200 | 12 |
| 6h | 9 | 2.1463 | 3.0200 | 6.2800 | 3 |
| 12h | 6 | 1.9267 | 3.7200 | 7.3500 | 1 |
| 24/48h | 0 | — | — | — | 0 |

The six-hour selected-window MAEs are 1.37/2.88/6.66°F; twelve-hour selected
MAEs are 1.157/5.4/9.36°F. All selected six/twelve-hour origins belong to **one
Mountain issue day, October5**. Their multiple windows do not establish independent
seasonal support. Short selected origins span October5/6, with the latter day still
partial. All scored intervals cover outcomes but remain about 10.414°F wide; all
publications retain low confidence. Daily/48-hour targets were immature at this clock.

## First daily outcome and today's natural delivery

At fixed **14:20:00Z**, two original-source reports match byte-for-byte. The
October5 publication issued at 14:05:58Z now has one mature 24h target at
October6 14:00Z. Absolute errors are **1.373°F model, 3.060°F recent-cycle and
2.520°F persistence**; all three underpredict. Its interval covers the target,
with width 10.413°F and low confidence. The outdoor forecast error is +5.320°F;
this does not identify the cause of the indoor error. This is one selected window
from one issue day, not evidence of general daily skill or action readiness.
The earlier 13:35 assessment remains a valid snapshot with no mature daily target.

Today's new accepted artifact was naturally published at **08:11:01 MDT**.
Its canonical captured artifact identity is
`366e01fe286804956d40bd4c233dd969f0cbb12d73f30bba1280f21e227665f7`,
separate from October5's `bad329e1...` cohort. Exact installed-runtime replay,
current Item equality, one matching original JDBC row, successful terminal
systemd invocation bound to its active timer, original accepted-file binding and
unexpired native temperature/radiation receipts all pass. The capture decision
is 14:10:59.369310Z and JDBC storage is 14:11:01.600Z. Delivery verification does
not supply a mature daily outcome for this new artifact. No manual service start,
training or publisher run was used.

## Structural correction and data requirements

The current accepted coefficients still reproduce the compound-shade defect:
legacy both-closed forcing selects the indoor-only gain, while outdoor-only forcing
selects the nearly-zero outdoor gain. Air gains are 0.000317756576 versus
approximately 3.29e-14; mass gains are 0.00001372586 versus 0. These are feature
coefficients, not observed physical shade effects. See the
[qualified offline diagnosis](2026-10-05-thermal-offline-error-diagnosis.md).

The existing `joint_solar.py` candidate distinguishes all four regimes and constrains
both-closed gain below either single-shade gain. Its current fitter is coupled to
split window/skylight airflow. A fresh SELECT-only journal census has **zero window
or skylight events**, one `nostr_confirmed` indoor-shade event, one `manual_dm`
outdoor-shade event, one reconstructed outdoor-shade event and eight model-inferred
Kiva events. Unknown openings must remain unknown. Existing genuine journal events
must not be confused with the artifact's zero fully qualified action-training rows.

A cutoff-bound projection of the journal over the accepted model's 400-day range
finds **90.349 hours with both shades jointly confirmed closed** and no jointly
confirmed intervals for the other three shade combinations. The other 9,509.651
hours are not jointly confirmed. This is an upper bound from held journal states,
not temperature-qualified training hours or proof of continuous physical state.
It uses effective timestamps and reports received by the training cutoff; some
reports arrived after their effective time, so it also does not establish what
was known at each historical decision. Window/skylight states remain unknown.
The retained installed projection functions reproduce the intervals exactly.
A solar-only refactor removes the opening-state dependency but cannot independently
validate four shade gains from the current confirmed labels.

The proposed next model work is an **offline solar-only candidate**, retaining the
existing ventilation contract and refitting its own four-regime coefficients.
Compare chronology-preserving held-out errors with both baselines, retain explicit
label provenance and rank/identifiability requirements, and keep original coefficients
separate. The track preference is pending; no new candidate implementation, production
training, model replacement, action label, notification or household command occurred.

## Outdoor-weather algorithm comparison

The existing `experiment-forecast-solar-context.py` now reaches its unchanged
minimum of **ten training days and five held-out days**. The split remains
September29 **08:45 Mountain**, fixed before fitting, with ridge strength 1
and training-only feature scaling. Fifteen source-qualified pairs use archived
raw forecasts available by each 08:45 origin and qualified outdoor temperature
receipts at the 24h target. Training origins are September19–28; test origins
are September29/30 and October1/3/4. October2 lacks a usable forecast. Fourteen
earlier requested dates lack qualified outdoor outcomes and remain excluded.

| Residual variant | Held-out MAE°F | Signed bias°F | Maximum absolute error°F |
| --- | ---: | ---: | ---: |
| Raw forecast | 2.1870 | -0.5050 | 4.8400 |
| Fitted constant bias | 3.3736 | -2.6260 | 6.9610 |
| Season only | 3.2040 | -2.3433 | 6.6783 |
| Daylight only | 2.3871 | -1.0177 | 5.0272 |
| Daylight and season | 2.3407 | -0.5609 | 4.4206 |

Every fitted variant loses to raw on MAE. The combined variant reduces the
maximum error on these five days but does not meet the MAE improvement goal;
no weight or coefficient is promoted. This is a retrospective diagnostic of
archived raw-provider forecasts, not a comparison with the current production
Kalman correction, an untouched prospective validation, a thermal forecast,
or seasonal skill. All five test days are autumn, with daylight spanning only
11.586–11.791h; broader regimes remain untested.

The initial September20-onward extraction had only nine training days and
correctly withheld fitting. Extending the earlier bound to September5 adds
September19's already-qualified pair; split, thresholds, ridge strength and
held-out cohort are unchanged. No minimum is relaxed and no weights are tuned
on the test errors. Two complete restricted reads reproduce identical pairs,
reader returns and metrics; only report/request assessment clocks differ.
Offline replay reconstructs both pair assembly and every fitted result from
those retained inputs. All24 existing experiment/ablation tests pass.

Pair SHA-256:
`d36c0b1be3f58da56cf96980ae21b3dc86630cc4388ff319da9eaf5b2d776385`.
Sealed private capsule: `ml-weather-holdout-20261006-vyp5tj75/`, below the evidence
root. It retains original reader returns, paired rows, both reports, read-only
capture/offline-replay scripts, source pins, the insufficient initial assessment
and verification, with mode0600 files in mode0700 directories. Historical
forecast and model state, publishers, journal labels and household controls
are unchanged.

## PV, sunset and pre-dusk model diagnosis

The unchanged restricted benchmark qualifies five complete September29–October4
pre-dusk comparisons; October2 lacks origin components. The original morning
issue, original late atomic SoC and the same three prior-night sample ending
dates are retained. Historical profiles are assessed at the original morning
clock and matched to each late issue's exact sunset-relative phase. Existing
cloud penalty, rounding and clamps are unchanged.

| Original prediction day | Qualified trough% | Original pre-dusk% | Phase-matched comparison% | Sunset-only comparison% |
| --- | ---: | ---: | ---: | ---: |
| September29 | 81 | 81 | 81 | 83 |
| September30 | 65 | 64 | 68 | 70 |
| October1 | 72 | 65 | 69 | 72 |
| October3 | 86 | 74 | 82 | 83 |
| October4 | 85 | 74 | 83 | 84 |

On these five matched nights, original pre-dusk MAE is **6.2 SoC points**;
phase-matched MAE is **2.4**, sunset-only **2.2**. Phase matching worsens
September30's error from -1 to +3 points and improves the three October cases.
The sunset-only comparison has slightly lower aggregate error here but omits
the issue-to-sunset phase distinction. These are existing retrospective
counterfactuals, not original issued predictions or newly fitted model skill;
October3 separately retains its previously frozen pre-outcome comparison.
Five nights cannot establish calibration or seasonal performance.

Four qualified PV/sunset joins also reproduce from fresh restricted native
PV reads and original public prediction receipts, with exact atomic-SoC
origin binding. Original raw-weather archives verify for October1/3/4;
September30's original morning record/receipt has no issue-bound archive/digest.
Its recorded scalar quantities and qualified outcomes remain diagnostic evidence;
it cannot supply the missing hourly weather curve for an hourly-input fit.

| Day | PV error kWh | Sunset SoC error, points |
| --- | ---: | ---: |
| September30 | -0.958 | -14.807 |
| October1 | -0.117 | -12.542 |
| October3 | +0.821 | -3.990 |
| October4 | +0.654 | -4.614 |

All four originals use the resource-limited branch. At fixed direct demand,
SoC and other inputs, increasing solar gain monotonically increases both PV
and the modeled evening SoC (until their caps); decreasing it reduces both.
Thus gain alone cannot simultaneously reduce the opposing PV/sunset misses
on October3/4. This is a constraint of the current formula, not physical or
causal load attribution. An effective-demand or joint energy-balance candidate
needs its own qualified chronological evaluation; no inferred AC/DC conversion
or harvested-PV-as-solar-potential label is introduced.

Independent source repeats match after removing only the explicit assessment
clocks. Offline replay reproduces all44 retained profile calculations and the
component errors; all141 relevant existing tests pass. Native profile inputs,
original public receipts/weather archives, qualified PV-reader returns,
source pins and offline replay are sealed in
`ml-energy-chain-20261006-4td1a0pz/` below the evidence root (25 files plus manifest).
The proposed next bounded change is a pure offline phase predictor extracted
from this existing comparison, preserving provenance and production behavior.
The operator design prompt is pending; no predictor implementation or release,
production training, Item write, notification or household command occurred.

## Evidence

Private original forecasts/outcomes, repeated report, current accepted/backtest
copies, installed validator/dynamics/dataset source and aggregate action counts:
`/home/sat/.local/state/thermal-intel/qualification-receipts/ml-focus-20261006-d1o4hxuc/`.
Eleven mode 0600 files plus manifest are retained in a mode 0700 directory.
The initial derived summary mistakenly used `pair_details` instead of the scorer's
`pairs` key and consequently omitted local-day lists. That derived summary is rejected;
original scorer reports and exact-repeat evidence are unchanged. Corrected local-day
counts are independently checked against each selected-window count and retained in
`/home/sat/.local/state/thermal-intel/qualification-receipts/ml-focus-20261006-d1o4hxuc-summary-correction/`.
No raw household history is committed.

Additional sealed private capsules (mode 0700 directories, mode 0600 files):

- `solar-label-coverage-20261006-zcyce0_r/`: six files plus manifest, original
  cutoff-bounded journal export, interval projection and offline reproduction.
- `ml-daily-target-20261006-mqs6hyrv/`: five files plus manifest, exact-repeat
  original-outcome reports, scorer/baseline source and fixed-clock read-only command.
- `ml-natural-delivery-20261006-ns7wiror/`: ten files plus manifest, immutable
  original capture, accepted artifact, delivery/replay evidence and verifier source.

All three reside below
`/home/sat/.local/state/thermal-intel/qualification-receipts/`.
