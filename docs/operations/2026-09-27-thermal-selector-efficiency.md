# Thermal endpoint-selector efficiency — September 27

## October 3 deferred daily-endpoint materialization deployed

The next measured selector cost was constructing a `RolloutEndpoint` and its
up-to-288-row prefix for every eligible timestamp, then discarding almost all
of them during daily ranking. The selector now retains each winning index,
then materializes just the selected daily prefixes. Complete row validation,
contiguity/forcing eligibility, confidence minima, longest-run/earliest-origin
ranking, local-day assignment and final chronological order are unchanged.
No training input, horizon, solver, equation or acceptance gate changes.

The new allocation regression fails on the actual old implementation: **576
endpoints constructed for three returned daily origins**. Twenty-three new
cases cover an independent eager reference at all five horizons, missing rows,
unknown actions, inactive solar, confidence minima, Mountain local midnight and
fall DST, empty/short inputs, refusal behavior and complete-fit equality.
The dynamics/glazing/selector group passes **95 tests** and the pipeline/v2/
artifact/selector group **254 tests** (326 distinct cases). These synthetic
DST cases do not replace a live winter qualification.

Two interleaved 400-day comparisons retain identical origin/target/forcing
objects and confidences at every horizon. Selector-only times are
**0.892159 / 0.884018 seconds** before and **0.359813 / 0.353040 seconds**
after. Complete fits take **4.071683 / 4.083921 seconds** before and
**3.541060 / 3.543602 seconds** after: approximately **13% further improvement
for this isolated synthetic fit**, not a measured whole-run speedup or a
percentage to add to the previous optimization. Complete fit SHA remains
`3ca0ce06a668d4e17e0e7a345a01c9e28208a1478fa423560b281cadac5eb739`.

The compatible v4 backport changes only `_eligible_daily_endpoints_from_prepared`;
all other installed module AST is identical. Its 30-day complete-fit SHA remains
`754def4eb21d19a31f2e3ab894b40ea8f356843286517c5ba8b54fc58b3da091`,
and all 30 new selector/prior-glazing cases pass against that actual candidate.
Original file SHA is `adc2908c357f4ace67857fb50fa744a0c1130dd30db7a360368d75afe811d85b`;
installed SHA is `24d7b3039ec46346c46ee49acf06a0967f14076c8bff0107eefb4981f0fdd719`.
At **21:45:02.801952Z**, actual receipt-bound install/original restore/reinstall
passed. Private source, rollback bytes, transaction code and timer/source/model
receipts remain at
`/home/sat/.local/state/thermal-intel/deploy-receipts/endpoint-materialization-20261003T2146Z/`.
All 25 other files, four models/reports, OpenHAB PID 1696 and original shadow
deadline are unchanged. Both user timers are active/enabled; no job, household
control, label, model refit or OpenHAB restart was started. The transaction
explicitly refuses application at/after 21:50Z, ahead of the natural publisher.

Current runtime is
`15267d7af9323d7c23dc14d6b3c5526515195474ab983e004b101c66e656cb8c`,
superseding `ccddda9b...` before its first natural publication; accepted training
still retains `cd77cd16...`. Reuse the qualified post-glazing archive below as
the exact preimage recovery point; no redundant preimage archive was created.
The new private postimage archive is
`/home/sat/backups/earthship-energy/thermal-post-endpoint-20261003T2145Z-15267d7a.tar.gz`,
SHA `d638c6a6a9a81eb00eca58edb87b7a7a07939c199c112dfffc5c4ab7ee575125`.
Creation and independent verification agree on 153 members and 122 captures.
Independent cold imports match the new runtime, validate the unchanged typed
eligible artifact and all 122 captures, reproduce the unchanged 30-day fit,
and pass all 30 regressions. The original 19:53:38Z forecast replays exactly
from cold code, output SHA
`2a5f3d2bc4eb195dbc45bd4a193f81866b400a429834753eefb7ce05c6d033c0`.
The two owned temporary compatibility/extraction directories were removed;
the qualified private transaction and recovery archives remain.

Rollback uses this receipt parent and the same guarded single-entry `dynamics.py`
manifest documented below, with both workers idle and only their timers briefly
stopped/restored. Retain the qualified private evidence. The **21:53Z natural
publisher** and **October 4 06:50 MDT trainer** remain production continuity/
resource/accepted-artifact gates; no accuracy or shadow-exit claim is made.

### First natural post-selector publication verified

The original timer triggered at **21:53:54.173331Z**; invocation
`a7532cb92efc4f1895e036f581161d82` started at 21:53:54.187839Z and exited zero
at 21:53:58.197399Z, with `NRestarts=0`. Decision/publication clocks are
21:53:55.878437Z / 21:53:58.152849Z. The unchanged accepted `d9163729...`
artifact retains training revision `cd77cd16...`, while the installed runtime
is explicitly `15267d7a...`. The 72-point output remains shadow/low confidence,
with learning and household controls off.

The live Item, exactly one original JDBC row at **21:53:58.153Z**, and capture
`20261003T215355Z-fddbb7fe6f231109.json.gz` match output SHA
`fddbb7fe6f231109615d8ae0cac29320f25c9c0a06ec5b5275bb7ddc50329496`.
Native radiation and all three temperature receipts pass at decision and
publication; radiation was decoded at 21:53:39Z and expires at 21:55:39Z.
Exact installed-runtime replay passes. Repeated source/invocation/Item checks
are unchanged through verification at **21:55:16.255637Z**. The private
`natural-publication.json` proof is retained in the selector receipt parent.
Both user timers remain active/enabled; OpenHAB PID remains 1696. This closes
natural publisher continuity for the two fit optimizations, not October 4's
whole-training resource/acceptance gate or scientific model graduation.

## October 3 fit-local glazing-row reuse deployed

A deterministic 400-day, 114,624-training-row profile found `_glazing_rows`
built the same auxiliary design twice in each fit (2.579 seconds cumulative
under profiling). Selection now retains those already validated rows for that
fit. The original selection/diagnostic contracts, envelope and auxiliary
validation, equations, solver, chronological inputs and acceptance gates remain
unchanged. Each subsequent fit builds its own rows; there is no cross-fit or
cross-run cache, warm start, shortened training window or reused model.

