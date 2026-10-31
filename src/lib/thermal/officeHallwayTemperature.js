// Display only. Acquisition evidence, not receiver health or a held numeric
// Item, establishes freshness. Hallway remains the current thermal model air.
// Legacy Item/stream identifiers preserve JDBC Item 663 and original receipts.
// The operator moved this sensor to Office Hallway on September 30; earlier
// commissioning observations must not be relabeled as that room's history.
// Current physical location: Bedroom, operator-reported October24.
// Legacy module/API names preserve compatibility; the new operational boundary
// prevents earlier Office Hallway receipts being presented as Bedroom readings.
// This boundary is not a claim of the exact physical move time.
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

export const OFFICE_HALLWAY_TEMPERATURE_ITEM = 'Bedroom_Temperature';
export const OFFICE_HALLWAY_SENSOR_ID = OFFICE_HALLWAY_SENSOR_CONTRACT.sensorId;
export const OFFICE_HALLWAY_VALID_FROM = '2026-09-30T23:15:00Z';
export const BEDROOM_VALID_FROM = '2026-10-24T23:14:52Z';

export function officeHallwayTemperature(raw, nowMs = Date.now()) {
  if (typeof raw !== 'string' || raw.length > 8192 || !Number.isFinite(nowMs)) return null;
  let snapshot;
  try { snapshot = JSON.parse(raw); } catch { return null; }
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
