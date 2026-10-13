# Native inference headroom diagnosis

The native current-input qualification at source5ab20b8 refused during retained
candidate numerical replay, before Java geometry, live input collection or any
publication. Private exact counters are retained in
`.superpowers/sdd/2026-10-12-household-common-cycle/native-current-capture-5ab20b8/private-diagnosis.json`.

The original TrainingHeadroom swap allowance is1048576bytes/second. Its callbacks
measure each interval independently. At the refusal, the previous sample was
518772.604404492 and the current sample518772.605123763: about0.000719seconds.
The host swap counter advanced by one4096-byte page. The computed allowance for
that tiny interval was about754bytes, so a single page refused inference. PSI
some/full totals did not change across the interval; pressure averages were
0.00/0.00/0.03. This proves the immediate refusal cause, not which process caused
the page read. No threshold, guard or production unit was changed.

A prior quiet runtime probe also passed five-second preflight then refused58
pages(232KiB) over0.10488seconds. Both checks enforce an instantaneous rate over
arbitrarily short callback intervals, despite the allowance being expressed per
second. Occupied swap alone is not an admission criterion; no attribution to
another daemon or proof of model readiness follows from these counters.

## Approved adjustment

For native read-only inference and qualification only, measure the same maximum
1MiB of host swap reads over a trailing one-second window rather than restarting
the budget at every numerical callback. Retain per-callback host memory reserve,
all original PSI-average and interval limits, unchanged host swap-out/OOM
counters, worker memory-limit/OOM checks, actual sharedlock, CPU20percent,
memory256MiB/swap0/tasks24/nice15/idleIO limits and all execution deadlines.
Keep fitting and its original TrainingHeadroom implementation unchanged.

A correct implementation must use original sampled cumulative page counts, retain
a sample at or before the one-second boundary, reject counter regression and
reject more than1MiB within any retained one-second span. It must not manufacture
counter values or reset checks after a refusal. Startup still requires the
original five-second quiet preflight. Library/model/source identity, telemetry
freshness, publication receipts, numerical replay and action authority remain
independent gates.

Expected tests: one4KiB page over a submillisecond callback is allowed while a
trailing-window total over1MiB refuses; repeated bursts cannot renew the window;
window expiry cannot discard an unmeasured partial interval; swap-out, OOM,
pressure, memory reserve, caps, lock changes and deadline failures still refuse.
The user explicitly approved the one-second inference window on October 13.
The implementation belongs to a separate native inference policy module;
TrainingHeadroom and all fitted source bytes remain unchanged. This approval
covers the bounded inference adjustment and qualification, while model selection
and production readiness still require their existing evidence.

## Verification

Commit434f861 passed80 affected tests (19.29s) and a final10-case family
verification run (7.61s). All72 fitted and12 native-runtime source hashes remain
unchanged. Fresh stage434f861-native contains219 sealed sources and retains the
original512a5d91 model andcc182b83 runtime pins.

The first actual production-interpreter replay refused the preserved interval
PSI check after25.99s, with128253952-byte peak and no memory-limit/OOM events.
The bounded quiet retry passed original candidate numerical replay and runtime
verification in40.37s, with113811456-byte peak and all memory-limit/OOM counters
zero. No fitting, live-unit change, publication or model selection occurred.
Current-input capture and full pipeline qualification remain pending.

A subsequent read-only current-input attempt at source04fb1d0 stopped during
candidate replay before Java geometry. It recorded zero swap-read pages in
the refusal interval. PSI some increased1201 microseconds over0.08199373s
(1.465percent), exceeding the preserved0.5percent interval limit;
all three pressure averages were zero. This is a separate preserved pressure
condition. No further safeguard adjustment or production readiness is claimed.
The current-input attempt retained private diagnostics and made no live writes.
