# Isolated sensor qualification resource contract

## Current three-retirement candidate, 2026-10-29

Keep OpenHAB144tasks: a136-task run subsequently hits that cap during startup.
Python controller32tasks, browser controller60, guardian8. Complete all original
11 Python bodies and prove child exit0 before any retirement. Retire the exact
ChirpStack, Redis, then completed one-shot simulator IDs with durable phase
acknowledgements and positive stopped/PID0/cgroup-empty proofs. The browser
stimulus publishes directly to MQTT and does not start the simulator container.
Once retired none of the three may start/restart; uncertain replies or recovery
perform cleanup only. Browser capacity is restored only after all three proofs.

All seven services and original13 bodies remain. Task commitments are204
external during Python and180 after all three retirements:32+8+204=244 and
60+8+180=248, leaving the original eight-slot uncertainty margin under256.
No container memory or CPU reservation is released. Controller1024MiB and
external2112MiB retain3136MiB commitment, original6144MiB aggregate/no-swap,
3072MiB host reserve,256MiB uncertainty,2752MiB residual ceiling and6208MiB
initial host requirement. Original readiness/browser/overall deadlines stay.
The full uninterrupted workload and separate post-retirement guardian8 recovery
must pass. Old lower-cap attempts and their failures are retained below.

The first real three-retirement browser run passes the1280x720 body, including
real SSE/transitions and full navigation. Its first page setup hits56tasks and
times out. Move four task slots from private PostgreSQL24 to20 (observed full
workload peak17) and browser56 to60. No memory, CPU, image, feature or deadline
changes. The original13 bodies and all resource events must pass in a fresh run.

## Current balanced candidate, 2026-10-29

The first real browser startup subsequently exhausts the provisional controller
512MiB cap: the kernel records two Node OOM kills in that exact scope. The
guardian recovers and cleans up; this is not host-wide memory exhaustion or a
passing browser run. Use the already established UI allocation of1024MiB for
the qualification controller. Keep the global6144MiB limit, no swap, original
256MiB accounting uncertainty and3072MiB host reserve. Conservative commitment
is now3136MiB (1024controller+2112external); allowable residual tightens to
2752MiB, and initial host availability must be at least6208MiB. The original
budget functions derive both stricter checks from the declared allocation.
No container memory reservation is released at retirement. CPU caps remain unchanged; task allocations below are the latest measured
candidate and require a new full run.

The allocations are provisional until the complete real workload passes.
The144-task OpenHAB /48-task browser split passes all eleven Python cases but
then exhausts the browser controller's task limit. The unchanged standalone
component browser bodies peak77tasks; consolidated browser services and bounded
Node/V8 pools reduce this without removing assertions. The single-process
experiment fails its second context and is not used. The new candidate keeps
OpenHAB at136tasks (observed prior peaks133–136), Python controller32, browser
controller56, guardian8. External task reservations are200 during Python and184
after the same two irreversible retirements. Totals are240 and248, respectively;
the256-task aggregate and at least eight unallocated slots remain unchanged.
No simulator reservation is released. All browser contexts and real SSE/state
transition assertions remain required. Only the disposable sensors project
consolidates GPU/network/audio services and bounds V8/background GC pools;
Node's worker pool and the Go Docker client's GOMAXPROCS are explicitly bounded
rather than inherited from the host. The first full bounded-browser run reaches
the real UI, then the unbounded Go inspection subprocess hits the shared task
limit; all11 Python cases pass and both terminal checks preserve production.
A fresh full run must qualify the additional Go-pool bound.

The launcher admission remains64 before containers start; exact manager and
kernel limits narrow to32 before any external lifecycle effect. Browser-ready
alone permits the fixed32-to56 handoff after both retirements.
Memory, CPU, swap prohibition, all seven services/images, thirteen test bodies,
deadlines, source custody, private inputs, retained volumes and cleanup behavior
remain required. Neither a successful old test nor this arithmetic qualifies
the new split; require the full uninterrupted run and separate guardian8 recovery
witness with zero new resource-limit events. The original per-service profile
below remains retained as historical evidence and did not qualify.

