import { currentShadeObservation } from './observation.js';
import { OFFICE_HALLWAY_TEMPERATURE_ITEM } from '../thermal/officeHallwayTemperature.js';

// The adapter remains in santyr/dooya_blinds_openhab. Populate these Item
// mappings only from the commissioned device inventory, never guessed RF IDs.
// A Rollershutter report uses 0=open and 100=closed; no optimistic state.
export const HALLWAY_TEMPERATURE_ITEM = 'AmbientWeatherWS2902A_IndoorSensor_Temperature';
export const SHADE_GROUPS = Object.freeze([
  Object.freeze({ id: 'kitchen', label: 'Kitchen', first: 1, last: 8,
    temperatureItem: HALLWAY_TEMPERATURE_ITEM, temperatureRole: 'hallway_kitchen_reference' }),
  Object.freeze({ id: 'living', label: 'Living Room', first: 9, last: 17,
    temperatureItem: null, temperatureRole: 'unavailable' }),
  Object.freeze({ id: 'bathroom', label: 'Bathroom', first: 18, last: 21,
    temperatureItem: null, temperatureRole: 'unavailable' }),
  Object.freeze({ id: 'bedroom', label: 'Bedroom', first: 22, last: 26,
    temperatureItem: OFFICE_HALLWAY_TEMPERATURE_ITEM, temperatureRole: 'bedroom_sensor' }),
]);
export const SHADE_COUNT = 26;
export const SHADE_VIEWS = Object.freeze([
  Object.freeze({ id: 'living-zones', label: 'Kitchen + Living Room', rooms: Object.freeze(['kitchen', 'living']) }),
  Object.freeze({ id: 'private-zones', label: 'Bathroom + Bedroom', rooms: Object.freeze(['bathroom', 'bedroom']) }),
]);
export const MAX_REPORT_AGE_MS = 30 * 60 * 1000;

export const SHADE_SLOTS = Object.freeze(SHADE_GROUPS.flatMap((group) =>
  Array.from({ length: group.last - group.first + 1 }, (_, index) => {
    const number = group.first + index;
    return Object.freeze({
      number,
      room: group.id,
      label: `${group.label} Shade ${String(number).padStart(2, '0')}`,
      positionItem: null,
      availabilityItem: null,
      stateItem: null,
      serviceAvailabilityItem: null,
      bridgeAvailabilityItem: null,
      serviceStateItem: null,
      bridgeStateItem: null,
      serviceThingUID: null,
      resultItem: null,
      adapterShadeId: null,
      sourceIdentity: null,
      commissionedEpoch: null,
    });
  }),
));

export function shadePreviewEnabled(slots) {
  return slots.length === SHADE_COUNT && slots.every((slot) =>
    !['positionItem','availabilityItem','stateItem','serviceAvailabilityItem','bridgeAvailabilityItem','serviceStateItem','bridgeStateItem','serviceThingUID','resultItem','adapterShadeId','sourceIdentity','commissionedEpoch'].some(key => slot[key]));
}

export function shadePosition(raw) {
  if (typeof raw !== 'string' && typeof raw !== 'number') return null;
  const value = String(raw).trim();
  if (!/^(?:100|\d{1,2})(?:\.\d+)?$/.test(value)) return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 && number <= 100 ? number : null;
}

// Historical v1 reader only. Active consumers use the session-bound v2 path.
export function parseShadeReport(raw, nowMs = Date.now()) {
  if (typeof raw !== 'string' || raw.length > 8192 || !Number.isFinite(nowMs)) return null;
  let report;
  try { report = JSON.parse(raw); } catch { return null; }
  if (!report || typeof report !== 'object' || Array.isArray(report)
      || report.schema_version !== 1 || report.source !== 'motor_report' || report.stale !== false
      || !Number.isInteger(report.reported_position) || report.reported_position < 0 || report.reported_position > 100
      || typeof report.report_received_at !== 'number' || !Number.isFinite(report.report_received_at)) return null;
  const ageMs = nowMs - report.report_received_at * 1000;
  if (ageMs < -60_000 || ageMs > MAX_REPORT_AGE_MS) return null;
  return { position: report.reported_position, observedAtMs: report.report_received_at * 1000, ageMs };
}

export function shadePresentation(slot, states, connection, nowMs = Date.now(), providers = {}) {
  return currentShadeObservation(slot, states, connection, nowMs, providers);
}

export function shadeGroupPresentation(slots, states, connection, nowMs = Date.now(), providers = {}) {
  const reports = slots.map((slot) => shadePresentation(slot, states, connection, nowMs, providers));
  if (reports.length === 0 || reports.some((report) => report.state !== 'reported')) {
    return { state: 'unavailable', openPercent: null, label: 'Position unavailable' };
  }
  const first = reports[0].openPercent;
  if (reports.some((report) => report.openPercent !== first)) {
    return { state: 'mixed', openPercent: null, label: 'Mixed positions' };
  }
  return { state: 'reported', openPercent: first, label: `${first}% open` };
}
