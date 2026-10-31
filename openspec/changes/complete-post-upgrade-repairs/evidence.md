# Implementation evidence

## Task 2.1: current scheduled family reconciled

The Oct28 18:00 UTC fit is selected at deployment `1a41c89d47c3bbc5a110903789548144071ecddd260b19b4e4da608d3d490ae8`.
All 470 source files match the retained release and staged manifest, all five
installed family files match, and the activation owner completed restoration.
The three original timers retain their exact state and calendars, including both
score-timer entries. Of 855 previously protected files, 851 are unchanged; the
four changed files are verified scheduled-family/checkpoint transitions. Original
baselines are preserved.

Evidence: `artifacts/post-upgrade-repairs-20261024.local/openspec-runtime-20261028/current-family.json`
(SHA-256 `39c31854e425e29b9a8096ea6703dc443b0036ebacd82fd1e3004b65ad29bd32`)
and sibling `authorized-current-guards.json`.

The deployed source remains `e5828bd4c5e4059032713f5d628fa097e0264d34`;
the repaired `a14b6e3` source has not been activated. This evidence closes state
reconciliation, not forecast recovery or deployment qualification.

## Task 2.2: production-equivalent historical fixture prepared

The active unit executes its coordinator at depth 14. The selected retained
model's original stage/script/config depths are 9/13/9. The fresh `historical198-a03`
fixture matches all four, rather than copying the earlier release-location
assumption. Its setup completed in 1.416 seconds under the original
256 MiB/24-task/120-second recipe, with no resource-event increments.
All 869 protected hashes remained unchanged. The exact 197 original retained
records and genuine extra job are preserved; no product source or limits changed.

Evidence: `artifacts/post-upgrade-repairs-20261024.local/openspec-runtime-20261028/historical198-prep-a03/production-layout.json`,
`mechanical-delta.diff`, and `parent-preparation-terminal.json`.
At setup the full timed body remained pending; its subsequent full-run results
are recorded below. Fixture setup alone receives no numerical qualification credit.

## Task 2.3: complete historical run passed

The fresh run completed successfully in 116.784 seconds, within the original
119-second body/120-second scope. It retained all 198 required records, scored
the genuine extra job, and matched the independently recomputed report.
Actual acquisition used two HTTP GETs and two PostgreSQL read-only sessions;
both connections closed without commits. Final checks proved all 869 protected
hashes unchanged. The original 256 MiB/24-task/no-swap/CPU4 limits were retained;
memory-event counters were zero and all managed scopes were gone after exit.
Terminal PID-event counters were not separately captured and are not claimed.

Evidence: sibling `historical198-a03/run-a01/receipt.json` and
`historical198-prep-a03/parent-historical198-terminal.json` under
`artifacts/post-upgrade-repairs-20261024.local/openspec-runtime-20261028/`.
This proves the historical/current-OP path at signed source `a14b6e3`, not the
new dense 256 workload or production deployment.

## Task 2.4: missing synthetic extra-origin design corrected

`synthetic-fixture.md` and `synthetic-fixture-design.json` specify and verify ten
seed contexts plus the distinct 05:55 extra origin, with complete capture,
geometry, conditioned weather, modeled receipts, and a delivery that references
the generated capture. The seeded 320 packets and extra 32-packet prefetch are
accounted separately. This is verified design metadata; data generation and
numerical execution remain tasks 2.6 and 2.7.

## Task 2.5: explicit fixture acquisition interface

Signed clean runtime revision `3154cd18f5bee3ad84e9ac502fecd622f51758a8` adds the
keyword-only in-memory factory through the complete retained coordinator. When
omitted, the existing production factory and call arguments remain unchanged.
The original model/source/lock checks and nonrenewable numeric acquisition
callback remain in place. No CLI, environment, or configuration override was
added. The retained-helper pin and its real-loader regression name the new exact
helper bytes. All native 19-file, fitted 81-file, and codec bytes are unchanged.

There are 89 verified covering cases across two post-implementation runs:
88 passed in the complete covering run; one new test's expected error text was
corrected to the earlier, correct serving-configuration refusal, then that case
passed separately. The product source was unchanged between those runs. The
initial missing-interface run had nine expected failures and two default-path
passes. All test scopes exited, with no memory/PID event increments under the
original 256 MiB/24-task/90-second recipe.

Evidence: `artifacts/post-upgrade-repairs-20261024.local/openspec-runtime-20261028/reader-factory-tests/parent-terminal.json`
and its raw/JUnit/resource files. Operator documentation is
`.worktrees/post-upgrade-runtime-20261024/docs/operations/native-score-fixture-reader.md`.
The full actual historical run also passed on this exact revision in 116.306
seconds: 198 required records, independent report equality, two actual read-only
PostgreSQL sessions closed with zero commits, all 877 protected hashes unchanged,
and all managed scopes gone. Original limits and production-equivalent paths
were preserved. See sibling `historical198-prep-a04/parent-historical198-terminal.json`.
The earlier full success remains preserved and specific to `a14b6e3`.

## Task 2.6: partial synthetic construction, task still open

The original synthetic preparation command was recovered from its retained
Oct25 execution record: 256 MiB minimum/preferred, 24 tasks, 600 seconds, CPU2.
`openspec-runtime-20261028/original-synthetic-preparation-reference.json` binds
the exact session record, timestamp, and command bounds. This is command
provenance, not permission to claim a new full fixture or benchmark success.

`synthetic-query-shape-a01` extracts value-free topology and independently checks
all 834 inspected original input hashes. It retains 40 horizon contexts, 320
packets, 2,992 rows, 1,642 snapshot equality classes, the original 5/9/10-row
distribution, and bedroom/north-wall invalid occurrences of 9/1. Its shape
SHA-256 is `9c09fa5d13c82ea3f4fb6a6ae7a87f0f5c4a7d0b3ba2fa6e423095189419d8c5`.
Actual temperatures, raw strings, collector UUIDs, and outcome values are not
exported into that specification.

`synthetic-queries-a03` successfully constructs all 320 new complete four-role
query packets through the public receipt builder and original collector expiry,
then original source build/write/read/replay. All 1,642 equality classes remain;
the new raw query corpus totals 4,946,857 bytes. It completed in 1.016 seconds,
with 46,211,072-byte peak memory, one task, and no memory/PID event increments.
No actual PostgreSQL, publication, or full numerical qualification is claimed.

Two failed private constructor attempts remain retained. They tested and
disproved the inference that persistence storage clocks can define a single
global atomic collector timeline for all retained packets. The final constructor
uses the design's allowed independent protocol-receipt ledger; each full packet
retains its own storage clock, receipt identities, ordering, and invalid states.
It does not edit collector private state or original protocol/source functions.

`synthetic-origin-component-a01` separately verifies one full new dense
temperature/geometry component: 8,641 raw ledger rows, 8,625 retained query rows
including one carry, 13,675,272 raw bytes in two segments, all three 289-point
grids with exactly one mass None, original latent-mass observer and binding
read/replay, and a full 288-point declared synthetic geometry. It completed in
8.691 seconds with 105,443,328-byte peak memory, one task, and zero memory/PID
events. There is no arbitrary raw-byte minimum or padding. The complete fixture,
weather conditioning, modeled extra delivery/acquisition, and timed body remain
unproven; the task checkbox stays open.

The subsequent complete eleven-context construction is retained at
`synthetic-origin-contexts-a02`: all ten scheduled seeds and the distinct extra
05:55 origin have their own complete dense four-role ledger, source binding, and
288-point declared geometry. Every context preserves three 289-point grids and
exactly one mass None. All eleven source-binding and geometry identities are
distinct. The single original-bound preparation scope completed in 91.281
seconds, peaking at 121,028,608 bytes and one task, with zero memory/PID events.
Original bound inputs remained unchanged; the scope and its unit were confirmed
gone. `synthetic-construction-parent-terminal.json` records the checks and frozen
constructor source copies. Runtime revision `3154cd18` remained clean.

Its first complete attempt, `synthetic-origin-contexts-a01`, built every context
but failed final resource verification with 44 `memory.max` events; it receives
no passing credit. The corrected private constructor streams the full ledger
hash, fsyncs that completed file, and issues `POSIX_FADV_DONTNEED` for that file
only. Per-context measurements demonstrate roughly 15 MiB less charged file
cache after each operation. All raw files stay retained and every codec, source,
binding, grid, and geometry operation remains. There is no global/cgroup cache
reclaim, limit increase, source thinning, or change to production code.

This remains partial fixture construction. Eleven conditioned weather products
and serving captures, the 64 four-horizon completion cohorts, the extra delivery
and full acquisition prefetch, and the unsplit numerical body are still pending.

