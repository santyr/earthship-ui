# Preserve original model admission across deployment changes

After increasing scoring CPU, the normal 20:41 UTC run persisted a valid native
one-hour source score and completion for model `52dd5d12...526506`. Report
reconciliation then failed at `native_model_serving_receipt.py:229`: the latest
deployment's model-verification receipt was issued after the 19:15 forecast.
The model artifact was unchanged, but each deployment had unnecessarily minted
a new admission receipt. Report validation correctly refused that chronology.

Packaging now searches only the explicitly pinned current/historical stages for
an admission of the exact candidate. Each matching stage, candidate, original
evidence and receipt is freshly verified through the existing owned-selection
reader. The earliest verified receipt and its original candidate file are reused.
A different candidate or runtime cannot reuse that admission; a new model still
gets a new candidate and receipt. No numerical code, chronology check, evidence
validation, model identity, or actuator authority is relaxed.

Forty-four admission, candidate-identity, receipt, scheduling and upgrade tests
passed in 17.27 seconds. The three new regressions failed before implementation.
The original production report was reconciled offline in 5.449 seconds, then the unchanged model was activated as recorded below.

Deployment `0c2d2549` from source `fe597bb` reused the original 19:08:13 UTC
admission, retained the same model, and passed effective service/timer readback.
The 20:51 production invocation persisted a second one-hour completion and wrote
a valid current-model report: n=2, model MAE 0.156463 F, persistence MAE 0.27 F.
Its final consistency check nevertheless returned a reader deadline error after
the report was written. Acquisition had already finished; the base reader was
incorrectly applying its 50-second read budget to later offline verification.

The current batch reader now enforces that unchanged 50-second deadline before
and after acquisition checks. Post-acquisition verification still hashes all
original private configuration and runs the existing full-job guard, without
reusing the read timer. The 120-second job and 130-second service limits remain.
Two regressions failed before this correction; 58 reader/query/batching/scoring,
deadline and scheduling tests passed in 5.32 seconds. Deployment `715078d7`
from `cbec265` passed effective readback and retains the original admission.

The natural 21:01 UTC invocation `1aeb5e9dcdff4545b8410d958be49c1f`
finished at 21:02:05 with exit 0: one newly scored forecast and three current-model
outcomes in total. It used 62.244 CPU seconds, 97.2 MiB peak RAM and no swap.
The report assessed at 21:01:27 UTC has one-hour MAE 0.110915 F versus
0.30 F persistence. These three overlapping observations do not establish model
superiority or graduation; longer horizons remain unscored.

The 20:55 UTC live OpenHAB publication and deployed UI parser already displayed
the preceding two-outcome report as ready/provisional. The daily production
checkout is clean at `cbec265`; the next natural daily fit remains unverified.


At 21:05 UTC the normal forecast publication included all three outcomes, and
the deployed UI parser returned ready/provisional with 0.11 F model MAE and
0.30 F persistence MAE. The subsequent callback-only release `2fbad86` retains
the same model and original admission; its effective deployment is recorded
in the scoring CPU document.
