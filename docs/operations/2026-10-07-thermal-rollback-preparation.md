# Thermal shadow recovery preparation

This is a source implementation of immutable recovery retention and private
recovery-file preparation. It does not install files, change a schedule, publish
historical output, restart a service or operate household equipment. A production
cutover still requires the full rollback inventory and cold rehearsal described
below.

`thermal_model.rollback.retain_snapshot` retains the previous eligible artifact,
its exact available v1 shadow publication and the complete verified runtime
bundle. The artifact must match that publication's model identity and dates.
Every source and interpreter byte remains bound by the runtime manifest. Snapshot
metadata binds the artifact, output, runtime and actual capture clock. Private
files and directories are required; corrupt, extra or exposed files are refused.
Copies and directory entries are synced before atomic publication.

`prepare_restore` requires an explicit reason: baseline regression, calibration
failure, sensor epoch change, artifact corruption, model instability, publication
failure or operator rollback. It checks the currently executing interpreter hash,
Python version and loaded numerical dependency versions against the retained
runtime. A changed environment refuses recovery preparation. It copies sources
and the accepted artifact into a new private recovery generation, retains the
historical publication and records the reason and snapshot identity. Existing
paths are never replaced, and interrupted copies expose no partial generation.
Linux atomic no-replacement rename is required.

The deterministic preparation command is:

```text
python scripts/rollback-thermal-release.py \
  --snapshot /private/snapshots/SNAPSHOT_SHA256 \
  --destination /private/new-recovery-generation \
  --reason baseline_regression
```

Run it only under the established serial, low-priority CPU/memory/task scope.
Success means recovery files were prepared. The receipt explicitly says
`installed: false`, `cold_runtime_qualified: false` and
`dependency_environment_retained: false`; it grants no production eligibility.
Never republish `last-shadow.json` as a fresh prediction. Fresh shadow output must
be computed with qualified current inputs after a compatible guarded installation.
Existing household safety alerts remain independent.

The current snapshot reader understands the repository's exact v5 artifact
contract. It cannot validate or relabel the installed legacy v4 artifact. Before
any production transition, preserve and cold-qualify that complete prior v4
runtime/artifact/environment through its compatible reader. A compatible v5
snapshot does not replace that obligation.

Remaining rollback work before cutover includes retaining the complete dependency
and native-library environment, cold runtime and restored-journal verification,
matching the recovered model registry path, guarded installation and schedule
reconciliation, active-to-shadow UI withdrawal and natural fresh shadow
publication verification. Prospective regression and calibration signals must
feed withdrawal independently of capture caches. None of those gates is closed
by this preparation component alone.
