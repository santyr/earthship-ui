import { forecastDisplayDay } from './forecastRange.js';
import { HOUSEHOLD_TIMEZONE } from '../site.js';
export const FORECAST_DETAIL_ITEM = 'Forecast_10Day_JSON';
export const FORECAST_DETAIL_MAX_BYTES = 64 * 1024;
export const FORECAST_DETAIL_STALE_MS = 4 * 60 * 60 * 1_000;
export const FORECAST_DETAIL_HOURS = 12;

const FUTURE_DAY_START_HOUR = 7;
const FUTURE_DAY_END_HOUR = 18;

const SENTINELS = new Set(['', 'NULL', 'UNDEF']);
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const OFFSET_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

function unavailable(reason, legacyFallbackAllowed = true) {
  return Object.freeze({
    status: 'unavailable',
    reason,
    legacyFallbackAllowed,
    generatedAtMs: null,
    timezone: HOUSEHOLD_TIMEZONE,
    days: Object.freeze([]),
  });
}

function nullableNumber(value, field) {
  if (value === null) return null;
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new TypeError(`${field} must be a finite number or null`);
  }
  return value;
}

function finiteNumber(value, field) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new TypeError(`${field} must be a finite number`);
  }
  return value;
}

function normalizeTemperatureAdjustment(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new TypeError('temperature adjustment is required for version 2');
  }
  const highCorrectionF = finiteNumber(raw.highCorrectionF, 'high correction');
  const lowCorrectionF = finiteNumber(raw.lowCorrectionF, 'low correction');
  if (!['daily-fallback', 'hourly-blend'].includes(raw.hourlyMethod)) {
    throw new TypeError('temperature adjustment method is invalid');
  }
  if (!Array.isArray(raw.hourBuckets) || raw.hourBuckets.length !== 24) {
    throw new TypeError('temperature adjustment requires 24 hour buckets');
  }
  const hourBuckets = raw.hourBuckets.map((bucket, hour) => {
    if (!bucket || typeof bucket !== 'object' || Array.isArray(bucket) || bucket.hour !== hour) {
      throw new TypeError('temperature adjustment buckets must be ordered by hour');
    }
    const count = finiteNumber(bucket.count, 'hour bucket count');
    const weight = finiteNumber(bucket.weight, 'hour bucket weight');
    if (!Number.isInteger(count) || count < 0) {
      throw new TypeError('hour bucket count must be a non-negative integer');
    }
    if (weight < 0 || weight > 1) {
      throw new TypeError('hour bucket weight must be between zero and one');
    }
    return Object.freeze({ hour, count, weight });
  });
  return Object.freeze({
    highCorrectionF,
    lowCorrectionF,
    hourlyMethod: raw.hourlyMethod,
    hourBuckets: Object.freeze(hourBuckets),
  });
}

function normalizeHour(raw, date, production = false) {
  if (!raw || typeof raw !== 'object' || !OFFSET_TIMESTAMP.test(raw.at ?? '')) {
    throw new TypeError('hour timestamp must include an offset');
  }
  const atMs = Date.parse(raw.at);
  if (!Number.isFinite(atMs) || raw.at.slice(0, 10) !== date) {
    throw new TypeError('hour timestamp must belong to its day');
  }
  return Object.freeze({
    at: raw.at,
    atMs,
    ...(raw.forecastProfile ? { forecastProfile: raw.forecastProfile } : {}),
    isDay: typeof raw.isDay === 'boolean' ? raw.isDay : null,
    tempF: nullableNumber(raw.tempF, 'tempF'),
    precipPct: nullableNumber(production ? raw.precipPct ?? null : raw.precipPct, 'precipPct'),
    precipIn: nullableNumber(raw.precipIn ?? null, 'precipIn'),
    radiationWm2: nullableNumber(raw.radiationWm2, 'radiationWm2'),
    windMph: nullableNumber(production ? raw.windMeanMph ?? raw.windMph : raw.windMph, 'windMph'),
    ...(production ? {
      nativeWindMph: nullableNumber(raw.windMph, 'nativeWindMph'),
      windStatistic: raw.windMeanMph == null ? 'native_instantaneous' : 'local_hour_mean',
    } : {}),
    weatherCode: nullableNumber(production ? raw.weatherCode ?? null : raw.weatherCode, 'weatherCode'),
    cloudPct: nullableNumber(raw.cloudPct ?? null, 'cloudPct'),
  });
}