The weather construction has now passed separately. `weather-source-7db-a01`
is a fresh exact export of all 2,569 Git files at `7db2c575` (42,752,300 bytes),
with every blob checked against Git and every resulting file hashed. It includes
the two production-weather policy/protocol files missing from the native-only
stage. The native stage was not modified. All eight original weather bundles
loaded with `require_current=True`; original admissions, validity windows, and
the pinned numerical environment passed unchanged. Preparation took 1.288
seconds with zero memory/PID events.

`synthetic-weather-component-a01` first validated the complete construction for
one origin in 23.758 seconds. The subsequent original-bound single-scope
`synthetic-weather-contexts-a01` built all eleven distinct weather contexts in
252.301 seconds, peaking at 140,468,224 bytes and one task, with zero memory/PID
events. All 2,569 source files and declared inputs remained unchanged; 132 private
output files have full byte hashes. Each context includes a new complete
360-hour station/gridded source, the full original near-term/extended production
product, the original native forecast, modeled memory-only state confirmations,
and original thermal conditioning/readback. Every origin has exactly 25 future
temperature points using `local_model_mean` and three original source references.
Source, issue, emission, forecast, and conditioning identities are all distinct
across the eleven contexts. The eight actual models/admissions were not refit,
re-admitted, re-clocked, or changed. These private callback confirmations provide
no actual provider, OpenHAB, PostgreSQL, publication, or natural-runtime credit.

Serving capture assembly, cohorts, extra acquisition, and the full numerical
body remain unproven at this point; task 2.6 is still open.

`synthetic-serving-captures-a01` subsequently constructed all eleven complete
version-5 serving captures through the unchanged genuine PhaseE model
`39984d65` and deployment `c1025fa2`. It replays each full retained dense source,
three native grids, the original latent-mass observer, new geometry, confirmed
private weather conditioning, native numerical trajectory, and capture readback.
All eleven full input, capture, geometry, and conditioning identities are
distinct. It also retains the original serving-model association for each origin.

Only the distinct extra 05:55 origin receives a modeled delivery, avoiding
unintended seed acquisition jobs. Its original closed delivery schema,
canonical digest, persistence primitive, `validate_delivery`, and full
`load_cycle_delivery` replay and custody checks all passed. No missing capture or
delivery is fabricated by an acquisition reader. The genuine model, admission,
stage, and all declared input bytes remained unchanged.

This single original-bound preparation scope completed in 110.724 seconds,
peaking at 154,214,400 bytes and one task, with zero memory/PID events.
`synthetic-origins-parent-terminal.json` verifies the exact terminal cleanup of
the source, single-weather, eleven-weather, and eleven-capture scopes; all their
units/cgroups were gone. It also checks current inputs and the clean runtime
revision `3154cd18`, and binds frozen copies of the construction programs.
These are synthetic origins and modeled callbacks, not actual provider,
PostgreSQL, OpenHAB delivery, or natural-runtime qualification.

Task 2.6 still needs the 64 four-horizon score/completion cohorts and the extra
job's full 32-packet acquisition with its 24 unused retained prefetched packets.
Task 2.7 still requires the original unsplit timed coordinator, newest-256
selection, both reports, independent equality, and terminal custody checks.

The first full cohort constructor, `synthetic-cohorts-a01`, reached its original
599-second internal / 600-second scope bound. It wrote 108 complete markers and
28 capture files before refusing during segmented-source decoding. The partial
fixture is retained and is not accepted as the required 64/256 fixture. It peaked
at 151,744,512 bytes with zero memory/PID events; the complete final inventory
check was not reached, and no full preparation or numerical pass is claimed.

`synthetic-cohort-profile-a01` then ran one explicitly diagnostic four-horizon
cohort under the original 256 MiB/24-task/90-second diagnostic bound. It completed
in 42.795 instrumented seconds, reproduced the same four original scored pairs,
and retained its profile. Of 41.945 seconds in the measured function,
`origin_source_files` consumed 35.061 cumulative seconds over 22 calls; there
were 24 complete raw-source replays. These file-inventory calls repeatedly enter
the full codec's read/replay path despite identical validated source bytes.
The profile peaked at 108,359,680 bytes with zero memory/PID events.

`synthetic-cohort-diagnosis-parent-terminal.json` proves both exact scopes and
units are gone, retains the failed full attempt and successful diagnostic source,
and verifies the runtime checkout remains clean. This identifies a demonstrated
performance issue for correction in the operational report helper; it does not
authorize reducing the workload, loosening limits, changing the codec/model, or
grant numerical credit to the partial data.

## Task 2.6 progress: signed inventory repair and all 64 cohorts

Signed runtime source `493619ecdd407f3df8856542c18d6c8aa0b8b084` corrects
the measured repeated inventory decoding in the operational report helper.
Its exact helper digest is
`9c2877ce9dbfff5bfbd531639113584bc82fe263ab2d0cee08a05f268b143735`.
The first complete source replay remains mandatory. Subsequent inventory checks
freshly read and hash the complete manifest and all children, checking original
bindings and file identities while retaining the existing cache and guard bounds.
The native 19-file closure, fitted 81-file closure, and codec remain unchanged.

Three complete final-source test groups passed: 20 focused segmented-inventory
cases, 20 legacy capture/coordinator cases, and 22 report cases. These are 62
unique passing cases across three commands, with zero memory/PID event increments.
Earlier refusals, failed tests, and resource-pressure runs remain retained.

The same diagnostic four-pair cohort now completes in 10.059 instrumented seconds,
compared with the retained 42.795-second diagnostic. Full codec replays decreased
from 24 to three; original cold validation still runs. This comparison is a
diagnostic result, not the complete coordinator benchmark.

`synthetic-cohorts-a03` then constructed all 64 captures and 256 complete markers
in 191.395 seconds under the original 256 MiB/24-task/600-second preparation
limits. Peak memory was 202,743,808 bytes, with zero memory/PID events.
All 256 independent prediction/error checks and all twelve independently
recomputed summary groups matched. The fixture retains 40 query contexts,
320 referenced packets, 2,992 row occurrences, and 1,642 snapshot equality
classes. All declared original input hashes and final source checks passed.

Authoritative evidence:
`artifacts/post-upgrade-repairs-20261024.local/openspec-runtime-20261028/inventory-repair-parent-terminal.json`.
It verifies the signed clean runtime source, freezes the four source files,
and proves all five exact test/preparation/diagnostic scopes and cgroups are gone.

Task 2.6 remains open for the extra job's singleton plus 31-pair acquisition,
including the 24 unused retained packets. The complete unsplit timed coordinator,
actual historical PostgreSQL recheck on source `493619e`, deployment, and live
operation remain unqualified. The historical `3154cd18` result remains valid
only for its recorded source and inputs.

## Task 2.6: full synthetic fixture prepared

`synthetic-acquisition-a02` verifies the original reader's singleton and full
31-pair prefetch using an explicit private in-memory transport/connection adapter.
The unchanged query loop built 32 packets from a new 315-row four-role receiver
ledger covering 63 endpoints. Eight packets were persisted/read/replayed; all 24
unused packets remained in the original pending inventory and were independently
replayed during preparation. Two original HTTP response parses and two modeled
read-only repeatable-read connections used four actual paced budget requests.
The original SQL loop executed 128 SELECT, four SHOW, and 140 SET statements,
with both modeled connections closed and zero commits. No socket was used.

This preparation passed in 4.136 seconds, peaking at 60,575,744 bytes with zero
memory/PID events. Its first attempt correctly refused an erroneous adapter
measurement that compared I/O-arrival times instead of original budget-start
times. That failure and both exact source files remain retained. The corrected
measurement observes original budget timestamps; pacing and production code
were not changed.

`synthetic256-a01` assembles all 256 complete seeded records and the distinct
extra delivery using signed source `493619e` and the original genuine model and
admission. The newly packaged stage preserves the native 19-file and fitted
81-file numerical closures exactly. Its stage/script/operational-file/config
depths are 10/14/14/10. Only private paths and their original canonical digests
were mechanically rebased; source values and clocks remain unchanged.

Assembly passed in 1.815 seconds, peaking at 92,753,920 bytes with zero memory/PID
events. The frozen input inventory and all 936 declared original hashes match.
`synthetic-acquisition-parent-terminal.json` verifies the three exact preparation
cgroups are gone and retains frozen copies of the constructors, adapter, and
prepared benchmark. This completes fixture preparation, not task 2.7's full
timed coordinator, report-time pending-packet custody, actual PostgreSQL,
publication, or deployment qualification.

## Task 2.7: first complete timed body reached its original deadline

The fresh `synthetic256-a01` body entered the original window with 283.403 seconds
until the genuine next issue. It attempted the complete 256-entry reconciliation
after acquiring/scoring the distinct extra job. It refused at 119.002 seconds
during the report, with final outcome `score lifetime elapsed`. Complete reports,
independent full-report equality, and inside-body final checks did not finish;
this is not a numerical pass. The acquisition adapter's refusal-time cleanup
check superseded the original timeout exception, so no stronger originating
exception claim is made from the retained traceback.

