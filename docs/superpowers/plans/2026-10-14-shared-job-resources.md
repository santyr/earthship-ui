# Shared Job Resources Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for inline implementation. Keep the full PR #3 objective active; this is its operational resource allocation work, not a replacement objective.

**Goal:** Let development and native ML jobs share available host capacity without independently overcommitting RAM or starving jobs behind tiny fixed CPU quotas.

**Architecture:** A systemd user slice supplies a combined ceiling. A serialized launcher reserves each active unit's maximum RAM from fresh kernel cgroup accounting before admitting another unit. CPU weights distribute spare capacity automatically; application worker counts remain explicit. Kernel ceilings continue to apply if the launcher exits.

**Tech Stack:** Python standard library, Linux cgroup v2, systemd 255 user units.

**Spec:** User's October14 instruction: more resources are acceptable in development and production; combined jobs must not overwhelm the host. Dynamic individual limits should maximize performance within a safe margin. Existing numerical/model/actuator contracts stay unchanged.

## Global constraints

- Initial aggregate MemoryMax:6GiB, MemoryHigh:5GiB, MemorySwapMax:0, CPUQuota:800%, TasksMax:256. New jobs require a3GiB host reserve. These are operational configuration, not fitted model constants.
- Fixed maximums are emergency ceilings. Admission also accounts for live MemAvailable, active unit commitments and charged pool memory. Host swap remains enabled.
- CPUWeight favors production over development. No promise that CPU quota alone guarantees latency or that unrelated services cannot exhaust the host.
- Managed launcher pressure monitoring uses ten-second PSI averages: some<=5%, full<=1%; a running job stops if available RAM falls below1.5GiB. Sample once per second. Existing production guards are unchanged until migration.
- Never lower a running unit's hard memory limit. On sustained pressure defer new work; existing kernel bounds and invocation pressure/deadline checks remain active.
- Keep native numerical fitting serial initially. More CPU quota allows a serial worker to use a whole idle core; it does not make numerical code parallel.
- Every managed job must reside in the same pool, including agent-launched tests/builds. Existing unrelated services remain outside it and are accounted for through host headroom.
- Preserve archived numerical/model receipt sources. Legacy collection/fit paths requiring exact leaf limits receive compatible finite leaf budgets inside the pool until deliberately migrated.
- No fitting, actuator changes, secret publication, off-host execution or recovery exercises are required to implement or verify admission.

## Review focus

- Two launchers must not reserve the same free RAM: serialize discovery through confirmed unit creation.
- A job growing from present usage to its hard limit must already be reserved. Host admission subtracts full sibling limits without crediting separately sampled usage; this intentionally trades some concurrent capacity for race-free admission accounting.
- Memory charged to the parent outside observed child units must count against the pool.
- Failed launch, vanished unit and launcher interruption must not silently release a still-running unit's reservation: kernel unit state is authoritative.
- An unavailable/uncapped/foreign cgroup must refuse new admission, not imply zero usage.

## Task 1: Memory admission calculation

Files: `openhab/scripts/household_job_budget.py`, `openhab/scripts/test_household_job_budget.py`.

- [x] Test exact allocations from host reserve, aggregate cap and outstanding per-job growth; test refusal below a requested minimum and bounded reduction from preferred size.
- [x] Implement `admit_memory(*, available_bytes, pool_limit_bytes, pool_used_bytes, jobs, minimum_bytes, preferred_bytes, reserve_bytes)` returning an allocated byte count or a typed admission deferral. Each job provides current usage and its finite limit. Account for unassigned parent charges. Round allocations down to whole MiB.
- [x] Reject malformed counters, duplicate job identities, nonfinite/unlimited budgets and current usage above the declared cap. Zero active jobs is valid.
- [x] Verify with `PYTHONPATH=openhab/scripts python3 -m pytest -q openhab/scripts/test_household_job_budget.py`.

## Task 2: Serialized systemd launcher and resource snapshot

Files: `openhab/scripts/household_job_pool.py`, `openhab/scripts/household_job_launch.py`, `scripts/run-household-job.py`, `openhab/systemd/user/earthship-work.slice`, corresponding focused tests.

- [x] Read actual pool and immediate child unit cgroups; bound directory traversal and reject uncapped/unrecognized children. Read host counters freshly. A disappearing child may be retried conservatively.
- [x] Hold a private flock across snapshot, admission and confirmed scoped-unit creation. Reservations derive from actual active unit limits, not caller claims or stale JSON leases. A private socket handshake prevents the scoped command from executing before verification; revoke permission before failed-start cleanup while holding the lock.
- [x] Launch a unique scope with a finite chosen MemoryMax, zero swap, explicit task/thread limits, declared CPUWeight and shared Slice. Preserve command arguments without a shell. Forward output and return the command status.
- [x] On cancellation clean up only the owned scope; never stop another worker. Confirm that an exited launcher with a still-active unit remains counted by the next admission.
- [x] Test concurrent launch requests, command failure, missing cgroup, uncapped sibling, startup failure and cleanup using controlled unit/cgroup fixtures. Perform one tiny real scoped command, not a stress test.

## Task 3: Production integration and rollout

Files: `household_cycle_resources.py`, `household_native_family.py`, `household_native_install.py`, `household_native_training.py`, native daily unit and their tests; existing operations docs/tracker.

- [x] Add explicit verified shared-pool admission while retaining strict legacy admission outside the pool. Verify actual ancestry and aggregate/leaf budgets; an environment flag alone cannot authorize relaxed limits.
- [x] Update owned-family rendering and effective readback together so expected Slice, CPU and RAM policy match. Avoid changing fitted sources or pretending old archived numerical code has changed.
- [x] Route development work through the launcher first. Then migrate forecast/scoring/preparer and daily orchestration coherently, handling strict acquisition children with compatible leaf limits.
- [ ] Verify first natural forecast and score, effective group accounting and original model continuity. Leave the natural daily fit explicitly pending until it actually runs.
- [ ] One final independent review of the complete resource allocation delta. Update the existing progress tracker with actual evidence and remaining work.
