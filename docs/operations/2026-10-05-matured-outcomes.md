# October 5 completed energy and thermal outcomes

Read-only assessments at fixed **2026-10-05T18:16:05Z** close the fourth
original PV/charge/night comparison and extend three separate thermal cohorts.
Each of four reports was produced by two independent source reads and is
byte-identical to its repeat. No production configuration or model changed.

## October 4 original energy forecasts

| Quantity | Original forecast | Qualified outcome | Signed error |
| --- | ---: | ---: | ---: |
| Native daily PV harvest | 6.780 kWh | 6.126 kWh | +0.654 kWh |
| Sunset SoC | 93.386% | 98% | -4.614 percentage points |
| Morning overnight trough | 69% | 85% | -16 percentage points |
| Pre-dusk overnight trough | 74% | 85% | -11 percentage points |

The morning issue remains October 4 **12:40:57.827890Z**, after its original
weather capture at **12:40:57.822554Z**. Its distinct atomic SoC assessment
remains **12:40:57.840Z**, with 87% SoC. The archived raw weather digest,
original public receipt, retained PV diagnostics and original SoC input agree.
The PV read reproduces the previously qualified 1,998 receipts, native Item
655 mapping and **99.9612986%** calendar-day coverage. Sunset and first
reported-full observations retain their [original charge proof](2026-09-29-prediction-learning-review.md).

The original pre-dusk issue is **23:30:00.923128Z**, persisted at
**23:30:00.926Z**. Its exact atomic source persisted at **23:29:49.183994Z**.
The source-bound receipt/numeric-history verifier accepts the unchanged 74%
numeric anchor at October 3 **23:30:00.936Z**; no new numeric row is invented.
Both forecasts precede the October 4 night window.

The completed native night spans **October 5 02:00Z–17:00Z**, corresponding
to October 4 20:00 MDT–October 5 11:00 MDT. The pure atomic evidence assessor
finds minimum **85%**, maximum 100%, **887** in-window receipts/segments and
**99.9885950%** validated coverage. Its restricted SELECT-only REPEATABLE READ
query includes the original boundary carry and 120-second lookback. The bank
epoch is taken from the unique current physical bank; neither held numeric SoC
nor a partial night is substituted.

This completes the fourth source-qualified joint day, comprising two no-full
days and two reported-full days. The pre-dusk forecast reduces this day's
absolute error by five points but remains eleven points low. Four days do not
establish calibration, seasonal skill, causal load attribution or enough
independent cases to promote a fitted full-charge scheduler.

Night evidence digest:
`3ba033f22b11a355b03703973bb71cddf323e71e8a276280c2bf520edd430bd8`.
Original pre-dusk atomic input digest:
`eabae07a0168bebcd23800eb959b19dabd70eec84ec6e98aa0416f6a8abd17d5`.

## Thermal outcomes by original artifact

All pairs require the exact original private forcing capture and a qualified
native temperature outcome. The comparator uses seven qualified prior days
at matching local clocks, selected using the original issue boundary. Rows
are assessed separately by artifact; overlapping forecasts are not treated
as independent trials. Here “windows” means the scorer's non-overlapping
selection, not an assertion of statistical independence.

| Artifact / horizon | Pairs / windows | Model MAE °F | Recent-cycle MAE °F | Persistence MAE °F | Interval coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| October 5 `bad329`, 1 h | 2 / 2 | 0.4045 | 0.1800 | 1.3500 | 2/2 |
| October 4 `a4ea9f`, 1 h | 12 / 12 | 0.5237 | 0.4950 | 1.0200 | 12/12 |
| October 4 `a4ea9f`, 6 h | 12 / 4 | 1.3508 | 2.7300 | 5.6850 | 11/12 |
| October 4 `a4ea9f`, 12 h | 9 / 2 | 1.0551 | 3.4400 | 6.7800 | 9/9 |
| October 4 `a4ea9f`, 24 h | 3 / 1 | 1.4777 | 0.2400 | 0.4200 | 3/3 |
| October 3 `d91637`, 1 h | 6 / 6 | 0.8028 | 0.9600 | 1.7700 | 6/6 |
| October 3 `d91637`, 6 h | 6 / 2 | 1.4795 | 4.6800 | 8.3400 | 6/6 |
| October 3 `d91637`, 12 h | 6 / 1 | 1.0598 | 4.5300 | 8.2500 | 6/6 |
| October 3 `d91637`, 24 h | 6 / 1 | 2.2828 | 1.1100 | 0.5400 | 5/6 |
| October 3 `d91637`, 48 h | 3 / 1 | 3.1417 | 1.0800 | 0.2400 | 2/3 |

