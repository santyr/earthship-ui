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
