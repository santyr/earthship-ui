# Separate pre-dusk SoC trough issue

The 06:40 `forecast-intel.timer` remains responsible for weather/PV issuance,
scoring and coefficient updates. It currently projects dusk SoC from morning
atomic SoC plus predicted full-day PV. Moving that unchanged formula later
would still use the wrong reference. On September 29 its frozen morning
components were 72% source-bound SoC, 5.36 kWh predicted PV, 71.799%
estimated dusk and a 53% overnight trough. By 12:45 MDT the live atomic SoC
was 100% and the native PV-day receipt already showed 7.302 kWh. This is a
time-of-issue and PV-input problem, not evidence that the bank actually fell
to 53%.

## Chronological read-only counterfactual

For each completed September 25–28 night, use the persisted local Astro
sunset and select an origin 75 minutes earlier. The restricted
`energy_power_reader` resolved only `BMS_SOC_Evidence_JSON` to `item0613` and
selected original receipts persisted no later than that origin. The strict
SoC interval builder supplied the value at origin; no change-only `BMS_SOC`
carry or future receipt was used. Subtract each day's *as-issued morning*
`overnight_drop_final_pct` from that source-bound SoC, retaining the morning
drop assumption and no further-charge projection. Later outcomes came from
the existing completed-night atomic-SoC assessor, not the Item minimum.

| Day | Pre-dusk SoC | Morning drop | Morning / late estimate | Measured trough |
| --- | ---: | ---: | ---: | ---: |
| Sep 25 | 98% | 15.667 pp | 63% / 82% | 84% |
| Sep 26 | 100% | 20.000 pp | 73% / 80% | 84% |
| Sep 27 | 99% | 19.667 pp | 71% / 79% | 80% |
| Sep 28 | 86% | 19.333 pp | 46% / 67% | 70% |

Absolute error is 16.25 percentage points for the frozen morning forecasts
and 2.5 points for this late-origin counterfactual. Four warm-season nights
are useful feasibility evidence, not a seasonal calibration or proof that
the morning overnight-drop proxy is optimal. The estimate deliberately
assumes no further charge after the pre-dusk issue; that can bias low on
late-charging days. It has its own persisted provenance and should be scored
over additional naturally issued nights before it drives deep-cycle DMs or
any control.

## Source and operational contract

`forecast_pre_dusk.py` is a separate, display-only worker. A half-hourly
14:00–20:30 local timer checks today's `Sun_Set_Start`; only the first check
60–90 minutes before sunset can issue. It requires a same-day morning issue,
at least two qualified completed-night drop samples and a currently valid
atomic `BMS_SOC_Evidence_JSON` receipt. It writes
`Predicted_SoC_Trough_PreDusk` first, then
`Forecast_PreDusk_Trough_Receipt_JSON` as the display commit. A current-day
receipt prevents repeat issuance. An unavailable or expired input withholds
publication; it never falls back to the held numeric SoC, inferred 99%, or
the old 12-point drop. A timer check outside its gate is a read-only no-op.

The UI selects the later, dated pre-dusk receipt when present and otherwise
retains the morning estimate. The morning receipt, PV/temperature predictions,
state-file scoring, calibration and Nostr DM policy are untouched. The late
estimate is explicitly labelled in the Energy card and its chart; a separate
Item keeps the two forecast histories distinguishable. This is not thermal
model promotion or a control authorization.

Release gate: exact-file deploy the two new Items and worker, verify provider
and installed hashes, enable the user timer, then check the first *natural*
pre-dusk run for fresh source identity, one receipt, numeric/receipt equality,
JDBC persistence and correct UI selection. Do not manually run the service
inside the issue window merely to manufacture a successful gate. Retain the
source copy and installed-file backup for rollback.

## September 29 additive release checkpoint

The worker, Item file and user service/timer were installed at their exact
paths with source-matching SHA-256 hashes. Both new Items are `editable=false`
and initially `NULL`. `forecast-pre-dusk.timer` is enabled and waiting for its
first natural 14:00 MDT check; the service was not started manually. JDBC's
existing `* : everyChange` policy includes the new Items. This is a deployed
collector/display candidate, **not** a qualified forecast outcome: the first
natural issue, persisted receipt, UI readback and later scored night remain
to be verified. No morning forecast, DM threshold, thermal advice or pump
control was changed.

The follow-on charge-timing and prediction-feature review is recorded in
[prediction learning review](2026-09-29-prediction-learning-review.md). It does
not authorize moving this issue window or publishing an early full-charge
estimate from the current short history.

At the first natural 14:00 MDT timer firing, the service exited zero with
`pre-dusk trough: outside_window`. Both new OpenHAB Item states remained
`NULL`, and the enabled timer advanced to 14:30. This verifies the outside-
window no-publication path only. The first eligible issue is expected near
17:30 MDT for today's 18:48:23 sunset; its source, JDBC and UI checks remain
open until it actually runs.

Before the first eligible issue, the display-only worker was updated to add
`socStreamEpoch` and `socEvidenceSha256` to its v1 receipt. The digest binds
the exact atomic SoC JSON read at issue time; it is not itself proof that the
matching source record persisted. The UI now requires both fields before
selecting a pre-dusk value, and the origin-pair scorer requires their format.
`pre_dusk_tuning.verify_issue_soc` can then match the issue to the original
JDBC evidence bytes, stream epoch, recorded time, value and source expiry,
refusing a later-persisted or changed receipt. A 41-test Python group, all
1,909 UI unit tests, the UI build and all 15 Energy browser checks passed.
The idle installed worker matched the previous tracked SHA-256
`68e3b61f37ce9dc8c1b608b0d33cf382ba377037f3e56466e4cd8b8949379479`
before replacement and matched the new tracked digest
`6e7919e98c0b39fc073cf577525433f924da161c8db5ab3463d8e6aaa5b66365`
afterward. An exact private rollback copy remains at
`/home/sat/.local/state/forecast-pre-dusk-provenance-20260929/forecast_pre_dusk.py.before`.
The timer stayed active; no manual issue or Item write was made. Natural
publication, matching JDBC source/value receipts, and actual UI selection
remain release gates, not outcomes of these source tests.

The read-only `scripts/qualify-pre-dusk-natural-issue.py --day 2026-09-29`
now checks the two exact as-issued JSON histories and the bounded numeric
history through local OpenHAB JDBC REST, then (only when a natural late issue
exists) resolves the unique atomic-SoC Item table under the restricted
`energy_power_reader` role. Its repeatable-read, read-only query selects the
latest original evidence row at or before the issue and requires the exact
stream/digest, recorded time, percent and unexpired source receipt. It also
requires one numeric write matching the dated late receipt and its explicit
morning origin. Before the eligible window it returned one archived morning
issue and `pending_natural_issue`, with zero late issues; no worker was run.
An independent read-only database preflight resolved the unique atomic SoC
mapping to Item 613 under `energy_power_reader` and confirmed SELECT on
`public.item0613`; it did not read or publish a forecast value.
The script deliberately reports `display_selection_verified=false` and
`night_outcome_scored=false` even after an archive pass. After the natural
timer firing, rerun this command, check the actual Energy display separately,
and assess the following night only after its 11:00 MDT target window ends.
