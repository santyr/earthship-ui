'use strict';
// Triggerless one-shot configuration action. No Item state or command writes.
const PHASE = 'preflight';
const MARKER = 'POWER_RESOURCE_INSTALL';
if (!['preflight', 'items', 'links'].includes(PHASE)) throw new Error('Unknown install phase');
const specs = [
  ['Power_Evidence_JSON', 'Validated battery and PV power evidence'],
  ['Battery_Power_Observation_JSON', 'Battery power acquisition observation'],
  ['PV_Input_Power_Observation_JSON', 'PV input power acquisition observation'],
  ['PV_Output_Power_Observation_JSON', 'PV output power acquisition observation'],
];
const sourceLinks = [
  [specs[1][0], 'modbus:data:schneiderBatterySunSpec:battery802Core:powerObservation'],
  [specs[2][0], 'modbus:data:9eb978a141:mppt60Input:powerObservation'],
  [specs[3][0], 'modbus:data:9eb978a141:mppt60Output:powerObservation'],
];
const FrameworkUtil = Java.type('org.osgi.framework.FrameworkUtil');
const ItemRegistryClass = Java.type('org.openhab.core.items.ItemRegistry');
const StringItem = Java.type('org.openhab.core.library.items.StringItem');
const ThingUID = Java.type('org.openhab.core.thing.ThingUID');
const ChannelUID = Java.type('org.openhab.core.thing.ChannelUID');
const ItemChannelLink = Java.type('org.openhab.core.thing.link.ItemChannelLink');
const Configuration = Java.type('org.openhab.core.config.core.Configuration');
const context = FrameworkUtil.getBundle(ItemRegistryClass.class).getBundleContext();
const references = [];
function service(name) {
  const reference = context.getServiceReference(name);
  if (reference === null) throw new Error('Required install service absent');
  references.push(reference);
  const value = context.getService(reference);
  if (value === null) throw new Error('Required install service unavailable');
  return value;
}
try {
  const itemRegistry = service('org.openhab.core.items.ItemRegistry');
  const itemProvider = service('org.openhab.core.items.ManagedItemProvider');
  const thingRegistry = service('org.openhab.core.thing.ThingRegistry');
  const linkRegistry = service('org.openhab.core.thing.link.ItemChannelLinkRegistry');
  const linkProvider = service('org.openhab.core.thing.link.ManagedItemChannelLinkProvider');
  if (PHASE !== 'links') {
    for (const [name] of specs) {
      if (itemRegistry.get(name) !== null || itemProvider.get(name) !== null) {
        throw new Error('Item collision; no upsert permitted');
      }
    }
  } else {
    for (const [name, label] of specs) {
      const item = itemRegistry.get(name);
      if (item === null || String(item.getType()) !== 'String' || String(item.getLabel()) !== label
          || String(item.getCategory()) !== '' || !item.getGroupNames().isEmpty() || !item.getTags().isEmpty()) {
        throw new Error('Expected installed Item definition absent or changed');
      }
    }
    for (const [, uid] of sourceLinks) {
      const thing = thingRegistry.get(new ThingUID(uid));
      if (thing === null || String(thing.getStatusInfo().getStatusDetail()) !== 'DISABLED') {
        throw new Error('Source Thing must be disabled before linking');
      }
      for (const key of ['writeStart', 'writeType', 'writeValueType']) {
        if (thing.getConfiguration().get(key) !== null) throw new Error('Unexpected write configuration');
      }
    }
  }
  const candidates = sourceLinks.map(([name, uid]) => {
    const configuration = new Configuration();
    configuration.put('profile', 'system:default');
    const link = new ItemChannelLink(name, new ChannelUID(uid + ':string'), configuration);
    if (linkRegistry.get(link.getUID()) !== null || linkProvider.get(link.getUID()) !== null) {
      throw new Error('Link collision; no upsert permitted');
    }
    return link;
  });
  let created = 0;
  if (PHASE === 'items') {
    for (const [name, label] of specs) {
      const item = new StringItem(name);
      item.setLabel(label);
      item.setCategory('');
      itemProvider.add(item);
      created += 1;
      console.info(MARKER + ' CREATED item=' + name);
    }
  }
  if (PHASE === 'links') {
    for (const link of candidates) {
      linkProvider.add(link);
      created += 1;
      console.info(MARKER + ' CREATED link=' + link.getUID());
    }
  }
  console.info(MARKER + ' PASS phase=' + PHASE + ' created=' + created);
} finally {
  for (const reference of references) context.ungetService(reference);
}
