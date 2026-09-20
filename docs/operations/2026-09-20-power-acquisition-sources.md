# Power acquisition source audit and observation draft

Read-only live inspection on September20, approximately08:07–08:10MDT.
The new transform/resource files are **source only, not deployed**. They are
absent from the managed-resource manifest and cannot activate through its normal
deployment path. All proposed data Things are disabled by default.

## Live topology

Four Modbus TCP bridges share one gateway host but have distinct(port,unit)
pairs, all ONLINE at inspection:

| Purpose | Port | Unit | Child acquisition |
|---|---:|---:|---|
| MPPT60 |503|30|input/output5s; energy30s pollers|
| Discover BMS |503|190|main/counter30s pollers|
| Inverter |502|10|SunSpec split-phase Thing,5s refresh|
| SunSpec battery |502|1|802core5s poller|

The live inventory contains46data Things,6pollers and1split-phase inverter Thing.
Data Things are not separate TCP slaves. No consolidation is indicated by these
distinct endpoint/unit identities. This is a configuration observation, not a
measurement of physical socket count or gateway capacity.

## Exact raw sources

| Metric | Existing poller | Register/type | Existing raw Item |
|---|---|---|---|
| battery.dc_power_w |schneiderBatterySunSpec:battery802Core|40291/int16|DCData_Native_Power_Raw_W|
| pv.input_power_w |9eb978a141:mppt60Input|80/uint32|MPPT60_Native_PV_Power_W|
| pv.output_power_w |9eb978a141:mppt60Output|92/uint32|MPPT60_Native_DC_OutputPower_W|

Each existing raw data Thing sets updateUnchangedValuesEveryMillis1000; parent
pollers refresh5000ms. The battery scaler is change-triggered plus30s cron;
the MPPT scaler is voltage-change-triggered plus30s cron. Both post quantities
only on change and skip invalid raw values rather than clearing older quantities.
Therefore scaled quantity receipt time is not independent acquisition evidence.

Household load uses ConextGateway_ACPowerValue linked directly to
`modbus:inverter-split-phase:1ed74db72c:e853aec444:acGeneral#ac-power`.
It needs a separately verified acquisition contract; no guessed raw register,
scale or receipt transform is included for it.

A bounded natural SSE observation saw four ItemStateEvents for each of these
four power inputs, with four distinct values each. REST SSE exposed no source
field in those event objects. This proves events occurred, not unchanged-value
delivery, exact Java event provenance, or queue-delay bounds. The first probe
aborted on an SSE heartbeat message; the corrected probe explicitly ignored
messages without an Item topic. Neither probe mutated Items or forced polling.

## Draft observation contract

`openhab/power-observation-resources.json` adds only three data Things and String
Items beneath the existing battery/PV pollers. Register types and locations match
the live raw sources above; no bridge, poller or control is added or modified.
Three pure JS transforms stamp acquisition-transform time once and preserve raw
input text in `{version:1,field,observedAt,value}`. Invalid values and sentinels
remain visible for downstream rejection; no validity or freshness is asserted.

The timestamps distinguish unchanged physical observations without depending on
change-only numeric persistence. They are host transform timestamps, not device
clock timestamps. This follows the existing BMS observation architecture but
does not inherit its qualification results automatically.

Before activation: implement/test the validated observer with strict source
binding, source-specific validity, expiry, clock/restart behavior and invalid
barriers; select bounded persistence; perform create-only collision/rollback
preflight; then verify natural acquisition and restart behavior. Do not point
analytics at these raw observations as if they were qualified intervals.

The corresponding interval-math foundation is Solar_PV branch
`feat/qualified-power-accounting`, commita8925f9, with543analytics tests passing.
No existing cumulative totals, BMS counters, safety publishers or pump controls
have changed. Full producer/reader/accounting/cutover integration remains open.

## Source-only observer implementation

`openhab/rules/power-evidence.js` and its separate disabled resource descriptor
now define the observational `Power_Evidence_JSON` publisher. It authenticates
the original ItemStateEvent topic, Item name and exact binding channel source;
requires canonical bounded receipt JSON; preserves per-field acquisition times;
rejects future/expired/malformed readings; and publishes null-valued barriers on
invalid input. Signed battery values are retained; raw int16 minimum and uint32
maximum are conservatively excluded. These are encoding/sentinel bounds, not
physical power plausibility certification. PV negatives are rejected.

