# Thermal endpoint-selector efficiency — September 27

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
