export function normalizedComms(value) {
  const text = value == null ? '' : String(value).trim();
  return ['', 'NULL', 'UNDEF'].includes(text.toUpperCase()) ? '' : text;
}
export function normalizedDevicePresent(value) {
  const normalized = normalizedComms(value).toUpperCase();
  if (!normalized) return null;
  if (['1', 'ON', 'TRUE', 'PRESENT', 'ONLINE', 'OK'].includes(normalized)) return true;
  if (['0', 'OFF', 'FALSE', 'ABSENT', 'OFFLINE', 'ERROR', 'FAULT'].includes(normalized)) return false;
  return null;
}

export function bmsHealthPresentation(commsValue, deviceValue) {
  const comms = normalizedComms(commsValue).toUpperCase();
  const present = normalizedDevicePresent(deviceValue);
  if (present === false) return { state: 'fault', label: 'Absent', detail: 'BMS device reports absent.' };
  if (comms === 'OK') return present === true
    ? { state: 'ok', label: 'OK', detail: 'BMS communications and device presence report OK.' }
    : { state: 'unknown', label: 'Unknown', detail: 'BMS device presence is unavailable.' };
  if (/^STALE(?:\b|$)/.test(comms)) {
    return { state: 'stale', label: 'Stale', detail: 'BMS communications are stale; held values do not establish current health.' };
  }
  if (comms) return { state: 'fault', label: 'Fault', detail: 'BMS communications report a fault.' };
  return { state: 'unknown', label: 'Unknown', detail: 'BMS communication status is unavailable.' };
}