The first balanced run passes ten of eleven real Python cases with zero
observed memory/task-limit events (OpenHAB peak 134, controller peak 17).
Database-outage recovery still fails: ingestion deliberately exits without
acknowledging the packet after its DB connection breaks, but the private
fixture has Docker restart disabled. Production's restart policy supplies that
recovery. The private candidate therefore adds a fixed worker supervisor inside
the existing ingestion container. Docker restart remains disabled and every
container lifecycle action remains guardian-owned. The supervisor forwards
termination, waits for the worker, retries nonzero exits after one second, and
stops on clean exit or requested shutdown. Its additional process must fit the
same ingestion cap of eight. A separately sealed read-only copy of the tracked
supervisor is mounted into the unchanged image; the original 38 immutable inputs
and database/broker volumes remain retained. Require the original outage test,
all other test bodies and resource checks to pass; this is not yet qualified.

The supervised run subsequently passes all eleven Python bodies, including the
unchanged database-outage recovery case. All observed service resource events
remain zero (OpenHAB peak136, ingestion8, controller17). Its browser bootstrap
still invokes the earlier all-running Python preflight after ChirpStack and
Redis have been intentionally retired. Correct the browser bootstrap to use
the four running dependencies while retaining all original container ownership
checks, the immutable lease, and a stable durable `armed/browser` receipt.
Reuse the existing backend's exact-ID stopped/cgroup-empty retirement proof;
keep the default Python bootstrap at all six running services. Verify this
handoff and rerun both actual browser bodies. The refused browser bootstrap
does not establish browser capacity or completion.

## Original per-service candidate (historical)

This provisional test profile is source-only. Qualification requires an actual
guardian8 failure/recovery witness and a separate uninterrupted original11Python
plus2REST/SSE/browser run, with all resource and preservation gates passing.

The launcher still admits the controller at512MiB/64tasks/2CPU. Before starting
the guardian or any container, the controller narrows its exact owned user scope
to48tasks and reads back the manager identity and kernel limit. OpenHAB stays
1152MiB/128tasks/2CPU throughout; heap768MiB and all JVM options stay unchanged.

| Member | MiB | CPU | Python tasks | Browser reservation |
| --- | ---: | ---: | ---: | ---: |
| Controller and all children |512|2|48|64|
| Guardian |64|0.5|8|8|
| OpenHAB |1152|2|128|128|
| MQTT |64|0.25|8|8|
| PostgreSQL |256|1|24|24|
| Ingest |192|0.5|8|8|
| Redis |64|0.25|8|0 after irreversible retirement|
| ChirpStack |192|1|8|0 after irreversible retirement|
| Simulator, reservation retained |128|0.5|8|8|
| Committed total |2624|at most8|248|248|

The configured seven-container PID caps sum192. The simultaneous combination
controller64+guardian8+all192 is forbidden: it would be264. Python uses48+8+192;
browser uses64+8+176 only after both retirements. Memory and CPU reservations
remain conservative through retirement. Global6144MiB/8CPU/256tasks/no-swap,
per-managed-job maximum128tasks,8unallocated tasks and256MiB uncertainty remain
unchanged. The original residual ceiling is3264MiB and initial available-host
requirement5696MiB; continuing MemAvailable must remain at least3GiB. Cache/slab
accounting, original lock, drained-pool and launcher gates remain intact.

After the actual Python child exits0 and complete JUnit proves exactly11cases
with0failures/errors/skips, the original main controller alone may send
`retire-chirpstack-for-browser`, then `retire-redis-for-browser`. Each fixed
request carries only the existing immutable manifest digest and performs one
exact-ID `stop?t=10`, inside the original30s client/35s server bounds. The
qualification-only `workload_phase` journal advances through `python`,
`retiring-chirpstack`, `chirpstack-retired`, `retiring-redis`, `browser-ready`,
and `browser`. Lifetime `phase` and pending-action custody remain separate.

