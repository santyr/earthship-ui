# Native inference PSI window — approved implementation

The user explicitly approved the one-second PSI window on October 14. The exact proposed patch is applied in the implementation worktree; activation uses a new immutable deployment stage. The previous deployed archive remains unchanged until the owned handoff succeeds.

Actual evidence: the private diagnostic wrapper retained a124-microsecond increase in cumulative full memory stall and125microseconds in some stall, with avg10/60/300 all0.00 and unchanged OOM/swap counters across the retained samples. Its per-callback interval check refused before the driver started. Natural geometry preparation also sometimes returns geometry_withheld; its generic CLI output does not establish the same exact cause.

Proposed change: evaluate native inference's cumulative PSI deltas over a trailing one-second window, capped at5,000microseconds some and1,000microseconds full (the existing0.5%/0.1% bounds over one second). Retain the sample preceding the boundary; never interpolate counters or discard an unmeasured interval. Refuse counter regression and more than65,536 retained samples. Refusals remain latched.

Every callback still freshly checks worker limits, long-term PSI averages, the1.5GiB available-memory reserve, monotonic time, host swap-out/OOM changes, the approved1MiB trailing-one-second swap-read cap, and source/lock/deadline checks. Five-second admission,20%CPU,256MiB memory,zero swap,24 tasks,IOWeight10,nice15,idleIO and one numerical thread remain. The original fitting guard remains byte-for-byte unchanged. Preparation75seconds, service90seconds, scorer50seconds and every causal margin remain.

The proposal exists only as the private patch .superpowers/sdd/2026-10-13-native-model-serving-receipt/psi-window-proposal.patch (SHA256 a5bf6d60db5ddd080fab1072016084cb6ddc0cf10a5aacd0cd104d8939946360). Active source SHA256 remains62e8e3cee10376e8ced116ae9ccb3c01ac08526188ed5577bbfd818671315781, equal to the deployed copy.

Verification: the measured124-microsecond synthetic regression fails against the active implementation (run-u13837). The inactive proposal passes10 deterministic tests (run-u13838), covering full/some budget exhaustion, nonrenewal/latching, observed expiry, conservative partial intervals, counter regression, unchanged swap-read/OOM/swap-out/reserve/worker barriers, unchanged strict fitting PSI and five-second admission. All test kernel inputs are temporary synthetic files; no live policy was changed.

Approval would authorize applying this exact policy change, updating affected regression expectations and sealed source bindings, then qualifying and deploying under the same limits. Retaining current sampling leaves the current guard active and intermittent refusals under observation.

Implementation verification (October 14): active-source regression reproduced the 124-microsecond refusal (run-u19567). After applying the exact approved patch, 47 tests and 4 subtests passed in 4.45 seconds (run-u19586), including unchanged fitting policy. Source SHA256 is 0f1cbad112aebd3b4253ea31cf54783fbaaea1b5f75064e0e6874bdb4df624c8. All three original timer states and definition bytes were restored; no live telemetry write or fit occurred. Production activation remains pending qualification and handoff.