Observed phase costs include 7.832 seconds loading the complete extra delivery,
71.752 seconds spent in the unfinished report, and 115,417 complete source-guard
calls consuming 33.422 seconds. Nested phase timings overlap and must not be
added. Only sixteen source-score/completion builder calls had been entered when
the full report stopped; the remaining records were not verified.

Peak memory was 124,588,032 bytes with zero memory/PID event increments.
`synthetic256-parent-terminal-failure.json` verifies the exact unit and cgroup are
gone and independently rechecks every frozen/original hash. Those later parent
checks do not substitute for the timed body's incomplete checks. The original
failure and complete fixture are retained. A new identical private fixture is
prepared for full-workload profiling before another product correction; workload,
model, source, bounds, and freshness rules remain unchanged. Task 2.7 stays open.

The fresh `synthetic256-profile-a01` diagnostic profiles report reconciliation
inside the complete unchanged coordinator. It reached the original limit at
119.024 seconds. In 71.903 measured report seconds, 25 complete segmented replays
consumed 59.610 cumulative seconds across five completion reads. Nested timings
overlap. This is diagnostic evidence, not a passing benchmark or new production
behavior. The full extra acquisition was verified before reporting (32 builds,
eight referenced packets, 24 pending packets, four paced requests, two modeled
read-only connections, both closed, zero commits). The pending count was still
24 at report refusal; full after-report custody verification was not reached.

Peak memory was 120,262,656 bytes with zero memory/PID event increments.
`synthetic256-profile-parent-terminal.json` verifies the exact preparation and
diagnostic units/cgroups are gone, all original/frozen inputs remain unchanged,
and the diagnostic harness is retained by hash. The measured follow-up design is
`dense-segmented-replay-design.md`. No product change or benchmark pass is claimed
by this new profile. Production readback at approximately Oct28 22:57 UTC still
showed the forecast service failed; geometry and scoring exited successfully.
The user's deployment approval remains active for fixes as relevant checks pass.

## Task 2.7 progress: signed complete segmented-replay correction

Signed source `29d635eacfab2f749154c909e12dcb6118e0b777` implements the measured
correction in the operational report helper. Its exact digest is
`7e0cfcb883c8bd6740660021c296a87dafa2e7d61108d11fb5618afece5d7a77`;
the coordinator pins those bytes. Complete three-role replay results share the
existing 8 MiB/16,384-entry query LRU with complete retained-object accounting.
The first original decode remains mandatory. Hits freshly read every manifest
and child, verify complete bytes/digests/identities/context and unchanged codec
functions, register every original byte in the active source inventory, copy all
roles/receipts/missing values, and retain final guard/custody checks. The codec,
native 19-file and fitted 81-file closures remain unchanged.

The final source passed 81 unique cases across three complete groups: 39 new
replay/prior-inventory cases, 20 legacy capture/coordinator cases, and 22 report
cases. All memory/PID event counters remained unchanged. The earlier focused
13-pass/one-failure run exposed absent source-inventory observations, which the
correction now records explicitly; that run and its exact source are retained.
Subsequent 14-case and 39-case intermediate runs remain source-specific evidence.

`segmented-replay-repair-parent-terminal.json` verifies the clean signed runtime,
freezes all four changed files, proves all three final test units/cgroups are
gone, and checks the fresh `synthetic256-a02` fixture's 938 original hashes.
This fixture retains the original cohort constructor helper at its frozen
`493619e` bytes and records the exact authorized transition to `29d635e`; old
source baselines are not overwritten. Complete preparation passed in 1.829
seconds with unchanged limits and zero resource-event increments.

The fresh historical actual-acquisition case `historical198-a05` is also
prepared (1.404 seconds, zero memory/PID event increments), preserving the full
197-plus-one workload and original path depths. Its source-transition receipt
verifies only the coordinator and report-helper changes against Git, with the
other 875 protected hashes unchanged. Both complete timed requalifications and
production activation remain pending at this point.

## Task 2.7 correction: preserve the original native loader's implementation checks

The `synthetic256-a02` complete run at source `29d635e` refused after 48.220
seconds with `shared native helper loaded implementation differs`. The native
loader correctly rejects replacement of a checked public codec function. The
earlier 81-case result did not cover this integration, so it provided no
deployment qualification. The failure, original source, exact scope cleanup,
unchanged frozen fixture, and two preserved working-source transitions are
retained in `synthetic256-a02-parent-terminal-failure.json`. Resource-event
counters stayed unchanged; no source from that implementation was deployed.

Signed correction `7d411352571480729e560b6032dc37c05ea507fb` leaves every checked
public codec and binding function original. It adapts only the private operation
boundary and delegates every read/replay through the original nonrenewable
deadline and terminal-custody adapter. Cold reads execute the original codec;
the first complete explicit replay admits a grid into the unchanged shared
cache. Later reads build fresh custody handles only after complete original
manifest/child byte, identity, ownership, and context checks. No loader check,
codec source, model, admission, resource limit, or freshness rule is loosened.
The exact operational helper digest is
`868c5ca1e59f0865ac4ca4d880cc7aeca67fc4ab3fd315bc5f9c4aa913ea6b1b`.

The final source passes 82 unique cases in three complete groups (40 segmented
replay/inventory cases including the real loader, 20 legacy/coordinator, and 22
report), all with unchanged memory/PID event counters. The genuine same dense
four-horizon diagnostic also passes in 10.122 instrumented seconds, with all
original pairs equal and final source checks complete. It is a diagnostic,
not the full numerical body.

`operation-boundary-repair-parent-terminal.json` verifies the clean signed
source, freezes all four files, checks exact test/diagnostic cleanup, confirms
the native 19-file, fitted 81-file, and codec bytes unchanged, and verifies all
938 original hashes in fresh fixture `synthetic256-a03`. Preparation took
1.846 seconds with unchanged limits and no new events. Historical actual case
`historical198-a06` is separately prepared with the original workload and limits.
Complete timed qualification, actual historical recheck, and deployment remain
pending at this point.

## Current-source historical acquisition passed; dense timing remains open

The complete actual historical run `historical198-a06` at source `7d41135`
passed in 115.766 seconds within the original 119/120/50-second limits. All 198
required records and the independent report matched. Actual acquisition used
two fixed HTTP GETs and two read-only repeatable-read PostgreSQL sessions, both
closed with zero commits; eight original query packets were retained. Final
checks verified the original protected inputs. The parent's separate arithmetic
check recomputed all twelve summary groups and confirmed both report files are
byte-identical. All 877 protected hashes match. The exact worker was observed
live, then its precise unit/cgroup were verified gone. Memory-event counters
were zero; terminal PID-event counters were not separately captured and are not
claimed. Authoritative receipt:
`openspec-runtime-20261028/historical198-prep-a06/parent-historical198-terminal.json`.
This proves the complete historical actual-acquisition path on the current
operational source, not the dense 256 workload or deployment.

The complete dense `synthetic256-a03` run at the same source reached its original
119.002-second bound during reconciliation. It passed the original loader seals
and completed the distinct extra acquisition but did not finish the report or
final checks. Its exact scope is gone; all original/frozen hashes are unchanged,
and memory/PID counters remain zero. Complete source-guard calls consumed 33.292
seconds across 114,880 calls. Nested phase timings overlap. This failure remains
retained and receives no full numerical qualification credit.

Two separately bounded eight-entry diagnostics measured the actual cache rather
than changing code. Two distinct contexts completed in 11.487 report seconds
using at most 1,023,039 cache bytes (two cold admissions). Two distinct captures
sharing one genuine context completed in 6.798 seconds using at most 531,575
bytes (one miss and two hits). Both complete diagnostic reports passed, with
unchanged inputs, no memory/PID event increments, and exact worker cleanup.
These measurements establish that reuse is active and works across captures;
they do not establish full-workload residency or timed qualification. See
`openspec-runtime-20261028/dense-report-cache-parent-terminal.json`.

A fresh identical full fixture is prepared for per-entry/cache observations
inside the original guarded coordinator. It keeps all 256 records, the extra
job, both reports, full independent comparison, source guards, original resource
limits, and final checks. No speculative source edit or deployment followed the
timeout. Task 2.7 remains open; the approved production activation path follows
relevant completed qualification.

The fresh full guarded observation `synthetic256-observe-a01` also reached the
original limit (119.006 seconds). It completed fifteen report entries and was
interrupted in the sixteenth. Per-entry observations prove capture reuse was
active in one original inventory, with no fragmentation or eviction in the
observed prefix. Segmented reuse recorded nine misses and fourteen hits across
nine contexts, all admissions succeeding, with at most 4,476,424 bytes retained.
Cold-context completion reads took approximately 7.17–7.49 seconds; entries
using already-seen contexts took approximately 0.81–0.83 seconds. Complete source
guards consumed 33.511 cumulative seconds over 115,207 calls. These measurements
identify expensive cold context work, rather than an inactive or exhausted
cache, in the guarded path. They provide no full-run passing credit.

