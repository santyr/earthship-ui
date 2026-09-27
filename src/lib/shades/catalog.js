// The adapter remains in santyr/dooya_blinds_openhab. Populate these Item
// mappings only from the commissioned device inventory, never guessed RF IDs.
// A Rollershutter report uses 0=open and 100=closed; no optimistic state.
export const SHADE_COUNT = 26;
export const SHADES_PER_PAGE = 13;
export const MAX_REPORT_AGE_MS = 30 * 60 * 1000;

export const SHADE_SLOTS = Object.freeze(Array.from({ length: SHADE_COUNT }, (_, index) =>
  Object.freeze({
    number: index + 1,
    label: `Shade ${String(index + 1).padStart(2, '0')}`,
    positionItem: null,
    availabilityItem: null,
    stateItem: null,
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
    label: position === 0 ? 'Open' : position === 100 ? 'Closed' : `${position}% closed`,
    position,
    observedAtMs: report.observedAtMs,
  };
}
