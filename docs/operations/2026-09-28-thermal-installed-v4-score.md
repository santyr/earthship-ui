# Installed-v4 thermal shadow score — September 28

The Git tree's v5 artifact validator rejects production's accepted v4 model.
Both read-only audits now accept an explicit `--runtime-root`. Live shadow
scoring used `/home/sat/openhab/scripts` for its outcome reader and
forcing-capture verifier; the artifact audit selected the same installed root
for v4 validation. The installed validator source
SHA-256 was `5425ffa06dec539a2191514cd66fa661c88cde17bac747012d10feea088358d8`.
An incomplete runtime root fails closed. No model, advice, Item, control or
training state changed.

Read-only, exact-capture-qualified publications from September 23 onward
score against later qualified indoor outcomes. The non-overlap policy greedily
selects a forecast only after the preceding target; revisions and warm-season
conditions are mixed.

| Horizon | Non-overlapping pairs | Model MAE (°F) | Same-origin persistence MAE (°F) | Model bias (°F) |
| --- | ---: | ---: | ---: | ---: |
| 1 hour | 59 | 1.105 | 0.516 | −0.904 |
| 6 hours | 18 | 3.532 | 3.230 | −2.948 |
| 12 hours | 9 | 3.112 | 4.720 | −2.811 |
| 24 hours | 4 | 4.158 | 1.485 | −4.158 |

The 24-hour nominal interval is roughly 10.414°F wide and covers only two
of four independent targets. The 47 overlapping 24-hour pairs are not 47
independent days. All scored publications have low confidence; eight earlier
publication rows lacked exact captures. At 24 hours the paired outdoor
forecast bias is +2.888°F while the indoor model bias is −3.104°F over the
overlapping set. This sign contrast does not establish a cause or justify a
blanket weather correction. The 12-hour improvement is real within this
small observational sample, but cannot substitute for 1- and 24-hour skill.

The installed-v4 accepted artifact/backtest pair passed coherent validation:
accepted SHA-256 `a9f608d638b5e450e4d0a6f53c7b887bbfdb74290f8d21b78364a313a5fcfc8a`,
report SHA-256 `d4e52ca21102e1ac7a5b765a5e74011a5cdac47a3030aaa3dc74b3bd86415ab6`.
Its historical 24-hour air MAE is 2.179°F, versus 1.690°F persistence and
1.834°F recent-cycle baseline across 119 paired targets; confirmed-action
training rows, evaluation targets and disjoint folds are all zero. The
artifact is shadow-only and has no approved graduation thresholds. Historical
hindcast and operational-origin errors answer different questions, and neither
supports graduation now.

Next diagnostic work is exact-origin replay that separates forcing, dynamics
and *assumed* vent/shade schedules without treating operator recollection as
signed action labels. A new candidate needs chronological holdout and
prospective score against both baselines before any thermal advice authority
is considered. No coefficient or schedule was changed in this audit.

## Exact-source replayability and vent hypothesis

The four selected independent 24-hour origins use revisions
`c87551f92f02`, `507748cee9ca`, `6084d8f6034e`, and `01b0eda24b6e`.
A bounded read-only search of 76 Git runtime-source commits found a complete
tree matching only the first (`ce34dee19073`, also present in two later
commits). The other three are not reconstructible from a single matching Git
tree in that search. These earlier captures are v1 and do not embed their
accepted artifacts; a source match alone is not an exact-replay license.

`scripts/replay-thermal-forcing.py` now requires a v2 capture with embedded
artifact, a matching runtime-manifest revision, and bit-for-bit as-issued
output replay before it can compare an in-memory assumed-closed vent schedule.
The hypothetical is explicitly not an action confirmation or training label.
Five focused tests cover CLI runtime selection, schedule isolation, target
alignment, v1/source refusal, and the exact-replay gate. A live read-only
replay of the September 28 08:20 MDT capture under installed revision
`53d96e5e9637` matched its publication exactly. Assuming closed vents changed
its 1-hour prediction by 0.000°F and its *not-yet-scored* 24-hour prediction
by +0.708°F. Its first mature qualified one-hour outcome had issued model
error +0.972°F versus 0.000°F persistence error; that miss cannot be assigned
to tonight's later vent window.

A second isolated replay of the September 28 04:20 MDT v2 capture used the
historical `831893709152` source bundle. Its preserved v2 verifier was
overlaid into the disposable source tree because the historical importable
module predated v2; the 21-file revision hash was unchanged. Exact publication
equality passed, and the assumed-closed schedule raised its unscored 24-hour
prediction by +0.996°F. The disposable tree was removed. Those deltas are
model sensitivities only; the associated 24-hour outcomes are not mature and
no vent state has been qualified. This sets a reproducible source-matched
path for later outcome scoring without retroactively treating recollections
as signed actions.
