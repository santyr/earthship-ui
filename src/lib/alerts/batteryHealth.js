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
