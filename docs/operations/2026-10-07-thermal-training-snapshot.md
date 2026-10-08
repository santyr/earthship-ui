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

## Capture inputs before fitting

`thermal_model.training_inputs.capture_training_inputs` separates read-only input
collection from optimization. It takes an explicitly retaining native temperature
reader, journal reader, interval, capture clock and collection revision callback.
It preserves all original measurement series, journal event fields, native grids
and the dataset manifest in `earthship-thermal-training-inputs/v1`. No registry,
fitter, publisher or actuator is accepted by this API. A reader that has not
explicitly enabled native-grid retention refuses before source reads.

Nonfinite measurement values become explicit null invalid barriers; UTC timestamp
normalization is declared in the contract. Missing native receipts remain missing.
Historical reconstruction labels and confidence are preserved, and legacy points
before the cutover retain their legacy classification. Capture does not qualify
such points for a native-only release.

`write_training_inputs` publishes an owned private content-addressed file atomically
without replacing an existing path. Matching retries are idempotent; changed or
exposed files refuse. `read_training_inputs` verifies the closed schema, private
ownership, digest and address. `restore_training_inputs` reconstructs the dataset
using the existing builder, verifies its manifest and native-grid hashes, and
requires every post-cutover raw temperature to match its original receipt or
missing barrier. Rehashing a changed dataset cannot repair that binding.

Capture and restore share an interval cap of 20,000 five-minute steps, checked
before source I/O or dataset expansion. Series points are bounded at 120,000 total,
journal events at 10,000 per event kind and serialized snapshots at 32 MB. Restored
readers serve only the exact frozen interval and known Items. Fitting, installation
and release-authority flags remain false.

This is a library component for private off-host preparation. The operational
capture command and offline fitting integration remain unfinished. Supplied
backends still need their own query deadlines and read pacing before live use.
Continue the serial CPU/memory/task scope; no live capture or local optimizer was
invoked here. Household snapshots remain private and require an explicitly
identified destination before transfer. The existing post-fit source contract,
artifact validation and numerical qualification gates remain unchanged.
