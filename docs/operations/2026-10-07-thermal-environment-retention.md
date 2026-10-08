# Thermal dependency-byte retention

`thermal_model.environment_bundle.capture_environment_files(directory, files)`
retains an explicitly declared map of logical absolute dependency paths to
resolved regular source files. It can retain interpreter, Python module and native
library bytes. It does not recursively discover files, execute dependencies,
install a recovered environment or declare an inventory complete.

The writer streams fixed-size chunks rather than loading an entire environment
into memory. It checks file ownership, permissions, bounds, inode/timestamp
stability and SHA-256 identity, then rechecks sources after copying. Identical
content is deduplicated into immutable private blobs. Manifests bind each logical
path, hash and byte count. Copies and directory entries are synced before atomic
no-replacement publication. Interrupted attempts are removed; identical retries
reuse a verified bundle.

`read_environment_bundle` verifies the manifest/address, exact blob membership,
private ownership/modes and every streamed content hash. Changed or exposed files,
extra blobs, malformed paths and attempts to promote qualification flags refuse
verification. Symlinks are not followed implicitly: a reviewed logical alias can
be recorded only with an explicitly resolved source file. The archive contains
regular private blobs, not links back to mutable installed files.

The schema is `earthship-thermal-environment-files/v1`.
`cold_environment_qualified` and `production_qualified` are always false.
Retaining declared bytes is separate from inventory completeness, compatible
relocation, cold execution and restored-journal qualification.

Build the inventory from the interpreter actually used by the service and the
actual locations of imported dependencies. Default library paths alone can omit
installed packages. Include reviewed aliases and the native-link dependency
closure; a loaded-library probe alone does not establish every lazy dependency.
Keep host-specific inventory, versions, paths and scope measurements in private
staging. Complete retention, relocation and cold application/journal checks remain
required before production cutover.

Local tests use tiny files in the established serial resource scope. The component
does not rebuild or automatically copy the installed environment, change a service
or publish a thermal state.

## Reviewed tree inventory

`inventory_environment_files(roots, aliases=...)` builds the explicit capture map
from reviewed library roots. File and directory symlinks require an exact declared
logical-path-to-resolved-target mapping. Unreviewed, changed or unused aliases
refuse the inventory. Cycles, overlapping file coverage, unsafe entries and
traversal/file-count limits are checked. Directory membership changes during the
scan also refuse it. Bytecode cache directories are excluded; recovered execution
must keep bytecode writes disabled.

The resulting map feeds the streaming byte capturer. Inventory success establishes
only the reviewed trees and aliases, not complete native-link closure, retained
bytes, compatible relocation, cold journal recovery or release eligibility. Keep
actual roots, alias maps and size measurements in private staging. No automatic
installation, service change or full-environment copy is performed by the inventory
function.

## Isolated dependency recovery

`prepare_environment_restore(bundle, destination)` materializes verified retained
blobs in a new private `rootfs` mirror. Logical absolute paths become relative
paths inside that mirror; no original installed paths are written. Conflicting
file/directory paths are refused. Copies remain non-executable 0600 files, and
directories are private. An existing destination is never replaced. Partial copies
are removed, and a verified complete preparation is synced and published atomically.

`verify_environment_restore` rechecks the retained bundle, exact file and directory
membership, private permissions, every mirrored byte count/hash and the closed
preparation receipt. Changed files, extra directories, symlinks and attempts to
claim installation or qualification are refused.

The command `prepare-thermal-environment.py` accepts `--bundle`, `--destination`
and optional `--verify-only`. It prepares new isolated files or rechecks an existing
mirror. It never executes a recovered interpreter, installs files or changes a
service. Its `earthship-thermal-environment-restore/v1` receipt always records
`installed`, `cold_environment_qualified` and `production_qualified` as false.

A mirror is not yet a runnable recovered environment. Native-link closure,
interpreter/library relocation, cold application and restored-journal checks,
compatible runtime/artifact integration and guarded installation remain required.
Do not promote preparation flags manually. Use the existing resource limits and
keep host-specific receipts and inventory details in private staging.
