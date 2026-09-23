# AC-load qualification audit

Read-only inspection after qualified feature/lifecycle deployment. No Item,
Thing, rule, poller or actuator was modified.

The configured `house.ac_power_w` Item is `ConextGateway_ACPowerValue`, directly
linked without a link profile to
`modbus:inverter-split-phase:1ed74db72c:e853aec444:acGeneral#ac-power`.
The Thing is ONLINE; configuration address40070, length52, refresh5, maxTries3.
It is not one of the three acquisition-stamped power evidence inputs.

## Installed implementation evidence

Inspected the installed 5.2.1 SunSpec binding with the JVM's javap module, without
changing the running JVM. JAR SHA256:
`5b7254202fa401e497632d485680e1f1e1b147215574ace71a561fbe94da659d`.

- `InverterHandler.handlePolledData` publishes `acGeneral/ac-power` using the
  parsed `acPower` and `acPowerSF` fields, scaled to Watts (bytecode251–278).
- `AbstractSunSpecHandler.handleError` changes status to
  OFFLINE/COMMUNICATION_ERROR; this branch does not clear channel state.
- `handleCommand` returns without action. No refresh command was attempted.

The official [SunSpec channel documentation](https://www.openhab.org/addons/bindings/modbus.sunspec/)
describes this as inverter AC power across phases. Treating it as household
consumption additionally requires verifying the site's operating topology and
import/export/bypass semantics; a channel label is not that proof.

September23 operator clarification: the site currently runs entirely on
inverter output, with no bypass or generator supplementation. Under that
current topology, qualified inverter-output power can represent the load being
served to the household. This is conditional on the topology remaining true;
the channel by itself does not prove that bypass, supplementation or export is
absent at a future time. No existing historical period was retroactively
qualified by this statement.

## Natural observation and remaining gates

A 33.4-second REST event observation saw six ItemStateEvents approximately5.12s
apart. All values differed. Event envelopes exposed only payload/topic/type,
not original Java source or acquisition time. This proves natural updates, not
unchanged-value delivery or bounded event-queue delay.
September23 follow-up: a bounded 65-second authenticated WebSocket subscription
to only this Item observed 13 ItemStateEvents, 13 ItemStateChangedEvents and 13
ItemStateUpdatedEvents. The first two event kinds carried exact source
`org.openhab.core.thing$modbus:inverter-split-phase:1ed74db72c:e853aec444:acGeneral#ac-power`;
the updated events omitted source, as previously seen on this runtime.
State-event intervals were 5.07–5.16 seconds. All 13 values differed, so this
sample still cannot prove an unchanged-value receipt in live operation. The
probe sent only a topic filter and heartbeat, no Item event or command, and
did not print power values or credentials. The inverter Thing remained
ONLINE/NONE at readback.

Version-matched installed SunSpec bytecode shows `InverterHandler.handlePolledData`
calling `updateState` on `acGeneral#ac-power` after parsing and scaling each
received inverter model block, without a value-change comparison in that
handler. This supports the candidate unchanged-update path, but downstream
event delivery and an actual unchanged-value acquisition still require live
qualification. The channel has no native `lastReadSuccess` companion in its
current Thing channel set. An eventual collector must bind to the original
`ItemStateEvent` source, not assume the source-less updated event authenticates
a binding read; distinguish host event time from device measurement time.
The existing `hex_schneider_safety` uses an ItemStateUpdate trigger and routes
this Item through `stampIfFresh` to `Schneider_ACLoad_LastUpdate`; it is not an
atomic value/acquisition receipt in the qualified power stream.

Next qualification must establish binding-origin event identity, acquisition
timestamp semantics, unchanged receipts, invalid/offline barriers and restart
behavior without issuing hardware commands. Preserve the current three-field
stream/cutover until a versioned extension and its consumers are verified.
Do not guess a new raw register or count a generic numeric update as independent
physical freshness. AC-load energy, balances and winter replay remain withheld
until the acquisition receipt and topology-period gates are satisfied. A future
report should retain an explicit inverter-output basis so it cannot silently
be read as whole-house load after a topology change.

## Active non-authoritative acquisition-adjacent observation

The source tree now contains a file-owned `Inverter_AC_Output_Observation_JSON`
Item linked *additively* to the existing AC-power channel using the documented
`transform:JS` to-Item profile. Its transform emits version, field name, host
transform timestamp and the exact incoming state text, including invalid text.
It is an observation format only: the timestamp is not a device timestamp, and
the JSON is not a qualified power receipt or household-load authority. The
existing `ConextGateway_ACPowerValue` link and Modbus Thing are untouched.
Eight focused tests cover preservation of valid and invalid input text,
repeated-value receipts and the
read-side link configuration. The disposable networkless 5.2.1 check passed:
the file Item and exact transform-profile link loaded as non-editable, the
installed script bytes matched source, and the labeled container and tmpfs
were removed. This did not exercise binding-to-profile execution or JDBC.
September23 bounded production trial: exact files were installed under
`/etc/openhab/items/` and `/etc/openhab/transform/`; the original managed
`ConextGateway_ACPowerValue` Item/link and ONLINE inverter Thing were unchanged.
Natural binding-to-profile execution produced canonical JSON with a recent host
timestamp and Watt-valued raw text. In a 70-second read-only sample, REST
observed 14 distinct receipt timestamps with no invalid envelopes; the log
recorded 13 candidate changes and 13 original-Item changes. A separate
candidate-event audit initially found ten consecutively parsed changes with
the exact Modbus channel source and monotonic receipt times, no mismatches.
The first 70-second sample did not show a consecutive unchanged Watt value.
At 14:01 MDT, a larger read-only natural-event audit found 94 parsed,
binding-sourced monotonic changed receipts and **two consecutive unchanged
raw-Watt values with a newer receipt**. Two additional changes were initial
NULL-to-JSON transitions, not source mismatches. This closes the real
unchanged-value delivery gate for the observed operating period, not a fault
or restarted-binding gate.

The new Item's first JDBC readback had 33 canonical rows because the current
wildcard strategy persists every change, including transform timestamps. This
is observational history, not a qualified energy stream; its roughly five-second
cadence needs volume/retention review before indefinite reliance.
At 14:02 MDT, the last measured minute held 12 rows at a 5.121-second median
interval, an indicative 15,840 rows/day at that rate. This high-rate raw
observation must be monitored and either bounded by retention or moved to an
explicit qualified stream before indefinite accumulation.
JDBC identity 652 (`item0652`) held 123 rows in a 64 KiB table+index allocation
at the read-only size check; the host filesystem reported 627G free. This is
not an immediate capacity emergency, but the rate should not become an
unreviewed indefinite retention policy. The exact
two-file withdrawal was tested live: OpenHAB removed only the candidate Item
and link, left the original link intact, then reinstallation restored a fresh
natural receipt. JDBC still returned 78 canonical rows afterward, retaining
the earlier observations. The file-ownership inventory again reported zero issues.
No Item command, synthetic state, poller change, binding refresh, service
restart or hardware disruption was used.

The observation remains active solely for evidence collection. Invalid/offline
barriers, restart behavior and independent
qualified persistence are unproven. AC-load energy/balances remain withheld;
any future consumer must authenticate the original binding source, validate
the canonical envelope and expiration, and carry the explicit inverter-output
basis plus the operator-confirmed topology period.