Both retired services lose all lifecycle authority when retirement begins.
Each must retain its original identity and configuration, inspect as
Running=false/Pid0, and have an absent cgroup or populated0 plus pids.current0.
Only durable `browser-ready` acknowledgement permits the exact original64-task
restoration. That handoff alone permits manager/kernel48or64 while systemd
applies it. `enter-browser` requires manager/kernel64, both retirements and all
four browser dependencies running; its durable acknowledgement precedes the
unchanged browser command. No transition is retried after a lost reply.

Every known recovered phase is cleanup-only. Quiesce the original controller
scope and its root launch clients, remove all seven immutable IDs with v=0,
positively prove all IDs and cgroups absent/empty, persist terminal, then
revalidate source/mode/lock/context before FDStore removal/barrier/count0.
Unknown state or changed ownership retains the original OFD for reconciliation.
Retired containers stay in the original inventory until this final cleanup;
all three retained volumes and production inventory remain protected.

Lifecycle proof remains controller1024MiB/96tasks, guardian64MiB/16tasks,
external128MiB and MQTT-only. Its receipt schema has no workload phase and its
protocol exposes no retirement or restoration operation. Readiness180s,
browser30s, both viewports, the original1800s lease, all thirteen test bodies,
images, credentials, ports, policy, epochs and TTL120 remain unchanged.

Helper passes cannot establish actual128-task OpenHAB capacity, Python48,
browser64/512MiB or guardian8 suitability. Parent-owned observation must capture
startup/restart/simulator/browser peaks and zero new memory/PID events through
cleanup, actual post-retirement guardian recovery, terminal unit GC, original
flock freedom, and source/private-input/volume/production preservation.
# Private OpenHAB startup pool profile, 2026-10-29

The retained first-PID-event diagnostic at
`artifacts/post-upgrade-repairs-20261024.local/sensor-confirmed-start-witness-20261029-a01/`
contains a complete 124-Java-thread dump captured in 0.276 seconds, with before
and after task censuses. It identifies five workers each in the common,
discovery, file-processing and mDNS suggestion-finder pools. Those workers are mostly
waiting while MQTT initialization fails to create its scheduler thread at the
original 128-task container limit. Both exact cleanup verifiers passed.

The configured restart also shows five timed-waiting `thingManager` workers and
four timed-waiting `safeCall` workers at a later PID-limit event. The first four
pools are already at two in that capture; no startup-default override was
observed. The candidate therefore includes these two additional measured pools.

The isolated candidate copies the tracked profile file
`deploy/lorawan/openhab/qualification-threadpools.cfg` into its existing writable
private configuration directory, with two workers for
each of those six named pools through `org.openhab.threadpool`. Work remains
queued through the same providers and executors. All seven services, features,
eleven Python cases, two browser cases, guardian allocation, memory/CPU/task
caps, deadlines and retained volumes remain in the qualification workload.
The original private input files remain unchanged; this candidate uses an
isolated verified copy. The added profile is sealed separately from the original
38 immutable inputs. The image requires writable configuration during its
startup ownership step; an extra read-only bind is incompatible. The explicit
controller root selects this worktree.

This is a candidate profile until the full actual workload and resource-event
checks pass. Focused source checks alone do not establish startup, device
delivery, restart recovery or browser qualification. Production OpenHAB is not
changed by this private profile.

Before a configured-start qualification, seed the six initial ConfigAdmin
values while the private fixture is stopped, preserving the exact prior file
and its metadata. Retain the tracked configuration file for subsequent starts.
Record the actual six initial values in the pre-start receipt. Existing pools
can retain excess workers during their idle interval, so installing the file
during a startup is not proof that its initial allocation used the profile.