Two interleaved single-thread 400-day fits took **4.414680 / 4.427041 seconds**
before and **4.031289 / 4.033409 seconds** after: approximately **9% faster for
this isolated synthetic fit**, not a measured whole-trainer improvement. Every
complete fit has SHA-256
`3ca0ce06a668d4e17e0e7a345a01c9e28208a1478fa423560b281cadac5eb739`
and final objective `0.00016809381152404807`.

Seven new regressions cover one construction per fit, no reuse across fits,
changed inputs, exact complete-fit parity in both inactive-action modes,
selector/diagnostic compatibility and unchanged malformed-input refusals.
The dynamics group passes **72 tests** and the pipeline/v2/artifact group
**238 tests** (303 distinct cases; the seven new cases occur in both groups).

Production received only a compatible backport onto its actual installed v4
file, not the repository's unrelated split-airflow/solar changes. Original
`dynamics.py` SHA is
`3b50fec19289ed09fbc2a507f0b5747e7906d427ae009e596835d8b54ecd87ce`;
installed SHA is
`adc2908c357f4ace67857fb50fa744a0c1130dd30db7a360368d75afe811d85b`.
All other module AST is identical. The seven regressions also pass against
the compatible runtime, and its complete 30-day fit matches the actual old
runtime exactly, SHA
`754def4eb21d19a31f2e3ab894b40ea8f356843286517c5ba8b54fc58b3da091`.

At **21:23:49.670342Z**, the existing receipt-bound file engine performed an
actual `install -> original restore -> reinstall` with digest verification.
Private source, original rollback bytes, before/round-trip/timer receipts and
the one-shot transaction code remain at
`/home/sat/.local/state/thermal-intel/deploy-receipts/glazing-reuse-20261003T2125Z/`.
All 25 other runtime files and all four model/report files are byte-identical.
OpenHAB PID 1696 is unchanged. Only the two thermal user timers were briefly
stopped, then restored active/enabled with the original shadow deadline
`1d 8h 28min 29.734179s`. No worker, refit, forecast publication, label,
household control or OpenHAB restart was started by this transaction.

The publication runtime is now
`ccddda9bb8bf2d005d91376662be7dba7c6e89800f6060f2c96fa59e46f730bb`;
accepted training retains its original `cd77cd16...` revision. Intentional
private pre/post recovery archives each verify 153 data members and 122 captures:

- `/home/sat/backups/earthship-energy/thermal-pre-glazing-20261003T2123Z-ae5310c4.tar.gz`,
  SHA `316216a5110b32a5ba9ed731d74ddca71308427420188bca4413ce058d71ccbc`.
- `/home/sat/backups/earthship-energy/thermal-post-glazing-20261003T2125Z-ccddda9b.tar.gz`,
  SHA `d8d51d74b0da6df6f224a36c60a5d5c5cd438f701bca63a32c16817058e68e27`.

Independent cold extraction matches the full new runtime, validates the typed
unchanged accepted artifact and all 122 captures, reproduces the identical
30-day fit, and passes all seven regressions. The original 19:53:38Z capture
replays exactly from restored code under the explicit new runtime pin, output
SHA `2a5f3d2bc4eb195dbc45bd4a193f81866b400a429834753eefb7ce05c6d033c0`.
Training/publication identities remain distinct. This is cold code/model/capture
recovery, not a new whole-host restore or a natural new-runtime publication.
The owned temporary source/extraction/test directories and one-shot script
were removed; the qualified private receipt and recovery archives remain.

The next natural **21:53Z publisher** and **October 4 06:50 MDT trainer** remain
continuity/resource/accepted-artifact gates. No accuracy or shadow-exit claim.
To roll back with both workers idle and a clear timer window, use the existing
receipt engine, source root `<receipt-parent>/source`, receipt directory
`<receipt-parent>/files` and this exact single-entry manifest:
`source=dynamics.py`, `target=/home/sat/openhab/scripts/thermal_model/dynamics.py`,
`phase=code`, `mode=0644`. Stop/restore only the two thermal user timers around
the guarded transaction; refuse later unowned edits and retain recovery bytes.

## October 3 chronological-prefix bookkeeping deployed

The evaluator previously scanned the whole sample set for each daily training
prefix and rescanned that prefix for both provenance histograms. `_TrainingPrefixes`
now selects the same strictly earlier tuple with `bisect_left`, counts each newly
eligible training row once, and returns detached histogram snapshots. It is
fit-local only: no model/fit reuse, cross-run cache, changed 400-day window,
different forecast equation or relaxed validation. Origins with no complete
future horizon still skip without consuming training provenance.

Two interleaved 115,200-row / 386-fold metadata-only comparisons took
5.996741 / 5.981424 seconds before and 0.133852 / 0.134652 seconds after.
Both complete metadata digests equal
`7e4733d49550f7cd56d7db38927097eaaf47d28e03c55c5b4964bbc5272e0892`.
This saves about six seconds of bookkeeping, **not** a 45-fold speedup of the
whole trainer. Numerical fitting remains dominant; October 3's unchanged
natural trainer took 26m04s, about 365.15 MiB peak memory and zero peak swap.

Five new regressions were observed failing against the old evaluator, then
passed with the implementation; the final six-case group adds skipped-origin
coverage. The evaluator/pipeline/artifact group passes
252 tests. Complete reports and every fit input match a separate naive-scan
reference, including mixed action/radiation provenance, missing intervals,
repeated/strict cutoffs and failed fits. Tests also prove once-per-row counting,
detached earlier evidence, skipped unscorable origins and reverse-prefix refusal.

Production retains its existing 15% persistence shrinkage; the repository's
separate raw-trajectory scoring change was **not** deployed. An isolated
compatible copy started from installed SHA
`aa8f380d189c0f852bee2621a0275ec5cce4ae9b0e19e675d1e20df27d91ff43`
and changes only this import/helper and chronological-prefix bookkeeping.
All other module AST and the model-scoring AST are unchanged. Against the
installed v4 import tree, the complete report and all 31 fit inputs match the
actual pre-change module, with report SHA
`18ee5e972a0fdafcfbdea2f5ceac67e477e4c1e12f661af9675c9a3da61294ca`;
all six prefix regressions pass there as well.

