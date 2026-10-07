const HOUR_MS = 60 * 60 * 1000;
const FRESH_MS = 3 * HOUR_MS;
const UNAVAILABLE_MS = 26 * HOUR_MS;
const MAX_BYTES = 16 * 1024;
const MICROSECONDS_PER_MILLISECOND = 1000n;
const MICROSECONDS_PER_SECOND = 1_000_000n;
const FRESH_US = BigInt(FRESH_MS) * MICROSECONDS_PER_MILLISECOND;
const UNAVAILABLE_US = BigInt(UNAVAILABLE_MS) * MICROSECONDS_PER_MILLISECOND;

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
    modelCreatedAtMs: null,
    trainedThroughMs: null,
    modelAgeHours: null,
    trainingDataAgeHours: null,
    hallwayHigh: null,
    hallwayLow: null,
    morningMass: null,
    baselineVentAssumption: null,
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

function timestamp(value) {
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

  const fractionMicros = BigInt(fraction.padEnd(6, '0').slice(0, 6));
  const local = new Date(0);
  local.setUTCFullYear(year, month - 1, day);
  local.setUTCHours(hour, minute, second, 0);
  const offsetMinutes = zone === 'Z'
    ? 0
    : (offsetSign === '+' ? 1 : -1) * (offsetHour * 60 + offsetMinute);
  const wholeSecondMs = local.getTime() - offsetMinutes * 60_000;
  const epochMicros = BigInt(wholeSecondMs) * MICROSECONDS_PER_MILLISECOND + fractionMicros;
  const epochMs = wholeSecondMs + Number(fractionMicros / MICROSECONDS_PER_MILLISECOND);
  if (!Number.isFinite(epochMs)) throw new TypeError('invalid timestamp');

  const sinceLocalFiveMinute = BigInt((minute % 5) * 60 + second) * MICROSECONDS_PER_SECOND
    + fractionMicros;
  return {
    epochMicros,
    epochMs,
    fiveMinuteStartMicros: epochMicros - sinceLocalFiveMinute,
  };
}

function optionalTimestamp(value) {
  return value === null ? null : timestamp(value);
}

function millisecondsToMicros(value) {
  return BigInt(Math.trunc(value)) * MICROSECONDS_PER_MILLISECOND;
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
  const opened = optionalTimestamp(value.ventOpenAt);
  const closed = optionalTimestamp(value.ventCloseAt);
  if ((opened === null) !== (closed === null)) throw new TypeError('incomplete vent window');
  if (opened !== null && !(
    horizonStart <= opened.epochMicros
    && opened.epochMicros < closed.epochMicros
    && closed.epochMicros <= horizonEnd
  )) {
    throw new TypeError('vent window outside horizon');
  }
  return {
    opened: opened?.epochMs ?? null,
    closed: closed?.epochMs ?? null,
  };
}

