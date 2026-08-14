const HOUR_MS = 60 * 60 * 1000;
const FRESH_MS = 3 * HOUR_MS;
const UNAVAILABLE_MS = 26 * HOUR_MS;
const MAX_BYTES = 16 * 1024;

const TOP_LEVEL_FIELDS = new Set([
  'version', 'status', 'generatedAt', 'model', 'current', 'forecast',
  'schedule', 'confidence', 'provenance', 'reasons',
]);
const MODEL_FIELDS = new Set(['createdAt', 'trainedThrough', 'codeRevision']);
const CURRENT_FIELDS = new Set(['hallwayF', 'massF', 'glazingF']);
const FORECAST_FIELDS = new Set([
  'availableHours', 'hallwayHighF', 'hallwayHighAt', 'hallwayLowF',
  'hallwayLowAt', 'morningMassF', 'intervalLowF', 'intervalHighF',
  'trajectory', 'observed',
]);
const SCHEDULE_FIELDS = new Set(['baseline', 'candidate', 'effect']);
const SCHEDULE_TIME_FIELDS = new Set(['ventOpenAt', 'ventCloseAt']);
const EFFECT_FIELDS = new Set(['morningMassDeltaF', 'hallwayPeakDeltaF']);
const TRAJECTORY_FIELDS = new Set(['at', 'hallwayF', 'massF', 'lowF', 'highF', 'actions']);
const OBSERVED_FIELDS = new Set(['at', 'hallwayF', 'massF']);
const CONFIDENCE_FIELDS = new Set(['grade', 'actionLabels']);
const PROVENANCE_FIELDS = new Set([
  'sensorItems', 'actions', 'currentAgeMinutes', 'modelAgeHours',
  'trainingDataAgeHours',
]);
const SENSOR_ITEMS = Object.freeze({
  air: 'AmbientWeatherWS2902A_IndoorSensor_Temperature',
  mass: 'AmbientWeatherWS2902A_WH31E_193_Temperature',
  glazing: 'Shelly_HT1_Indoor_Temperature',
  outdoor: 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature',
  radiation: 'AmbientWeatherWS2902A_SolarRadiation',
});
const SENSOR_ROLES = new Set(Object.keys(SENSOR_ITEMS));
const ACTION_MARKERS = new Set([
  'vent_open', 'vent_close', 'indoor_shade_open', 'indoor_shade_close',
  'outdoor_shade_installed', 'outdoor_shade_removed',
]);
const ACTION_SOURCES = Object.freeze({
  unknown: 'unknown',
  model_inferred: 'model_inferred',
  reconstructed: 'historical_reconstruction',
  photosensor: 'photosensor',
  confirmed: 'operator_confirmed',
});
const ISO_WITH_ZONE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|([+-])(\d{2}):(\d{2}))$/;
const PYTHON_UNPRINTABLE = /[\p{C}\p{Z}]/u;
const LOCAL_HOUR = /^\d{4}-\d{2}-\d{2}T\d{2}:00:00(?:\.0+)?(?:Z|[+-]\d{2}:\d{2})$/;

function unavailableResult(reasons = []) {
  return {
    state: 'unavailable',
    badge: 'SHADOW',
    generatedAtMs: null,
    hallwayHigh: null,
    hallwayLow: null,
    morningMass: null,
    ventWindow: null,
    effect: { morningMassDeltaF: null, hallwayPeakDeltaF: null },
    confidence: 'unavailable',
    trajectory: [],
    observed: [],
    reasons,
  };
}

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function exactObject(value, fields) {
  if (!isObject(value)) throw new TypeError('expected object');
  const keys = Object.keys(value);
  if (keys.length !== fields.size || keys.some((key) => !fields.has(key))) {
    throw new TypeError('object has missing or unknown fields');
  }
  return value;
}

function finiteNumber(value, { optional = false, minimum = -Infinity } = {}) {
  if (optional && value === null) return null;
  if (typeof value !== 'number' || !Number.isFinite(value) || value < minimum) {
    throw new TypeError('expected finite number');
  }
  return value;
}

