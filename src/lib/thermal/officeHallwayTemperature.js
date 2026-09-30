// Display only. Acquisition evidence, not receiver health or a held numeric
// Item, establishes freshness. Hallway remains the current thermal model air.
// Legacy Item/stream identifiers preserve JDBC Item 663 and original receipts.
// The operator moved this sensor to Office Hallway on September 30; earlier
// commissioning observations must not be relabeled as that room's history.
export const OFFICE_HALLWAY_TEMPERATURE_ITEM = 'Bedroom_Temperature';
export const OFFICE_HALLWAY_SENSOR_ID = 223;
export const OFFICE_HALLWAY_VALID_FROM = '2026-09-30T23:15:00Z';

export function officeHallwayTemperature(raw, nowMs = Date.now()) {
  if (typeof raw !== 'string' || raw.length > 8192 || !Number.isFinite(nowMs)) return null;
  let snapshot;
  try { snapshot = JSON.parse(raw); } catch { return null; }
  const record = snapshot?.records?.bedroom;
  const received = Date.parse(record?.receivedAt);
  const recorded = Date.parse(record?.recordedAt);
  const expires = Date.parse(record?.validUntil);
  if (snapshot?.version !== 1 || record?.version !== 1
      || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(snapshot?.streamEpoch)
      || record.streamEpoch !== snapshot.streamEpoch
      || record.model !== 'AmbientWeather-WH31E' || record.sensorId !== OFFICE_HALLWAY_SENSOR_ID
      || record.field !== 'tempinf' || record.status !== 'valid' || record.reason !== 'accepted'
      || !Number.isFinite(received) || received !== recorded || received > nowMs
      || !Number.isFinite(expires) || expires <= nowMs || expires <= received || expires - received > 120_000
      || typeof record.temperatureF !== 'number' || !Number.isFinite(record.temperatureF)
      || record.temperatureF < -40 || record.temperatureF > 140) return null;
  return record.temperatureF;
}
