export const ENERGY_ANALYTICS_MAX_BYTES = 16 * 1024;
export const ENERGY_ANALYTICS_STALE_MS = 15 * 60_000;
export const ENERGY_ANALYTICS_REFRESH_MS = 30_000;
const SCHEMAS = new Set(['earthship-energy-ui/v1', 'earthship-energy-ui/v2', 'earthship-energy-ui/v3']);
const STATUS = new Set(['ok', 'degraded', 'unavailable', 'stale', 'fault']);
const FORECAST_STATUS = new Set(['current', 'stale', 'unavailable', 'degraded']);

const TOP = ['battery', 'energy', 'epochId', 'forecast', 'generatedAt', 'health',
  'lifecycle', 'schema', 'status', 'throughDate', 'timezone', 'winter'];
const ACCOUNTING = ['basis', 'cutover', 'daysPresent', 'latestBatteryCoverage',
  'latestPvCoverage', 'latestRevision', 'loadStatus', 'missingDays', 'policy',
  'windowEndExclusive', 'windowStart'];
const BATTERY = ['currentNoFullDays', 'daysSinceFull', 'endingCumulativeEfc',
  'latestMinSocPct', 'latestReached99', 'status'];
const BATTERY_V2 = [...BATTERY, 'latestDepthOfDischargePct', 'latestEfc'].sort();
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
const HEALTH = ['analytics', 'bms', 'collector', 'forecast', 'publisher', 'reasons',
  'schneider', 'status', 'weather'];

function unavailable(reason) {
  return Object.freeze({
    state: 'unavailable', generatedAtMs: null, throughDate: null, epochId: null,
    battery: null, energy: null, winter: null, lifecycle: null, forecast: null,
    health: null, accounting: null, reasons: Object.freeze([reason]),
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
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    throw new Error(path + "_date");
  }
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1
      || parsed.getUTCDate() !== day) throw new Error(path + "_date");
  return value;
}

function localDate(ms, timezone) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date(ms));
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return byType.year + "-" + byType.month + "-" + byType.day;
}

function boundedText(value, path, optional = true) {
  if (value === null && optional) return null;
  if (typeof value !== 'string' || new TextEncoder().encode(value).byteLength > 256
      || /[<>]/.test(value)) throw new Error(`${path}_text`);
  return value;
}

