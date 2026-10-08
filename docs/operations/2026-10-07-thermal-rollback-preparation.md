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

## Recheck prepared recovery files

The preparation command accepts `--verify-only` with the same snapshot,
destination and reason. This reads existing recovery files without modifying
them. `verify_prepared_restore` checks the exact source tree, private ownership
and modes, retained hashes, model registry and historical output against the
original snapshot. It checks the executing environment again. Extra files,
changed bytes, symlinks and attempts to turn preparation flags into installation
or cold-qualification claims are refused.

Compatible staged versions of `thermal_intel.py` now accept `--model-directory`
for `shadow` and `release`. The default registry remains the existing one.
An isolated recovery preview can explicitly select its prepared model registry:

```text
PYTHONDONTWRITEBYTECODE=1 python /private/recovery/runtime/thermal_intel.py shadow \
  --model-directory /private/recovery/models \
  --output /private/recovery-checks/fresh-shadow.json
```

Run that only after the cold-runtime/dependency/journal gates are satisfied for
the retained generation. Earlier retained runtimes, including the installed v4
runtime, may lack this option and need their compatible guarded launcher.
Selecting a registry cannot bypass source-backed qualification on the release
command. Nothing here invokes a live preview or publication automatically.

Keep fresh outputs outside the retained generation and disable bytecode writes in
its source tree. The normal private empty `.registry.lock` produced by an
accepted-model read is allowed; other additional registry files still refuse
verification. Prepared generation verification is a byte/identity check, not a
replacement for the cold runtime/journal and natural-publication gates.

The separate [cold-reader check](2026-10-07-thermal-cold-reader.md) now rehearses
the prior v4 artifact/publication through its own retained reader. That reader
component has a real private rehearsal; the snapshot API and full environment,
journal and install integration remain incomplete.

[Dependency-byte retention](2026-10-07-thermal-environment-retention.md) now
streams a reviewed explicit file inventory into immutable blobs. Complete
retention, relocation and recovery integration remain required; host-specific
inventory evidence stays in private staging.

## Preserve a legacy v4 generation

`thermal_model.legacy_recovery.prepare_legacy_generation` separately preserves
original v4 artifact and available v1 publication bytes with their original
source closure. It requires explicit ordered revision paths, interpreter and
native bindings, retained source/environment archive references and a rollback
reason. It creates a new private generation atomically without replacing an
existing destination. `verify_legacy_generation` checks the generation and all
referenced archives again. The archives remain required recovery inputs; the
generation does not duplicate the full dependency archives.

This is a preservation contract, not a legacy numerical eligibility decision.
Artifact-reader, cold-runtime, restored-journal, installation and automatic
actuation flags stay false. Qualification must use the original pinned reader;
v5 decoding and the existing v1 snapshot reader remain separate contracts.
Historical output remains evidence and must never be published as current.

Both functions accept `max_read_bytes_per_second`. Archive reads and source
copies share a pacer; artifact, output and generation-manifest reads reserve
their full bounded maximum before I/O. Small documents therefore also incur
conservative pacing. Environment mapping type, count and labels are checked
before archive reads. Continue using serial resource caps and private staging.
This component does not provide guarded installation or schedule reconciliation.