function timestampMs(value) {
  const match = typeof value === 'string' ? ISO_WITH_ZONE.exec(value) : null;
  if (!match) throw new TypeError('expected aware ISO-8601 timestamp');

  const [
    , yearText, monthText, dayText, hourText, minuteText, secondText,
    fraction = '', zone, offsetSign = '+', offsetHourText = '0', offsetMinuteText = '0',
  ] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  const offsetHour = Number(offsetHourText);
  const offsetMinute = Number(offsetMinuteText);
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (
    year < 1
    || month < 1 || month > 12
    || day < 1 || day > daysInMonth[month - 1]
    || hour > 23 || minute > 59 || second > 59
    || offsetHour > 23 || offsetMinute > 59
  ) {
    throw new TypeError('invalid timestamp');
  }

  const milliseconds = Number(fraction.padEnd(3, '0').slice(0, 3));
  const local = new Date(0);
  local.setUTCFullYear(year, month - 1, day);
  local.setUTCHours(hour, minute, second, milliseconds);
  const offsetMinutes = zone === 'Z'
    ? 0
    : (offsetSign === '+' ? 1 : -1) * (offsetHour * 60 + offsetMinute);
  const parsed = local.getTime() - offsetMinutes * 60_000;
  if (!Number.isFinite(parsed)) throw new TypeError('invalid timestamp');
  return parsed;
}

function optionalTimestampMs(value) {
  return value === null ? null : timestampMs(value);
}

function sameExactObject(left, right) {
  if (!isObject(left) || !isObject(right)) return Object.is(left, right);
  const leftKeys = Object.keys(left).sort();
  const rightKeys = Object.keys(right).sort();
  return leftKeys.length === rightKeys.length
    && leftKeys.every((key, index) => (
      key === rightKeys[index] && sameExactObject(left[key], right[key])
    ));
}

function validateScheduleWindow(value, horizonStart, horizonEnd) {
  exactObject(value, SCHEDULE_TIME_FIELDS);
  const opened = optionalTimestampMs(value.ventOpenAt);
  const closed = optionalTimestampMs(value.ventCloseAt);
  if ((opened === null) !== (closed === null)) throw new TypeError('incomplete vent window');
  if (opened !== null && !(horizonStart <= opened && opened < closed && closed <= horizonEnd)) {
    throw new TypeError('vent window outside horizon');
  }
  return { opened, closed };
}

function validateRows(rows, fields, limit, { localHour = false } = {}) {
  if (!Array.isArray(rows) || rows.length > limit) throw new TypeError('invalid row list');
  let prior = null;
  return rows.map((row) => {
    exactObject(row, fields);
    if (localHour && !LOCAL_HOUR.test(row.at)) throw new TypeError('forecast row is not hourly');
    const atMs = timestampMs(row.at);
    if (prior !== null && atMs <= prior) throw new TypeError('rows are not ordered');
    prior = atMs;
    return { row, atMs };
  });
}

