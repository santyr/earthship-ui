import { atomicSocFreshness } from '../alerts/atomicSoc.js';
import { normalizedComms, normalizedDevicePresent } from '../alerts/batteryHealth.js';

// The numeric BMS_SOC Item is change-only and cannot establish current source
// health. Its scaled, source-bound receipt carries the current display value.
export function freshCurrentSoc(items, nowMs = Date.now()) {
  if (normalizedComms(items?.BMS_Comms_Status).toUpperCase() !== 'OK'
      || normalizedDevicePresent(items?.BMS_DevicePresent) !== true) return null;
  return atomicSocFreshness(items?.BMS_SOC_Evidence_JSON, nowMs)?.soc ?? null;
}