`guarded-cache-observability-parent-terminal.json` freezes the three measurement
programs, verifies the exact unit/cgroup gone and every original/frozen input
unchanged, and records zero memory/PID event increments (peak 130,224,128 bytes).
The runtime source remains clean signed `7d41135`. No production deployment
occurred. The next source correction must reduce original cold decoding and
repeated acquisition work while retaining the original complete workload,
byte/identity checks, deadlines, and resource/cache bounds. A larger cache or a
fixture prepared with warm results is not a remedy.

## Task 2.7 progress: retain the first original cold-read result

Signed source `db726125b2e5d8f9bdaa1ce59fc72b77625df00a` removes an identified
cold-path duplication. The private operation adapter already constructs the
same original custody handle through the original directory, bounded read,
manifest, child, identity and hash checks. It now calls the full original codec
replay once and retains that returned three-role grid, instead of calling the
original reader that decodes and discards the grid before another explicit
replay. Public codec/binding functions, raw parsing, source files, model,
admission, numerical values, guards, deadlines, and cache capacity are unchanged.
If the original adapter's terminal check refuses after decoding, its new cache
admission is removed. The exact report-helper digest is
`a664b93fd67cca99d5025d44ef1bd1e53b67296fdde91ffbbffb741e3687c775`.

The final source passes 83 unique cases in three complete groups: 41 focused
segmented cases (including the actual loader and terminal-refusal regression),
20 legacy/coordinator, and 22 report cases. Memory/PID event counters remained
unchanged. The genuine dense four-horizon diagnostic reproduces all original
pairs and final custody checks in 6.879 instrumented seconds, compared with
10.122 seconds on `7d41135`. Its full codec replay count decreased from three
to one. This remains diagnostic, not full coordinator qualification.

`cold-read-repair-parent-terminal.json` verifies the signed clean source,
freezes all four changed files, checks exact test/diagnostic cleanup, confirms
native 19-file/fitted 81-file/codec identities unchanged, and verifies all 938
original hashes in fresh `synthetic256-a04`. Separate historical case
`historical198-a07` is prepared using the complete original workload. Both full
timed source rechecks and production activation remain pending at this point.

## Job-local temperature reuse source and 97 covering cases

Signed commit `fcf627d0e0d15ac8b6d53f27a0542205fa02fc21` extends only pure
temperature decoding reuse across acquisition and reporting within one bounded
score job. Both phases keep their original caller guards and final original-byte
checks; the report also keeps its own guard on every borrowed cache lookup.
The existing 16/8 MiB caches are shared rather than duplicated, clear on exit,
and remain isolated across jobs and unrelated contexts. Model/capture admission
remains report-local. See `dense-segmented-replay-design.md`.

The final 55-case focused suite, 20-case legacy suite and 22-case report suite
all passed at the committed source: 97 unique cases, zero memory/PID event
changes and exact scope removal. Receipt:
`artifacts/post-upgrade-repairs-20261024.local/openspec-runtime-20261028/job-temperature-repair-parent-terminal.json`.

The prior cold-read source `db72612` full 256-case body still reached its original
119-second stop before completing reporting. Its original 938 inputs, frozen
fixture, zero event changes and scope cleanup are verified; the two deliberately
changed current source files retain their original bytes in the signed snapshot.
Receipt: `openspec-runtime-20261028/cold-read-full-dense-parent-terminal.json`
under the repair artifacts. This is retained failure evidence, not qualification.

Fresh full fixtures `synthetic256-a05` and `historical198-a08` are prepared for
`fcf627d`. The full dense body is scheduled once for the next original issue
window. Full qualification and deployment remain unclaimed.

A current production journal read at 2026-10-29 00:45 UTC confirms forecast
withdrawal with `ValueError` at `weather_temperature_sources.py:44` (original raw
native source byte bound). The old production family remains selected. Its
failure is distinct from passing isolated source tests.

## Complete numerical qualification and deployed current-fit runtime repair

Signed source `48eebb04850e0d528bfe514f1a1d9394933ff0f0` passes 115
covering cases. The complete unsplit dense run `synthetic256-a08` passes in
103.597752 seconds under the original 119/120/50 limits, 256 MiB/24 tasks/no
swap, including newest-256 selection from 257 completions, all 256 independent
errors, twelve independent summary groups, both report bytes, the 24 unused
prefetch packets held throughout, and final source checks. All 938 original
and 1,000 frozen files are verified, limit event counters unchanged and the
exact scope removed. See `copy-custody-full-dense-parent-terminal.json`.
The prior `synthetic256-a07` coordinator also finished its report, but the
harness incorrectly requested a guarded acquisition receipt after lock release.
That failure is retained. The corrected harness takes the same receipt while
the lock is held and compares pure terminal acquisition state afterward; it
changes no scorer or workload/limit.

The actual read-only PostgreSQL `historical198-a09` passes in 88.971474 seconds:
198 full scores, two GETs, two read-only sessions closed without commits, the
original 128 SELECT/4 SHOW/140 SET workload, eight packets and fifty-second
acquisition budget. Parent verification reproduces twelve summary groups and
both reports; 877 protected, 197 original and 215 additional file hashes remain
correct. Memory events are zero; terminal PID events were not captured separately.
The exact observed PID/cgroup and owner scope are gone. Scheduled midnight fit
changes are explicitly reconciled, including the exact prior activation checkpoint
reconstructed from its immutable package and verified against its original hash.
See `historical198-prep-a09/parent-historical198-terminal.json`.

The replacement package preserves the genuine model trained through midnight
UTC, all fit coefficients and all four original references. Full candidate, new
admission, archive and five-file family verification passed privately in 25.3
cold seconds. The production stage restores the original shared evidence/cache
outputs, retains history and credentials, and preserves all 473 qualified sources.
Its selected deployment is `1efc34b49506ffc3ab18a2dd79e895749e3ed985cad6169182daa455979703c1`,
artifact `bba12eb11d26e808b196395e532bce59274090d7313d6b62bf4be5650b0d3484`,
runtime `88cb3fb10ea74643ae9f00248ba58b830bd3e9eb9008683c45a4232551f1388b`.
This is an explicit same-fit operator runtime upgrade, not a claimed new fit;
the daily fitter's coverage-advance rule is unchanged. The operator entry uses
the original reserved handoff, 240/150 opportunity checks, cold qualification,
geometry preparation, locks, rollback and external timer owner. Its only
transaction difference requires exact same fit/originals and the qualified new
runtime; the full diff is `operator-runtime-handoff.diff`.

The first operator attempt stopped on a missing import before handoff. Its
original source and failure remain retained; exact source-route/timer restoration
and owner termination are verified in `runtime-attempt-a01-terminal.json`.
The corrected attempt activated the complete family, restored all three timers,
terminated its exact owner, preserved unrelated definitions and removed its
controller scope with unchanged memory/PID event counters. Future daily/owner
routes now use the same clean qualified runtime checkout. See
`production-runtime-parent-terminal.json` and the before/result/backup records.

The first natural repaired forecast created a verified as-issued origin at
01:35:20 UTC and persisted its confirmed delivery at 01:35:33, but the overall
90-second service timed out at 01:36:15 during later work. Fresh household
observation products remain unresolved; 4.3 and natural-operation completion
remain open. A nonblocking stack-only sampler is queued for the next original
forecast worker to diagnose the post-publication stall. No timeout or freshness
limits have been extended, and no equipment actuation is enabled.

All receipt names in this section are under
`artifacts/post-upgrade-repairs-20261024.local/openspec-runtime-20261028/`.

### 2026-10-29 operational cycle and publication reuse

Signed source `506d09d` is deployed as `f76fa9f548e9eda1701b2943a2d4b6752f3a8c9381ef978e371ed085157809bd`. Its numeric remaining-time guard preserves the original nonrenewable 85-second work and 90-second service limits. All other 472 runtime source files and numerical/scoring helpers are unchanged from the qualified `48eebb0` source. The retained focused/covering suites pass 185 distinct cases. The real read-only replay reproduces the complete original capture in 7.485 seconds, with no PUT or database access.

Natural forecast cycles now publish verified thermal products and finish the entire observer/household cycle successfully (first 02:19:45–02:21:11 UTC; also observed 03:09:45–03:11:06). Household energy, calibrated energy, chronological summaries and the current-energy snapshot writer are publishing again. Read-only UI audit `openspec-runtime-20261028/ui-api-current-20261029T0319.json` distinguishes fresh current products from stale performance caches and deliberately unavailable profiled storage. Observation freshness remains too short relative to processing latency; an HTTP 200 is not proof of freshness.