function normalizeDay(raw, production = false) {
  if (!raw || typeof raw !== 'object' || !DATE.test(raw.date ?? '')) {
    throw new TypeError('day date must be ISO');
  }
  if (!Array.isArray(raw.hours)) throw new TypeError('day hours are required');
  const summary = raw.summary ?? {};
  if (production && (!['remaining', 'full_day'].includes(summary.temperatureScope)
      || summary.temperatureStatistic !== 'extrema_of_hourly_point_forecasts')) {
    throw new TypeError('production temperature summary scope is invalid');
  }
  const hours = raw.hours.map((value) => normalizeHour(value, raw.date, production));
  for (let index = 1; index < hours.length; index += 1) {
    if (hours[index - 1].atMs >= hours[index].atMs) {
      throw new TypeError('hours must be strictly ascending');
    }
  }
  return Object.freeze({
    date: raw.date,
    label: typeof raw.label === 'string' && raw.label.trim() ? raw.label.trim() : raw.date,
    summary: Object.freeze({
      highF: nullableNumber(summary.highF, 'highF'),
      lowF: nullableNumber(summary.lowF, 'lowF'),
      precipPct: nullableNumber(summary.precipPct, 'summary.precipPct'),
      precipSumIn: nullableNumber(summary.precipSumIn ?? null, 'summary.precipSumIn'),
      weatherCode: nullableNumber(summary.weatherCode, 'summary.weatherCode'),
      pvKwh: nullableNumber(summary.pvKwh, 'pvKwh'),
      cloudPct: nullableNumber(summary.cloudPct ?? null, 'summary.cloudPct'),
      ...(production ? { temperatureScope: summary.temperatureScope, temperatureStatistic: summary.temperatureStatistic } : {}),
      ...(summary.forecastProfile ? { forecastProfile: summary.forecastProfile } : {}),
      ...(summary.precipitationScope === 'remaining' ? {
        precipitationScope: 'remaining',
        precipitationFromAt: summary.precipitationFromAt,
        precipitationThroughAt: summary.precipitationThroughAt,
        precipitationForecastProfile: summary.precipitationForecastProfile,
      } : {}),
    }),
    hours: Object.freeze(hours),
  });
}

export function parseForecast10Day(raw, { nowMs = Date.now() } = {}) {
  if (typeof raw !== 'string' || SENTINELS.has(raw.trim())) {
    return unavailable('forecast detail missing');
  }
  if (new TextEncoder().encode(raw).length > FORECAST_DETAIL_MAX_BYTES) {
    return unavailable('forecast detail exceeds size limit');
  }
  let legacyFallbackAllowed = true;
  try {
    const parsed = JSON.parse(raw);
    legacyFallbackAllowed = parsed?.provider !== 'weathernext3';
    if (![1, 2, 3].includes(parsed?.version)) {
      throw new TypeError('unsupported forecast detail version');
    }
    const temperatureAdjustment = parsed.version === 2
      ? normalizeTemperatureAdjustment(parsed.temperatureAdjustment)
      : null;
    let productionModel = null;
    if (parsed.version === 3) {
      const model = parsed.productionModel;
      if (parsed.provider !== 'weathernext3' || !/^[a-f0-9]{64}$/.test(model?.issueSha256 ?? '')
          || !['ACTIVE', 'MIXED_WITH_RAW_FALLBACK', 'RAW_FALLBACK'].includes(model?.status)
          || model.localCoverageQualified !== false || model.probabilityClaim !== false
          || model.temperatureStatistic !== 'model_point_with_declared_raw_fallback'
          || model.windStatistic !== 'native_instantaneous_with_separate_local_hour_mean') {
        throw new TypeError('production model identity or target semantics are invalid');
      }
      productionModel = Object.freeze({ ...model });
    }
    if (parsed.timezone !== HOUSEHOLD_TIMEZONE) throw new TypeError('unexpected forecast timezone');
    if (!OFFSET_TIMESTAMP.test(parsed.generatedAt ?? '')) {
      throw new TypeError('generatedAt must include an offset');
    }
    const generatedAtMs = Date.parse(parsed.generatedAt);
    if (!Number.isFinite(generatedAtMs)) throw new TypeError('generatedAt is invalid');
    if (generatedAtMs > nowMs) throw new TypeError('forecast generatedAt is in the future');
    if (!Array.isArray(parsed.days) || parsed.days.length > 10) {
      throw new TypeError('forecast days must contain at most ten entries');
    }
    if (parsed.provider === 'weathernext3' && parsed.providerStatus === 'UNAVAILABLE') {
      if (parsed.days.length || parsed.source !== null || parsed.issueSha256 !== null) {
        throw new TypeError('unavailable WeatherNext forecast carries predictions');
      }
      return unavailable('WeatherNext forecast unavailable', false);
    }
    if (!parsed.days.length) return unavailable('forecast days missing', legacyFallbackAllowed);
    const days = parsed.days.map(day => normalizeDay(day, parsed.version === 3));
    const seen = new Set();
    for (let index = 0; index < days.length; index += 1) {
      if (seen.has(days[index].date)) throw new TypeError('duplicate forecast day');
      seen.add(days[index].date);
      if (index > 0 && days[index - 1].date >= days[index].date) {
        throw new TypeError('forecast days must be strictly ascending');
      }
    }
    return Object.freeze({
      status: nowMs - generatedAtMs > FORECAST_DETAIL_STALE_MS ? 'stale' : 'ready',
      reason: '',
      legacyFallbackAllowed,
      generatedAtMs,
      timezone: parsed.timezone,
      provider: parsed.provider === 'weathernext3' ? 'weathernext3' : null,
      temperatureAdjustment,
      ...(productionModel ? { productionModel } : {}),
      ...(parsed.profiles ? { profiles: Object.freeze(parsed.profiles) } : {}),
      days: Object.freeze(days),
    });
  } catch (error) {
    return unavailable(error?.message || 'forecast detail invalid', legacyFallbackAllowed);
  }
}

