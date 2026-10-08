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
capture command and actual private development capture remain unfinished. The
offline fitting integration is described below. Supplied
backends still need their own query deadlines and read pacing before live use.
Continue the serial CPU/memory/task scope; no live capture or local optimizer was
invoked here. Household snapshots remain private and require an explicitly
identified destination before transfer. The existing post-fit source contract,
artifact validation and numerical qualification gates remain unchanged.

## Fit a frozen snapshot off-host

`scripts/train-thermal-snapshot.py` verifies a retained input snapshot or delegates
fitting to the existing training pipeline using only frozen series and journal
readers. No household database, weather fetch or site-settings callback is supplied.
The existing artifact, conditioning, block-refit, evaluation and shadow-promotion
gates remain in force.

Verification is read-only and requires no fitting opt-in:

```text
python scripts/train-thermal-snapshot.py \
  --snapshot /private/SNAPSHOT_SHA.training-inputs-v1.json --verify-only
```

Run verification under the existing serial resource scope on this host. Run the
following fitting command only on the designated off-host machine, after private
transfer to an explicitly identified destination:

```text
EARTHSHIP_REMOTE_QUALIFICATION_FIT=1 python scripts/train-thermal-snapshot.py \
  --snapshot /private/SNAPSHOT_SHA.training-inputs-v1.json --fit \
  --state-dir /private/new-model-directory \
  --fit-evidence-dir /private/new-proof-directory
```

Both output directories must already be empty, owned mode-0700 directories,
resolved and separate, with neither nested inside the other. No production path
is selected by default. The environment variable is an explicit workload opt-in;
it does not prove that a machine is off-host. This fitting command has not been
invoked on the household host.

Before candidate promotion, the pipeline saves the original training source proof,
a private immutable `earthship-thermal-training-input-binding/v1` receipt linking
the input snapshot to the candidate artifact, and the measured fit proof. Source,
binding or proof persistence failure preserves the prior candidate. The wrapper
requires the fitted interval and dataset manifest to match the frozen capture and
rechecks the fit source revision before each proof write. The CLI source identity
includes the release source closure, snapshot reader, training wrapper and CLI;
it does not attest the interpreter/native dependency environment.

Exit 0 means inputs verified or a shadow candidate accepted in the isolated
registry; exit 1 means the existing training gates refused; exit 2 means input,
workload intent or private destination checks refused. Successful fitting grants
no production forecast/advisory authority. Preregistration, untouched/prospective
source-bound skill and complete rollback qualification remain required.

Local tests exercise real pipeline orchestration with all numerical boundaries
replaced by controlled fixtures. Genuine optimizer verification runs in hosted CI
or on the designated worker. Actual capture, off-host placement, real fitting and
candidate qualification remain open.


## Capture transport limits

The capture-only `thermal_model.capture_readers` library permits GET requests to
explicit loopback OpenHAB endpoints for known training Items. It requests at most
one day per query, preserves exact fractional interval boundaries, refuses
redirects, disables ambient proxies, and bounds responses at 1 MiB each and 32 MB
in total. Accepted points and requests have independent caps. Byte reads share
mandatory pacing at no more than 1 MiB/s; callers may reduce that rate.

`ReadBudget` spaces operation starts by at least one second, with no idle-time
burst credit; callers may choose an integer spacing up to five seconds. A shared
budget covers HTTP and wrapped journal operations. Pacing refuses before a
request if its wait would reach the deadline, and rechecks after every wait.
It checks a monotonic deadline before and after each operation. HTTP
socket timeouts are at most five seconds. The journal DSN helper pins the local
address, port and database, rejects alternate routing fields, and overrides
connection, statement and lock timeouts with read-only transaction defaults.
It neither connects nor establishes that the supplied database role is read-only.

These are transport bounds, not a hard process deadline. A blocking callback or
repeated socket reads must run under the worker guard described below. Integration of the shared budget into every capture backend, verified resource
containment, native-history integration and the operational
capture command remain required before live collection. The tests use fake HTTP
and parse synthetic DSNs; no household data was collected or model fitted.


## Capture worker guard