Signed source `b3946da` reuses the already qualified per-job temperature reader only inside the existing publication lock and guard. Its 203 distinct cases pass, and two real full reads reproduce the same original capture in 3.213 and 1.665 seconds with 2,536 full guard calls, no PUT, no database access, unchanged cgroup events and terminal cleanup. This changes only the operational cycle source relative to `506d09d`; no model is refit.

The three preserved deployment attempts did not select `b3946da`: the first deferred on admission, the second had no usable idle window, and the third raised ValueError after preparing the handoff. Exact exception text was not retained by the old child; its rollback restored the `506d09d` family, routes and timers. Measured controller usage peaked at 199,622,656 bytes under the original 512 MiB cap. A later idle read-only check passes handoff bindings but rejects its 02:37:40 history proof because the battery scoring index has changed. A separate check overlapping publication observed a future-candidate clock refusal; that result does not establish the original deployment failure's cause. Preserve both facts. A fresh history-bound package and diagnostic child are prepared for a single original bounded transaction; no limits or validation are relaxed.

The sensitivity worker now reaches completed current originals but exits with an original-native-scenario child failure; the public sensitivity cache remains stale. Diagnose the full retained child error before claiming this consumer restored.

The fresh history-bound `b3946da` package activated successfully in the original safe-window lifecycle. Deployment `592a4f887a034526e29b1a003db005064037522d586a0e79e92cb824a9fc1e7f` retains artifact `bba12eb11d26e808b196395e532bce59274090d7313d6b62bf4be5650b0d3484`, runtime `88cb3fb10ea74643ae9f00248ba58b830bd3e9eb9008683c45a4232551f1388b`, genuine 00:00 UTC fit and original admission receipt. No fit was executed. Independent parent terminal proof at 03:24:22 confirms all five files match, timers restored, external owner inactive/PID zero, controller cgroup gone and memory/PID event counters unchanged. See `production-publication-reuse-deployment-result.json` and `production-publication-reuse-parent-terminal.json`. Natural publication from this deployment is still to be observed.

Natural operation of deployment `592a4f88…` is confirmed: the 03:24:45–03:25:53 UTC cycle published verified thermal delivery and completed all observer work with exit zero in 68 seconds; the next cycle finished 03:30:54. The UI proxy serves the genuine 03:25:15 thermal forecast with the unchanged candidate/runtime identities. The following scoring service exited zero with a truthful historical-selection waiting result. The 03:27 acquisition inserted three current household-energy rows alongside current weather and PV products. This is natural publication/snapshot evidence, not a subsequent model fit or completed historical numerical scoring claim.

Sensitivity diagnosis now preserves the actual native child refusal (`diagnose-sensitivity-readonly-a02-result.json`): its dependency adapter calls the legacy compressed origin-binding decoder for a segmented capture. The isolated sensitivity worktree adds explicit schema dispatch through the producer's already sealed segmented helper, preserving legacy fallback. The regression restores the fixture's real legacy decoder and reproduces the same production error before the fix; after the fix, central 24-hour air/wall parity and child-file deletion checks pass. The 26 focused tests pass under the original 256 MiB/24-task/90-second scope. A broader combined run was terminated without a final receipt; separate original-limit file runs are in progress. No sensitivity deployment is claimed yet.

Remaining storage absence has a concrete freshness cause in the first current original energy receipt: inverter AC evidence is qualified at the 03:25:15 origin but expires 03:25:34.760; the energy projection is actually assessed 03:25:36.341 and correctly reports required_source_expired. Declared bank (400 Ah/20.48 kWh) and inverter-only topology are present in the original configuration, so missing bank data is not established. Preserve the original timestamps and expiry checks while resolving processing latency.

### 2026-10-29 sensitivity publication and final radio/host recheck

Signed isolated sensitivity source `0075a1d791598b86b7097c11c0bb06eba221c530` is installed through one private EnvironmentFile and one new owned worker override. All previous fragments, timers, EnvironmentFiles and other overrides are byte-preserved; existing fit/producer selections and production resource limits are unchanged. Four independent test scopes pass 81 unique cases. The large-report file peaks at 335,089,664 bytes and passes all 15 cases in the existing 512 MiB managed worker profile; the earlier grouped 256 MiB attempts were OOM-killed, not timed out. Those failures remain retained. The original nonpublishing current-data replay completes all three stress cases in 67.590 seconds under the unchanged production 90/100-second limits.

Actual publication then succeeds in 75.873 seconds: the worker confirms original report `5256faca1cfa33dd3e85b08797d059315eaec88d970876131d10ffae0510fe73`, origin 03:40:15 UTC, with unchanged original generated clock 03:43:43.825648 and expiry 05:40:15. The live UI sensitivity API returns HTTP 200 and exact cache bytes. See `sensitivity-worker-deployment.json` and `sensitivity-worker-live-confirmation.json`. Joint evidence remains explicitly insufficient; no probability or physical calibration claim is added.

The natural current-model scoring slot at 03:41 completes with status scored, scored=1 and current_revision_scored=2. A transient forecast failure at 03:35:05 occurred during a test OOM event; the following 03:39:45–03:40:53 cycle recovered. Do not erase the failure or claim uninterrupted service. No exact pressure sample was captured to establish its internal refusal cause.

The final 03:24:19–03:34:19 UTC radio watch records 600 samples on all four read-only paths, all four temperature roles fresh, Bedroom reachable, no errors/expiry/stream-epoch changes, and maximum new-receipt delay 2.496 seconds. The live decoder SHA matches `3502425d82158e42efe4a7a77a285d12ad5af80eea1dc0e9954e2f2b031a4184`; receiver service is active/running with NRestarts=0. Host recheck confirms valid sudoers syntax, installed libmtp-runtime, empty dpkg audit, routable/online wlo1, and no kernel error entries in the inspected interval. At 03:48 UTC there are no failed user services. See `radio-final-parent-20261029T0335.json`, `radio-live-selector-20261029T0347.json`, `host-health-20261029T0336.json`; the earlier host snapshot truthfully retains its transient failed-service list.

### 2026-10-29 complete route audit and tablet corrections

All six supported routes were observed with live OpenHAB (466 Items) at 1280x720, 960x600 and 893x533. The initial 18-view audit recorded no exceptions, console errors, failed reads or write attempts, but screenshots exposed overlapping forecast labels and cropped zone readings on the shortest landscape tablet. The candidate preserves the exact existing deployed source except Home/forecast CSS and its maintained clock-row assertion. Forecast tracks now retain their full content width and permit local horizontal pan; short landscape spacing retains temperature-sized 64px time, two unbroken energy rows, a readable forecast row and all four zone readings.

The complete maintained UI suite passes 3,404 cases in a disposable writable copy of the exact release source; 167 focused Home cases pass after the final short-landscape refinement, and the production build passes. Initial read-only-copy setup failures, the stale 3.2rem row assertion, an observed resource defer and the undersized 512 MiB preview OOM are retained separately. No production/global/native-scoring limits changed. The successful preview uses the existing 1 GiB browser/build profile and copies the existing terrain-source setting; all 11 original clock/viewport cases plus forecast-card containment, all-ten-days reachability and four-zone visibility checks pass.

The tested release `ui-release-forecast-readable-20261029-3bbf7d6caca1-a02` is now active. Only the existing owned UI selector was replaced; all 13 other overrides, the service fragment and private EnvironmentFile are byte-preserved. Public and built connection configuration retain SHA `857b675107d80f78f60e76074f2957ee63b85a20f2b978221cbaf0230daeef9f`. The final 18 live route views again have zero runtime/console/read failures and zero write attempts, with unchanged resource counters and terminal browser/preview cleanup. See `ui-forecast-readable.diff`, `ui-forecast-deployment-result.json`, `ui-final-route-audit-parent.json`, and the retained screenshots. This proves the UI route/layout path; remaining source-freshness and physical/private-stack requirements remain open.

### 2026-10-29 production point decoding qualification

Signed clean source `39b0070b5ea1f1546f2513482f4a2824f3535c07` adds bounded publication-local reuse of decoded production weather points. Every reuse freshly reads all three original view/emission/issue files and compares their complete bytes and identities; the existing request validation, source checks, shared lock and original deadline remain in force. All other 472 existing runtime source files, numerical sources and scoring helpers remain byte-identical. The focused and covering suites pass 235 distinct cases with unchanged resource-event counters and collected scopes (`production-point-source-parent.json`).

