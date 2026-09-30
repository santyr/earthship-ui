'use strict';

// Observational only: source-bound temperature, never a device command.
// Legacy Item/stream/rule IDs are retained; sensor 223 is in Office Hallway.
function bedroomTemperature(raw, nowMs = Date.now()) {
  if (typeof raw !== 'string' || raw.length > 8192 || !Number.isFinite(nowMs)) return null;
  let snapshot;
  try { snapshot = JSON.parse(raw); } catch (_) { return null; }
  const record = snapshot?.records?.bedroom;
  const received = Date.parse(record?.receivedAt);
  const recorded = Date.parse(record?.recordedAt);
  const expires = Date.parse(record?.validUntil);
  if (snapshot?.version !== 1 || record?.version !== 1
      || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(snapshot?.streamEpoch)
      || record.streamEpoch !== snapshot.streamEpoch
      || record.model !== 'AmbientWeather-WH31E' || record.sensorId !== 223
      || record.field !== 'tempinf' || record.status !== 'valid' || record.reason !== 'accepted'
      || !Number.isFinite(received) || received !== recorded || received > nowMs
      || !Number.isFinite(expires) || expires <= nowMs || expires <= received || expires - received > 120_000
      || typeof record.temperatureF !== 'number' || !Number.isFinite(record.temperatureF)
      || record.temperatureF < -40 || record.temperatureF > 140) return null;
  return record.temperatureF;
}

const { rules, triggers, items } = require('openhab');
rules.JSRule({
  id: 'hex_bedroom_temperature',
  name: 'Office Hallway source-bound temperature',
  triggers: [triggers.ItemStateUpdateTrigger('Weather_Temperature_Evidence_JSON'),
    triggers.GenericCronTrigger('0/30 * * * * ?')],
  execute: () => {
    const value = bedroomTemperature(String(items.getItem('Weather_Temperature_Evidence_JSON').state));
    items.getItem('Bedroom_Temperature').postUpdate(value === null ? 'UNDEF' : `${value} °F`);
  },
});