`thermal_model.capture_guard.run_guarded_capture` refuses unless the current
Linux unified cgroup enforces CPU at or below 25%, memory at or below 768 MiB,
zero swap and at most 48 tasks, and the process has nice priority 15 or lower
scheduling priority. It checks kernel files rather than relying on requested
systemd properties. Where the I/O controller is available, its default weight
must be at most 10 with no device override. Otherwise the process must have
verified idle I/O priority. Idle priority is scheduling preference, not an I/O
throughput cap; transport byte pacing remains mandatory.

A trusted caller supplies the fixed capture worker argv. The guard uses no shell,
forces fitting intent off and numerical threads to one, and discards child stdout
and stderr to avoid buffering data or leaking credentials. Private receipts must
be written by the eventual capture worker. A monotonic deadline of at most 90
seconds terminates the fresh worker process group, including inherited descendants,
on timeout or leader exit. The leader remains unreaped until group cleanup to
prevent PID reuse during signaling. Cleanup allows two seconds for leader reaping.

This protects a cooperative, trusted capture worker. It does not prevent a
malicious descendant from creating another session, and an uninterruptible kernel
wait may delay termination. It creates no resource scope and performs no live
collection. Operational integration, source budgets and actual private capture
remain unfinished. Small worker tests exercise success, timeout, signaled status
and inherited-child cleanup; source collection and optimization are absent.


## Native temperature capture backend

`thermal_model.capture_backends.configured_capture_history` explicitly retains
native grids and reuses the existing collector, private reader-role configuration,
fixed temperature policy and receipt selection. It injects the shared read budget
immediately before each database connection, pins the address and port, and forces
read-only connection defaults. It refuses a connection when fewer than two seconds
remain because libpq rounds smaller connection timeouts upward. The existing
fetcher still checks read-only repeatable-read transactions, statement/lock timeouts,
unique Item mapping, bounded rows and oversized-value barriers.

Original qualified metadata and null barriers pass through the existing history
reader without interpolation or legacy fallback after cutover. The default
scheduled collector path is unchanged. Tests exercise the real collector and
receipt selection using fake SQL connections. This backend must run inside the
capture guard; the operational capture command and bounded journal integration
remain unfinished. No private development snapshot has been acquired by this work.


## Bounded journal capture backend

`configured_capture_journal` exposes only effective action/mode reads, with the
shared connection-start budget and bounded interval. Its connection pins the
local endpoint, enforces the existing timeouts, verifies read-only transactions,
and closes on success and failure. It does not establish role privileges or
replace restored-journal qualification.

The journal's opt-in read limit preserves the original correction-aware queries,
including persistent carry and kiva context. It requests at most 10,001 rows and
refuses more than 10,000. A capture-only server projection checks each original
row at 2,048 bytes across all fields. Oversized rows return a refusal marker
without their large values; the entire read fails. Accepted rows retain their
original values and source confidence. The bounded payload is about 20.5 MB plus
fixed protocol overhead, before later snapshot validation. No partial result or
truncated note can become training evidence. Existing unbounded journal callers
keep their original query and connection defaults.

Fake-connection tests cover query/context preservation, overflow, byte markers,
retained fields, shared pacing, read-only checks, expiry and connection cleanup.
Real PostgreSQL projection checks belong to the existing disposable hosted-CI
suite; they must pass before live use. Operational worker/CLI integration and an
actual private capture remain unfinished, and fitting stays off this host.


## Guarded private capture command

`scripts/capture-thermal-inputs.py --config <absolute-private-config> --destination
<absolute-new-private-directory> --check-only` validates configuration without
querying sources or launching a worker. Use the approved resource scope for this
command: CPUQuota=25%, MemoryMax=768M, MemorySwapMax=0, TasksMax=48, nice 15,
idle I/O priority where the I/O controller is absent, and one numerical thread.
The command verifies enforced caps rather than assuming scope properties worked.

The owned mode-0600 JSON config, in an owned mode-0700 directory, has exactly these
string fields:

| Field | Meaning |
| --- | --- |
| `start`, `end` | Explicit UTC development interval, completed before collection |
| `openhab_base` | Approved loopback REST endpoint |
| `token_file` | Absolute private file containing the existing OpenHAB token |
| `journal_dsn_file` | Absolute private file containing the existing local journal DSN |
| `native_db_config` | Absolute private native reader-role JSON config |
| `native_policy` | Absolute private file containing the fixed three-stream temperature policy |
| `native_cutover` | Explicit elapsed five-minute-aligned native-evidence cutover |