export function parseLegacyDailyForecast(raw) {
  if (typeof raw !== 'string' || SENTINELS.has(raw.trim())) return [];
  try {
    const rows = JSON.parse(raw);
    if (!Array.isArray(rows)) return [];
    const legacyNumber = (value) => {
      if (value === null || value === undefined || SENTINELS.has(String(value).trim())) return null;
      const number = Number(value);
      return Number.isFinite(number) ? number : null;
    };
    return rows.slice(0, 7).map((row, index) => Object.freeze({
      date: null,
      label: index === 1
        ? 'Tomorrow'
        : String(row?.d ?? (index === 0 ? 'Today' : `D${index + 1}`)),
      summary: Object.freeze({
        highF: legacyNumber(row?.hi),
        lowF: legacyNumber(row?.lo),
        precipPct: legacyNumber(row?.p),
        precipSumIn: legacyNumber(row?.a),
        weatherCode: legacyNumber(row?.w),
        pvKwh: legacyNumber(row?.pv),
      }),
      hours: Object.freeze([]),
    }));
  } catch {
    return [];
  }
}

export function localDateAt(nowMs, timezone) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(nowMs);
  const value = Object.fromEntries(parts.map(({ type, value: part }) => [type, part]));
  return `${value.year}-${value.month}-${value.day}`;
}

export function todayPvForecastKwh(result, { nowMs = Date.now() } = {}) {
  if (result?.status !== 'ready' || !Number.isFinite(result.generatedAtMs)
      || nowMs - result.generatedAtMs > FORECAST_DETAIL_STALE_MS) return null;
  const today = localDateAt(nowMs, result.timezone);
  return result.days.find(({ date }) => date === today)?.summary.pvKwh ?? null;
}

export function pvForecastDaysFromToday(result, { nowMs = Date.now() } = {}) {
  if (result?.status !== 'ready' || !Number.isFinite(result.generatedAtMs)
      || nowMs - result.generatedAtMs > FORECAST_DETAIL_STALE_MS) return [];
  const today = localDateAt(nowMs, result.timezone);
  const days = result.days.filter(({ date }) => date >= today).slice(0, 7);
  return days[0]?.date === today ? days : [];
}

export function forecastDaysFromToday(result, { nowMs = Date.now() } = {}) {
  if (result?.status !== 'ready') return [];
  const today = localDateAt(nowMs, result.timezone);
  const tomorrow = new Date(Date.parse(`${today}T12:00:00Z`) + 86_400_000)
    .toISOString().slice(0, 10);
  return result.days.filter(({ date }) => date >= today).map((day) => ({
    ...forecastDisplayDay(day, { nowMs, timezone: result.timezone }),
    label: day.date === today ? 'Today' : day.date === tomorrow ? 'Tomorrow' : day.label,
  }));
}

