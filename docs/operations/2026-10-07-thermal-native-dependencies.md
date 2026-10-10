# Passive native dependency closure

`thermal_model.native_dependencies.elf_dependencies` reads bounded ELF64 header,
program-segment and dynamic-string metadata without loading or executing an image.
It supports both ELF byte orders and records architecture, `DT_NEEDED` names and
the optional interpreter path. File ownership, permissions, sizes, metadata offsets,
string termination and stable file identity are checked. Unsupported and malformed
images refuse the read.

`native_dependency_closure(seeds, libraries=...)` follows only explicit reviewed
library-name/interpreter bindings. It handles repeated edges and transitive cycles,
checks a common architecture/byte order and enforces root, graph and metadata bounds.
An unbound dependency refuses the closure. It does not run binaries, the loader or
`ldd`, or automatically select a search path.

The `earthship-thermal-native-closure/v1` result is a metadata graph.
`cold_environment_qualified` and `production_qualified` remain false. A reviewed
binding map must reflect the actual required loader search behavior; graph
resolution does not prove symbol-version compatibility, lazy `dlopen` dependencies,
complete byte retention, correct relocation or cold application/journal behavior.
Those remain required before rollback installation or production cutover.

A bounded private rehearsal read the prior interpreter and reviewed Python native
extensions, using reviewed system library-cache bindings. It resolved their
transitive metadata without executing retained binaries. Its actual paths, graph
and scope measurements remain in ignored private staging. No installed files,
services, forecasts, controls or model fits changed during the rehearsal.


## Retained name bindings

`bound_native_dependency_closure(seeds, libraries=...)` returns a separate
`earthship-thermal-native-closure/v2` graph with explicit seed paths and the
required dependency-name-to-resolved-file bindings. It retains multiple required
aliases for the same file and the interpreter loader's absolute binding; unused
search-map entries are omitted. The original metadata-only closure API and its
v1 shape remain unchanged.

Use retained, verified dependency blobs as graph inputs and keep the graph with
their immutable byte-manifest identities in private staging. Recovery must
preserve the exact bindings even when a requested library name differs from a
resolved file's basename. A loader silently falling back to installed libraries
is not isolated recovery. Version 2 remains metadata evidence with both
qualification flags false; symbol compatibility, actual loader search behavior,
lazy dependencies, cold application and restored-journal checks remain required.
