# Measured thermal fit evidence

`earthship-thermal-fit-evidence/v1` binds measured numerical evidence to the
exact existing v5 candidate artifact and its canonical training-input digest.
It supplies no forecast release or action-advice authority. Qualified raw
training sources remain necessary; this wrapper does not qualify them.

The existing default fitter keeps its numerical path and initializer block
stability checks. An explicit `collect_graduation_evidence=True` request adds:

- measured condition numbers and dimensions from the actual normalized design and sensitivity checks;
- a full-rank, normalized conditioning check at the final optimized coefficients;
- deterministic independent-day block refits of the complete optimized model;
- every omitted local day and the actual refitted coefficient vector.

The independent-day floor, four deterministic blocks, normalized condition limit
and maximum movement of 0.25 of each declared physical coefficient span remain
unchanged. Short histories report insufficient support. Relaxed evaluation-only
fits cannot supply this strict proof. Measurement context resets after success
or refusal and cannot leak into a later default fit.

The wrapper checks the artifact, source-selection dimensions and optimizer
metrics, verifies deterministic omitted-day assignment within the training
interval, and recomputes coefficient movement from the stored vectors. It derives
its numerical gates rather than accepting supplied pass flags. Exact JSON types,
finite values, original limits and artifact identity are validated. A numerical
fit pass does not require or claim legacy shadow-forecast promotion; prediction
skill and release eligibility remain separate gates.

Fit evidence lives outside the exact legacy artifact schema. Owned 0700 storage
and immutable 0600 files retain the complete measured proof. Identical writes are
idempotent, conflicting evidence cannot overwrite an artifact's proof, and reads
require the bound artifact. The wrapper always states `release_authorized: false`.

`run_training(..., fit_evidence_writer=writer)` explicitly requests measurement
and persists the proof before saving or promoting the shadow candidate. A proof
write failure refuses that candidate operation and preserves the previous one.
Default training supplies no writer and changes no publication semantics.

On isolated qualification compute, the optional CLI path is:

```sh
"$qualified_python" openhab/scripts/thermal_intel.py train \
  --start "$training_start" --end "$training_end" \
  --state-dir "$private_model_dir" --fit-evidence-dir "$private_fit_dir"
```

Use the existing approved read-only source configuration and an already owned
0700 proof directory. This command performs additional model fitting and must
not run manually on the household host. No installed trainer, schedule or
production service has been changed or invoked by this implementation.

Local verification uses tiny matrix checks and controlled optimizer boundaries
in a single scope limited to 25% CPU, 768 MiB RAM, zero swap, 48 tasks and low
priority. The full synthetic qualification optimizer/refit test runs only in
hosted CI, enabled there by `EARTHSHIP_REMOTE_QUALIFICATION_FIT=1`; local checks
set that flag to 0. Synthetic tests establish software behavior, not evidence
that the real Earthship model qualifies. No genuine current-model fit proof has
been produced, and production activation remains closed.