Source configuration paths must be resolved private regular files. Native role,
endpoint and sensor policy are checked before collection. The output directory
must already exist, be owned mode-0700, be empty and separate from configuration.
Credentials never appear in command arguments, receipts or error messages.

Actual collection requires `EARTHSHIP_THERMAL_INPUT_CAPTURE=1` and omits
`--check-only`. The parent launches a fixed worker under the 90-second guard;
all backend connections share a 70-second read budget with mandatory request and
byte pacing. Worker stdout/stderr are discarded. Internal worker arguments and
the environment marker are cooperative coordination, not a security boundary or
operator entrypoint. The source tree must satisfy the existing source-pinning
permissions: no group/world write bits. Collection revision includes capture,
pacing and atomic-write helpers, and code drift refuses before persistence.

An interval whose minimum request count cannot fit the shared pacing budget
refuses before source queries. Passing preflight does not guarantee that database
or HTTP latency will fit; deadline expiry refuses the capture. This deliberately
keeps each run bounded. A short captured development window is not sufficient
release evidence by itself. Acquisition of a complete development history and a
genuinely qualifying off-host fit remain required.

A successful worker writes an immutable `*.training-inputs-v1.json` and an owned
mode-0600 `capture-receipt.json`. The receipt contains only status, snapshot and
collection revision hashes, and false fitting/installation/release flags. Failure
never emits a success receipt to the caller. A receipt-write failure can leave a
valid private snapshot; verify it with `train-thermal-snapshot.py --verify-only`
before using it. Retained files are never replaced by a retry. No actual private
capture, fitting, installation or production graduation follows from the synthetic
CLI tests. Real capture must wait for hosted CI and a verified source tree.


## Protect existing scheduled training

`openhab/systemd/user/thermal-model-train.service.d/resource-limits.conf` caps the
existing shadow trainer at 25% CPU, 768 MiB memory, zero swap and 48 tasks. It sets
nice 15, idle I/O preference and single numerical threads, with group termination
on an out-of-memory failure. It leaves the command, credential sources, schedule
and existing timeout unchanged. Qualification fitting and full suites continue to
belong on the designated off-host worker.

Install the reviewed drop-in and reload user unit metadata without starting or
restarting the trainer. Verify effective CPU, memory, swap, task, scheduling and
thread settings and confirm the service remains inactive. Controller availability
still determines whether I/O weight applies; idle I/O is a scheduling preference.
When the scheduled job next runs naturally, inspect its actual cgroup limits and
result. A resource-limited training failure must preserve the previous accepted
artifact and must not authorize graduation. Removing only this drop-in and
reloading metadata restores the previous resource settings.


## Assemble bounded acquisition windows

`thermal_model.training_assembly.assemble_training_inputs` combines original
measurements from two to eight adjacent snapshots under aggregate 32 MB,
120,000-point and existing interval bounds. It validates originals before journal
access and requires one measurement collection revision, cutover and source
identity. It preserves exact series, native receipts and missing barriers, and
recomputes the combined native-grid hashes. Input order is normalized chronologically.

Chunk journal subsets are not merged. A supplied trusted journal reader must
fetch correction-aware action and mode context for the full combined interval.
The existing dataset builder then reconstructs one ordinary input snapshot using
that fresh view. No action confidence is promoted and no fitter or publisher is
accepted by the assembler. Code drift refuses before returning an assembled result.

The new `earthship-thermal-training-assembly/v1` binding records original input
hashes, measurement and assembly revisions, combined snapshot identity, interval
and journal capture time. Its fitting, installation and release flags stay false.
`verify_training_assembly` rechecks supplied originals and exact combined
measurements/grids; internally consistent rehashing of a changed assembled
measurement cannot repair its lineage. Private content-addressed binding writes
are atomic, do not replace files, and clean partial temporary files.

The guarded command and fitting integration below preserve this binding. Actual
full-interval assembly and real off-host fitting still require private evidence.
Library verification proves consistency with the supplied originals; fresh journal
provenance still depends on the supplied reader. No production release follows
from assembly alone.


## Guarded assembly command

`scripts/assemble-thermal-inputs.py` takes repeated `--part` paths, an explicit
`--journal-dsn-file` and a new empty private `--destination`. Use the same verified
resource scope and `EARTHSHIP_THERMAL_INPUT_CAPTURE=1` as input capture. The parent
launches a fixed worker under the existing 90-second guard with fitting disabled.
No HTTP or native-history recollection occurs; only the full-interval journal is
read again through the bounded read-only backend.

