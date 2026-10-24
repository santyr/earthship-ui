'use strict';

// PREPARED / UNINSTALLED. This empty registration has no runtime side effects.
// A separate private bootstrap may read the credential-free mapping JSON and
// explicitly call the factory. There are no guessed Thing UIDs or default paths.
const PREPARED_PROVIDER_HISTORY_MAPPINGS = Object.freeze([]);
const MAX_PROVIDER_MAPPINGS = 26;
const MAX_MAPPING_BYTES = 16384;
const STATUS_ITEM = /^Shade_[A-Za-z0-9_]{1,64}_ProviderStatus$/;
const THING_UID = /^[A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+){2,7}$/;

function validateProviderHistoryMappings(mappings) {
  if (!Array.isArray(mappings) || mappings.length > MAX_PROVIDER_MAPPINGS) {
    throw new Error('invalid_provider_history_mapping');
  }
  const slots = new Set(), targets = new Set();
  const result = mappings.map(row => {
    if (!row || typeof row !== 'object' || Array.isArray(row)
        || Object.keys(row).sort().join(',') !== 'slot,statusItem,thingUID'
        || !Number.isInteger(row.slot) || row.slot < 1 || row.slot > 26
        || typeof row.thingUID !== 'string' || row.thingUID.length > 256 || !THING_UID.test(row.thingUID)
        || typeof row.statusItem !== 'string' || !STATUS_ITEM.test(row.statusItem)
        || slots.has(row.slot) || targets.has(row.statusItem)) {
      throw new Error('invalid_provider_history_mapping');
    }
    // Several logical shades may share one actual provider Thing. Their
    // observational targets remain distinct, never arbitrary command Items.
    slots.add(row.slot); targets.add(row.statusItem);
    return Object.freeze({slot:row.slot,thingUID:row.thingUID,statusItem:row.statusItem});
  });
  return Object.freeze(result);
}

function readShadeProviderHistoryMappings(path, readText) {
  if (typeof path !== 'string' || !path.startsWith('/') || path.length > 1024 || path.includes('\0')) {
    throw new Error('invalid_provider_history_mapping');
  }
  let raw;
  try {
    if (readText === undefined) {
      const Files = Java.type('java.nio.file.Files');
      const Path = Java.type('java.nio.file.Path');
      const file = Path.of(path);
      if (Number(Files.size(file)) > MAX_MAPPING_BYTES) throw new Error('mapping_bound');
      raw = String(Files.readString(file)); // Read-only: never writes configuration.
    } else {
      if (typeof readText !== 'function') throw new Error('mapping_reader');
      raw = readText(path);
    }
    if (typeof raw !== 'string' || raw.length > MAX_MAPPING_BYTES) throw new Error('mapping_bound');
    const parsed = validateProviderHistoryMappings(JSON.parse(raw));
    // The closed file format has exactly three literal property names per row.
    // Reject duplicate/escaped/unknown keys rather than accepting JSON's last key.
    const properties = Array.from(raw.matchAll(/"((?:[^"\\]|\\.)*)"\s*:/g), match => match[1]);
    if (properties.length !== parsed.length * 3
        || properties.some(name => !['slot','thingUID','statusItem'].includes(name))) {
      throw new Error('mapping_keys');
    }
    return parsed;
  } catch (_) {
    throw new Error('invalid_provider_history_mapping'); // No path, contents or credentials in errors.
  }
}

function registerShadeProviderHistory(api, mappings = PREPARED_PROVIDER_HISTORY_MAPPINGS) {
  const rows = validateProviderHistoryMappings(mappings);
  if (rows.length === 0) return Object.freeze([]);
  if (!api || typeof api.rules?.JSRule !== 'function'
      || typeof api.triggers?.ThingStatusChangeTrigger !== 'function'
      || typeof api.triggers?.SystemStartlevelTrigger !== 'function'
      || typeof api.items?.getItem !== 'function' || typeof api.things?.getThing !== 'function') {
    throw new Error('provider_history_runtime_unavailable');
  }
  const target = row => {
    const item = api.items.getItem(row.statusItem);
    if (!item || String(item.type) !== 'String' || typeof item.postUpdate !== 'function') {
      throw new Error('provider_history_target_unavailable');
    }
    return item;
  };
  try { rows.forEach(target); }
  catch (_) { throw new Error('provider_history_target_unavailable'); }
  const status = value => ['ONLINE','OFFLINE'].includes(String(value)) ? String(value) : 'UNDEF';
  const current = row => {
    try { return status(api.things.getThing(row.thingUID)?.status); }
    catch (_) { return 'UNDEF'; }
  };
  const update = (row,value) => {
    try { target(row).postUpdate(value); return true; }
    catch (_) { return false; }
  };
  // Invalidate restored ONLINE before reconciling the live registry. Existing
  // JDBC everyChange persists these update-only String transitions once installed.
  rows.forEach(row => update(row,'UNDEF'));
  const registered = rows.map(row => {
    const id = `hex_shade_provider_history_${String(row.slot).padStart(2,'0')}`;
    api.rules.JSRule({id,name:`Shade ${row.slot} provider status history`,
      description:'Observational String updates only; no motor or policy commands',
      triggers:[api.triggers.ThingStatusChangeTrigger(row.thingUID),api.triggers.SystemStartlevelTrigger(100)],
      execute:event => {
        if (event?.thingUID !== undefined) {
          if (String(event.thingUID) !== row.thingUID) return;
          let value = status(event.newStatus);
          // Preserve an outage event even if the registry has already advanced.
          // An old ONLINE event may not override a currently unavailable Thing.
          if (value === 'ONLINE') value = current(row);
          update(row,value);
        } else {
          update(row,'UNDEF');
          update(row,current(row));
        }
      }});
    update(row,current(row)); // Explicit hot-load reconciliation, no timer/poll.
    return Object.freeze({slot:row.slot,ruleUID:id,statusItem:row.statusItem});
  });
  return Object.freeze(registered);
}

if (typeof Java !== 'undefined' && PREPARED_PROVIDER_HISTORY_MAPPINGS.length > 0) {
  registerShadeProviderHistory(require('openhab'),PREPARED_PROVIDER_HISTORY_MAPPINGS);
}
if (typeof module !== 'undefined') module.exports = {PREPARED_PROVIDER_HISTORY_MAPPINGS,
  validateProviderHistoryMappings,readShadeProviderHistoryMappings,registerShadeProviderHistory};