At **19:41:35Z**, the existing receipt-bound engine performed an actual one-file
`install -> original restore -> reinstall`, verified each digest and retained
the compatible desired source and original rollback bytes at
`/home/sat/.local/state/thermal-intel/deploy-receipts/evaluation-prefix-20261003T1943Z/`.
Installed evaluator SHA is
`b5f3ba2f24b92702d95b9f0bf7147f397a8fba1fb23682f9f184d8ed9a8581f1`.
The other 25 runtime files and all four artifact/report files are byte-identical.
Both thermal user timers were briefly stopped and restored active/enabled;
their original shadow deadline remains `109709716162` monotonic microseconds.
No job was started, model refitted/relabelled, input/label published, household
control touched or OpenHAB restarted (PID 1696 unchanged).

The new publication/training runtime revision is
`ae5310c43d833c420871a98daf6b3ae132a1f2ab49920c7b3b7b8eff27574517`;
the accepted artifact retains its original `cd77cd16...` training revision.
Private pre/post publication-runtime archives both verify 152 members and 121
captures, preserving distinct training/runtime bindings:

- `/home/sat/backups/earthship-energy/thermal-pre-prefix-20261003T1943Z-cd77cd16.tar.gz`,
  SHA `3b1e4731be7a40f8b255e7621c0036c9edf573fef4ed11638097d4d184186e4c`.
- `/home/sat/backups/earthship-energy/thermal-post-prefix-20261003T1943Z-ae5310c4.tar.gz`,
  SHA `a828d8435d7f37ce332735898bd2344a87baa5a54f4dcedd61cdc5847bc7d106`.

An independent extraction of the post-install archive imported only restored
thermal code, matched the full new runtime revision, validated the unchanged
accepted artifact and all 121 captures, and passed the six prefix regressions.
The original 17:53:37Z publication also replays exactly using that restored
runtime/capture, output SHA
`4e1729cc5ab6ba22560847452957aa1b0ce28522d88dc90187566b96fac5a3b3`.
It also replays from the installed runtime under the same explicit source pin;
this is not a natural publication generated under the newer runtime. The
temporary test/staging/extraction directories were removed; the qualified
receipt and intentional recovery archives remain. This is cold-source/model/
capture recovery, not a new whole-host restore rehearsal.
The next natural publisher and October 4 06:50 MDT trainer remain the deployed
continuity/resource/accepted-artifact gates. No accuracy or shadow-exit claim.
Do not copy the whole repository evaluator into v4 production. To roll back
when both workers are idle and the timer window is clear, use the existing
receipt engine with source root `<receipt-parent>/source`, receipt directory
`<receipt-parent>/files` and the exact one-entry manifest:
`source=evaluation.py`,
`target=/home/sat/openhab/scripts/thermal_model/evaluation.py`,
`phase=code`, `mode=0644`. Stop/restore only the two thermal user timers around
that guarded transaction; refuse later unowned edits and preserve the backups.

### First natural post-prefix publication verified

The unchanged timer triggered at **19:53:36.437651Z**; invocation
`3335c9fad08d4fc9883829a5dba85e7e` started at 19:53:36.449676Z and exited
zero at 19:53:40.450974Z, with no restart/retry. Decision and publication clocks
are 19:53:38.161057Z and 19:53:40.406428Z. The live Item, exactly one original
JDBC row at **19:53:40.407Z**, and saved capture
`20261003T195338Z-2a5f3d2bc4eb195d.json.gz` match output SHA
`2a5f3d2bc4eb195dbc45bd4a193f81866b400a429834753eefb7ce05c6d033c0`.
Exact replay passes under explicit installed `ae5310c4...`; the accepted
artifact remains `d9163729...` with original training revision `cd77cd16...`.
Native radiation and all three temperature receipt expiries pass at decision
and publication, with matching source identities. The output has 72 forecast
points and remains shadow/low confidence, with learning and controls off.
Invocation/source/Item readbacks remain unchanged through verification.

This closes the first natural publisher/import/source/history/replay continuity
gate. It does not exercise the optimized training prefixes; October 4's 06:50
trainer is still required for whole-run resource and artifact acceptance.
The 19:41 recovery archives predate this publication; its original capture is
stored separately in the normal private capture history. Both timers remain
enabled/active. At 19:53:20Z, the read-only, non-atomic global ownership inventory
reports zero issues (380 managed/65 file-owned Items, 79/7 Things, 37/5 rules).

The 400-day trainer remains shadow-only. A representative isolated two-fit
`cProfile` run spent 2.208 seconds selecting multihorizon endpoints and
11.614 seconds in the numerical objective/gradient. Endpoint selection
rescanned up to 288 confidence values for every eligible origin. It now uses
a monotonic sliding minimum over each horizon's next-row window, preserving
the same endpoint, forcing prefix and exact minimum confidence.

The same deterministic two-fit profile after the change spent 1.477 seconds
in endpoint selection (about 33% less for that substep); overall profiled
time changed from 15.072 to 14.680 seconds, too small and noisy to predict
the full natural-run benefit. The optimizer remains the dominant CPU cost.
All 57 dynamics tests and 690 thermal Python tests passed, including a new
naive-prefix parity test across all five horizons and an invalid interior row.
No training objective, model coefficient bound, acceptance gate, published
trajectory or control policy was changed.

