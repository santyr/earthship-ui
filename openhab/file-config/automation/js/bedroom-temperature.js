'use strict';

// Observational only: source-bound temperature, never a device command.
// Legacy Item/stream/rule IDs are retained; sensor 223 is now in Bedroom; exact move time is unknown.
// Reviewed v2 receiver policy: /home/sat/.config/hex/weather-temperature-policy-v2.json.
// Pin hardware phase independently of each receipt; a sensor replacement requires
// a reviewed policy update here and in the paired OpenHAB/UI consumer.
const OFFICE_HALLWAY_SENSOR_CONTRACT = Object.freeze({
  version: 2,
  model: 'AmbientWeather-WH31E',
  sensorId: 223,
  field: 'tempinf',
  sensorEpoch: 'edbd6e3b-ed67-4a0f-9a00-405996be0528',
  minimumF: -40,
  maximumF: 140,
  validityMs: 120_000,
});
const BEDROOM_VALID_FROM = '2026-10-24T23:14:52Z'; // Prospective operational boundary.

function bedroomTemperature(raw, nowMs = Date.now()) {
  if (typeof raw !== 'string' || raw.length > 8192 || !Number.isFinite(nowMs)) return null;
  let snapshot;
  try { snapshot = JSON.parse(raw); } catch (_) { return null; }
  const record = snapshot?.records?.bedroom;
  const received = Date.parse(record?.receivedAt);
  const recorded = Date.parse(record?.recordedAt);
  const expires = Date.parse(record?.validUntil);
  if (snapshot?.version !== OFFICE_HALLWAY_SENSOR_CONTRACT.version
      || record?.version !== OFFICE_HALLWAY_SENSOR_CONTRACT.version
      || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(snapshot?.streamEpoch)
      || record.streamEpoch !== snapshot.streamEpoch
      || record.sensorEpoch !== OFFICE_HALLWAY_SENSOR_CONTRACT.sensorEpoch
      || record.model !== OFFICE_HALLWAY_SENSOR_CONTRACT.model
      || record.sensorId !== OFFICE_HALLWAY_SENSOR_CONTRACT.sensorId
      || record.field !== OFFICE_HALLWAY_SENSOR_CONTRACT.field || record.status !== 'valid' || record.reason !== 'accepted'
      || !Number.isFinite(received) || received < Date.parse(BEDROOM_VALID_FROM)
      || received !== recorded || received > nowMs
      || !Number.isFinite(expires) || expires <= nowMs || expires <= received || expires - received > OFFICE_HALLWAY_SENSOR_CONTRACT.validityMs
      || typeof record.temperatureF !== 'number' || !Number.isFinite(record.temperatureF)
      || record.temperatureF < OFFICE_HALLWAY_SENSOR_CONTRACT.minimumF
      || record.temperatureF > OFFICE_HALLWAY_SENSOR_CONTRACT.maximumF) return null;
  return record.temperatureF;
}

const { rules, triggers, items } = require('openhab');
rules.JSRule({
  id: 'hex_bedroom_temperature',
  name: 'Bedroom source-bound temperature',
  triggers: [triggers.ItemStateUpdateTrigger('Weather_Temperature_Evidence_JSON'),
    triggers.GenericCronTrigger('0/30 * * * * ?')],
  execute: () => {
    const value = bedroomTemperature(String(items.getItem('Weather_Temperature_Evidence_JSON').state));
    items.getItem('Bedroom_Temperature').postUpdate(value === null ? 'UNDEF' : `${value} °F`);
  },
});
