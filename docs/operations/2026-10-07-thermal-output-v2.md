# Explicit version 2 thermal publication

Version 1 remains the exact existing shadow contract. The new version 2 contract
adds `earthship-thermal-release/v1` metadata and explicit `shadow`,
`forecast_active`, `advisory_active` and `unavailable` operating modes. Old readers
refuse version 2 rather than interpreting an active forecast as shadow.

`build_release_output` requires a trusted `qualification_loader(now)` that
recomputes the source-backed decision. A serialized report dictionary, active
switch or artifact presence is insufficient. The builder verifies the frozen
artifact/runtime/epochs and policy, decision digest and gates, assessment age,
current forecast/input freshness, numeric bounds and complete existing trajectory.
It preserves the actual forecast-origin and model/training dates. Qualification
may finish immediately after the forecast origin; this does not rewrite that
origin to create artificial freshness.

A qualified Stage A publication has high forecast confidence and withholds action
advice. Candidate recommendations/effects and unqualified action markers are
removed from its human-facing data. The baseline assumption remains visible as
an assumption. Invalid evidence, stale sensors, unsupported identity, missing
forcing, non-finite/implausible values or expired qualification return explicit
unavailable data with an empty trajectory. Automatic actuation is always false.

The metadata retains the qualification/expires clocks, complete artifact/runtime,
policy/report hashes and frozen sensor epochs. Expiry uses the preregistered
qualification freshness rule while original model/training ages remain visible.
`advisory_active` is reserved and structurally validated, but the current combined
v1 evaluator withholds advice; a genuine confirmed-action evaluator is still
required before the builder can produce that mode.

`load_qualification_inputs` accepts an owned private file with this exact schema:

```json
{
  "schema": "earthship-thermal-release-inputs/v1",
  "registration_path": "/private/registration.json",
  "artifact_path": "/private/artifact.json",
  "fit_evidence_path": "/private/fit.json",
  "training_sources_path": "/private/training.json",
  "runtime_bundle_path": "/private/runtime-bundle",
  "pairs_path": "/private/original-pairs.json"
}
```

All references must be absolute. The returned evaluator rereads original private
files and recomputes qualification on every invocation. There is no pass/status
field in this input contract and no assessment-clock override.

`thermal_intel.publish_release_output` provides the bounded transport boundary.
It invokes the fresh evaluator through the builder and sends exactly one validated
version 2 state to `Thermal_Model_JSON`. Failed qualification sends explicit
unavailable data, replacing a previously active publication. Delivery errors
propagate instead of producing a success claim. This callable is not yet wired
into the installed scheduled emitter; it does not enable production by itself.

The UI understands both versions. It displays explicit mode badges, immutable
revision, forecast confidence and withheld action advice, retains model/training
ages and calibrated intervals, and refuses forged/expired/incomplete active
payloads. The existing card layout and independent household alerts remain intact.

This is source-only publication/consumer infrastructure. Installed services still
use the legacy v4 runtime/artifact pair. The production emitter, compatible runtime
inventory, versioned prospective capture, rollback and real candidate cutover remain
necessary. No active publication or installed service change occurred here.

Verification: 75 focused backend/qualification/schema checks and 64 frontend
parser/card checks passed. Local runs were serial with 25% CPU, 768 MiB RAM, zero
swap, 48 tasks and low priority. A Node worker initially hit the task limit;
limiting V8/libuv/build-worker threads resolved it without increasing the limits.
Full suites and builds run in hosted CI.
