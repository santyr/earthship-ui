export const ENERGY_ANALYTICS_MAX_BYTES = 16 * 1024;
export const ENERGY_ANALYTICS_STALE_MS = 15 * 60_000;
const FUTURE_TOLERANCE_MS = 2 * 60_000;
const SCHEMA = 'earthship-energy-ui/v1';
const STATUS = new Set(['ok', 'degraded', 'unavailable', 'stale', 'fault']);
const FORECAST_STATUS = new Set(['current', 'stale', 'unavailable', 'degraded']);

const TOP = ['battery', 'energy', 'epochId', 'forecast', 'generatedAt', 'health',
  'lifecycle', 'schema', 'status', 'throughDate', 'timezone', 'winter'];
const BATTERY = ['currentNoFullDays', 'daysSinceFull', 'endingCumulativeEfc',
  'latestMinSocPct', 'latestReached99', 'status'];
const ENERGY = ['activeLoads', 'latest', 'observedCurtailmentKwh',
  'observedCurtailmentStatus', 'status'];
const LATEST = ['chargeKwh', 'date', 'dischargeKwh', 'loadKwh', 'pvKwh'];
const ACTIVE = ['measurement', 'reason', 'status'];
const WINTER = ['longestNoFullDays', 'lowestSocPct', 'medianMinSocPct',
  'observationDays', 'status', 'worstDeficitPeriod'];
const DEFICIT = ['days', 'deficitKwh', 'end', 'loadKwh', 'pvKwh', 'start',
  'timeToReach99Days'];
const LIFECYCLE = ['chargeKwh', 'dischargeKwh', 'endingCumulativeEfc',
  'highSocHoursAbove90', 'highSocHoursAbove95', 'moduleHealth', 'periodEfc',
  'stateOfHealthPct', 'status'];
const MODULE = ['latestCurrentSharingRangeA', 'maximumCellSpreadMv', 'moduleCount',
  'reason', 'status'];
const FORECAST = ['fullToday', 'fullTomorrow', 'issuedAt', 'nextMorningSocPct',
  'pv24hKwh', 'reason', 'status', 'validFor'];
const HEALTH = ['analytics', 'bms', 'collector', 'forecast', 'reasons',
  'schneider', 'status', 'weather'];

function unavailable(reason) {
  return Object.freeze({
    state: 'unavailable', generatedAtMs: null, throughDate: null, epochId: null,
    battery: null, energy: null, winter: null, lifecycle: null, forecast: null,
    health: null, reasons: Object.freeze([reason]),
  });
}

