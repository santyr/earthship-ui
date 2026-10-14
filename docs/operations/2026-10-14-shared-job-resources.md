# Shared local job resource allocation

The shared launcher and `earthship-work.slice` are installed for development and production. Forecast, scoring and preparation now run workers inside the shared pool; daily training is configured for the same pool. The existing outer service limits supervise only the small launcher. Integration is tracked in [the implementation plan](../superpowers/plans/2026-10-14-shared-job-resources.md).

The slice has a6GiB combined MemoryMax,5GiB MemoryHigh, zero worker swap,256tasks and an eight-CPU-equivalent aggregate ceiling. Each launched job receives a dynamically selected finite RAM cap, a CPU weight (production100/development25), and no individual CPU quota. Thus a job can borrow idle CPU inside the shared ceiling. Numerical library threads remain one by default; this does not parallelize a serial model.

Example, from the active worktree:

```sh
python3 scripts/run-household-job.py --minimum-mib 256 --preferred-mib 1024 --seconds 600 -- /usr/bin/python3 -m pytest -q path/to/tests.py
```

The command path must be absolute. `--tasks` defaults to96, bounded at128. `--production` selects the higher CPU/I/O weight; it does not grant model release or actuator authority. Exit75 means admission deferred; the launcher does not spin on a busy pool. Other command statuses propagate. No command arguments or credential values are printed by admission errors.

A private flock stays held from kernel snapshot through confirmed scope creation and any failed-start cancellation. A scoped shim cannot execute its command until a private Unix socket grants permission after cap verification. EOF, cancellation, timeout or a delayed start after the socket is removed refuses execution. Every active child's finite MemoryMax is its reservation, including surviving descendants after a launcher exits. Host admission subtracts a3GiB reserve and every active sibling's full RAM commitment from observed available RAM. It deliberately does not credit separately sampled sibling usage: non-atomic host/cgroup readings could otherwise count freed RAM twice. This is conservative under concurrency; an idle pool still receives the full available allowance. Pool admission accounts for full commitments and direct parent charges. Preferred RAM can decrease to available capacity, but never below the caller's minimum. Missing counters, unlimited siblings and aliased directories refuse admission.

Once running, the launcher checks once per second for available RAM below1.5GiB or sustained memory PSI (ten-second some average above5%, full above1%). It stops only its own scope on refusal or interruption. Kernel limits remain continuous; unrelated processes can still consume host resources between samples. Running hard limits are not reduced in place. CPU distribution is automatic; memory allocation adapts at job starts and concurrency follows admission. This is not an application batch-size tuner.

Verification:40focused tests cover aggregate/host accounting, sibling future growth, parent charges, finite metadata, concurrent launch serialization, command exit, failed startup, sustained pressure and owned cleanup. A real tiny command received128MiB MemoryMax, memory.swap.max0 and cpu.max=max beneath the verified parent ceiling. The corrected full focused test run itself used the shared launcher with a512MiB budget. Regression tests cover contender exclusion during failed-start cleanup, parent disappearance before permission, delayed startup after cancellation, argument/exit-status preservation, and sibling shrink between samples. A real SIGTERM check returned130 and confirmed its own scope was removed. No fit or stress test ran. Production scoring separately completed its corrected historical slot at21:56UTC.

Independent review of correction `c102017` found no Critical or Important issues. Production integration is deployed from `2ba6e70` after230 affected tests. A final review identified an archived coordinator policy binding that was corrected with a failing-to-passing regression; the complete suite then passed.


## Production activation

Deployment `995ed1da43dcd7bcdfacf77f24a8b384ff0150315dd51d82c182182702087702` activated at2026-10-14T22:24:24Z. The selected artifact remains `52dd5d122485f0bdafa0aed4fa7412c0823ce9829ed3d9bdc920e44d88526506`, trained through2026-10-14T06:00:00Z; no fit or qualification probe ran. All five owned files, shared-launcher commands and active timers passed effective readback. UI, model and numerical forecast endpoints returnedHTTP200.

The first scheduled forecast at22:24:45Z published its22:25:15Z forecast and household observation, ending22:25:29Z. Its actual shared leaf had512MiB MemoryMax, unrestricted individual CPU quota,24tasks and zero swap; the scope used13.108CPU seconds and78.3MiB peak RAM. The already prepared exact-issue geometry was independently replayed and copied with unchanged bytes and timestamps to preserve continuity through the switch.

The22:26Z legacy scoring slot completed in six seconds and refreshed monitoring:256 retained legacy outcomes, zero new mature outcomes, no actuator authority. This does not prove a new current-native scoring outcome. The first current-native scoring slot remains to be observed. The first newly calculated preparation at22:28:05Z completed at22:28:09Z; its original geometry receipt is retained in the private evidence. Daily training's clean dedicated checkout and unit now use the same revision; its next natural run is2026-10-15 at06:50MDT and has not yet executed under this profile.

Forecast/scoring/preparer workers request256MiB minimum and512MiB preferred. Daily orchestration requests512MiB minimum and2GiB preferred. Daily acquisition receives a separately counted256MiB/20percent CPU/24task scope compatible with unchanged collection checks. Current operational admission is selected outside fitted adapter source bytes; archived entry-point globals are temporarily rebound and restored. Running numerical code and original source/receipt checks remain intact.

The first activation attempt generated Python bytecode in the immutable stage and stopped before unit changes. Only those generated cache files were removed after every sealed source hash was checked; the successful invocation disabled bytecode writes. Private evidence is in `.superpowers/sdd/2026-10-14-shared-job-resources/production-2ba6e70/` (`activation-result.json`, `readback.json`, `first-active-scope-readback.json`, `first-natural-cycles.json`, `geometry-continuity.json`, `daily-install.json`).