The two thermal services were idle and their timers were stopped for the
attended installation. A full-manifest preflight found intentional source-only
v5 drift in `thermal_intel.py`, `artifacts.py` and `evaluation.py`; the full
installer was not run. Only the compatible `dynamics.py` was installed with
the existing receipt-bound, atomic transaction helper using a one-entry
manifest. Its prior SHA-256 was
`b94832dcdf0739d24ec5b6bf43e177bdf17308993c2fb8c3b9f49cea994421b2`;
installed and source SHA-256 now both equal
`82117c224b9fcfb6819a6b3dfa5fc14d60690e131813561b48b979dc8d7947b9`.
The verified rollback receipt is private at
`/home/sat/.local/state/thermal-intel/deploy-receipts/selector-one-20260927-wb3fHq/files/`.
The unused full-manifest preflight snapshot was deleted after inspecting its
exact 516 KiB contents. Both timers were restarted and passed the
`timers-enabled` state check. The next natural shadow publication and the
September 28 06:50 trainer are the runtime gates. Do not infer shadow-exit
readiness or swap relief from this isolated CPU profile.

## Second measured numerical-loop optimization

The same two-fit profile showed roughly 3.15 million NumPy `all()` reductions
in the rollout's per-step finite checks. Replacing only the two-element state
array reduction with two scalar `math.isfinite` checks left the sensitivity
array check, state transition arithmetic, objective, gradient and optimizer
unchanged. The representative profiled run fell from 14.680 to 13.173 seconds;
this is an isolated timing, not a measured 400-day trainer speedup. A new
overflow regression confirms a nonfinite state still refuses the rollout.
All 691 thermal Python tests passed.

Both services were idle and both timers briefly stopped for a second exact
one-file transaction. The expected installed preimage was
`82117c224b9fcfb6819a6b3dfa5fc14d60690e131813561b48b979dc8d7947b9`;
the installed/source SHA-256 is now
`59ae03f91afc4e0d51e7c24cdd8e2f3a7f477beb0052ce1201e67260e4b8ee7a`.
The private rollback receipt is
`/home/sat/.local/state/thermal-intel/deploy-receipts/finite-one-20260927-5EFjQC/files/`.
The installed module imports successfully and both timers again pass
`timers-enabled`. The next natural shadow publication and September 28 trainer
remain the runtime gates; no shadow-exit claim follows from this optimization.

The natural September 27 16:15 MDT shadow service subsequently exited zero
with 1.048 seconds CPU time. Live `Thermal_Model_JSON` advanced to a
22:15:50.065912Z publication with `status=shadow`, low confidence, no
candidate schedule and the accepted artifact's existing code revision.
`Thermal_Advisory` remained `none|No thermal action needed`. This closes the
post-install publisher/import compatibility check only. The optimized
endpoint selection and rollout objective are exercised by tomorrow's 06:50
training run, whose timing and artifact gates remain unverified.

## Third measured source-only allocation reduction

A fresh isolated 30-day synthetic fit profile spent 6.035 of 7.234 seconds in
61 multihorizon objective/gradient evaluations, with 914,808 small-array
finite reductions and repeated two-by-two Jacobian and direct-gradient
allocations. Reusing those two scratch arrays within each endpoint and updating
the two-element state in place reduced that same profiled fit to 6.149 seconds
overall and 4.947 seconds in the objective (one run each; not a whole-trainer
claim). The objective and gradient matched the prior committed implementation
bit-for-bit on the same 30-day evidence, and all 691 thermal Python tests
passed. No model equation, coefficient bound, scoring gate, or control policy
changed. The installed runtime still has the prior `dynamics.py` hash
`59ae03f91afc4e0d51e7c24cdd8e2f3a7f477beb0052ce1201e67260e4b8ee7a`
at the initial source-only checkpoint. At 17:29 MDT, both services were idle
and their enabled timers were briefly stopped for an exact one-file transaction.
The private receipt at
`/home/sat/.local/state/thermal-intel/deploy-receipts/array-one-20260927-3oieQT/files/`
pins that prior hash and the source hash
`2c8012d5c750a25f72b9cda5a0e5e241958ad7f3ee8334c96385e3fb2a864b0f`.
The guarded installer changed only installed `thermal_model/dynamics.py`;
receipt verification and source/runtime SHA equality passed. Both timers were
restarted and passed `timers-enabled`. The installed module imported and an
isolated 30-day synthetic fit completed with objective decreasing from
0.00017959468716428502 to 0.0001582665101962629. No production model artifact
or control was changed. The September 28 natural trainer remains the
whole-run timing and accepted-artifact gate.

The subsequent natural September 27 18:16 MDT shadow publisher exited zero.
Read-only live `Thermal_Model_JSON` showed generation at
`2026-09-28T00:16:51.147299+00:00`, `status=shadow`, low confidence and the
same accepted artifact revision. This verifies publication after the one-file
runtime installation, but does not exercise the next full training run or
support exiting shadow mode.

The first full natural training run with both the selector/finite-state work
and small-array reuse finished September 28 at 07:49 MDT, exit 0, with
58m 56.671s CPU, 366.3 MB memory peak and 0 B swap peak. The September 27
run consumed 1h 10m 32s CPU; that is about 16% less, but the training window
and scored folds changed, so the whole difference is not attributed to these
patches. The accepted v4 artifact was atomically promoted at 07:49 with the
installed 21-file code revision `53d96e5e9637d9c0c427afaffa35b29350243bf295ec6ed6f8a38f631d686396`;
its accepted file SHA-256 is `a9f608d638b5e450e4d0a6f53c7b887bbfdb74290f8d21b78364a313a5fcfc8a`.
This closes the natural whole-run completion and source-continuity gate, not
the causal performance attribution or shadow-exit gate. The artifact still
sets `shadow_only=true`, has zero confirmed-action training/evaluation rows,
and its 24-hour air MAE is 2.179°F versus 1.690°F for persistence. Its
provisional internal promotion tolerates up to 0.75°F worse 24-hour MAE; that
is not an approved operational graduation threshold. The next natural shadow
publisher must still demonstrate publication from this new accepted artifact.
The natural 08:20 MDT publisher subsequently exited zero in 2.116s CPU. The
new 240-row v2 capture embeds that accepted code revision and exactly equals
the live `Thermal_Model_JSON` under the installed v4 verifier. It is still
`shadow`/low confidence with no candidate. This closes the publisher-
continuity gate, not the independent accuracy or action-confirmation gates.

## September 28 horizon-independent row preparation

