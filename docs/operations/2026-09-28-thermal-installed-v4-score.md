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

## September 28 11:30 MDT current-revision checkpoint

The installed-v4, exact-capture-only scorer was rerun read-only across 61
publication rows. The independent one-hour set grew to 60 pairs:
model/persistence MAE **1.0896/0.5070°F**, with model signed bias **−0.8921°F**.
Only **two** pairs use the currently accepted `53d96e5e9637` revision; their
model/persistence MAE is **0.5705/0.0000°F** and their mean model error is
**+0.4015°F**. These two outcomes cannot establish skill, but their error sign
differs from the pooled low bias, so the pooled sample cannot license a
constant upward correction to the current artifact.

The independent six-, twelve- and 24-hour counts remain 18, 9 and 4.
Their model/persistence MAE remains 3.5322/3.2300, 3.1119/4.7200 and
4.1582/1.4850°F respectively; no 24-hour target from the current revision
has matured. All scored publications are low-confidence. Continue exact-origin
current-revision scoring and forcing/action diagnosis; do not graduate,
relabel remembered vent states as confirmations, or retune a global offset
from mixed-revision observations.

## September 28 19:34 MDT current-revision refresh

The same capture-strict read-only scorer, using the installed v4 runtime and
qualified temperature outcomes, now has 64 non-overlapping one-hour pairs:
model/persistence MAE **1.0367/0.4753°F**, with model bias **−0.8515°F**.
The accepted `53d96e5e9637` revision contributes six of those pairs:
**0.3520/0.0000°F** MAE and **−0.0280°F** model bias. Their persistence
targets were unchanged from origin, so six pairs do not establish model skill
or warrant an offset. At six hours, 20 independent mixed-revision pairs have
**3.3514/2.9430°F** MAE; the current revision has only one independent pair
at **1.3610/0.1800°F**. The currently accepted revision has no mature
24-hour pair. Five independent older-revision 24-hour pairs now have
**3.3444/2.3400°F** model/persistence MAE. All scored outputs remain low
confidence, and action outcomes and operational graduation thresholds are
still absent. The first current-revision 24-hour outcome cannot mature before
the September 29 morning target plus the scorer's five-minute lag. Keep the
artifact shadow-only and reassess then; these observations do not justify a
global bias or PV/vent coefficient change.

## September 28 22:30 MDT bounded current-revision check

An exact-capture-only read of the installed-v4 runtime from 14:20Z to 04:20Z
found seven independent, current-`53d96e5e9637` one-hour pairs. Model MAE was
0.3549°F with −0.0771°F bias; same-origin persistence MAE was 0.0000°F
because the qualified indoor target did not change in those seven windows.
At six hours, only two independent current-revision pairs matured: model MAE
1.4445°F versus persistence 0.0900°F. No current-revision 24-hour target has
matured. This is evidence against a short-horizon skill claim, not a basis for
an offset or coefficient update; retain shadow mode and the planned 24-hour
checkpoint.

## September 29 01:55 MDT current-revision 12-hour checkpoint

The installed-v4, exact-capture-only read-only scorer found three mature
12-hour pairs from the accepted `53d96e5e9637` revision, but only one
independent pair under its non-overlap policy. That pair had 0.861°F absolute
model error versus 0.180°F same-origin persistence error; its outdoor
forecast was 4.34°F warmer than the qualified outdoor outcome while its
indoor model prediction was 0.861°F low. The two overlapping pairs also lost
to persistence (three-pair model/persistence MAE 1.3467/0.4800°F), but must
not be counted as three independent days. The six-hour independent set still
has two current-revision pairs, model/persistence MAE 1.4445/0.0900°F.
All scored publications were low-confidence shadow outputs. This adds a
current-revision lead-time diagnostic, not a 24-hour score, action label,
weather-offset justification, model retune or shadow-exit evidence.

The selected independent 12-hour origin at 08:20 MDT was then replayed from
the verified accepted-source bundle
`thermal-replay-source-20260929T014041Z.tar.gz`, not the newer training-only
installed runtime. The archived v2 capture replayed its issued output
exactly. An in-memory assumed-closed vent schedule raised the 20:00 MDT
12-hour forecast from 68.039°F to 68.249°F, only +0.210°F; against the
qualified 68.900°F outcome, about 0.651°F of the original 0.861°F low miss
remains. The actual vent state was not verified, so this is a schedule
sensitivity bound, not an action label or evidence to apply a correction.
The temporary extraction was removed after verification; the private
source/evidence archive remains intact.

## September 29 04:29 MDT current-artifact checkpoint

The installed-v4 scorer again required exact archived forcing and qualified
indoor outcomes, selecting publications after the September 28 accepted
artifact was created. Its ten independent one-hour targets score model versus
same-origin persistence MAE **0.302/0.036°F** (eight persistence wins); eight
overlapping six-hour targets score **1.2774/0.3600°F** (all eight persistence
wins). The three independent six-hour windows score **1.4253/0.3000°F**.
Every scored publication is low-confidence. No current-artifact 24-hour target
has matured at this checkpoint; the first can be checked after its September
29 morning target and the five-minute outcome margin. A separate recent
mixed-revision 24-hour read scored 40 overlapping pairs at 2.441/2.5425°F,
but only four independent windows (3.412/2.070°F), so its overlapping average
does not demonstrate a release-quality improvement. No model, assumption,
advice, control or action label changed. Keep shadow-only pending independent
current-artifact 24-hour, confirmed-action and approved-threshold evidence.
