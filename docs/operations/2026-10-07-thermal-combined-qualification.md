# Combined thermal forecast qualification

`thermal_graduation_decision.qualify_candidate` recomputes seven forecast gates:
preregistered policy, frozen candidate, retained runtime, qualified raw training
sources, original source/outcome pairs, measured fit and predictive skill.
Every gate must pass before the report recommends `forecast_active`.
Structural failures recommend `unavailable`; valid structural evidence with
insufficient predictive skill remains `shadow`.

The evaluator reads the immutable source-backed registration, checks the exact
candidate artifact and dates, and verifies the retained runtime against the
frozen policy. It reads the actual artifact-bound fit proof and requires its
measured gates and active parameter count to match the candidate.

Training qualification accepts `earthship-thermal-training-sources/v1` with
exact canonical `samples` and complete `temperature_grids` for air, north wall
and outdoor. It verifies the artifact's canonical training-input hash, every
five-minute native target, original receipt/storage/expiry clocks, original
source-grid hashes and frozen hardware epochs. Missing receipts remain barriers.
Every retained sample's air/outdoor/raw north-wall values must match its native
receipt, and its mass state must reproduce the original causal observer.
Pre-cutover legacy training is explicitly refused as receipt-qualified evidence.
Other forcing/action inputs retain the existing artifact provenance contracts;
this temperature check does not claim confirmed causal action evidence.

Each evaluation packet retains the original archive path, persisted publication,
horizon, native outcome and seven-cycle receipt grid. The evaluator verifies the
exact original publication and recomputes errors. It refuses mixed artifact,
runtime or epoch identities, missing original hourly weather, malformed fields
and forcing that does not cover the actual trajectory. Native origin/outcome
validation and deterministic independent-window/day statistics remain separate
from weather-field and numerical-fit validation.

The report retains the complete preregistered policy and every numerical
threshold, frozen candidate/intervals/runtime, training source assessment, fit
measurements, independent horizon/regime statistics and original source hashes.
Its stage derives from the gates. A changed stage/pass flag, even with a new
outer checksum, cannot override failed gates. Reports are review caches;
production must recompute qualification from the raw references before cutover.
A report checksum alone is not an activation authority.

Action advice remains withheld in this first combined evaluator. A separate
confirmed-action comparative-outcome evaluator is still required before
`advisory_active` can be recommended. Missing action advice does not suppress
an otherwise qualified Stage A forecast. Automatic actuation is always disabled.

The read-only command is:

```sh
"$qualified_python" scripts/qualify-thermal-graduation.py \
  --registration "$private_registration" --artifact "$private_artifact" \
  --fit-evidence "$private_fit_proof" --training-sources "$private_training_sources" \
  --runtime-bundle "$private_runtime_bundle" --pairs "$private_original_pairs" \
  --report-directory "$private_report_directory"
```

Input files must be owned 0600 regular files in private 0700 directories.
The report directory must already be owned 0700. JSON and Markdown reports are
immutable, content-addressed 0600 files containing the same decision. Exit 0
means forecast gates passed, 1 means a closed gate report, and 2 means input or
report storage was refused. This command fits no model and invokes no household
API. It uses the actual assessment clock and has no manual activation option.

The current real model has not passed this evaluator. The explicit off-host qualification training path now retains complete native
training snapshots as described in `2026-10-07-thermal-training-snapshot.md`.
Compatible natural publication capture remains disabled on the installed v4 pair. Fully
assembled real candidate qualification, action-response qualification, version 2
publication/UI and rollback remain open. Synthetic fixtures establish software
behavior and are never release evidence.

Local verification passed 71 focused decision/source/policy/statistics tests in
one low-priority scope limited to 25% CPU, 768 MiB RAM, zero swap and 48 tasks.
Full suites run in hosted CI; no local fitting, service change or deployment ran.
