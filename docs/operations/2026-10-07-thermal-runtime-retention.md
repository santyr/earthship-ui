# Original thermal runtime retention and publisher capture

The optional `THERMAL_ORIGIN_CAPTURE_DIR` publisher path retains complete
`earthship-thermal-origin-capture/v1` observations after an accepted shadow
publication. Capture is disabled by default and does not run for unpublished
previews. It changes no forecast equations, model acceptance or household control.

The native temperature observer runs within the existing current-state read.
The original publication runtime is bound before inputs are collected. After
publication, the hook requires one complete native proof and the actual artifact
used by the predictor, rechecks the runtime, archives its bytes, and writes the
immutable original-input record. The input-availability clock is the existing
post-fetch decision clock; native observations retain their earlier assessment.
Known actions remain unknown rather than becoming confirmed from reconstruction.

A missing native proof, source change, unsafe archive directory or unavailable
capture dependency records an explicit `thermal origin capture gap` and leaves
that accepted publication intact. A gap cannot supply release evidence. The
existing legacy forcing-capture path remains separate and compatible. When both
paths are enabled, they share the same publication acknowledgment clock.

`earthship-thermal-runtime-bundle/v1` retains the declared ordered prediction
closure, observer source, actual interpreter bytes, interpreter identity and
loaded numerical dependency versions. The archive directory is addressed by the
complete runtime-binding digest, with private 0700 directories and immutable
0600 files. Source/configuration credentials are not collected: only the declared
Python files and interpreter are read. The interpreter copy is non-executable.

The reader recomputes every file hash and the ordered publication revision, and
rejects missing/extra files, unsafe modes, symlinks, malformed paths and changed
manifests. A complete generation is published atomically after source rechecks;
partial attempts are removed. Identical retries preserve the same generation.
An archived generation remains verifiable after the live installation changes.
The archive grants no release authority and never executes stored code.

This preserves the declared source/executable identity, rather than an entire
standalone software environment. Native libraries, dependency wheels and the
compatible installed environment still require retention and validation by the
release/rollback inventory. Loaded-code isolation belongs to the guarded
versioned deployment path; archiving disk bytes alone is not an execution attestation.

This source implementation has not been enabled in installed services. The
household currently uses a legacy v4 runtime/artifact pair, while this repository
uses v5. Deploying the entire current tree onto that pair is not a compatible
capture-only change. A compatible backport or complete staged candidate/runtime
transition remains necessary before natural collection.

Local verification ran 53 selected origin/runtime/publication/legacy-clock tests
in one low-priority scope limited to 25% CPU, 768 MiB RAM, zero swap and 48 tasks.
The broader suites run in hosted CI. No local container, model fitting, service
restart or production deployment was performed.
