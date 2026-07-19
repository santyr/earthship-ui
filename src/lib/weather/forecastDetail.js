export const FORECAST_DETAIL_ITEM = 'Forecast_10Day_JSON';
export const FORECAST_DETAIL_MAX_BYTES = 64 * 1024;
export const FORECAST_DETAIL_STALE_MS = 4 * 60 * 60 * 1_000;

const SENTINELS = new Set(['', 'NULL', 'UNDEF']);
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const OFFSET_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

function unavailable(reason) {
  return Object.freeze({
    status: 'unavailable',
    reason,
    generatedAtMs: null,
    timezone: 'America/Denver',
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

function normalizeHour(raw, date) {
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
    tempF: nullableNumber(raw.tempF, 'tempF'),
    precipPct: nullableNumber(raw.precipPct, 'precipPct'),
    precipIn: nullableNumber(raw.precipIn ?? null, 'precipIn'),
    radiationWm2: nullableNumber(raw.radiationWm2, 'radiationWm2'),
    windMph: nullableNumber(raw.windMph, 'windMph'),
    weatherCode: nullableNumber(raw.weatherCode, 'weatherCode'),
  });
}

function normalizeDay(raw) {
  if (!raw || typeof raw !== 'object' || !DATE.test(raw.date ?? '')) {
    throw new TypeError('day date must be ISO');
  }
  if (!Array.isArray(raw.hours)) throw new TypeError('day hours are required');
  const summary = raw.summary ?? {};
  const hours = raw.hours.map((value) => normalizeHour(value, raw.date));
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
  try {
    const parsed = JSON.parse(raw);
    if (parsed?.version !== 1) throw new TypeError('unsupported forecast detail version');
    if (parsed.timezone !== 'America/Denver') throw new TypeError('unexpected forecast timezone');
    if (!OFFSET_TIMESTAMP.test(parsed.generatedAt ?? '')) {
      throw new TypeError('generatedAt must include an offset');
    }
    const generatedAtMs = Date.parse(parsed.generatedAt);
    if (!Number.isFinite(generatedAtMs)) throw new TypeError('generatedAt is invalid');
    if (!Array.isArray(parsed.days) || parsed.days.length > 10) {
      throw new TypeError('forecast days must contain at most ten entries');
    }
    const days = parsed.days.map(normalizeDay);
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
      generatedAtMs,
      timezone: parsed.timezone,
      days: Object.freeze(days),
    });
  } catch (error) {
    return unavailable(error?.message || 'forecast detail invalid');
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

function localDateAt(nowMs, timezone) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(nowMs);
  const value = Object.fromEntries(parts.map(({ type, value: part }) => [type, part]));
  return `${value.year}-${value.month}-${value.day}`;
}

export function selectForecastWindow(result, selectedDate, { nowMs = Date.now() } = {}) {
  const allHours = result.days
    .flatMap(({ hours }) => hours)
    .sort((a, b) => a.atMs - b.atMs);
  const today = localDateAt(nowMs, result.timezone);
  let hours;
  let mode;
  if (selectedDate === today) {
    mode = 'rolling';
    const nextHourMs = Math.ceil(nowMs / 3_600_000) * 3_600_000;
    hours = allHours.filter(({ atMs }) => atMs >= nextHourMs).slice(0, 10);
  } else {
    mode = 'daytime';
    hours = allHours.filter(({ at }) => (
      at.slice(0, 10) === selectedDate
      && Number(at.slice(11, 13)) >= 8
      && Number(at.slice(11, 13)) <= 17
    ));
  }
  return Object.freeze({
    mode,
    hours: Object.freeze(hours),
    expectedHours: 10,
    missingHours: Math.max(0, 10 - hours.length),
  });
}