The observer does not read existing numeric or health Items, issue commands,
perform I/O, or adjust pollers. Its only Item access is posting the new evidence
String. Each field expires120seconds after its own acquisition timestamp; a
30-second observational timer publishes expiry status, while readers must honor
the exact validUntil boundary independently. Every accepted distinct acquisition
timestamp is published, including unchanged watts. This preserves evidence but
requires measuring publication/storage volume before persistence activation.

Private-cache reset or clock rollback creates a new stream epoch, starting
unavailable and requiring strictly post-reset acquisition. Delayed older receipts
do not renew values; conflicting same-time readings invalidate the field and
require a later receipt. Failed publication is retried without acknowledging a
successful post. Ambiguous original-event wrappers invalidate all fields.

The initial timestamp-only acquisition source and observer remain undeployed.
Tests exercise76observer cases in an isolated VM with forbidden numeric reads,
commands/network capabilities, injected clocks, original events and failures.
This is not proof of real binding-event provenance, a hardware fault response,
or a live restart. No persistence configuration is added yet. Required next
steps are the strict historical reader, bounded persistence plan, live source
and lifecycle qualification, household-load contract and versioned accounting
integration. Do not reuse the BMS parser on this different record schema.

The producer now adds a positive per-stream `sequence`, advanced after successful
publication, to order distinct snapshots recorded in the same millisecond.
Failed posts do not acknowledge sequence advancement. Cache reset restarts the
sequence under a new UUID epoch.77observer tests and1498full unit tests pass.
The separate Solar_PV power reader accepts this schema and preserves publication
delays, missing-sequence gaps and per-field independence.579analytics tests pass.
An isolated actual-transform/observer-to-reader/accounting probe also passed;
none of this substitutes for live provenance or bounded persistence checks.

## Live preflight and installed-engine qualification

September20 live preflight found no collisions for the four planned String
Items, three data Things, observer rule or three earlier proposed transformation
registry names. JDBC still has the existing wildcard everyChange/restoreOnStartup
policy; no persistence edit is needed or performed. Existing BMS transformations
are file-backed/editable=false, so copying their installation mechanism would
add files rather than meet the host's REST-managed configuration preference.

The power descriptor now embeds each exact source body as a single-line
`JS(|...)` readTransform in its managed Thing configuration. `transformSources`
identifies reviewed repository assets only, not transformation resources to
install. Tests require byte-exact newline-to-space equivalence with those assets.
No file under `/etc/openhab` was created, modified or removed.

Installed JS service qualification passed12checks (three transforms times four
raw inputs) through an ownership-verified temporary triggerless diagnostic rule:
`hex_power_transform_probe_0c1fe48b569c4518b78fb89afbdc44c8`.
A fresh correlated log receipt confirmed actual execution; the exact unchanged
probe was removed and verified absent. The diagnostic used no Item writes,
commands, poller changes or notifications. This is engine-level qualification;
natural Modbus pipeline and original-event provenance still need verification.

The reviewed lifecycle helper from the earlier BMS qualification was reused by
`/tmp/hex-power-transform-probe.py`; it is an already-executed temporary receipt
artifact, not a deployment command to rerun. Source hashes:

- battery:391e3b8ea6d6e6090930b7e614bd3f7e76c87971f6e28a9c8883a2ccb2f7ddf0
- PV input:e1d7b96c8b80b48c33893d8b3788cab3276a1b06031fb2902f0ea648af71d3a0
- PV output:6ec8375c56c31722573b710da1e454936cdefe54bb5eb616b85fdfe84c149ee7

Create-only Items/links must use the verified provider-add semantics rather than
claiming REST PUT is atomic creation. Next installation should stage unlinked
Things disabled, stage the observer triggerless then disabled, add reviewed
triggers and links only after exact ownership/posture checks, and compare
protected controls/persistence/pollers with a private baseline. No power resource
has yet been installed or activated by this preflight.

The fixed-scope provider-add helper is now tracked at
`scripts/openhab-power-install-action.js`. It permits only preflight/items/links,
adds exactly four named String Items or three links, refuses collisions, requires
disabled source Things without configured write registers before linking, and
rejects changed Item labels/types/category/groups/tags. It never updates/removes
providers or writes states/commands.12deny-by-default VM tests pass, including
partial failure without retries and service-reference cleanup;1510full unit tests
pass. Live preflight verified installed providers and zero-created receipt via
`hex_power_install_1bd8524926c34f6faa108334c5e0a134`, then removed that exact
temporary diagnostic. Actual resource installation has not yet run.
