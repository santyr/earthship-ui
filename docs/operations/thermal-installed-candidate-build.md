# Offline installed-shade candidate build

`openhab/scripts/thermal_installed_train.py` connects an original frozen native-v2
training snapshot to the installed-outdoor-shade fitter and immutable candidate
writer. It creates a development candidate, with no release authority. It does
not acquire household inputs, select a live registry, publish telemetry, or
activate forecasts. Use the separate qualification and publication contracts
for subsequent calibration, preregistration and release assessment.

Default invocation validates the small private configuration and path metadata.
It does not read the original snapshot or import numerical fitting modules:

```sh
python3 /absolute/pinned/sources/thermal_installed_train.py --config /absolute/private/training-config.json
```

The closed configuration uses `schema` equal to
`earthship-installed-shade-training-config/v1`, and exactly these other fields:

| Field | Required value |
| --- | --- |
| `snapshot_path` | Absolute original native-v2 training-input file |
| `snapshot_sha256` | Original snapshot's declared SHA256 |
| `runtime_bundle_path` | Immutable compatible publication runtime bundle directory |
| `runtime_sha256` | Canonical original runtime binding SHA256 |
| `code_revision` | Runtime binding's SHA256 code revision, not a raw Git SHA |
| `sensor_epochs` | Explicit canonical hardware UUIDs for `air`, `mass`, `outdoor` |
| `training_start`, `training_end` | Aware timestamps defining the exclusive training interval |
| `initial_coefficients` | Ten finite coefficients chosen from training/development evidence only |
| `output_directory` | Existing owned private output directory |
| `shared_lock` | Existing global lock used by native input consumers |

File operands and configuration must be owned mode 0600, regular, single-link
files with resolved absolute paths. Directories must be owned mode 0700. The
configuration is capped at 16 KiB; duplicate fields, nonfinite values and extra
fields are refused. The loader opens without following symlinks and verifies
identity and stability during the bounded read. The default check does not
establish that the original snapshot or runtime bundle qualifies.

For explicit fitting, use a pinned source tree containing this worker and the
complete original publication closure. The original runtime bundle must match
those actual source bytes, interpreter and numerical dependency versions. The
worker retains its own exact source bytes in the private build receipt.

Run only one bounded workload. This example is one shell command; replace its
absolute operands with the reviewed private generation and configuration:

```sh
systemd-run --user --scope -p CPUQuota=20% -p MemoryMax=256M -p MemorySwapMax=0 -p TasksMax=24 -p IOWeight=10 nice -n 15 ionice -c 3 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 timeout 90s python3 /absolute/pinned/sources/thermal_installed_train.py --config /absolute/private/training-config.json --fit
```

Fitting refuses missing caps, scheduling/thread constraints, or the existing
conservative training headroom requirement: at least 3 GiB available RAM and at
most 128 MiB used swap. The publication reader's smaller headroom allowance does
not authorize this workload. The existing global consumer lock is held across
original reads, fitting, proof construction, persistence and readback. Lock
contention returns exit 75; it is not a successful build.

One 85-second monotonic budget covers the stages. Each numerical API receives
only the remaining budget; the outer command still has a 90-second hard timeout.
Fitting intent is temporarily enabled and restored on exit. Original snapshot,
phase, cutoff, physical, exact rank, normalized conditioning, required horizons
and deterministic independent-day stability gates remain enforced. Insufficient
stability or failed fit gates prevents candidate persistence.

A successful result has `status=development_candidate`, `fit_executed=true`,
`release_authorized=false`, and original candidate/build-receipt paths. The
candidate is written last after original source and numerical evidence, then
read back through the typed validator. The content-addressed mode-0600 receipt
uses `earthship-installed-shade-build-receipt/v1` and retains invocation clocks,
original identities, training cutoffs, phases, and both builder source files.
It explicitly reports `production_installed=false`. A receipt proves the
recorded build invocation; it does not prove predictive skill or release readiness.

A withheld result carries no accepted build claim. If failure occurs after
numerical dispatch, `fit_executed` is null because partial work may have run.
Partial immutable files can remain after a deadline or later validation failure;
their existence does not authorize bootstrap or release. Require a successful
result, exact immutable receipt, and the candidate's source/numerical readback.

Do not start a household build merely to test this command. First accumulate
sufficient qualified original training windows and independent days. Freeze the
valid uncalibrated candidate before genuine shadow collection for calibration;
freeze the calibrated candidate and preregister thresholds before inspecting
its untouched release holdout. Existing baseline and prospective release gates
remain required. Synthetic orchestration tests and source fixtures are not
household fit or graduation evidence.