function validatePayload(payload) {
  const qualified = payload?.schema === 'earthship-energy-ui/v3';
  exact(payload, qualified ? ['accounting', ...TOP] : TOP, 'payload');
  if (!SCHEMAS.has(payload.schema)) throw new Error('schema');
  const generatedAtMs = timestamp(payload.generatedAt, 'generatedAt');
  if (typeof payload.timezone !== 'string' || payload.timezone !== 'America/Denver') {
    throw new Error('timezone');
  }
  if (typeof payload.epochId !== 'string' || !payload.epochId
      || payload.epochId.length > 128 || /[<>]/.test(payload.epochId)) throw new Error('epochId');
  date(payload.throughDate, 'throughDate', true);
  if (payload.throughDate !== null
      && payload.throughDate > localDate(generatedAtMs, payload.timezone)) {
    throw new Error('throughDate_generatedAt');
  }
  status(payload.status, 'payload');

  const battery = exact(
    payload.battery,
    payload.schema !== 'earthship-energy-ui/v1' ? BATTERY_V2 : BATTERY,
    'battery',
  );
  status(battery.status, 'battery');
  number(battery.latestMinSocPct, 'battery_latestMinSocPct');
  bool(battery.latestReached99, 'battery_latestReached99');
  number(battery.endingCumulativeEfc, 'battery_endingCumulativeEfc');
  integer(battery.currentNoFullDays, 'battery_currentNoFullDays');
  integer(battery.daysSinceFull, 'battery_daysSinceFull');
  if (payload.schema !== 'earthship-energy-ui/v1') {
    const depthOfDischarge = number(
      battery.latestDepthOfDischargePct,
      'battery_latestDepthOfDischargePct',
    );
    const latestEfc = number(battery.latestEfc, 'battery_latestEfc');
    if (depthOfDischarge !== null && (depthOfDischarge < 0 || depthOfDischarge > 100)) {
      throw new Error('battery_latestDepthOfDischargePct_bounds');
    }
    if (latestEfc !== null && latestEfc < 0) throw new Error('battery_latestEfc_bounds');
  }

  const energy = exact(payload.energy, ENERGY, 'energy');
  status(energy.status, 'energy');
  if (energy.latest !== null) {
    const latest = exact(energy.latest, LATEST, 'energy_latest');
    date(latest.date, 'energy_latest_date');
    for (const field of ['chargeKwh', 'dischargeKwh', 'loadKwh', 'pvKwh']) {
      number(latest[field], `energy_latest_${field}`, qualified && field === 'loadKwh');
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
  for (const field of ['status', 'analytics', 'bms', 'collector', 'forecast', 'publisher',
    'schneider', 'weather']) status(health[field], `health_${field}`);
  if (!Array.isArray(health.reasons) || health.reasons.length > 16) throw new Error('health_reasons');
  health.reasons.forEach((reason, index) => boundedText(reason, `health_reason_${index}`, false));
  if (qualified) validateAccounting(payload, generatedAtMs);
  return generatedAtMs;
}

function validateAccounting(payload, generatedAtMs) {
  const a = exact(payload.accounting, ACCOUNTING, 'accounting');
  if (a.policy !== 'qualified_power_evidence_v1'
      || a.basis !== 'observed_qualified_throughput_in_requested_window'
      || a.loadStatus !== 'ac_load_evidence_unqualified') throw new Error('accounting_policy');
  const cutover = timestamp(a.cutover, 'accounting_cutover');
  date(a.windowStart, 'accounting_start');
  date(a.windowEndExclusive, 'accounting_end');
  const days = (Date.parse(a.windowEndExclusive) - Date.parse(a.windowStart)) / 86400000;
  if (cutover > generatedAtMs || days < 1 || days > 366
      || a.windowEndExclusive > localDate(generatedAtMs, payload.timezone)) {
    throw new Error('accounting_window');
  }
  integer(a.daysPresent, 'accounting_present', false);
  integer(a.missingDays, 'accounting_missing', false);
  if (a.daysPresent + a.missingDays !== days) throw new Error('accounting_days');
  for (const field of ['latestBatteryCoverage', 'latestPvCoverage']) {
    const value = number(a[field], field);
    if (value !== null && (value < 0 || value > 1)) throw new Error('accounting_coverage');
  }
  if (a.daysPresent === 0) {
    if (a.latestRevision !== null || payload.throughDate !== null || payload.energy.latest !== null
        || a.latestBatteryCoverage !== null || a.latestPvCoverage !== null
        || payload.battery.latestEfc !== null || payload.lifecycle.periodEfc !== null
        || payload.lifecycle.chargeKwh !== null || payload.lifecycle.dischargeKwh !== null) {
      throw new Error('accounting_empty');
    }
  } else {
    const revision = exact(a.latestRevision, ['computedAt', 'id', 'sha256'], 'accounting_revision');
    if (!Number.isSafeInteger(revision.id) || revision.id <= 0
        || typeof revision.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(revision.sha256)
        || timestamp(revision.computedAt, 'revision_time') > generatedAtMs
        || timestamp(revision.computedAt, 'revision_time') < cutover
        || payload.throughDate === null || payload.throughDate < a.windowStart
        || payload.throughDate < localDate(cutover, payload.timezone)
        || payload.throughDate >= a.windowEndExclusive
        || localDate(timestamp(revision.computedAt, 'revision_time'), payload.timezone) <= payload.throughDate
        || payload.energy.latest === null
        || a.latestBatteryCoverage === null || a.latestPvCoverage === null) {
      throw new Error('accounting_revision');
    }
  }
  if (payload.battery.endingCumulativeEfc !== null || payload.lifecycle.endingCumulativeEfc !== null
      || payload.energy.latest?.loadKwh != null || payload.winter.worstDeficitPeriod !== null) {
    throw new Error('accounting_unqualified_total');
  }
  for (const value of [payload.lifecycle.periodEfc, payload.lifecycle.chargeKwh,
    payload.lifecycle.dischargeKwh, payload.energy.latest?.pvKwh,
    payload.energy.latest?.chargeKwh, payload.energy.latest?.dischargeKwh]) {
    if (value != null && value < 0) throw new Error('accounting_negative');
  }
  if (a.missingDays > 0 && payload.status === 'ok') throw new Error('accounting_missing_status');
  if ((a.latestBatteryCoverage !== null && a.latestBatteryCoverage < 0.9 && payload.battery.status === 'ok')
      || (a.latestPvCoverage !== null && a.latestPvCoverage < 0.9 && payload.energy.status === 'ok')) {
    throw new Error('accounting_partial_status');
  }
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
    if (generatedAtMs > nowMs) {
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
      accounting: payload.accounting ? structuredClone(payload.accounting) : null,
      battery: {
        latestDepthOfDischargePct: null,
        latestEfc: null,
        ...structuredClone(payload.battery),
      },
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