The actual retained 05:15:15 UTC production issue passes the original decoder and both cold/warm paths with identical full context and 25 points. Original validation takes 0.545 seconds; the first scoped decode takes 0.376 seconds and warm complete-file validations take 0.0241 and 0.0239 seconds. Total replay is 0.984 seconds under the original shared lock, with 89 full guard calls, no network acquisition, SQL, fitting or publication, unchanged resource events and terminal cleanup (`qualify-production-point-reuse-real-a02-result.json`). The first diagnostic incorrectly prohibited stdlib's local socket capability probe; its failure is retained. The corrected diagnostic allows only local allocation/ephemeral loopback bind while retaining refusal of actual connect, DNS, send and database/subprocess access. It records two local setup events and no forbidden operations.

The qualified source has been staged against the unchanged genuine 00:00 UTC model and entered the original reserved activation lifecycle. This paragraph does not claim activation or natural publication. The 05:26 API baseline confirms current production weather, sensitivity, daily PV and performance responses. Nominal/profiled storage remains unavailable because the original AC-load evidence expires during processing; calibrated energy remains available. The sensitivity worker's natural 05:18 cycle also succeeds, preserving report `26c58f01ded63f8cd7225703e4eaf716e5df08007ddc7040ee57165b2e7c6126` and expiry 07:15:15. See `model-api-before-points-20261029T0526.json`.

The point-reuse deployment subsequently completed successfully. Independent parent verification at 05:28:10 UTC confirms deployment `cd09e40963e4c4e698c8b7d055cf08f400a1d6a7e030d942cd30bfd184c22b32`, exact five-file selection, all unrelated definitions preserved, restored timers, inactive/PID-zero external owner, collected controller scope and unchanged event counters. The genuine model/fit is unchanged; no fitting or actuation occurred. See `production-point-reuse-deployment-result.json` and `production-point-reuse-parent-terminal.json`. Natural publication remains pending.

The first natural point-reuse cycle (05:29:45–05:30:45 UTC) succeeds with verified thermal delivery and complete observer/advice/chronology/profiled/trajectory publication. Basic nominal storage and load-profile storage are now conditional/available, retaining the genuine declared 20.48 kWh bank; calibrated energy remains available. All three exact cache bodies are served by their live UI APIs and expire at the original 05:45:15. The original AC-load source expires 05:30:33.987; energy is actually assessed at 05:30:28.185362, leaving 5.802 seconds of genuine source freshness. No expiry was extended. The following scoring cycle returns scored=1/current_revision_scored=15 and exits zero. See `production-point-reuse-natural-cycle-a01.json` and `production-point-reuse-first-cycle-journal.json`. A second cycle and the next genuine scheduled fit remain to be observed.

The second natural cycle (05:34:45–05:35:45 UTC) again completes in 60 seconds. All three matching energy products are fresh and served byte-for-byte by the UI; nominal/profiled storage remains conditional/available. AC-load evidence is assessed 5.744 seconds before its original expiry. Remaining-today PV is correctly 0 kWh at local night while the full 24-hour projection is 22.3009 kWh. Together with the retained actual PostgreSQL acquisition/snapshot-writer evidence and natural sensitivity publication, this completes task 4.3. See `production-point-reuse-natural-cycle-a02.json`. Generic observation remains constrained by its original short-lived inputs and authority defaults; no actuation, probability or physical-calibration claim is added. The genuine scheduled fit, private stack and scoped integration remain open.

The fresh private case `sensor-pressure-witness-20261029-a01` records 189 exact original launcher health checks, all passing; minimum available RAM is 7101415424 bytes, maximum PSI avg10 some/full 0.42/0.42. This does not recover the unknown old refusal readings. The current case instead demonstrates OpenHAB PID-limit events (96 under its unchanged 128 cap) and a retained MQTT BrokerHandler initialization failure while starting RxJava scheduler threads. All eleven Python cases fail at the original 180-second module readiness setup (181.20 seconds total); no browser tests run. The external observer exits on `caps_changed` before Java snapshot; no dump signal is sent, so no thread-dump attribution is claimed. Both original and supplemental terminal checks pass: seven exact IDs/scopes gone, production and volumes preserved, guardian/store cleared, lock free, immutable38/helpers unchanged, mutable MQTT state recorded truthfully. See `openhab-pressure-witness-20261029-prep/parent-diagnostic-result.json` and the private case logs. Task 3.2 is complete; startup repair/full qualification remain open. Improve cap-mismatch diagnostic detail before selecting another source-attribution case.

# Empty cgroup startup correction

The prior exact-cap case retained a private OpenHAB cgroup at 05:46:47.053325 UTC with populated 0, empty cgroup.procs, memory.current/peak and pids.current/peak all zero, zero memory/PID events, and inherited/default memory/swap/cpu limits before Docker configured it. Its later running cgroup received the original reviewed limits. The observer mistook this never-populated configuration interval for drift and terminated before the JVM appeared. Eleven actual Python cases then failed original readiness; no browser or thread-dump credit applies. Both terminal verifiers pass.

The corrected observer records such an exact never-populated, event-free and identity-stable generation separately as pending. It never enters the running-cgroup/JVM intervention path on that row. Once any process has run, all original cap checks remain mandatory. A populated/written/event-bearing mismatch still refuses, including after cleanup. The correction performs no cgroup write, signal, lifecycle change or deadline/cap extension. Nine focused fixture cases cover actual empty startup, strict-default behavior, population/procs/past task/past memory/PID event/memory event refusals and correctly capped running work. Exact input files remain unchanged.

One fresh case sensor-startup-witness-20261029-a01 and nonce b7000000000000000000000000001204 will use the unchanged full seven-service/eleven-Python/two-browser workload, launcher pressure witness and original bounded first-PID-event thread-dump conditions. Prior cases and immutable38/retained volumes remain preserved. Original and supplemental terminal checks remain mandatory. No Java pool tuning or feature removal is included.


The first corrected-observer launch (`sensor-startup-witness-20261029-a01`) stops before create intents or manifest; the original controller hides its exception. No cause is asserted from the observed scheduling coincidence. The observer expires its original manifest wait without a signal. Independent pre-create terminal proof confirms no private fixture containers, preserved seven production fingerprints and retained volume metadata/content, immutable38 unchanged, controller/observer gone and real admission lock free (`precreate-terminal.json`). A fresh diagnostic entry calls the unchanged controller main and records exception type/message/sites without locals before returning the same failure; success and lock-refusal returns remain unchanged in three fixture checks. It preserves the original source, guard, cleanup and complete workload. Fresh unique case `sensor-startup-exception-witness-20261029-a01` is scheduled only in a naturally quiet interval after completed terminal verification.

# Observer bound to original confirmed container starts

The prior fresh case reached actual Docker initialization with a populated MQTT cgroup (two tasks, 786432 bytes) while inherited/default limits were still visible. Its retained exact mismatch proves that an empty-only exception does not cover this setup phase. No thread-dump signal was sent. The unchanged original controller later failed Python readiness, and both terminal verifiers passed. The pre-receipt setup interval is not claimed as cap-qualified.

The original guardian already writes container-caps.json only after Docker start/restart returns and container_caps validates the exact container ID, init PID/cgroup and all reviewed running limits. The observer now binds to that existing measured receipt. Before a service has such a receipt, its complete cgroup telemetry is retained separately as unconfirmed/pending and cannot enter the JVM intervention path. Once confirmed, the observer applies the same strict running cap check; wrong identity, unknown service, wrong receipt limits, disappearing confirmed receipts outside cleanup, and current running cap drift still refuse. Original first-PID-event, first-sample-zero, startup age, source/pidfd/signal mode, shared ownership and dump deadline requirements remain unchanged. No controller, workload, cap, threshold, JVM pool or feature changes are made.

Eight fixture cases exercise pending populated setup, confirmed drift refusal, confirmed running acceptance, absent/valid receipts and receipt identity/limit/service refusals. The unchanged controller entry still records actual exceptions without locals. The fresh case sensor-confirmed-start-witness-20261029-a01 and nonce b7000000000000000000000000001206 are single-use. Original and supplemental terminal verification remain required. This is diagnostic source attribution, not completed private-stack qualification.


The confirmed-start observer captured one complete 124-Java-thread dump in 0.275923 seconds (150088 bytes, SHA cfa1390fb914c4d8f02d58d64adf65f985d5f52e02658fc05c4d308c7abe4b35). All five workers in each of common, discovery, file-processing and mdns-addon-suggestion-finder are timed-waiting at the first PID event. Census/dump differences are retained (one unmatched before, six after); no total attribution beyond those observations is claimed. Both terminal verifiers passed. See `openspec-runtime-20261028/openhab-pool-diagnostic-parent.json`.

An isolated candidate d8df38d adds an extra read-only config bind, which conflicts with the pinned image entrypoint unconditional recursive chown. Its Python ownership preflight finds a stopped fixture; the external observer also rejects a stale source-commit pin before capture. The exact seven-container terminal verifier and all pre-result supplemental checks pass; `early-observer-terminal.json` truthfully records the absent observer result/no signal. The failed source and case remain retained.