function formatLocalTime(atMs) {
  return new Date(atMs).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function validateReasons(value) {
  if (!Array.isArray(value) || value.length < 1 || value.length > 8) {
    throw new TypeError('invalid reasons');
  }
  const encoder = new TextEncoder();
  for (const reason of value) {
    if (
      typeof reason !== 'string'
      || reason.length === 0
      || encoder.encode(reason).length > 256
      || reason !== [...reason]
        .map((character) => character === ' ' || !PYTHON_UNPRINTABLE.test(character) ? character : ' ')
        .join('')
        .split(' ')
        .filter(Boolean)
        .join(' ')
    ) {
      throw new TypeError('invalid reason');
    }
  }
  return [...value];
}

function validatePayload(payload) {
  exactObject(payload, TOP_LEVEL_FIELDS);
  if (payload.version !== 1 || !Number.isInteger(payload.version) || payload.status !== 'shadow') {
    throw new TypeError('unsupported thermal result');
  }
  const generatedAtMs = timestampMs(payload.generatedAt);

  const model = payload.model;
  if (Object.keys(exactObject(model, new Set(Object.keys(model)))).length > 0) {
    exactObject(model, MODEL_FIELDS);
    const createdAt = timestampMs(model.createdAt);
    const trainedThrough = timestampMs(model.trainedThrough);
    if (!(trainedThrough <= createdAt && createdAt <= generatedAtMs)) {
      throw new TypeError('invalid model chronology');
    }
    if (typeof model.codeRevision !== 'string' || !/^[0-9a-f]{7,64}$/.test(model.codeRevision)) {
      throw new TypeError('invalid model revision');
    }
  }

  const current = exactObject(payload.current, CURRENT_FIELDS);
  for (const field of CURRENT_FIELDS) finiteNumber(current[field], { optional: true });

  const forecast = exactObject(payload.forecast, FORECAST_FIELDS);
  if (!Number.isInteger(forecast.availableHours) || forecast.availableHours < 0 || forecast.availableHours > 72) {
    throw new TypeError('invalid forecast horizon');
  }
  const horizonStart = Math.floor(generatedAtMs / (5 * 60_000)) * 5 * 60_000;
  const horizonEnd = horizonStart + forecast.availableHours * HOUR_MS;
  const summaryNumbers = [
    'hallwayHighF', 'hallwayLowF', 'morningMassF', 'intervalLowF', 'intervalHighF',
  ];
  for (const field of summaryNumbers) finiteNumber(forecast[field], { optional: true });
  const hallwayHighAt = optionalTimestampMs(forecast.hallwayHighAt);
  const hallwayLowAt = optionalTimestampMs(forecast.hallwayLowAt);
  if ((forecast.intervalLowF === null) !== (forecast.intervalHighF === null)) {
    throw new TypeError('incomplete interval');
  }
  if (forecast.intervalLowF !== null && forecast.intervalLowF > forecast.intervalHighF) {
    throw new TypeError('reversed interval');
  }

  const trajectoryRows = validateRows(forecast.trajectory, TRAJECTORY_FIELDS, 73, { localHour: true });
  const trajectory = trajectoryRows.map(({ row, atMs }) => {
    const hallwayF = finiteNumber(row.hallwayF);
    const massF = finiteNumber(row.massF);
    const lowF = finiteNumber(row.lowF);
    const highF = finiteNumber(row.highF);
    if (!(lowF <= hallwayF && hallwayF <= highF)) throw new TypeError('invalid row interval');
    if (!(horizonStart <= atMs && atMs <= horizonEnd)) throw new TypeError('row outside horizon');
    if (
      !Array.isArray(row.actions)
      || row.actions.some((action) => typeof action !== 'string' || !ACTION_MARKERS.has(action))
      || new Set(row.actions).size !== row.actions.length
    ) {
      throw new TypeError('invalid action markers');
    }
    return { atMs, hallwayF, massF, lowF, highF, actions: [...row.actions] };
  });

  const observed = validateRows(forecast.observed, OBSERVED_FIELDS, 25).map(({ row, atMs }) => {
    if (atMs > generatedAtMs) throw new TypeError('future observation');
    return { atMs, hallwayF: finiteNumber(row.hallwayF), massF: finiteNumber(row.massF) };
  });

  let candidateWindow = null;
  let effect = { morningMassDeltaF: null, hallwayPeakDeltaF: null };
  const schedule = payload.schedule;
  if (Object.keys(exactObject(schedule, new Set(Object.keys(schedule)))).length > 0) {
    exactObject(schedule, SCHEDULE_FIELDS);
    const baselineWindow = validateScheduleWindow(schedule.baseline, horizonStart, horizonEnd);
    if (schedule.candidate !== null) {
      candidateWindow = validateScheduleWindow(schedule.candidate, horizonStart, horizonEnd);
    }
    exactObject(schedule.effect, EFFECT_FIELDS);
    effect = {
      morningMassDeltaF: finiteNumber(schedule.effect.morningMassDeltaF),
      hallwayPeakDeltaF: finiteNumber(schedule.effect.hallwayPeakDeltaF),
    };
    if (candidateWindow === null && Object.values(effect).some((value) => value !== 0)) {
      throw new TypeError('effect without candidate');
    }
    if (candidateWindow !== null && sameExactObject(schedule.candidate, schedule.baseline)) {
      throw new TypeError('candidate duplicates baseline');
    }
    void baselineWindow;
  }

  const confidence = exactObject(payload.confidence, CONFIDENCE_FIELDS);
  if (!['low', 'unavailable'].includes(confidence.grade) || !(confidence.actionLabels in ACTION_SOURCES)) {
    throw new TypeError('invalid confidence');
  }
  const unavailable = confidence.grade === 'unavailable';

  const provenance = exactObject(payload.provenance, PROVENANCE_FIELDS);
  if (!sameExactObject(provenance.sensorItems, SENSOR_ITEMS)) throw new TypeError('invalid sensor provenance');
  if (provenance.actions !== ACTION_SOURCES[confidence.actionLabels]) throw new TypeError('invalid action provenance');
  const ages = exactObject(provenance.currentAgeMinutes, SENSOR_ROLES);
  for (const [role, age] of Object.entries(ages)) {
    const parsed = finiteNumber(age, { optional: true, minimum: 0 });
    if (!unavailable && ['air', 'mass', 'outdoor', 'radiation'].includes(role) && (parsed === null || parsed > 20)) {
      throw new TypeError('stale critical input');
    }
  }
  finiteNumber(provenance.modelAgeHours, { optional: true, minimum: 0 });
  finiteNumber(provenance.trainingDataAgeHours, { optional: true, minimum: 0 });
  const reasons = validateReasons(payload.reasons);

  if (unavailable) {
    if (
      confidence.actionLabels !== 'unknown'
      || Object.keys(schedule).length !== 0
      || forecast.availableHours !== 0
      || trajectory.length !== 0
      || summaryNumbers.some((field) => forecast[field] !== null)
    ) {
      throw new TypeError('invalid unavailable output');
    }
  } else {
    if (
      Object.keys(model).length === 0
      || forecast.availableHours < 24
      || Object.keys(schedule).length === 0
      || trajectory.length === 0
      || current.hallwayF === null
      || current.massF === null
      || summaryNumbers.some((field) => forecast[field] === null)
      || hallwayHighAt === null
      || hallwayLowAt === null
    ) {
      throw new TypeError('partial available output');
    }
    if (!(forecast.hallwayLowF <= forecast.hallwayHighF)) throw new TypeError('reversed extrema');
    const hallwayPoints = trajectory.map((row) => row.hallwayF);
    if (forecast.hallwayLowF > Math.min(...hallwayPoints) || forecast.hallwayHighF < Math.max(...hallwayPoints)) {
      throw new TypeError('extrema do not contain trajectory');
    }
    if (!(
      forecast.intervalLowF <= forecast.hallwayLowF
      && forecast.hallwayHighF <= forecast.intervalHighF
    )) throw new TypeError('extrema outside interval');
    if (
      hallwayHighAt < horizonStart || hallwayHighAt > horizonEnd
      || hallwayLowAt < horizonStart || hallwayLowAt > horizonEnd
    ) throw new TypeError('extrema times outside horizon');
  }

  return {
    generatedAtMs,
    forecast,
    trajectory,
    observed,
    candidateWindow,
    effect,
    confidence: confidence.grade,
    reasons,
  };
}

export function parseThermalModelResult(raw, nowMs = Date.now()) {
  if (typeof raw !== 'string' || !Number.isFinite(nowMs)) return unavailableResult();
  if (new TextEncoder().encode(raw).length >= MAX_BYTES) return unavailableResult();
  const trimmed = raw.trim();
  if (!trimmed || ['NULL', 'UNDEF'].includes(trimmed)) return unavailableResult();

  try {
    const parsed = validatePayload(JSON.parse(trimmed));
    const ageMs = nowMs - parsed.generatedAtMs;
    if (ageMs < 0) return unavailableResult();
    if (parsed.confidence === 'unavailable') return unavailableResult(parsed.reasons);
    if (ageMs > UNAVAILABLE_MS) return unavailableResult();

    return {
      state: ageMs > FRESH_MS ? 'stale' : 'ready',
      badge: 'SHADOW',
      generatedAtMs: parsed.generatedAtMs,
      hallwayHigh: parsed.forecast.hallwayHighF,
      hallwayLow: parsed.forecast.hallwayLowF,
      morningMass: parsed.forecast.morningMassF,
      ventWindow: parsed.candidateWindow === null
        ? null
        : `${formatLocalTime(parsed.candidateWindow.opened)}–${formatLocalTime(parsed.candidateWindow.closed)}`,
      effect: parsed.effect,
      confidence: parsed.confidence,
      trajectory: parsed.trajectory,
      observed: parsed.observed,
      reasons: parsed.reasons,
    };
  } catch {
    return unavailableResult();
  }
}