A fresh deterministic 30-day fit profile of the current source spent 0.797s
selecting endpoints, including five repeated passes over the same row validity,
inactive-forcing and confidence inputs. Preparing those inputs once for all
five horizons reduced that selector substep to 0.222s in one like-for-like
`cProfile` run; total profiled fit time was 6.483s before and 5.680s after.
These are single-run measurements, not a natural-trainer speedup claim. A
read-only comparison against the exact committed pre-change module found
identical per-horizon origin/target/confidence selections and bit-for-bit
identical fitted coefficients and objective evidence on the same 30-day data.
The existing 58 dynamics tests passed before the new regression test was added;
the seven selector-focused cases, including both active and inactive forcing
paths, passed afterward. A broader thermal-suite attempt was externally
terminated with exit 143 before completion, without a reported assertion
failure; it does not count as a full-suite pass. The same current 60-case
dynamics file subsequently passed in two bounded batches (24 and 36 tests).
The remaining thermal Python files passed in four bounded batches: 258, 222,
108 and 77 passed, with one PostgreSQL-dependent test skipped. This covers
all 725 passing tests plus the one skip without relying on the terminated job.

After the natural 18:24 MDT shadow run exited zero, both thermal services were
idle and both enabled timers were briefly stopped. A one-entry manifest for
only installed `thermal_model/dynamics.py` checked the expected preimage
`2c8012d5c750a25f72b9cda5a0e5e241958ad7f3ee8334c96385e3fb2a864b0f`
and source image
`90c21d0ba875461486f7cde0de8cbee62a090e166c63618b78fef7d866b7eafc`.
The receipt-bound installer made a private rollback copy at
`/home/sat/.local/state/thermal-intel/deploy-receipts/selector-rows-20260928-70o5wbfe/files`,
installed that exact one file, verified the receipt and source/runtime SHA
equality, and restored both timers. Both timers read back enabled and active.
The installed module completed the isolated 30-day fit with the same objective
decrease and origin counts as the source. No model artifact, advisory policy
or control was changed. The next natural 20:24 shadow publication and
September 29 06:50 trainer remain production continuity and whole-run gates.

The natural 20:24:41 MDT shadow service started after the timer trigger and
exited zero at 20:24:44. Its latest JDBC Item 610 row, persisted at
`2026-09-29T02:24:44.653342Z`, exactly matched the live
`Thermal_Model_JSON` generated at `2026-09-29T02:24:42.989315Z`. The
installed-v4 verifier accepted the matching v2 forcing capture: its output
SHA-256 was
`2fe39043ca28a4f44c8caacae46edb741923ed9cfb061f67839d107ec8551307`
and its embedded accepted-artifact SHA-256 was
`f7c85390f842d91685f88592c7b1e50c84805fd662d5fe7562261aa3eb881e17`.
This closes the first natural publisher-continuity gate after the row-prep
installation. The output remains `shadow`, low confidence, with no candidate;
the next natural trainer and all accuracy/action gates remain open.

## September 29 per-endpoint derivative finite check

A fresh deterministic 30-day fit profile spent 0.799 seconds in about
929,800 NumPy `all()` reductions, largely checking the two-by-twelve
sensitivity matrix after every five-minute forcing step. Nonfinite
derivatives propagate through the linear recurrence, so the source now
checks that matrix once at each endpoint while retaining scalar state checks
at every step. A direct regression forces derivative overflow with finite
state and confirms refusal. The same fixture's complete fitted-result digest
was identical before and after (`5801674fe8452ed81de5aef506cbb4863d545bae8bb0115b94210cceb333e401`);
one profiled fit fell from 5.662 to 4.424 seconds. This is a single-run
profile, not an asserted whole-trainer gain. All 726 thermal Python tests
passed, with one PostgreSQL-dependent skip. At this checkpoint the edit is
source-only; production's next natural trainer and artifact continuity
remain separate release gates.

At about 01:52 MDT, both thermal services were idle and both enabled timers
were briefly stopped. The one-entry receipt at
`/home/sat/.local/state/thermal-intel/deploy-receipts/sensitivity-endpoint-20260929T0151/files`
pinned installed preimage SHA-256
`90c21d0ba875461486f7cde0de8cbee62a090e166c63618b78fef7d866b7eafc`
and desired source SHA-256
`38144fe75042fe36a1a763c2803774cda547a9b903f89a9a8448b9eeb7419c2d`.
The existing atomic installer changed only `thermal_model/dynamics.py` and
verified its receipt. Both timers returned enabled and active; installed and
source hashes match. An installed-module 30-day synthetic fit reproduced the
same complete-result digest above. The next natural shadow publication and
trainer remain required runtime and whole-run performance gates. No artifact,
advice, Item, control or OpenHAB service was changed.

The first scheduled shadow service after this install ran at 02:25:29 MDT on
September 29 and exited 0 at 02:25:32. Its live `Thermal_Model_JSON`, latest
Item 610 JDBC row (persisted 08:25:32.138562Z), and verified private v2
forcing-capture output match exactly. The publication was generated at
08:25:30.467382Z under the accepted `53d96e5e9637` artifact and remains
`shadow` with low confidence and no candidate; `Thermal_Advisory` remained
`none|No thermal action needed`. This closes the one-file deployment's natural
publisher-continuity gate. The 06:50 natural trainer remains the first
whole-run CPU and accepted-artifact gate for this optimization.

## September 29 evening coefficient/Jacobian hoist — guarded shadow install