Corrected signed source 44c4a57 uses the existing writable configuration directory and restores the original Compose/bind contracts. All five original guardian/protocol helpers remain byte-identical. The tracked four-pool profile (two workers per observed pool) is copied only into the isolated private configuration and sealed separately; the original 38 immutable files and retained originals remain preserved. All 489 maintained guardian/controller cases pass in 5.371 seconds under original 256 MiB/24-task/90-second limits, with unchanged event counters and terminal scope cleanup. Fresh case `sensor-pool-profile-20261029-a02` has the explicit correct source pin, original seven-service/eleven-Python/two-browser workload and original limits. Actual qualification remains pending. The 06:50 genuine native fit has priority; cancel this private attempt through its existing controller/guardian cleanup if still active at 06:47, without claiming qualification from cancellation.

The actual enabled `thermal-native-six-hourly.timer` starts the repaired daily fitter at 06:50:00 UTC without an operator start. It executes a genuine fit over Oct21 06:00–Oct29 06:00; fit evidence is created 06:51:29.501519. The normal handoff selects artifact b21275bfabeb5fbfb8033295deeabfcf512229b406c579efee96abd1eb0ac101, deployment 1518ccbc22e8695f7d8ac5761cc00d72e1993289e2ed8e054962f4636952536c, runtime 88cb3fb10ea74643ae9f00248ba58b830bd3e9eb9008683c45a4232551f1388b, source 39b0070. The service exits zero at 06:57:47; independent proof verifies all five family files, restored timers, inactive/PID-zero owner, collected scope and preserved unrelated definitions. A read-only 1181-sample scope monitor observes unchanged event counters under original 2 GiB/48-task limits.

The first new-model 07:00:15 origin has the exact new stage/deployment/artifact binding and verified delivery; its whole observer cycle succeeds in 60 seconds. The next 07:05 cycle again serves matching unexpired basic/profiled/calibrated energy products byte-for-byte through the UI. The following scorer returns scored=1/current_revision_scored=0: eligible retained history was scored, while the new model has no mature one-hour forecast yet. No new-model maturity, model graduation or physical effect is claimed. This satisfies task 4.4 actual fit/publication/eligible scoring criteria with the distinction explicit. See `scheduled-six-hour-fit-parent-terminal-20261029T0650.json`, `scheduled-fit-first-natural-cycle-journal-20261029T0700.json` and `scheduled-fit-first-natural-publication-parent-20261029T0700.json`.

Private configured restart a03 confirms the four initial pool values are two and its first-event census also shows those four pools at two; the earlier startup-default hypothesis is not supported for that restart. Its later complete dump instead shows five timed-waiting ThingManager and four timed-waiting SafeCall workers at the limit. Both terminal verifiers pass. Signed candidate 9562464 adds those two observed pools to the profile. Exact backups precede offline configuration changes only in the stopped dedicated test volume and private copy; production, original immutable38 and volume identities are unchanged. All private work remains stopped through the genuine production fit. No private full-workload qualification is claimed yet.


### 2026-10-29 private startup profiles and post-fit UI audit

Private cases a04 through a06 preserve the original seven services, eleven Python
cases, two browser cases and all original caps/deadlines. Each reaches the
OpenHAB task ceiling and fails the 180-second sensor readiness fixture; no
Python test bodies or browser qualification are credited. Both exact terminal
verifiers pass for each case. Case a06 captures its existing bounded stderr tail
before its single permitted JVM dump, within the same unchanged dump window.
It shows failed OH-items allocations and the uncaught OH-OSGiEventManager
failure in BasePoolExecutor.resizePool. The shared events setting is a minimum,
not a hard maximum. Counter labels such as OH-events-48 do not mean 48 concurrent
workers. Its complete dump also records eight idle AsyncProxyServlet workers.

Exact installed 5.2.1 metadata and versioned upstream executor source establish
the supported items queue and proxy initialization setting. Signed candidate
dcd01c8 adds items=2 and proxy maxThreads=4 under the installed DS component
configuration PID. The image, Compose/binds, all six frozen helper bytes,
features, caps and workload remain unchanged. Exact prior ConfigAdmin/profile
bytes and metadata, plus the proxy configuration's original absence, are saved
before stopped-fixture preparation. The original immutable38 inputs remain
unchanged. Production OpenHAB is not modified. The fresh a07 case and nonce
b7000000000000000000000000001213 are currently executing; a first PID event has
already occurred, so this candidate has not established zero-event capacity.
No task 3.3 or 3.4 completion is claimed. Receipts and source references are under
openspec-runtime-20261028/items-proxy-profile-offline-state-before/,
installed-pool-source-reference-20261029/, and sensor-pool-profile-20261029-a07/.

The final deployed UI has also passed a fresh post-fit live audit: all eighteen
supported route/viewport combinations, 466 live Items, zero failed reads,
console errors, page exceptions or attempted equipment writes. Original
configuration and source/resource-event checks pass and the browser scope is
gone. See openspec-runtime-20261028/ui-post-fit-route-audit-parent.json and
live-post-fit-supported-routes-20261029/result.json. This verifies task 6.2
against the deployed release after the genuine 06:00 model fit; guarded Main
integration remains separate and incomplete.

The 08:01 naturally scheduled current scorer succeeds with scored=1 and
current_revision_scored=0. Its original maturity rule includes five minutes
after the forecast's target. The 08:06 rotating historical slot reports
waiting/scored=0/current_revision_scored=103 for its selected archived model;
that count is not new-model mature scoring evidence. Preserve this distinction
when reading journal counters. No manual scoring job was started.


The 08:11 **current** score slot subsequently returns scored=1 and
current_revision_scored=1. Independent readback of the artifact-specific report
binds artifact b21275bf… and assessed_at 08:11:23.932908 to one completed one-hour
model outcome (other horizons zero). Report SHA is
09bbc5bec77cdc0892fc37876200153b13de269bb175ba57322bd06483aeb0c2.
See scheduled-fit-current-scoring-20261029T0811.json and
scheduled-fit-current-report-20261029T0811.json. This is the new genuine fit's
first mature outcome, distinct from the 08:06 archived-model count. It establishes
mature scoring, not graduation or an equipment effect.

Private a07 confirms four proxy workers, one Items worker and a complete
122-Java-thread dump, but readiness still fails. Both exact terminal verifiers
pass. Signed candidate 4a9afb9 switches the proxy to Jetty's documented existing
server executor and serializes the four measured discovery/file/ThingManager
pools; Common and SafeCall retain two workers. Exact installed 9.4.58 source
shows ContextHandler exposing this executor. Offline changes have exact backups
in shared-proxy-profile-offline-state-before/. Fresh a08/nonce …1214 retains all
six unchanged helpers, seven services, thirteen tests and original bounds. It
is currently running and has already recorded a first PID event; zero-event
qualification has not passed.


### Measured provisional allocation and actual database-outage finding

The original per-service 128-task OpenHAB profile does not qualify: both shared
and default event paths reach the ceiling. Cases a08 and a09 each execute all
11 Python bodies, with four passes and seven delivery timeouts; both original
and supplemental cleanup verifiers pass. No browser credit is claimed. The
constructor-only vendor experiment is uninstalled and insufficient: baseline
first-use minimum reproduction succeeds, but the attempted correction still
runs out of tasks when the original shared queue resizes with sequential queued
callbacks. Its failed builds, bytecode, inputs and candidate remain retained in
openhab-executor-constructor-diagnosis-20261029/. The installed core jar remains
68e37d9c0eaf2343603082b12f460523f328f6f02efbe9a99b19502fb44f78ed.

The harness explicitly marks per-process allocations provisional. Measured
controller peak17 and OpenHAB exhaustion justify moving16 controller slots to
OpenHAB while retaining all aggregate budgets: Python32+guardian8+external208
and browser48+guardian8+post-retirement192 both equal248, under original256 with
eight spare. All memory, CPU, swap, images, seven services, thirteen test bodies,
deadlines, private-input/volume and cleanup gates remain. This is a declared
new candidate, not qualification of the old per-service split. Design/task
wording now preserves the aggregate envelope and requires the revised split to
pass the complete actual workload and separate guardian8 recovery.

Signed 81f5d64 passes all489 maintained controller/ownership cases in5.397s,
original256MiB/24task/90s envelope, unchanged resource events and collected scope.
The first attempted observer refuses before readiness or case creation because
managed work is active; balanced-a01-precreate-refusal.json records no launcher,
containers or signals. Fresh balanced a02 runs the complete11 Python bodies:
10 pass, one database-outage recovery case times out. All observed service PID
and memory event counters remain zero; OpenHAB peaks134 and controller17.
Both exact terminal verifiers pass and no dump signal is sent. The private view
is explicitly simulation/observation_only and online; no physical qualification
is claimed.

