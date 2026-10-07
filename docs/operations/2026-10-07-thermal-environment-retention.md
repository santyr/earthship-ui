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