After the natural 06:50 run completed, a new bounded `cProfile` of one
deterministic 30-day synthetic fit found 3.421 of 4.298 profiled seconds in
the 61 multihorizon objective/gradient evaluations. The source-only
`dynamics.py` candidate now looks up the twelve fixed coefficients once per
evaluation and fills the three constant two-by-two Jacobian entries once per
endpoint; only the vent-dependent entry is updated at each five-minute step.
The arithmetic order of each state transition and derivative remains the
same. Two unprofiled pre-change fits took 3.335 and 3.295 seconds, and two
post-change fits took 2.990 and 2.991 seconds on the same 8,064-row fixture.
The complete dataclass JSON SHA-256 remained exactly
`e80023c12069181675e515389894fdbe732843587349a32ad693e8a92ca001bf`,
with final objective `0.0001582665101962629`. These are small-fixture
single-host timings, not a causal whole-trainer claim. All 61 dynamics and
139 adjacent pipeline/evaluation/behavior tests pass; `git diff --check`
passes. At this source-only checkpoint no installed runtime file, timer,
accepted artifact, live Item, advisory or control changed. The complete
28-file thermal Python suite later
passed 737 tests with one optional skip in 82.57 seconds. Source SHA-256 is
`2850ce20b4df5d39866dcead43f809c81b7501153af2f6d7377b9931e65a393c`;
the installed v4 `dynamics.py` was still the prior
`38144fe75042fe36a1a763c2803774cda547a9b903f89a9a8448b9eeb7419c2d`.
Both thermal timers were active/waiting.

At 19:15 MDT, with both thermal services inactive, the existing receipt-bound
installer took a private exact one-file rollback snapshot at
`/home/sat/.local/state/thermal-intel/deploy-receipts/dynamics-hoist-20260929T1915/files`.
It pinned the prior `38144fe...` hash and desired `2850ce...` hash, stopped
only the two thermal user timers, rechecked service quiescence and both hashes,
installed only `thermal_model/dynamics.py`, and verified its transaction
receipt and installed digest. A separate installed-v4 five-day synthetic fit
completed with finite, non-increasing objective. The timers were restarted;
independent readback found both enabled/active/waiting, both services inactive,
source and installed SHA-256 equal, receipt directory 0700 and manifest 0600.
An independent invocation of the receipt verifier returned true, and the
private backup bytes hash exactly to the pinned prior file. The next natural
shadow and trainer timers read back as 20:28:38 MDT tonight and 06:50 MDT
September 30 respectively.
No model artifact, live Item, advice, OpenHAB rule or control was changed.
The next natural shadow publication and September 30 06:50 trainer remain
the production import/whole-run performance and artifact-continuity gates;
this installation alone does not justify shadow exit.

The first later natural publisher started at 20:28:48 MDT September 29 and
exited zero at 20:28:51. Its live `Thermal_Model_JSON`, the JDBC row at
20:28:51.767 MDT, and the verified v2 forcing capture have identical output
digest `0452784bf09db7cd7eee3345e9a0a713b95e4f1cffe62cdc8d4be902386590a1`.
The installed/source dynamics hash remains `2850ce20...65a393c` and the
publication retains the same accepted artifact (`e707ce61...696ccff7`), 72
forecast points, shadow status and low confidence. The saved publication also
replayed exactly under the explicitly pinned installed runtime manifest
`1927d7e9...cb2747b`. This closes the optimization's first natural publisher
continuity gate. September 30 06:50 remains the whole-trainer performance and
accepted-artifact continuity check.

### September 30, 02:30 MDT natural publisher follow-through

The scheduled shadow service started at 02:30:19 MDT and exited zero at
02:30:23, using 2.165904 seconds CPU. Its decision time is
`2026-09-30T08:30:21.422307Z`; the live Item, one original JDBC row at
`2026-09-30T08:30:23.112Z`, and verified forcing capture
`20260930T083021Z-a1c10276a39f9e44.json.gz` have identical output SHA-256
`a1c10276a39f9e449e64a985667e96010b4a965a9617b400b58da76a726d1837`.
The full publication replays exactly under the explicitly pinned installed
runtime `fe044985ffb79b2ee911b67ceb67061c8f0b46fb8c849a08ca93bc8df5e51e27`.
The embedded accepted artifact remains
`e707ce61cac24571cc9d4280e54a400422f949f707cdc949481445de696ccff7`,
with training revision `00611a5e...`; the training and publication revisions
are deliberately not represented as identical. The output has 72 trajectory
points and remains shadow/low confidence. Verification was read-only: no job
was forced, input or label fabricated, runtime installed, or control activated.
The 06:50 natural trainer is still the whole-run performance and
accepted-artifact continuity gate; this successful repeated publication is
not graduation evidence.

## September 30 completed natural training

The existing scheduled process (PID 3673126) ran from 06:50:29 to 07:35:36
MDT and exited zero without a manual restart or duplicate. Its terminal
systemd counters and completion journal agree: 2,704.458959 seconds CPU
(45m 04s), 384,040,960-byte peak memory (366.25 MiB), and zero peak swap.
The September 29 run used 2,782.541918 seconds CPU; today's CPU use was about
2.8% lower. This is a measured whole-run observation, not a causal
optimization benchmark: samples increased from 99,830 to 99,849, scored
folds from 293 to 294, and fitted dynamics changed. Both runs have 378 folds.

The installed v4 validator accepts the new artifact and its backtest report;
their metrics agree exactly. Its training revision matches the full installed
runtime pin
`a4a68a173f7a3a9c206901b1c56bbc89f1ccaf8fc7ca7c04dbd1f627295f8b8a`.
Accepted file SHA-256 is
`904c76e964f9b7c103918cc24e993b4fc766db5a86a0da2af6ea334fb06a4e75`;
the canonical artifact identity used by captures is separately
`66bc754135da743f402e00c34e07d8ffaeb7c8e97061873e06808619fe734353`.
The prior artifact is retained and validates, with its unchanged canonical
identity `e707ce61...696ccff7`. Both user timers remain enabled and waiting.