The six-pool attempt reaches a more specific failure: `OH-OSGiEventManager`
terminates while creating `OH-eventexecutor-6-1`, leaving sensor Items at NULL
despite connected ingestion and a loaded supervision rule. The exact installed
5.2.1 `EventHandler.createExecutorRecord` bytecode passes the `events` key to
`ThreadPoolManager.getPoolBasedSequentialScheduledExecutorService`. Setting
`org.openhab.threadpool:events=2` enables that supported shared pool while
retaining each subscriber's sequential executor. This seventh profile option
does not remove subscribers or change their work. Include it in the initial
ConfigAdmin values before qualification. The retained bytecode SHA is
`1cc7a6f71d060ba58cc1360ecf2d9165276c6606deac4e4fb237c29d316bccda`;
`installed-event-pool-analysis.json` records the literal and call site.

The seven-pool diagnostic still reaches the task ceiling. Its pre-dump stderr
records failed `OH-items` allocations and an uncaught event-manager failure in
`BasePoolExecutor.resizePool`. The shared `events` value is a minimum; that
executor grows with pending work and is not capped at two threads. The same
capture shows eight idle `AsyncProxyServlet` workers. The next candidate adds
the supported `items=2` queueing pool limit and the proxy servlet's supported
`maxThreads=4` initialization setting. Its installed DS configuration PID is
`org.openhab.core.ui.internal.proxy.ProxyServletService`; the `service.pid`
property `org.openhab.proxy` is not an explicit DS configuration PID. Seed the
exact component configuration before startup, backing up existing bytes or
recording absence. The proxy remains enabled. Exact-version upstream source
and installed component metadata are retained in the repair artifacts.

These additions remain unqualified until the original complete workload passes
without new resource-limit events. Do not apply this private profile to
production OpenHAB on the strength of a thread dump or source inspection.

The item/proxy-four attempt confirms four actual proxy workers and one Items
worker, but still fails while growing the event pool and creating another
scheduler. Its complete dump shows both file-processing, discovery and
ThingManager workers parked; both mDNS finder workers are performing finite
blocking discovery calls. The next candidate serializes those four pools at
one worker, retaining their queued work. Common and SafeCall retain two workers.
The proxy now uses Jetty's documented `maxThreads=-` option to share the existing
server executor instead of allocating another private pool. Exact installed
Jetty 9.4.58 source shows ContextHandler exposing that executor and
AbstractProxyServlet selecting it for `-`. This preserves the proxy and its
requests, with the server's existing pool sizing. The seven-service workload
and original resource/deadline/cleanup gates remain required; this candidate
has no qualification credit until its actual run passes.

The shared-proxy attempt reaches all eleven Python bodies (four pass, seven
time out), but its event manager still fails at the task ceiling; browsers are
not run. Both terminal verifiers pass. The installed shared-executor bytecode
also omits initial minimum-size assignment. An isolated attempted correction
reproduces that omission but still exhausts a small task allocation while
queueing sequential callbacks: `submitToWorkQueue` counts every queued callback
when resizing, so a minimum-size correction does not bound its growth. No
patched vendor binary is installed; preserve the unsuccessful build/regression
artifacts rather than treating the constructor correction as qualified.

The current candidate therefore sets `events=0`, selecting the installed
ThreadPoolManager's supported default single-thread executor per subscriber.
It preserves every subscriber, sequential delivery and callback; this disables
only the optional shared-executor implementation. Retain the measured pool and
shared-proxy settings above and rerun the entire unchanged workload. Original
caps, zero-event qualification and cleanup requirements still apply.



The Go-bounded full case again passes all11 Python bodies but the browser's
Python stimulus plus CLI still exhausts56tasks; Compose reads then time out.
The browser-only inspection path now translates the same closed read commands
to the existing bounded Docker API client. Each read verifies the original
immutable lease, exact armed/browser receipt, and fresh Compose source bytes;
rendered configuration comes only from that admitted document. Container,
image, volume and foreign-consumer inventories remain fresh and continue through
the existing full validation. No lifecycle writes are added and unsupported
commands refuse. Python integration retains its original CLI path. This removes
inspection subprocess overhead, not checks, features, services or test bodies.
