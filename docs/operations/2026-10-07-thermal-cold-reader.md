# Cold validation of the retained thermal artifact reader

`verify-thermal-cold-reader.py` validates a retained artifact/publication pair
using that generation's own reader in a fresh process. It supports explicitly
pinned v4 and v5 source contracts; it does not relabel an artifact. It executes
reader imports and validation only, never the application entrypoint, trainer,
publisher or journal commands.

The private profile is `earthship-thermal-cold-reader/v1` with exact fields:
`schema`, `runtime`, `sources`, `artifact_schema`, `interpreter_sha256`, `artifact`
and `output`. `sources` maps relative Python filenames to complete SHA-256 hashes.
The two input entries contain absolute `path` and `sha256` fields. Sources and
inputs require owned 0600 files and 0700 directories. The source tree must match
the declared members exactly. The executing interpreter must match its pin and
have safe ownership/permissions. Changed bytes, schema mismatch, extra files,
symlinks, non-finite/duplicate JSON and warm thermal imports refuse the check.

Invoke the checker in a fresh compatible process with bytecode writes disabled,
under the established serial resource limits:

```text
PYTHONDONTWRITEBYTECODE=1 python scripts/verify-thermal-cold-reader.py \
  --profile /private/cold-reader/profile.json
```

The worker checks all pins before importing the retained readers, verifies the
reader's declared schema, validates the artifact's existing eligibility contract
and its exact available v1 shadow publication, then checks pins again. Python
socket connections and the PostgreSQL connection entrypoint are disabled during
validation. This is an offline check of approved retained source, not a general
sandbox for arbitrary code. Select known retained sources; a hash alone is not an
approval of unrelated code.

The receipt records the interpreter, source manifest, artifact/output identities,
actual dependency versions and original artifact schema. It reports
`cold_artifact_reader_verified: true` only after successful validation.
`journal_qualified`, `dependency_environment_retained`, `production_qualified`
and `automatic_actuation` remain false. No caller can set them through the profile.

A real private rehearsal copied the installed v4 source closure plus its forcing
capture helper, rechecked those bytes against the installation, and selected an
already-issued original v4 capture. In a fresh offline process its own reader
validated artifact `f5b7d75322911cd63bc8274f671f1e379d3f46707d7b30e41f8c6e605dbeb7f2`
and the captured publication. The v4 schema was preserved. No live Item update,
service change, fitting or journal/database request occurred. The copied sources,
private profile and receipt are retained in the ignored development staging area.

This closes the artifact-reader compatibility rehearsal component. Complete prior
dependency/native-library retention, restored-journal qualification, guarded
installation, schedule reconciliation and natural fresh shadow publication remain
necessary for full rollback. The current snapshot-preparation API remains v5-only;
its versioned legacy-pair retention/install integration is still required.