`--check-only` checks private paths, aggregate file sizes and restricted journal
configuration without parsing snapshots, querying the journal or launching a
worker. It is path/configuration validation, not scientific qualification.
The worker loads two to eight original files with mandatory read pacing at or
below 1 MiB/s. It reserves each inspected size plus one byte and enforces that
size at the actual read boundary, so growth during the pacing wait refuses before
larger unreserved I/O. Private ownership, address, digest and dataset reconstruction
remain required. File metadata is rechecked after loading and journal collection.

The command hashes the capture source closure plus its assembly library and CLI.
It persists the assembly binding before the assembled input snapshot, then writes
a minimal private `assembly-receipt.json`. Failed persistence or changed source
context never emits a success receipt. Outputs preserve false fitting,
installation and release flags. Internal worker markers are cooperative, as in
capture; operators invoke the ordinary parent command. Source-permission checks
and hosted CI must pass before actual use. Real off-host optimization remains required.


## Verify and retain assembly lineage during fitting

For assembled inputs, supply `--assembly-binding` and repeat `--input-part` for
every original snapshot when invoking `train-thermal-snapshot.py`, both for
`--verify-only` and for off-host `--fit`. The options are required together.
Original part reads retain their aggregate bounds and mandatory byte pacing.
The binding reader requires a private, bounded, content-addressed original file
and refuses duplicate keys and nonfinite JSON values. It verifies the complete
assembly against the supplied original parts before fitting begins.

```bash
python scripts/train-thermal-snapshot.py \
  --snapshot /private/COMBINED_SHA.training-inputs-v1.json \
  --assembly-binding /private/BINDING_SHA.training-assembly-v1.json \
  --input-part /private/FIRST_SHA.training-inputs-v1.json \
  --input-part /private/SECOND_SHA.training-inputs-v1.json --verify-only
```

On the designated off-host worker, use the same lineage options with the existing
explicit fitting opt-in, `--fit`, and new separate private state/proof directories.
The wrapper freezes validated caller inputs, then persists the original parents,
combined snapshot and assembly binding in the proof directory before candidate
promotion. An `earthship-thermal-training-input-binding/v2` record binds the
assembly digest and original input digests to the candidate artifact and fit code
revision. Ordinary unassembled snapshots retain the v1 binding contract. Failed
lineage persistence prevents promotion. No binding authorizes production release.

The fit revision also includes the assembly verifier, pacing helper and atomic
rename helper. Verification-only mode performs no optimizer work. Real numerical
qualification, untouched evaluation and production gates remain separate.

The underlying input schema remains v1 and does not itself distinguish an
assembled snapshot from an ordinary capture. Supply the lineage options explicitly
for assembled inputs; omitting both uses the ordinary snapshot path and does not
verify parent lineage. Such verification is not a production release gate pass.


## Origin sensor epoch consistency

Native initial-state collection and original v1/v2 archive validation require all
non-null trailing receipts for each sensor role to share the current receipt's
epoch. A valid UUID change within a history refuses that history before initial
state or proof is emitted and before latent mass reconstruction. Different sensor
roles may have different uniform epochs; missing receipts stay missing barriers.
Recomputing archive hashes cannot make a mixed history qualified. No reset or
relabeling policy is inferred. The release command withdraws to unavailable when
this source check fails. Historical archives that violate it remain unsuitable
for release scoring; preserve their original bytes for diagnosis.


## Stage A forecast assumptions

The release command generates its forecast by simulating the existing baseline
schedule, with candidate schedule search disabled. All trajectory points, extrema,
intervals and morning mass values come from that simulation. The ordinary v1
shadow path retains its existing default behavior. The release converter refuses
a shadow with a non-null candidate schedule rather than clearing that schedule
and retaining candidate-conditioned temperatures.

The published baseline describes conditional assumptions, not confirmed future
actions or qualified action advice. Stage A withholds candidate recommendations
and their claimed effects. Existing seasonal protocol and the winter no-vent
default are preserved. Forecast skill must still pass frozen-runtime, original
publication and independent outcome gates; simulation correctness grants neither
release nor actuation authority.