The remaining test's exact logs show the ingestion worker deliberately exits
InterfaceError without acknowledging the packet after PostgreSQL stops. The
fixture's required Docker restart=no has no replacement process supervision;
production Compose uses unless-stopped. Signed e07643f adds a fixed in-container
worker supervisor, preserving guardian-only Docker lifecycle and the ingestion
8-task cap. It forwards stop, waits for the worker, retries failure after1s,
and stops during backoff or clean exit. The extra read-only private source copy
is sealed separately from original38 inputs, SHA
bc17d680284e86e06bf6518ff43fc693d1650d02ddc4b17ef855ca850e4fbe9c.
All489 existing cases plus4 meaningful restart/shutdown cases pass (493 total,
5.406s, unchanged original small test limits/events and terminal scope gone).
See supervised-budget-covering-parent.json. The new supervised a01 case,
nonce …1218, is currently running the complete unchanged workload. No full
qualification or guardian recovery completion is claimed yet.


The supervised a01 run passes all eleven unchanged Python cases in238.03s,
including actual unacknowledged-packet recovery after PostgreSQL restart. Every
observed service memory/PID event counter remains zero; no dump is triggered.
Both exact terminal verifiers pass, including unchanged read-only supervisor
identity, original38 private files, preserved production/volumes, unit GC/store0
and free real admission lock. Its browser bootstrap refuses before Chrome:
stack_ownership.__main__ incorrectly still requires all six services running
after the two deliberate retirements. This is not a browser capacity failure.

Signed9318fd6 adds the explicit browser bootstrap mode. It first checks all
current container ownership/configuration, requires the four live dependencies,
verifies the immutable original lease and stable armed/browser receipt including
all seven admitted IDs, then reuses DockerBackend.browser_ready's existing exact
retirement/cgroup-empty proofs. The default Python bootstrap still requires all
six services running. Actual test bodies remain unchanged; only the browser
entry helper selects the phase-specific bootstrap. All502 maintained Python
cases plus the2 affected existing JavaScript tests pass, with unchanged event
counters and both scopes collected (browser-phase-covering-parent.json).
Fresh browser-phase a01/nonce …1219 now runs the original full workload again.
Neither browser completion nor guardian8 recovery is claimed yet.


2026-10-29 10:09 UTC: browser-phase a01 passed all11 Python bodies (238.21s)
and acknowledged all three phase transitions, but its original512MiB controller
OOM-killed Node in the private browser scope. This is retained as a failure,
not browser qualification (private-browser-512m-oom-20261029.json). The guardian
subsequently recovered cleanup; the first exception is not independently known.
The observer also correctly retained an empty retired Redis generation but its
old cap check treated that generation as active drift. The read-only observer
now accepts only positively stopped, exact-ID, stable-phase, empty retired groups;
all running/nonempty/unrelated/wrong-identity/drifting groups remain strict.
Eleven meaningful observer fixtures pass under original small test limits.

Signed ab63aac assigns1024MiB to the private controller while retaining the
original6GiB/256tasks/8CPU/no-swap aggregate limit,3GiB host reserve,256MiB
uncertainty, all seven services, original11+2 bodies, and all deadlines. Full
commitment3136MiB, residual ceiling2752MiB, initial host requirement6208MiB.
All502 maintained Python cases pass in5.482s with no limit events and terminal
scope gone. The unused a01 window expired without launch. A02 refused before
container creation because cached pool memory exceeded the original aggregate
headroom; its observer expires naturally without intervention. Bounded reclaim
in the idle owned work cgroup used the existing admission lock, no global cache
drop or file deletion, and preserved all limits/event counters. Receipts retain
actual requested and observed values, including partial_EAGAIN. Fresh a03,
nonce ...1222, has now created the seven private IDs and is running the complete
workload. Full browser and controlled guardian recovery remain unclaimed.

The immutable analytics-reader-release-2fd49d818476 passes all53 reader tests
in0.459s with original256MiB/24tasks/90s and zero observed events. Its only runtime
delta recomputes health after current forecast substitution while retaining
independent degraded components. Both reader selectors were installed10:07:56,
with exact original guards, backups,159 other unit/private files unchanged,
no writer changes, and no equipment commands. Natural publication verification
is pending. See analytics-reader-health-deployment-{before,result}.json.


2026-10-29 final repair completion (UTC). Evidence root remains
artifacts/post-upgrade-repairs-20261024.local/openspec-runtime-20261028.

Sensor source9060ef3:544 maintained cases pass, original256MiB/24tasks/90s,
zero observed events and scope gone. Current observer:18 cases pass0.32s.
Original full sensor-final-budget-20261029-a01:11 Python pass239.33s; both
unchanged browser bodies pass9.831s, zero unexpected/skipped/flaky. All four
phase acknowledgements and original full resource checks pass. Original and
supplemental terminal verifiers prove exact7IDs/cgroups gone, production7 and
retained volumes unchanged, original38 private inputs plus profile/supervisor
preserved, guardian GC/store0 and free actual lock. Independent external
observer timeout is retained and is not complete browser telemetry credit.
See sensor-final-budget-parent-full-pass-20261029.json and original case files.

Single same-source recovery: sensor-guardian-recovery-20261029-a07, nonce...1236.
All11 Python bodies pass249.33s; controller stopped only after four exact browser
phase acknowledgements. One guardian kill; actual PID874517 replaced by949231,
NRestarts1,8task/64MiB cap, stored original admission descriptor and real exclusion
held. Both guardian snapshots show zero memory/PID events. Original and independent
terminal checks pass. No repeated fault, no additional signal/lifecycle operation.
The wrapper's late READY race remains BLOCKED_NO_BYPASS in its original result;
guardian8-recovery-parent-adjudication-20261029.json separately proves all remaining
terminal facts read-only. Original root receipts and metadata are preserved;
byte-identical private publication copies are root-hash-attested. Diagnostic
coordinator RSS uses actual /proc/self VmHWM rather than inherited pre-exec rusage.

Main source: all73 exact targets applied through final-source-integration-20261029,
final-source-dependencies-20261029 and final-source-native-interval-20261029.
The initial older-checkout validation exposes10 missing qualified UI imports and
two stale browser test expectations. Their exact live-release dependency closure,
covering tests/fixtures, targeted contract corrections and optional native chart
interval fragment resolve them without overwriting unrelated modules or existing
precipitation/time-label edits. All original failures/copies remain retained.
Final exact-main writable copy:2398/2398 UI unit cases pass53.483s,544 helper
cases pass6.05s,53 actual integrated analytics reader cases pass0.22s. Fresh build
passes2.429s/866modules. Original1GiB/96tasks/600s UI and small Python budgets
remain; completed resource events unchanged and all owned test scopes gone.
See main-final-*-20261029-a03 resources/results, integrated-main-helpers-final-a01
and integrated-analytics-final-a01 receipts. Neither production UI bytes nor
private configuration is replaced by a temporary validation copy.

Production source39 remains installed with actual06:50 timer-triggered fit,
training through06:00, artifactb21275bf..., deployment1518ccbc..., natural07:00
publication and true08:11 current-artifact H1 score1. Final fresh11:40 issue is
model-bound to that artifact/runtime, all five actual installed family files match,
all three UI energy APIs equal their current cache bytes and remain unexpired.
Production weather and sensitivity HTTP200/unexpired. Forecast reader health is
ok; independent daily_source_quality_not_ok remains truthful. All four receiver
and OpenHAB temperature roles are fresh, same epoch, Bedroom reachable. A new
120-sample two-minute watch under load passes with no errors/expiry/resets;
maximum new receipt lag2.568s. Earlier600-sample ten-minute proof remains retained.
See final-live-runtime-readback-20261029.json, radio-under-final-load-parent-20261029.
The final natural forecast service exits0 and enabled six-hour/forecast/score/
geometry timers are restored. Two old code75 scorer deferrals caused by the
private test window are rerun with their original commands and limits; both
actually exit0. No failed system/user units remain. Wi-Fi wlo1 UP/LOWER_UP,
192.168.1.217; sudoers valid/newline restored, libmtp-runtime1.1.22 installed,
dpkg audit empty and no kernel errors since final private cleanup. See
final-host-health-20261029.json and final-runtime-terminal-and-scorers-20261029.

The deployed immutable UI release remains the one with3404 full tests,167 focused
checks and18 post-fit supported live route/viewport views, no unexplained failed
reads, runtime errors or control writes. Time64px left of energy, date14px first
row before Suggestions, Today on its own unbroken energy row, restored labels,
landscape forecast labels/zones usable. No later live UI source change invalidates
that audit. Current full source validation is recorded separately above.
Equipment actuation remains disabled. No security scan/hardening/Superpowers
workflow was invoked. OpenSpec tracks all24 tasks with separate source, test,
deployment, natural-operation and qualification evidence.
