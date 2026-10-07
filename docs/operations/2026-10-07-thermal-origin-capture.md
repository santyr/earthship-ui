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

The producer hook, durable runtime-source bundle integration, qualification
policy and production publication remain subsequent work. No installed service,
legacy capture directory or live publication path has been enabled by this source
change. Existing legacy captures are not upgraded.

Verification on the household host was limited to one capped low-priority check:
126 focused origin/evidence/receipt/schema/comparator tests passed in 10.50 seconds;
four pipeline/dataset-related cases were left for remote CI. Limits were 25% of
one core, 768 MiB RAM, no swap, 48 tasks and low IO/process priority. No local
container suite or model fitting ran.
