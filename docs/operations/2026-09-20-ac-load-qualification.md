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