const HOUR_MS = 3_600_000;

function localTimestamp(atMs, timezone) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23', timeZoneName: 'longOffset',
  }).formatToParts(atMs).map(({ type, value }) => [type, value]));
  const offset = parts.timeZoneName.replace('GMT', '') || 'Z';
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}${offset}`;
}

function daytimeStartMs(date, timezone) {
  const wanted = Date.parse(`${date}T${String(FUTURE_DAY_START_HOUR).padStart(2, '0')}:00:00Z`);
  let atMs = wanted;
  // Resolve the local daytime boundary, including a DST change earlier that day.
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const localAsUtc = Date.parse(`${localTimestamp(atMs, timezone).slice(0, 19)}Z`);
    atMs += wanted - localAsUtc;
  }
  return atMs;
}

function forecastSlots(hours, startMs, count, timezone) {
  const byTime = new Map(hours.map(hour => [hour.atMs, hour]));
  return Array.from({ length: count }, (_, index) => {
    const atMs = startMs + index * HOUR_MS;
    return byTime.get(atMs) ?? Object.freeze({
      at: localTimestamp(atMs, timezone), atMs, missing: true,
      isDay: null, tempF: null, precipPct: null, precipIn: null,
      radiationWm2: null, windMph: null, weatherCode: null, cloudPct: null,
    });
  });
}

/** Repeated fall-back hours retain separate positions and distinct offset labels. */
export function forecastHourLabels(hours, { compact = false } = {}) {
  const labels = hours.map(({ at }) => {
    const hour = Number(at.slice(11, 13));
    return compact ? `${hour % 12 || 12}${hour < 12 ? 'a' : 'p'}`
      : `${hour % 12 || 12} ${hour < 12 ? 'AM' : 'PM'}`;
  });
  const counts = new Map();
  for (const label of labels) counts.set(label, (counts.get(label) ?? 0) + 1);
  return labels.map((label, index) => counts.get(label) > 1
    ? `${label} UTC${hours[index].at.endsWith('Z') ? '+00:00' : hours[index].at.slice(-6)}` : label);
}

export function hourlyForecastFromDetail(result, { nowMs = Date.now() } = {}) {
  if (result?.status !== 'ready' || !Number.isFinite(nowMs)
      || !Number.isFinite(result.generatedAtMs)
      || nowMs - result.generatedAtMs > FORECAST_DETAIL_STALE_MS) return [];
  // The strip includes the current hour; absent targets keep null-valued slots.
  const currentHourMs = Math.floor(nowMs / HOUR_MS) * HOUR_MS;
  const slots = forecastSlots(result.days.flatMap(({ hours }) => hours), currentHourMs, 14, result.timezone);
  const labels = forecastHourLabels(slots, { compact: true });
  return slots.map((hour, index) => ({
    at: hour.at,
    isDay: hour.isDay,
    h: labels[index],
    t: hour.tempF,
    p: hour.precipPct,
    a: hour.precipIn,
    r: hour.radiationWm2,
    w: hour.weatherCode,
    c: hour.cloudPct,
    ...(hour.missing ? { missing: true } : {}),
  }));
}

export function selectForecastWindow(result, selectedDate, { nowMs = Date.now() } = {}) {
  const allHours = result.days.flatMap(({ hours }) => hours);
  const today = localDateAt(nowMs, result.timezone);
  const mode = selectedDate === today ? 'rolling' : 'daytime';
  // Preserve the existing inclusive exact-boundary convention. Select elapsed
  // time slots, never the next twelve available rows beyond a missing target.
  const startMs = mode === 'rolling' ? Math.ceil(nowMs / HOUR_MS) * HOUR_MS
    : daytimeStartMs(selectedDate, result.timezone);
  const count = mode === 'rolling' ? FORECAST_DETAIL_HOURS : FUTURE_DAY_END_HOUR - FUTURE_DAY_START_HOUR + 1;
  const slots = forecastSlots(allHours, startMs, count, result.timezone);
  const hours = slots.filter(hour => !hour.missing);
  return Object.freeze({
    mode,
    hours: Object.freeze(hours),
    slots: Object.freeze(slots),
    expectedHours: count,
    missingHours: count - hours.length,
  });
}
