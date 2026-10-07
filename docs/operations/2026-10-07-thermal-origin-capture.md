# Original thermal input capture contract

This is a prerequisite for the existing thermal graduation goal. It introduces
`earthship-thermal-origin-capture/v1` alongside the exact legacy forcing-capture
contracts. It grants no production forecast, advisory or actuator authority.
PR #3 household-planner architecture remains deferred.

The optional native temperature observer preserves the actual complete selected
receipt grids, including missing-data barriers, source identities, original
receipt/storage/expiry clocks, stream epochs and snapshot hashes. It emits only
after all three required current roles qualify. Its normal return values and the
existing current-state assembler's default behavior are unchanged.

`build_origin_capture` binds:

- the exact original output, artifact, weather response, forecast rows and current state;
- original native temperature grids and initial sensor epochs;
- the causal north-wall mass observer's actual selected state;
- publication runtime, interpreter and dependency identities, separate from training revision;
- known action evidence, if supplied, with original receipt/commit/effective clocks.

Unknown actions remain null. A captured action snapshot does not itself prove
causal benefit or advisory eligibility. This first contract captures available
version 1 shadow output only. A future production-output contract must use an
explicit compatible capture version; old readers refuse this new schema.

`build_runtime_binding` hashes the declared prediction source closure, observer
source and executing interpreter and records loaded dependency versions. Source
paths are bounded Python files; writable, missing or escaping paths refuse. It
rechecks the closure after collection so a concurrent update cannot create a
mixed runtime identity. Runtime identity does not assert model predictive skill.

`write_origin_capture` creates only private observational files: an owned 0700
root/month and 0600 bounded compressed records. Same-record retries are
idempotent; changed content cannot overwrite an existing origin identity.
Reads reject unsafe ownership/modes, symlinks, malformed JSON, changed digests,
unqualified native receipts, incorrect selected state or expired publication inputs.

The opt-in producer hook and durable declared-runtime bundle are implemented in
`2026-10-07-thermal-runtime-retention.md`. Combined qualification, the compatible
installed-runtime transition and production publication remain subsequent work. No installed service,
legacy capture directory or live publication path has been enabled by this source
change. Existing legacy captures are not upgraded.

Verification on the household host was limited to one capped low-priority check:
126 focused origin/evidence/receipt/schema/comparator tests passed in 10.50 seconds;
four pipeline/dataset-related cases were left for remote CI. Limits were 25% of
one core, 768 MiB RAM, no swap, 48 tasks and low IO/process priority. No local
container suite or model fitting ran.

## Version 2 publication capture

`earthship-thermal-origin-capture/v2` retains the exact version 2 thermal output
and all the same original input/native-receipt/runtime bindings. Release
artifact/runtime hashes and sensor epochs must match the retained bytes. The
qualification must already exist and remain unexpired at publication
acknowledgement. Native initial state must match the issued values. Unknown
actions remain unknown; capture supplies no qualification or causal authority.

The new builder/reader/writer are `build_release_origin_capture`,
`read_release_origin_capture` and `write_release_origin_capture`. They use
immutable private `*-origin-v2.json.gz` files. The original v1 reader and validator
refuse v2. Explicit `read_observed_origin_capture` dispatch supports the two
validated contracts for scoring and policy registration; it does not upgrade any
legacy record. The scorer still requires an exact match with the real persisted
publication and qualified later outcome/native recent-cycle receipts.

The release command accepts `--origin-capture-dir /private/origins`, or the existing
`THERMAL_ORIGIN_CAPTURE_DIR`. Configure this for a future staged production
release. After an accepted available publication, it retains the complete release
runtime bundle and original v2 record using the actual acknowledgement clock.
Previews and unavailable withdrawals create no available-publication evidence.
Capture/storage failures report an explicit gap and do not retry or invent proof
for an already accepted write. Missing archive configuration also reports a gap.
Cutover verification must require actual retained captures and ongoing mature
source-bound baseline scores, not just an accepted UI state.

The v2 implementation remains undeployed. Its storage/scoring tests use synthetic
publication fixtures, including real private-file transactions; they do not prove
that the household model qualifies for release.