function validateRows(rows, fields, limit, { localHour = false } = {}) {
  if (!Array.isArray(rows) || rows.length > limit) throw new TypeError('invalid row list');
  let prior = null;
  return rows.map((row) => {
    exactObject(row, fields);
    if (localHour && !LOCAL_HOUR.test(row.at)) throw new TypeError('forecast row is not hourly');
    const at = timestamp(row.at);
    if (prior !== null && at.epochMicros <= prior) throw new TypeError('rows are not ordered');
    prior = at.epochMicros;
    return { row, atMs: at.epochMs, atMicros: at.epochMicros };
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

const RELEASE_FIELDS = new Set([
  'schema', 'qualifiedAt', 'expiresAt', 'artifactSha256', 'runtimeSha256',
  'policySha256', 'reportSha256', 'sensorEpochs', 'forecastQualified', 'advisoryQualified', 'automaticActuation',
]);

function validateReleasePayload(payload) {
  exactObject(payload, new Set([...TOP_LEVEL_FIELDS, 'release']));
  const release = exactObject(payload.release, RELEASE_FIELDS);
  if (release.schema !== 'earthship-thermal-release/v1'
    || !['shadow', 'forecast_active', 'advisory_active', 'unavailable'].includes(payload.status)) {
    throw new TypeError('unsupported release publication');
  }
  for (const key of ['forecastQualified', 'advisoryQualified', 'automaticActuation']) {
    if (typeof release[key] !== 'boolean') throw new TypeError('invalid release flags');
  }
  if (release.automaticActuation) throw new TypeError('automatic actuation prohibited');
  const active = ['forecast_active', 'advisory_active'].includes(payload.status);
  const available = payload.confidence.grade !== 'unavailable';
  for (const key of ['artifactSha256', 'runtimeSha256', 'policySha256', 'reportSha256']) {
    if (release[key] !== null && (typeof release[key] !== 'string' || !/^[0-9a-f]{64}$/.test(release[key]))) {
      throw new TypeError('invalid release revision');
    }
    if (active && release[key] === null) throw new TypeError('active release lacks evidence identity');
  }
  let qualifiedAt = null;
  let expiresAt = null;
  if (active) {
    if (!available || !release.forecastQualified || payload.confidence.grade !== 'high') {
      throw new TypeError('active release lacks forecast qualification');
    }
    exactObject(release.sensorEpochs, new Set(['air', 'mass', 'outdoor']));
    for (const value of Object.values(release.sensorEpochs)) {
      if (typeof value !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value)) {
        throw new TypeError('invalid release hardware epoch');
      }
    }
    qualifiedAt = timestamp(release.qualifiedAt);
    expiresAt = timestamp(release.expiresAt);
    const issue = timestamp(payload.generatedAt);
    if (!(issue.epochMicros < expiresAt.epochMicros && qualifiedAt.epochMicros < expiresAt.epochMicros)
      || qualifiedAt.epochMicros > issue.epochMicros + 20n * 60_000_000n
      || expiresAt.epochMicros - qualifiedAt.epochMicros > 24n * BigInt(HOUR_MS) * MICROSECONDS_PER_MILLISECOND) {
      throw new TypeError('release evidence expired or future');
    }
  } else if (release.forecastQualified || release.advisoryQualified
    || (payload.status === 'unavailable' ? available : !available || payload.confidence.grade !== 'low')) {
    throw new TypeError('inactive release claims qualification');
  }
  if (payload.status === 'forecast_active' && release.advisoryQualified) throw new TypeError('forecast-only mode claims advice');
  if (payload.status === 'advisory_active' && (!release.advisoryQualified || payload.confidence.actionLabels !== 'confirmed')) {
    throw new TypeError('action advice lacks confirmed qualification');
  }
  if (!release.advisoryQualified) {
    if (Object.keys(payload.schedule).length && (payload.schedule.candidate !== null
      || Object.values(payload.schedule.effect).some((value) => value !== 0))) {
      throw new TypeError('unqualified recommendation');
    }
    if (payload.forecast.trajectory.some((point) => point.actions.length)) throw new TypeError('unqualified action markers');
  }
  const base = structuredClone(payload);
  delete base.release;
  base.version = 1;
  base.status = 'shadow';
  if (base.confidence.grade === 'high') base.confidence.grade = 'low';
  const parsed = validatePayload(base);
  return { ...parsed, confidence: payload.confidence.grade, mode: payload.status,
    release, qualifiedAtMs: qualifiedAt?.epochMs ?? null, expiresAtMs: expiresAt?.epochMs ?? null,
    artifactRevision: release.artifactSha256,
    actionConfidence: release.advisoryQualified ? 'confirmed' : 'withheld' };
}

function validatePayload(payload) {
  if (payload?.version === 2) return validateReleasePayload(payload);
  exactObject(payload, TOP_LEVEL_FIELDS);
  if (payload.version !== 1 || !Number.isInteger(payload.version) || payload.status !== 'shadow') {
    throw new TypeError('unsupported thermal result');
  }
  const generatedAt = timestamp(payload.generatedAt);

  const model = payload.model;
  let modelCreatedAt = null;
  let trainedThrough = null;
  if (Object.keys(exactObject(model, new Set(Object.keys(model)))).length > 0) {
    exactObject(model, MODEL_FIELDS);
    modelCreatedAt = timestamp(model.createdAt);
    trainedThrough = timestamp(model.trainedThrough);
    if (!(
      trainedThrough.epochMicros <= modelCreatedAt.epochMicros
      && modelCreatedAt.epochMicros <= generatedAt.epochMicros
    )) {
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
  const horizonStart = generatedAt.fiveMinuteStartMicros;
  const horizonEnd = horizonStart
    + BigInt(forecast.availableHours * HOUR_MS) * MICROSECONDS_PER_MILLISECOND;
  const summaryNumbers = [
    'hallwayHighF', 'hallwayLowF', 'morningMassF', 'intervalLowF', 'intervalHighF',
  ];
  for (const field of summaryNumbers) finiteNumber(forecast[field], { optional: true });
  const hallwayHighAt = optionalTimestamp(forecast.hallwayHighAt);
  const hallwayLowAt = optionalTimestamp(forecast.hallwayLowAt);
  if ((forecast.intervalLowF === null) !== (forecast.intervalHighF === null)) {
    throw new TypeError('incomplete interval');
  }
  if (forecast.intervalLowF !== null && forecast.intervalLowF > forecast.intervalHighF) {
    throw new TypeError('reversed interval');
  }

  const trajectoryRows = validateRows(forecast.trajectory, TRAJECTORY_FIELDS, 73, { localHour: true });
  const trajectory = trajectoryRows.map(({ row, atMs, atMicros }) => {
    const hallwayF = finiteNumber(row.hallwayF);
    const massF = finiteNumber(row.massF);
    const lowF = finiteNumber(row.lowF);
    const highF = finiteNumber(row.highF);
    if (!(lowF <= hallwayF && hallwayF <= highF)) throw new TypeError('invalid row interval');
    if (!(horizonStart <= atMicros && atMicros <= horizonEnd)) throw new TypeError('row outside horizon');
    if (
      !Array.isArray(row.actions)
      || row.actions.some((action) => typeof action !== 'string' || !ACTION_MARKERS.has(action))
      || new Set(row.actions).size !== row.actions.length
    ) {
      throw new TypeError('invalid action markers');
    }
    return { atMs, hallwayF, massF, lowF, highF, actions: [...row.actions] };
  });

  const observed = validateRows(forecast.observed, OBSERVED_FIELDS, 25).map(({ row, atMs, atMicros }) => {
    if (atMicros > generatedAt.epochMicros) throw new TypeError('future observation');
    return { atMs, hallwayF: finiteNumber(row.hallwayF), massF: finiteNumber(row.massF) };
  });

  let baselineWindow = null;
  let candidateWindow = null;
  let effect = { morningMassDeltaF: null, hallwayPeakDeltaF: null };
  const schedule = payload.schedule;
  if (Object.keys(exactObject(schedule, new Set(Object.keys(schedule)))).length > 0) {
    exactObject(schedule, SCHEDULE_FIELDS);
    baselineWindow = validateScheduleWindow(schedule.baseline, horizonStart, horizonEnd);
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
  const modelAgeHours = finiteNumber(
    provenance.modelAgeHours, { optional: true, minimum: 0 },
  );
  const trainingDataAgeHours = finiteNumber(
    provenance.trainingDataAgeHours, { optional: true, minimum: 0 },
  );
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
      hallwayHighAt.epochMicros < horizonStart || hallwayHighAt.epochMicros > horizonEnd
      || hallwayLowAt.epochMicros < horizonStart || hallwayLowAt.epochMicros > horizonEnd
    ) throw new TypeError('extrema times outside horizon');
  }

  return {
    generatedAtMs: generatedAt.epochMs,
    generatedAtMicros: generatedAt.epochMicros,
    modelCreatedAtMs: modelCreatedAt?.epochMs ?? null,
    trainedThroughMs: trainedThrough?.epochMs ?? null,
    modelAgeHours,
    trainingDataAgeHours,
    forecast,
    trajectory,
    observed,
    baselineWindow,
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
    const parsed = validatePayload(JSON.parse(raw));
    const ageMicros = millisecondsToMicros(nowMs) - parsed.generatedAtMicros;
    if (ageMicros < 0n) return unavailableResult();
    if (parsed.confidence === 'unavailable') {
      const unavailable = unavailableResult(parsed.reasons);
      return parsed.mode ? { ...unavailable, mode: 'unavailable', badge: 'UNAVAILABLE' } : unavailable;
    }
    if (parsed.mode && (parsed.qualifiedAtMs > nowMs || parsed.expiresAtMs !== null && nowMs >= parsed.expiresAtMs)) return unavailableResult();
    if (ageMicros > UNAVAILABLE_US) return unavailableResult();

    return {
      state: ageMicros > FRESH_US ? 'stale' : 'ready',
      badge: parsed.mode === 'forecast_active' ? 'FORECAST' : parsed.mode === 'advisory_active' ? 'ADVISORY' : 'SHADOW',
      ...(parsed.mode ? { mode: parsed.mode, artifactRevision: parsed.artifactRevision, actionConfidence: parsed.actionConfidence } : {}),
      generatedAtMs: parsed.generatedAtMs,
      modelCreatedAtMs: parsed.modelCreatedAtMs,
      trainedThroughMs: parsed.trainedThroughMs,
      modelAgeHours: parsed.modelAgeHours,
      trainingDataAgeHours: parsed.trainingDataAgeHours,
      hallwayHigh: parsed.forecast.hallwayHighF,
      hallwayLow: parsed.forecast.hallwayLowF,
      morningMass: parsed.forecast.morningMassF,
      baselineVentAssumption: parsed.baselineWindow.opened === null
        ? 'No venting assumed'
        : `${formatLocalTime(parsed.baselineWindow.opened)}–${formatLocalTime(parsed.baselineWindow.closed)}`,
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