The 20 original publications yield **65** mature horizon pairs. All report low
confidence. The October 5 fit has no mature 6/12/24/48-hour outcomes in this
assessment. Its second one-hour target at **17:00Z** has model/cycle/persistence
signed errors **+0.225/0.000/−2.160°F**; the first at 15:00Z remains
**+0.584/−0.360/−0.540°F**. Both model errors exceed the paired cycle errors.

October 4's newly matured daily targets at **16:00Z** and **18:00Z** have
model errors **−2.514°F** and **+1.852°F**, respectively. Its favorable first
daily target alone does not support a daily-horizon skill claim. The original
six-hour interval miss at October 5 00:00Z remains in the cohort.

The older October 3 48-hour target at **18:00Z** has model error **−7.112°F**,
versus cycle **+0.900°F** and persistence **+0.180°F**, and falls outside its
original interval. Its three mature 48-hour forecasts lose to persistence on
every pair. The selected single non-overlapping window excludes this later
miss, so both the full cohort and selected-window results must remain visible.
Intervals average about 10.414°F wide; observed coverage alone is insufficient
for operational readiness. These results preserve the
[offline diagnosis](2026-10-05-thermal-offline-error-diagnosis.md) priorities
and leave seasonal, action-outcome and model graduation gates open.

## Reproduction and private evidence

Thermal audits use `scripts/audit-thermal-shadow-publications.py` with
`--runtime-root /home/sat/openhab/scripts --assessed-at 2026-10-05T18:16:05Z
--require-capture --include-pairs --recent-cycles --horizons 1 6 12 24 48`.
Bounded issue intervals and exact artifact selectors are:

| Report | `--since` | `--until` | Full `--artifact-id` |
| --- | --- | --- | --- |
| `d916` | 2026-10-03T13:00:00Z | 2026-10-04T00:00:00Z | `d9163729bcc75e38e147c33eb76c863b9e125179abc92088352192d5bc6d3be9` |
| `a4` | 2026-10-04T13:00:00Z | 2026-10-05T13:00:00Z | `a4ea9f4a0ddb11a54d881cb8d83ded73b57836122778a44c65e3c0bfd3ed01df` |
| `bad329` | 2026-10-05T14:00:00Z | 2026-10-05T18:06:00Z | `bad329e1299847957b261975e8f6140985050c2604356e623ba8d381cccb0f09` |

The artifact option separates assessment; issue bounds constrain the actual
publication read. Every returned pair's artifact identity is checked. The
fixed assessment also requires target maturity before scoring. Every earlier
qualified pair remains byte-identical in the extended cohorts.

Durable mode-0700 capsule:
`/home/sat/.local/state/thermal-intel/qualification-receipts/20261005-midday/`.
It retains mode-0600 reports/repeats, original ordered native night rows,
read-only audit sources and verifier runtime pins, with a hashed manifest.
Exact repeated report SHA-256 values are:

| Report | SHA-256 |
| --- | --- |
| `oct4-joint.json` | `c3bb89c47b27b77335dba607729f64b5bf5f70211eec390ab85c2cafb1bfb471` |
| `bad329.json` | `7a162da9f6022cc5a64ef62dd375cd23505d35a43d6990dbf5e9523a29b7005e` |
| `a4.json` | `d1f9680538522b946a139f109648bd10c36be9a85ed021327a4eea2ea4537a9a` |
| `d916.json` | `e28849cf6e2b379f016da267fca10c3abd7c22a6b8e5bbe2351d3d9decf65f3f` |

OpenHAB still runs PID **1696**. Production restart qualification awaits host
authentication; no restart receipt is claimed. Forecasts, coefficients,
filters, thresholds, training, publishers, notifications, action labels and
household commands were not changed by these assessments. November's approved
no-venting default remains intact.
