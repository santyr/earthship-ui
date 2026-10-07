# Original raw thermal training snapshots

The explicit off-host `train --fit-evidence-dir` path now retains both the
measured numerical proof and the original training snapshot. Default training
retains its existing values, artifact schema and memory behavior.

`QualifiedTemperatureHistory(..., retain_raw=True)` retains each fully validated
native temperature grid as read, including original receipt/storage/expiry
clocks, hardware epochs, snapshot hashes and missing targets. The accessor
requires all three roles and returns a detached copy. Retention is bounded by
64 MB of encoded original receipt data and does not relabel pre-cutover legacy
points. Requesting retention without qualified native-reader configuration
refuses before fitting.

`earthship-thermal-training-sources/v1` holds the exact canonical sample table
used by the fitter, its original radiation provenance, and the retained air,
north-wall and outdoor receipt grids. Its sample hash and every source-grid hash
must match the candidate artifact's manifest. It preserves raw north-wall values
alongside causal latent mass and keeps missing receipts as barriers.

The source snapshot is stored as a private immutable 0600 file in the existing
owned 0700 proof directory, addressed by the complete training manifest digest.
Readers require the bound manifest, exact schema, finite JSON and private storage.
Identical retries are idempotent; changed data cannot overwrite the original.

The qualification pipeline writes raw sources before the measured fit proof and
before candidate save/promotion. A source write failure preserves the previous
candidate. This does not authorize production: the combined evaluator still
recomputes receipt qualification, frozen epochs, causal mass, fit measurements,
independent forecast errors and every preregistered threshold. Legacy source rows
may be retained honestly, but remain ineligible for the native-only release gate.

The existing off-host command needs no additional source flag:

```sh
"$qualified_python" openhab/scripts/thermal_intel.py train \
  --start "$training_start" --end "$training_end" \
  --state-dir "$private_model_dir" --fit-evidence-dir "$private_fit_dir"
```

Use the existing approved read-only qualified-source configuration. This command
performs additional fitting and must not be run manually on the household host.
It has not been invoked against production here. Current installed v4 sources and
services remain unchanged. A genuine frozen candidate and untouched/prospective
release evidence are still required; no actual graduation claim is made.

Verification: 68 focused source retention/storage/pipeline/decision tests pass,
including a retained snapshot checked by the actual combined source verifier.
Local checks ran alone with 25% CPU, 768 MiB RAM, zero swap, 48 tasks and low
priority. Full suites run in hosted CI.