function exact(value, keys, path) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${path}_shape`);
  }
  const actual = Object.keys(value).sort();
  if (actual.length !== keys.length || actual.some((key, index) => key !== keys[index])) {
    throw new Error(`${path}_fields`);
  }
  return value;
}

function number(value, path, optional = true) {
  if (value === null && optional) return null;
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`${path}_number`);
  return value;
}

function integer(value, path, optional = true) {
  if (value === null && optional) return null;
  if (!Number.isInteger(value) || value < 0) throw new Error(`${path}_integer`);
  return value;
}

function bool(value, path, optional = true) {
  if (value === null && optional) return null;
  if (typeof value !== 'boolean') throw new Error(`${path}_boolean`);
  return value;
}

function status(value, path) {
  if (!STATUS.has(value)) throw new Error(`${path}_status`);
  return value;
}

function timestamp(value, path, optional = false) {
  if (value === null && optional) return null;
  if (typeof value !== 'string' || !/(?:Z|[+-]\d\d:\d\d)$/.test(value)) {
    throw new Error(`${path}_timestamp`);
  }
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) throw new Error(`${path}_timestamp`);
  return parsed;
}

function date(value, path, optional = false) {
  if (value === null && optional) return null;
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)
      || Number.isNaN(Date.parse(`${value}T00:00:00Z`))) throw new Error(`${path}_date`);
  return value;
}

function boundedText(value, path, optional = true) {
  if (value === null && optional) return null;
  if (typeof value !== 'string' || new TextEncoder().encode(value).byteLength > 256
      || /[<>]/.test(value)) throw new Error(`${path}_text`);
  return value;
}

function validatePayload(payload) {
  exact(payload, TOP, 'payload');
  if (payload.schema !== SCHEMA) throw new Error('schema');
  const generatedAtMs = timestamp(payload.generatedAt, 'generatedAt');
  if (typeof payload.timezone !== 'string' || payload.timezone !== 'America/Denver') {
    throw new Error('timezone');
  }
  if (typeof payload.epochId !== 'string' || !payload.epochId
      || payload.epochId.length > 128 || /[<>]/.test(payload.epochId)) throw new Error('epochId');
  date(payload.throughDate, 'throughDate', true);
  status(payload.status, 'payload');

  const battery = exact(payload.battery, BATTERY, 'battery');
  status(battery.status, 'battery');
  number(battery.latestMinSocPct, 'battery_latestMinSocPct');
  bool(battery.latestReached99, 'battery_latestReached99');
  number(battery.endingCumulativeEfc, 'battery_endingCumulativeEfc');
  integer(battery.currentNoFullDays, 'battery_currentNoFullDays');
  integer(battery.daysSinceFull, 'battery_daysSinceFull');

  const energy = exact(payload.energy, ENERGY, 'energy');
  status(energy.status, 'energy');
  if (energy.latest !== null) {
    const latest = exact(energy.latest, LATEST, 'energy_latest');
    date(latest.date, 'energy_latest_date');
    for (const field of ['chargeKwh', 'dischargeKwh', 'loadKwh', 'pvKwh']) {
      number(latest[field], `energy_latest_${field}`, false);
    }
    if (payload.throughDate !== null && latest.date !== payload.throughDate) {
      throw new Error('energy_latest_throughDate');
    }
  }
  const active = exact(energy.activeLoads, ACTIVE, 'energy_activeLoads');
  status(active.status, 'energy_activeLoads');
  if (active.measurement !== 'state_only') throw new Error('active_load_measurement');
  boundedText(active.reason, 'active_load_reason', false);
  number(energy.observedCurtailmentKwh, 'observedCurtailmentKwh');
  status(energy.observedCurtailmentStatus, 'observedCurtailment');

  const winter = exact(payload.winter, WINTER, 'winter');
  status(winter.status, 'winter');
  integer(winter.observationDays, 'winter_observationDays', false);
  number(winter.lowestSocPct, 'winter_lowestSocPct');
  number(winter.medianMinSocPct, 'winter_medianMinSocPct');
  integer(winter.longestNoFullDays, 'winter_longestNoFullDays');
  if (winter.worstDeficitPeriod !== null) {
    const deficit = exact(winter.worstDeficitPeriod, DEFICIT, 'winter_deficit');
    date(deficit.start, 'winter_deficit_start');
    date(deficit.end, 'winter_deficit_end');
    integer(deficit.days, 'winter_deficit_days', false);
    integer(deficit.timeToReach99Days, 'winter_recovery');
    for (const field of ['deficitKwh', 'loadKwh', 'pvKwh']) {
      number(deficit[field], `winter_deficit_${field}`, false);
    }
  }

  const lifecycle = exact(payload.lifecycle, LIFECYCLE, 'lifecycle');
  status(lifecycle.status, 'lifecycle');
  for (const field of ['chargeKwh', 'dischargeKwh', 'endingCumulativeEfc',
    'highSocHoursAbove90', 'highSocHoursAbove95', 'periodEfc', 'stateOfHealthPct']) {
    number(lifecycle[field], `lifecycle_${field}`);
  }
  const moduleHealth = exact(lifecycle.moduleHealth, MODULE, 'moduleHealth');
  status(moduleHealth.status, 'moduleHealth');
  boundedText(moduleHealth.reason, 'moduleHealth_reason');
  integer(moduleHealth.moduleCount, 'moduleHealth_moduleCount');
  number(moduleHealth.latestCurrentSharingRangeA, 'moduleHealth_currentRange');
  number(moduleHealth.maximumCellSpreadMv, 'moduleHealth_cellSpread');

  const forecast = exact(payload.forecast, FORECAST, 'forecast');
  if (!FORECAST_STATUS.has(forecast.status)) throw new Error('forecast_status');
  timestamp(forecast.issuedAt, 'forecast_issuedAt', true);
  timestamp(forecast.validFor, 'forecast_validFor', true);
  number(forecast.pv24hKwh, 'forecast_pv24hKwh');
  number(forecast.nextMorningSocPct, 'forecast_nextMorningSocPct');
  bool(forecast.fullToday, 'forecast_fullToday');
  bool(forecast.fullTomorrow, 'forecast_fullTomorrow');
  boundedText(forecast.reason, 'forecast_reason');

  const health = exact(payload.health, HEALTH, 'health');
  for (const field of ['status', 'analytics', 'bms', 'collector', 'forecast',
    'schneider', 'weather']) status(health[field], `health_${field}`);
  if (!Array.isArray(health.reasons) || health.reasons.length > 16) throw new Error('health_reasons');
  health.reasons.forEach((reason, index) => boundedText(reason, `health_reason_${index}`, false));
  return generatedAtMs;
}

function deepFreeze(value) {
  if (!value || typeof value !== 'object' || Object.isFrozen(value)) return value;
  Object.values(value).forEach(deepFreeze);
  return Object.freeze(value);
}

export function parseEnergyAnalyticsResult(raw, nowMs = Date.now()) {
  if (typeof raw !== 'string' || !raw.trim() || ['NULL', 'UNDEF'].includes(raw.trim())) {
    return unavailable('analytics_payload_unavailable');
  }
  if (new TextEncoder().encode(raw).byteLength >= ENERGY_ANALYTICS_MAX_BYTES) {
    return unavailable('analytics_payload_too_large');
  }
  if (!Number.isFinite(nowMs)) return unavailable('analytics_clock_invalid');
  let payload;
  try {
    payload = JSON.parse(raw);
    const generatedAtMs = validatePayload(payload);
    if (generatedAtMs - nowMs > FUTURE_TOLERANCE_MS) {
      return unavailable('analytics_payload_from_future');
    }
    const stale = nowMs - generatedAtMs > ENERGY_ANALYTICS_STALE_MS;
    const reasons = [...payload.health.reasons];
    if (stale) reasons.push('analytics_payload_stale');
    return deepFreeze({
      state: stale ? 'stale' : payload.status === 'ok' ? 'ready' : payload.status,
      generatedAtMs,
      throughDate: payload.throughDate,
      epochId: payload.epochId,
      battery: structuredClone(payload.battery),
      energy: structuredClone(payload.energy),
      winter: structuredClone(payload.winter),
      lifecycle: structuredClone(payload.lifecycle),
      forecast: structuredClone(payload.forecast),
      health: structuredClone(payload.health),
      reasons,
    });
  } catch {
    return unavailable('analytics_payload_invalid');
  }
}
