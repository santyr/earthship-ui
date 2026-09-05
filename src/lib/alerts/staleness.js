import { parseSourceTimestamp } from '../openhab/timestamp.js';
import { normalizedComms, normalizedDevicePresent } from './batteryHealth.js';

export const ESSENTIAL_STALE_THRESHOLD_MS = 15 * 60000;
export const STALENESS_CHECK_INTERVAL_MS = 60000;
export const ESSENTIAL_ITEMS = Object.freeze([
  Object.freeze({ name: 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', label: 'Outdoor temperature', route: 'home' }),
  Object.freeze({ name: 'AmbientWeatherWS2902A_IndoorSensor_Temperature', label: 'Indoor temperature', route: 'home' }),
  Object.freeze({ name: 'BMS_SOC', label: 'Battery SoC', route: 'energy', thresholdMs: 12 * 60000 }),
]);
export const TEMPERATURE_ITEMS = Object.freeze(ESSENTIAL_ITEMS.filter(item => item.name !== 'BMS_SOC'));

export function computeStaleEssentials(evidence = {}, nowMs = Date.now(), { values = {}, ready = false } = {}) {
  if (!ready) return [];
  const stale = [];
  for (const item of ESSENTIAL_ITEMS) {
    const limit = item.thresholdMs ?? ESSENTIAL_STALE_THRESHOLD_MS;
    let timestamp;
    if (item.name === 'BMS_SOC') {
      const comms = normalizedComms(values.BMS_Comms_Status);
      if ((comms && comms.toUpperCase() !== 'OK') || normalizedDevicePresent(values.BMS_DevicePresent) === false) continue;
      timestamp = comms ? parseSourceTimestamp(values.BMS_SOC_LastUpdate, nowMs) : null;
    } else {
      const source = evidence[item.name];
      timestamp = source?.available ? parseSourceTimestamp(source.lastKnown, nowMs) : null;
    }
    const unavailable = timestamp === null;
    if (!unavailable && nowMs - timestamp <= limit) continue;
    stale.push({
      name: item.name, label: item.label, route: item.route, severity: 'warning',
      ...(unavailable ? { unavailable: true } : { transitionAt: timestamp + limit }),
      fullText: unavailable ? `${item.label} freshness is unavailable.`
        : `${item.label} has not updated in over ${Math.round(limit / 60000)} minutes.`,
    });
  }
  return stale;
}
