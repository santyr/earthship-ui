// The adapter remains in santyr/dooya_blinds_openhab. Populate these Item
// mappings only from the commissioned device inventory, never guessed RF IDs.
// A Rollershutter report uses 0=open and 100=closed; no optimistic state.
export const HALLWAY_TEMPERATURE_ITEM = 'AmbientWeatherWS2902A_IndoorSensor_Temperature';
export const SHADE_GROUPS = Object.freeze([
  Object.freeze({ id: 'kitchen', label: 'Kitchen', first: 1, last: 8,
    temperatureItem: HALLWAY_TEMPERATURE_ITEM, temperatureRole: 'hallway_kitchen_reference' }),
  Object.freeze({ id: 'living', label: 'Living Room', first: 9, last: 17,
    temperatureItem: HALLWAY_TEMPERATURE_ITEM, temperatureRole: 'hallway_proxy' }),
  Object.freeze({ id: 'bathroom', label: 'Bathroom', first: 18, last: 22,
    temperatureItem: null, temperatureRole: 'unavailable' }),
  Object.freeze({ id: 'bedroom', label: 'Bedroom', first: 23, last: 27,
    temperatureItem: HALLWAY_TEMPERATURE_ITEM, temperatureRole: 'hallway_proxy' }),
]);
export const SHADE_COUNT = 27;
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
    });
  }),
));

export function shadePosition(raw) {
  if (typeof raw !== 'string' && typeof raw !== 'number') return null;
  const value = String(raw).trim();
  if (!/^(?:100|\d{1,2})(?:\.\d+)?$/.test(value)) return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 && number <= 100 ? number : null;
}

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

export function shadePresentation(slot, states, connection, nowMs = Date.now()) {
  if (!slot?.positionItem || !slot?.availabilityItem || !slot?.stateItem) {
    return { state: 'unmapped', label: 'Awaiting Item mapping', position: null };
  }
  if (connection !== 'live') {
    return { state: 'unavailable', label: 'openHAB unavailable', position: null };
  }
  const availability = states?.[slot.availabilityItem];
  if (availability !== 'ON') {
    return { state: 'unavailable', label: availability === 'OFF' ? 'Shade offline' : 'Availability unknown', position: null };
  }
  const report = parseShadeReport(states?.[slot.stateItem], nowMs);
  if (!report) {
    return { state: 'unavailable', label: 'No fresh position report', position: null };
  }
  const position = shadePosition(states?.[slot.positionItem]);
  if (position !== report.position) {
    return { state: 'unavailable', label: 'Position sources disagree', position: null };
  }
  return {
    state: 'reported',
    label: position === 0 ? 'Open' : position === 100 ? 'Closed' : `${100 - position}% open`,
    position,
    openPercent: 100 - position,
    observedAtMs: report.observedAtMs,
  };
}

export function shadeGroupPresentation(slots, states, connection, nowMs = Date.now()) {
  const reports = slots.map((slot) => shadePresentation(slot, states, connection, nowMs));
  if (reports.length === 0 || reports.some((report) => report.state !== 'reported')) {
    return { state: 'unavailable', openPercent: null, label: 'Position unavailable' };
  }
  const first = reports[0].openPercent;
  if (reports.some((report) => report.openPercent !== first)) {
    return { state: 'mixed', openPercent: null, label: 'Mixed positions' };
  }
  return { state: 'reported', openPercent: first, label: `${first}% open` };
}
