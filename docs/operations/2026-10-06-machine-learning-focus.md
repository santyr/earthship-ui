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

The proposed next model work is an **offline solar-only candidate**, retaining the
existing ventilation contract and refitting its own four-regime coefficients.
Compare chronology-preserving held-out errors with both baselines, retain explicit
label provenance and rank/identifiability requirements, and keep original coefficients
separate. The track preference is pending; no new candidate implementation, production
training, model replacement, action label, notification or household command occurred.

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
