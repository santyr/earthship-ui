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
Actual package/report reconstruction and activation remain pending.
