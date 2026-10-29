# Private retained-score fixture reader

The retained coordinator accepts an optional keyword-only `reader_factory` for
an explicit in-memory acquisition fixture. It passes the callable through
`run_retained_worker` and the retained runner to the existing reader-construction
point in `score_jobs`. It does not expose a CLI, environment, or configuration
override. Production callers omit it and retain the original closed reader
selection and source checks.

The callable receives the same closed reader configuration and
`shared_lock_guard` callback as the production constructor. That callback returns
the remaining original, nonrenewable deadline and still performs the existing
lock, pressure, source, and configuration checks. Model/context validation occurs
before acquisition. Supplying both a reader and a factory, a non-callable
factory, or an explicit factory returning no reader is refused.

Fixtures must retain the complete coordinator, query/receipt parsing, original
acquisition budget and pacing, source accounting, reports, independent equality,
and final custody checks. Synthetic readers and modeled transport/SQL do not
establish actual PostgreSQL, publication, sensor, or natural-score qualification.
The original actual historical workload remains a separate test.

The operational report helper also retains segmented source-inventory metadata
inside its existing invocation-local capture cache. The complete capture,
serving-model, selection, and expected-hash keys remain unchanged. Inventory
metadata binds the full schema/runtime/binding inputs to the manifest and every
child's bytes and identity. It stores no selected grid or raw-source payload.

The first inventory operation still uses the original complete decoder. Only a
successful full capture validation admits its metadata into the existing
64-entry/1 MiB cache, with the new metadata included in that byte accounting.
Every hit freshly reads and hashes all files and checks their original manifest
declarations, identity, ownership, deadline, and final custody. The original
source inventory and terminal verification remain active. Failed validations do
not admit metadata; unknown or older implementations use their original path.
All scoped adapters restore on exit, and no metadata survives an invocation.

### Full segmented decoding within report-local reuse

The operational report helper may reuse a complete successful three-role
segmented replay within its existing temperature-query LRU. This shares the
unchanged 8 MiB and 16,384-entry limits with ordinary query results; it adds no
separate cache. The codec, binding, model, source formats, and fitted closures
remain unchanged.

All public codec and binding functions remain original, so the native loader's
source and implementation checks run unchanged. Reuse is scoped at the binding's
private operation boundary and always delegates to its original nonrenewable
guard and terminal-custody adapter. A cold retained read constructs the same
original custody handle and executes the full original decoder. Its complete
grid is retained for the subsequent explicit replay rather than discarded.
Terminal refusals remove admissions made before the final check.

Each lookup freshly reads the complete manifest and all children through the
original bounded custody readers. It checks exact bytes, stored digests, file
identities, complete manifest context, original codec functions, and caller
context. All freshly read bytes are registered in the report's original source
inventory. The first full decode remains mandatory; hits copy every role, target,
receipt, and missing value and keep terminal file/guard checks. Unknown or
unretained handles use the original replay. Standalone reports discard their
temperature cache on exit. Explicit coordinated scoring uses the same bounded
cache for one complete original job, so acquisition and reporting can share
identical decoded inputs. Reports retain their own guard at every reuse; all
HTTP/SQL operations, pacing, 50-second acquisition budget, full model/source
checks and original job deadline remain. Model and capture-validation caches
stay report-local. No temperature result survives job exit or cancellation;
separate jobs and foreign/nested scopes cannot borrow hits implicitly.

For an inventory already admitted by a successful full capture validation,
snapshot construction obtains its fingerprints directly from that inventory's
fresh-byte verifier. This avoids separately validating the same file list and
then immediately fingerprinting it again. Each call still reads all original
files, compares their stored digests and identities, checks the original caller
guard, and registers the bytes with the report's complete final inventory.