This closes the optimization's natural whole-run resource, acceptance and
training-source continuity gates. It does not improve the unchanged 119-pair
24-hour air MAE of 2.178550°F versus persistence's 1.689895°F. Confirmed-action
training/evaluation rows remain zero; `promotion.shadow_only` is true and
operational graduation thresholds are unset. The provisional promotion gate
still tolerates a worse-than-persistence score and is not operational approval.
The first scheduled publication from the new artifact was subsequently verified
as recorded below; this does not change the shadow-only or accuracy gates.
See the [new private recovery point](2026-09-28-thermal-replay-recovery.md#september-30-post-training-source-and-artifact-recovery).

### First natural publication from the September 30 artifact

The scheduled shadow service ran at 08:30:48–08:30:51 MDT, exit zero. Its
decision clock is `2026-09-30T14:30:49.586807Z`. The live Item, exactly one
original Item 610 JDBC receipt and saved forcing capture
`20260930T143049Z-633ceb38d1e005b9.json.gz` have identical output SHA-256
`633ceb38d1e005b9cb21bd50bed1edb848c942bf1aeb30ab73c57a3bb6807c72`.
The capture's artifact equals the current accepted payload and validates;
its canonical identity is `66bc7541...734353` and its training revision equals
the installed `a4a68a17...` runtime pin. All 72 forecast points replay exactly
under that artifact-bound runtime without a source-revision override. Status
remains shadow with low confidence. No job was forced, receipt or action label
fabricated, or control changed. This closes natural new-artifact Item/JDBC/
capture/replay continuity, not scientific graduation. The earlier same-host
recovery archive predates this publication and does not contain this capture.

## September 30 fit-local rollout batching candidate

The daily training range is a **rolling 400-day lookback**: the default CLI
sets `end=now` and `start=end-400 days`. Each daily run shifts both endpoints
forward approximately one day; it does not advance by 400 days. Today's
accepted window is August 26, 2025–September 30, 2026, versus August 25,
2025–September 29, 2026 yesterday (with timer-clock jitter). Removing the
oldest day changes the chronological training prefixes. Reusing yesterday's
fold fit without verifying those inputs would not preserve the current fit.
This candidate therefore retains the window and every chronological refit.

Independent endpoint rollouts within each of the five identification horizons
are now evaluated together with NumPy arrays. Forcings, origins, targets and
confidence are prepared once per fit into read-only arrays; there is no global
object-identity cache or reuse between daily runs. Existing bounded selection
still allows at most 64 origins per horizon. State equations, forcing-step
order, Jacobian/sensitivity arithmetic, endpoint/state loss accumulation order,
optimizer, coefficient constraints and rank/acceptance gates are unchanged.
The deliberately scalar final reductions preserve floating-point rounding.

Two interleaved 30-day synthetic fits (8,064 training rows, seed 20260930,
single-threaded BLAS/OpenMP) took 3.161/3.261 seconds using the committed scalar
implementation and 0.899/0.911 seconds using the source candidate. All four
complete fitted-result digests equal
`754def4eb21d19a31f2e3ab894b40ea8f356843286517c5ba8b54fc58b3da091`;
the final objective is `0.00016668050842605494`. This is approximately a
3.5× isolated-fit speedup, **not a measured whole daily-run improvement**.
A separate sensitivity scratch-buffer experiment was slightly slower despite
exact fit parity and was rejected. No packages were installed.

New regressions compare exact loss, gradient and sensitivity rows against a
frozen pre-change scalar oracle across randomized coefficient perturbations,
prepared/unprepared forcings and zero/fractional/full confidence. They check
that read-only prepared arrays remain unchanged, mutable inputs are not cached
by identity, and the complete fitted result remains identical.
The final full thermal Python suite passed **889 tests**, with one optional
PostgreSQL integration skip, in 89.91 seconds. Owned test directories and the
experimental prototype were removed after the runs completed.

At the initial candidate checkpoint it was **source-only**. Installed v4 had SHA-256
`2850ce20b4df5d39866dcead43f809c81b7501153af2f6d7377b9931e65a393c`
and differs from repository source because separate airflow work remains
uninstalled. Do not copy the whole source file into production. Deployment
requires an exact v4-compatible backport, idle services, a guarded one-file
transaction with pinned preimage/rollback receipt, installed-fit parity,
timer recovery, and subsequent natural publication/training qualification.
No production file, model artifact, schedule, confirmation label or control
was changed by these experiments.

### Guarded v4-compatible deployment

The backport starts from that exact installed preimage and replaces only
`_multihorizon_objective_and_gradient` and `_refine_multihorizon`, adding
`_prepare_multihorizon_batches`. An AST comparison proves the remainder of
the installed module unchanged; no uninstalled split-airflow or solar-fitting
behavior was copied from repository source. The compatible candidate hash is
`3b50fec19289ed09fbc2a507f0b5747e7906d427ae009e596835d8b54ecd87ce`.
Against the installed v4 schema/import tree, all 26 selected multihorizon/
batching regressions passed. A separate complete 8,064-row fit matched the
prior digest exactly (3.042 seconds before, 0.866 seconds for the backport).

With both services inactive and both enabled timers active, the installer
took a private one-file rollback receipt at
`/home/sat/.local/state/thermal-intel/deploy-receipts/dynamics-batch-20260930T1015/files`.
It stopped only the two thermal user timers, rechecked service quiescence and
source/target hashes, atomically installed that one compatible file, verified
the receipt and reproduced the exact complete fit from installed imports.
Both timers were restored active/enabled; `timers-enabled` passed. Independent
receipt verification passed and the private rollback bytes retain the exact
`2850ce20...` preimage. The compatible desired source is deliberately retained
inside the private receipt parent for reproducible transaction verification.
Temporary test bytecode was removed. No OpenHAB restart or control change.

The full installed runtime revision is now
`8b528a34fa4641061018b2d039117c0cb85789abe4f427855b5669be1a011fc5`.
The accepted model remains at its original `a4a68a17...` training revision;
no artifact was refitted or relabelled. The next natural shadow publication
must prove Item/JDBC/capture/as-issued replay continuity under the explicit
new runtime pin. October 1's daily trainer is the full-run resource and
accepted-artifact gate. Shadow exit and forecast skill remain separately open.

Pre-install training-bound recovery archive
`/home/sat/backups/earthship-energy/thermal-pre-batch-20260930T1615Z-a4a68a17.tar.gz`
verified with 109 members/83 captures and SHA-256
`f219afedd47061273c7f7eeb173b01cf75b8f38916e0b967e6a420440df89891`.
The post-install explicit-publication-runtime archive
`/home/sat/backups/earthship-energy/thermal-publication-runtime-20260930T1618Z-8b528a34.tar.gz`
verified with the same member/capture counts and SHA-256
`941e2ba79694d5ee59ef4afef6e0b1f2ec4e7cc59c0c60eb4783084773c894a0`.
It preserves distinct training/publication bindings; it does not claim those
older captures were generated under the new revision. These archives passed
inventory/digest verification, not a new independent full-restore rehearsal.

### First natural post-batching publication

The scheduled shadow service ran at 10:31:48–10:31:51 MDT, exit zero, using
2.167665 seconds CPU. Its decision time is `2026-09-30T16:31:50.189895Z`.
The live Item, exactly one original JDBC row at `16:31:51.896Z`, and verified
capture `20260930T163150Z-40f98cb893678739.json.gz` agree exactly, with output
SHA-256 `40f98cb893678739eea68daca7684e6df3c52cb95ab27e5d30b51d030050dc72`.
The captured artifact equals the accepted payload (`66bc7541...734353`),
retains training revision `a4a68a17...`, and all 72 points replay exactly under
the explicitly pinned installed `8b528a34...` publication runtime. Status
remains shadow, confidence low. This closes batching's first natural
publication gate, not October 1's whole-trainer resource/acceptance gate.
No job was forced or action label fabricated.

The later morning-trough DM retirement changes only the notification policy
in `forecast_intel.py`, which participates in the thermal runtime manifest.
Current revision is therefore `0864f4d6...`; the same captured publication
also replays exactly under that explicit pin. This is a compatibility check,
not a natural publication generated under the newer revision. The pre-change
private archive `thermal-publication-runtime-20260930-pre-morning-dm-retire-8b528a34.tar.gz`
includes the new 10:31 capture: 110 members/84 captures, SHA-256
`58f74d8f1df333b5747f837c364fc352108ba85468012c94719e3dd417885cc8`.
The corresponding current-runtime archive
`thermal-publication-runtime-20260930-post-morning-dm-retire-0864f4d6.tar.gz`
has the same inventory and SHA-256
`5f31b57de220a22f81f695d58d1c178ee2dbe229138f47f214fb456716f53aec`.
Both are under `/home/sat/backups/earthship-energy/`, private and verified;
training/publication identities remain explicitly distinct.

## October 1 completed natural batched training

The first full natural trainer after the fit-local batching backport started
06:50:29 MDT and ended 07:10:05 MDT, exit zero, without a restart or duplicate.
The same invocation `4139b15428954166b6bd3fcd5ea4ef20` completed; original PID
914042 is now zero, unit inactive/dead, Result success. Resource counters:
1,173.674619 seconds CPU, 383,791,104 bytes peak memory (366.01 MiB), and zero
peak swap. Elapsed time was 19m36s versus September 30's 45m07s, about 57%
lower; CPU was about 56.6% lower. This is one natural whole-run measurement,
not a controlled identical-input benchmark or a guarantee for future days.

The original invocation journal reports `promoted`, trained through
`2026-10-01T12:50:29.152333Z`, with training revision matching the complete
installed runtime pin
`7f57eb3f00dcc13e09958d6200d99e0ff172be48c5659ad660de22e90bd19095`.
Read-only validation using installed pure decoders/validators independently
accepts both accepted.json and candidate.json with require_eligible=True;
their identical file SHA-256 is
`a2a0a8f26c567ae9dcef57aba0671485d8d6cc8edf0dfa922edd8370dd146e09`.
previous.json still validates and retains the exact September 30 file digest
`904c76e964f9b7c103918cc24e993b4fc766db5a86a0da2af6ea334fb06a4e75`.
The backtest report validates independently, its metrics equal the accepted
artifact's exactly, and its SHA-256 is
`d6ca964e028b60e194c5ae5e95f6b1d09e89171af431b76549f4a673c0fe0089`.
No quarantine/restoration or ArtifactRegistry mutating load was invoked.

This closes batching's first natural whole-run resource/acceptance/source
identity gate. The artifact still declares promotion.shadow_only=true and
graduation_thresholds=null. Thermal operational graduation, confirmed-action
evidence and first subsequent new-artifact natural publication qualification
remain separate; no control was activated and no physical state was relabelled.
The new run has 99,855 samples, 377 folds and 295 scored folds. Its 119-pair
24-hour air MAE remains 2.178550°F versus persistence's 1.689895°F; confirmed
action training/evaluation counts remain zero. The provisional promotion gate
must not be interpreted as evidence of beating persistence operationally.

### October 1 first natural new-artifact publication

The subsequent natural shadow invocation
`9013bf07fdb94cf79228b628f45c0ba2` ran at 09:05:29–09:05:31 MDT, exit zero,
Result success, and is now inactive/dead. It was not manually invoked or
restarted. Its decision timestamp is `2026-10-01T15:05:30.159006+00:00`.
Live `Thermal_Model_JSON`, local `shadow.json` and the verified original
forcing capture match exactly. Output SHA-256:
`25496c123c0be79f021e4858fb6dfe93f04cf106fdbb07dd2a594c6e1994de89`.
The private retained capture is
`/home/sat/.local/state/thermal-intel/forcing-captures/2026-10/20261001T150530Z-25496c123c0be79f.json.gz`.

The embedded artifact equals the current accepted artifact, whose file digest
remains `a2a0a8f26c567ae9dcef57aba0671485d8d6cc8edf0dfa922edd8370dd146e09`.
The original JDBC qualification found the unique Item 610 mapping and exactly
one matching receipt in the bounded publication window, at
`2026-10-01T15:05:31.846160+00:00`. A repeated read-only exact replay under the
full installed `7f57eb3f00dcc13e09958d6200d99e0ff172be48c5659ad660de22e90bd19095`
pin reports `exact_as_issued=true` and
`training_revision_matches_runtime=true`. The installed `thermal_intel.py`
digest is `8d7873a0b37dc252cdc2fb59175a18952df229e69505402d28ec40e2bb88fcc2`.

This closes the first natural publication/source/artifact continuity gate
following today's training. Status remains shadow and confidence low. No
confirmed action, accuracy graduation, collector activation or control change
is implied. The chronological skill and actual action-observation gates remain
open.
