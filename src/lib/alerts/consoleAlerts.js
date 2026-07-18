import { num } from '../openhab/values.js';
import { adaptCurrentAqi } from '../ui/homeCardState.js';

export const CONTROL_OUTCOME_TTL_MS = 15 * 60_000;

export const ALERT_PRIORITY = Object.freeze([
  'connection-offline',
  'battery-critical',
  'telemetry-stale',
  'thermal-close',
  'soc-trough',
  'aqi-unhealthy',
  'thermal-vent',
  'control-outcome',
]);

const PRIORITY_INDEX = new Map(ALERT_PRIORITY.map((key, index) => [key, index]));
const SEVERITY_INDEX = Object.freeze({ critical: 0, warning: 1, advisory: 2, info: 3 });
const NULLISH = new Set(['', 'NULL', 'UNDEF']);
const CONTROL_ALERT_PHASES = new Set(['failed', 'sent-unconfirmed', 'outcome-unknown']);

function clean(value) {
  if (value === undefined || value === null) return '';
  const text = String(value).trim();
  return NULLISH.has(text.toUpperCase()) ? '' : text;
}

function numeric(value) {
  const parsed = num(value);
  return parsed === null || !Number.isFinite(parsed) ? null : parsed;
}

function baseAlert({ id, severity, shortText, fullText = shortText, route = null,
  dedupeKey = id, priorityKey, priorityOffset = 0, transitionAt }) {
  return {
    id, severity, shortText, fullText, route, dedupeKey, priorityKey, priorityOffset,
    ...(Number.isFinite(transitionAt) ? { transitionAt } : {}),
  };
}

function normalizedDevicePresent(value) {
  const normalized = clean(value).toUpperCase();
  if (!normalized) return null;
  if (['1', 'ON', 'TRUE', 'PRESENT', 'ONLINE', 'OK'].includes(normalized)) return true;
  if (['0', 'OFF', 'FALSE', 'ABSENT', 'OFFLINE', 'ERROR', 'FAULT'].includes(normalized)) return false;
  return null;
}

function stateSignature(alert) {
  return JSON.stringify([
    alert.id, alert.severity, alert.shortText, alert.fullText, alert.route,
    alert.dedupeKey, alert.priorityKey, alert.priorityOffset,
  ]);
}

export function compareConsoleAlerts(a, b) {
  const severity = (SEVERITY_INDEX[a.severity] ?? 99) - (SEVERITY_INDEX[b.severity] ?? 99);
  if (severity !== 0) return severity;
  const priority = (PRIORITY_INDEX.get(a.priorityKey) ?? 99) - (PRIORITY_INDEX.get(b.priorityKey) ?? 99);
  if (priority !== 0) return priority;
  const offset = (a.priorityOffset ?? 0) - (b.priorityOffset ?? 0);
  if (offset !== 0) return offset;
  const transition = (b.activeSince ?? b.transitionAt ?? 0) - (a.activeSince ?? a.transitionAt ?? 0);
  if (transition !== 0) return transition;
  return a.id.localeCompare(b.id);
}

function dedupeAndSort(alerts) {
  const ordered = [...alerts].sort(compareConsoleAlerts);
  const seen = new Set();
  return ordered.filter((alert) => {
    if (seen.has(alert.dedupeKey)) return false;
    seen.add(alert.dedupeKey);
    return true;
  });
}

/**
 * @typedef {object} ConsoleAlert
 * @property {string} id
 * @property {'critical'|'warning'|'advisory'|'info'} severity
 * @property {string} shortText
 * @property {string} fullText
 * @property {'home'|'energy'|'weather'|'earthship'|'controls'|null} route
 * @property {string} dedupeKey
 * @property {number=} activeSince
 */

/**
 * Project approved console sources into deterministic alerts. Explicit
 * stale/alarm inputs prevent the client from guessing cadence or thresholds.
 */
