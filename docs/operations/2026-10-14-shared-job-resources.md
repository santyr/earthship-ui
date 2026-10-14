# Shared local job resource allocation

The development launcher is implemented and its new `earthship-work.slice` is installed. Production forecast/scoring/preparer/daily units have not yet migrated. Their effective limits remain unchanged. Full integration is tracked in [the implementation plan](../superpowers/plans/2026-10-14-shared-job-resources.md).

The slice has a6GiB combined MemoryMax,5GiB MemoryHigh, zero worker swap,256tasks and an eight-CPU-equivalent aggregate ceiling. Each launched job receives a dynamically selected finite RAM cap, a CPU weight (production100/development25), and no individual CPU quota. Thus a job can borrow idle CPU inside the shared ceiling. Numerical library threads remain one by default; this does not parallelize a serial model.

Example, from the active worktree:

```sh
python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 1024 --seconds 600 -- /usr/bin/python3 -m pytest -q path/to/tests.py
```

The command path must be absolute. `--tasks` defaults to96, bounded at128. `--production` selects the higher CPU/I/O weight; it does not grant model release or actuator authority. Exit75 means admission deferred; the launcher does not spin on a busy pool. Other command statuses propagate. No command arguments or credential values are printed by admission errors.

A private flock stays held from kernel snapshot through confirmed scope creation and any failed-start cancellation. A scoped shim cannot execute its command until a private Unix socket grants permission after cap verification. EOF, cancellation, timeout or a delayed start after the socket is removed refuses execution. Every active child's finite MemoryMax is its reservation, including surviving descendants after a launcher exits. Host admission subtracts a3GiB reserve and every active sibling's full RAM commitment from observed available RAM. It deliberately does not credit separately sampled sibling usage: non-atomic host/cgroup readings could otherwise count freed RAM twice. This is conservative under concurrency; an idle pool still receives the full available allowance. Pool admission accounts for full commitments and direct parent charges. Preferred RAM can decrease to available capacity, but never below the caller's minimum. Missing counters, unlimited siblings and aliased directories refuse admission.

Once running, the launcher checks once per second for available RAM below1.5GiB or sustained memory PSI (ten-second some average above5%, full above1%). It stops only its own scope on refusal or interruption. Kernel limits remain continuous; unrelated processes can still consume host resources between samples. Running hard limits are not reduced in place. CPU distribution is automatic; memory allocation adapts at job starts and concurrency follows admission. This is not an application batch-size tuner.

Verification:40focused tests cover aggregate/host accounting, sibling future growth, parent charges, finite metadata, concurrent launch serialization, command exit, failed startup, sustained pressure and owned cleanup. A real tiny command received128MiB MemoryMax, memory.swap.max0 and cpu.max=max beneath the verified parent ceiling. The corrected full focused test run itself used the shared launcher with a512MiB budget. Regression tests cover contender exclusion during failed-start cleanup, parent disappearance before permission, delayed startup after cancellation, argument/exit-status preservation, and sibling shrink between samples. A real SIGTERM check returned130 and confirmed its own scope was removed. No fit or stress test ran. Production scoring separately completed its corrected historical slot at21:56UTC.
