// Display only. Acquisition evidence, not receiver health or a held numeric
// Item, establishes freshness. Hallway remains the current thermal model air.
export const BEDROOM_TEMPERATURE_ITEM = 'Bedroom_Temperature';
export const BEDROOM_SENSOR_ID = 223;

export function bedroomTemperature(raw, nowMs = Date.now()) {
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
      || record.model !== 'AmbientWeather-WH31E' || record.sensorId !== BEDROOM_SENSOR_ID
      || record.field !== 'tempinf' || record.status !== 'valid' || record.reason !== 'accepted'
      || !Number.isFinite(received) || received !== recorded || received > nowMs
      || !Number.isFinite(expires) || expires <= nowMs || expires <= received || expires - received > 120_000
      || typeof record.temperatureF !== 'number' || !Number.isFinite(record.temperatureF)
      || record.temperatureF < -40 || record.temperatureF > 140) return null;
  return record.temperatureF;
}