export function projectConsoleAlerts({ connection = 'connecting', items = {}, staleEssentials = [],
  batteryAlarms = [], outcomes = [], now = Date.now() } = {}) {
  const alerts = [];
  const diagnostics = [];

  if (connection === 'offline') {
    alerts.push(baseAlert({
      id: 'connection-offline', severity: 'critical', shortText: 'openHAB offline',
      fullText: 'openHAB offline. Live telemetry and controls are unavailable.',
      route: null, dedupeKey: 'connection:offline', priorityKey: 'connection-offline',
    }));
  }

  const comms = clean(items.BMS_Comms_Status);
  if (comms && comms.toUpperCase() !== 'OK') {
    alerts.push(baseAlert({
      id: 'battery-comms-critical', severity: 'critical', shortText: 'BMS communication fault',
      fullText: `BMS communication status: ${comms}`, route: 'energy',
      dedupeKey: 'battery:bms-comms', priorityKey: 'battery-critical', priorityOffset: 0,
    }));
  }

  if (normalizedDevicePresent(items.BMS_DevicePresent) === false) {
    alerts.push(baseAlert({
      id: 'battery-device-critical', severity: 'critical', shortText: 'BMS device absent',
      fullText: 'The battery-management device is not present.', route: 'energy',
      dedupeKey: 'battery:bms-device', priorityKey: 'battery-critical', priorityOffset: 1,
    }));
  }

  for (const alarm of Array.isArray(batteryAlarms) ? batteryAlarms : []) {
    if (!alarm?.active) continue;
    const alarmId = clean(alarm.id) || 'active';
    const text = clean(alarm.text) || 'Battery alarm active';
    alerts.push(baseAlert({
      id: `battery-alarm:${alarmId}`, severity: 'critical', shortText: text,
      fullText: clean(alarm.fullText) || text, route: 'energy',
      dedupeKey: clean(alarm.dedupeKey) || `battery:alarm:${alarmId}`,
      priorityKey: 'battery-critical', priorityOffset: 2,
      transitionAt: Number(alarm.transitionAt),
    }));
  }

  const soc = numeric(items.BMS_SOC);
  if (soc !== null && soc <= 12) {
    const rounded = Math.round(soc);
    alerts.push(baseAlert({
      id: 'battery-soc-critical', severity: 'critical',
      shortText: `Battery SoC critical · ${rounded}%`,
      fullText: `Battery SoC critical: current state of charge is ${rounded}%.`, route: 'energy',
      dedupeKey: 'battery:current-soc', priorityKey: 'battery-critical', priorityOffset: 3,
    }));
  }

  for (const stale of Array.isArray(staleEssentials) ? staleEssentials : []) {
    const name = clean(stale?.name);
    if (!name) continue;
    const label = clean(stale.label) || name;
    alerts.push(baseAlert({
      id: `telemetry-stale:${name}`,
      severity: stale.severity === 'critical' ? 'critical' : 'warning',
      shortText: `${label} stale`, fullText: clean(stale.fullText) || `${label} telemetry is stale.`,
      route: stale.route ?? null, dedupeKey: `telemetry:stale:${name}`,
      priorityKey: 'telemetry-stale', transitionAt: Number(stale.transitionAt),
    }));
  }

  const thermalParts = clean(items.Thermal_Advisory).split('|');
  const thermalCode = clean(thermalParts.shift()).toLowerCase();
  const thermalText = clean(thermalParts.join('|'));
  if (thermalCode === 'close_up_tomorrow') {
    alerts.push(baseAlert({
      id: 'thermal-close', severity: 'warning', shortText: thermalText || 'Close up tomorrow',
      fullText: thermalText || 'Close up tomorrow to retain thermal mass.', route: 'earthship',
      dedupeKey: 'thermal:close-up-tomorrow', priorityKey: 'thermal-close',
    }));
  } else if (thermalCode === 'vent_tonight') {
    alerts.push(baseAlert({
      id: 'thermal-vent', severity: 'advisory', shortText: thermalText || 'Vent tonight',
      fullText: thermalText || 'Vent tonight when outdoor conditions permit.', route: 'earthship',
      dedupeKey: 'thermal:vent-tonight', priorityKey: 'thermal-vent',
    }));
  } else if (thermalCode && thermalCode !== 'none') {
    alerts.push(baseAlert({
      id: `thermal-unknown:${thermalCode}`, severity: 'warning',
      shortText: thermalText || `Thermal advisory · ${thermalCode}`,
      fullText: thermalText || `Unknown thermal advisory code: ${thermalCode}`,
      route: 'earthship', dedupeKey: `thermal:unknown:${thermalCode}`, priorityKey: 'thermal-close',
    }));
    diagnostics.push({
      code: 'unknown-thermal-code', value: thermalCode,
      message: `Unknown Thermal_Advisory code: ${thermalCode}`,
    });
  }

  const trough = numeric(items.Predicted_SoC_Trough_Tomorrow);
  if (trough !== null && trough < 40) {
    const rounded = Math.round(trough);
    alerts.push(baseAlert({
      id: 'soc-trough', severity: trough <= 12 ? 'critical' : 'warning',
      shortText: `Predicted SoC trough · ${rounded}%`,
      fullText: `Predicted battery state-of-charge trough is ${rounded}%.`, route: 'energy',
      dedupeKey: 'battery:predicted-trough', priorityKey: 'soc-trough',
    }));
  }

  const currentAqi = adaptCurrentAqi(items.Current_US_AQI);
  if (currentAqi.value !== null && currentAqi.value >= 101) {
    const rounded = currentAqi.value;
    alerts.push(baseAlert({
      id: 'aqi-unhealthy', severity: 'warning', shortText: `AQI ${rounded}`,
      fullText: `Modeled US AQI ${rounded} is unhealthy.`, route: 'weather',
      dedupeKey: 'aqi:current-us', priorityKey: 'aqi-unhealthy',
    }));
  }

  for (const outcome of Array.isArray(outcomes) ? outcomes : []) {
    const controlId = clean(outcome?.controlId);
    const phase = clean(outcome?.phase).toLowerCase();
    const transitionAt = Number(outcome?.transitionAt);
    if (!controlId || !CONTROL_ALERT_PHASES.has(phase) || !Number.isFinite(transitionAt)) continue;
    if (transitionAt + CONTROL_OUTCOME_TTL_MS <= now) continue;
    const label = clean(outcome.controlLabel) || controlId;
    const phaseText = phase === 'failed' ? 'failed'
      : phase === 'sent-unconfirmed' ? 'unconfirmed' : 'outcome unknown';
    const reason = clean(outcome.reason);
    alerts.push(baseAlert({
      id: `control-outcome:${controlId}`, severity: 'warning',
      shortText: `${label} ${phaseText}`,
      fullText: reason ? `${label} ${phaseText}: ${reason}` : `${label} ${phaseText}.`,
      route: 'controls', dedupeKey: `control:${controlId}`,
      priorityKey: 'control-outcome', transitionAt,
    }));
  }

  return { alerts: dedupeAndSort(alerts), diagnostics };
}

export function createAlertProjector({ now = Date.now } = {}) {
  let previous = new Map();
  return {
    update(input = {}) {
      const at = now();
      const projected = projectConsoleAlerts({ ...input, now: at });
      const next = new Map();
      const alerts = projected.alerts.map((alert) => {
        const prior = previous.get(alert.dedupeKey);
        const signature = stateSignature(alert);
        const activeSince = Number.isFinite(alert.transitionAt) ? alert.transitionAt
          : prior?.signature === signature ? prior.activeSince : at;
        next.set(alert.dedupeKey, { signature, activeSince });
        return { ...alert, activeSince };
      });
      previous = next;
      return { alerts: dedupeAndSort(alerts), diagnostics: projected.diagnostics };
    },
    reset() { previous = new Map(); },
  };
}

export function selectHeaderAlerts(input) {
  const ordered = dedupeAndSort(Array.isArray(input) ? input : input?.alerts ?? []);
  return { winner: ordered[0] ?? null, additionalCount: Math.max(0, ordered.length - 1), ordered };
}
