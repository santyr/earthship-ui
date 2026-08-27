import { num } from '../openhab/values.js';

export const BITCOIN_CANDLE_COLORS = Object.freeze({
  up: '#22c55e',
  down: '#ef4444',
  neutral: '#f7931a',
});

const WHOLE_DOLLARS = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 0,
});

export function bitcoinCandleInterval(hours) {
  if (hours === 4) return { unit: 'minutes', value: 15 };
  if (hours === 24) return { unit: 'minutes', value: 60 };
  if (hours === 168) return { unit: 'minutes', value: 360 };
  return { unit: 'day', value: 1 };
}

function timestampMs(time) {
  if (time instanceof Date) return time.getTime();
  if (typeof time === 'number') return time;
  if (typeof time === 'string' && time.trim()) return new Date(time).getTime();
  return Number.NaN;
}

function localDayParts(timeMs, getLocalDateParts) {
  if (typeof getLocalDateParts === 'function') {
    const parts = getLocalDateParts(timeMs);
    if (Array.isArray(parts)) return parts;
    if (parts && typeof parts === 'object') return [parts.year, parts.month, parts.day];
  }
  const date = new Date(timeMs);
  return [date.getFullYear(), date.getMonth(), date.getDate()];
}

function dailyBucket(timeMs, getLocalDateParts) {
  const [year, month, day] = localDayParts(timeMs, getLocalDateParts);
  const startMs = new Date(year, month, day).getTime();
  return {
    startMs,
    endMs: new Date(year, month, day + 1).getTime(),
  };
}

function minuteBucket(timeMs, value) {
  const intervalMs = value * 60_000;
  const startMs = Math.floor(timeMs / intervalMs) * intervalMs;
  return { startMs, endMs: startMs + intervalMs };
}

function candleDirection(candle) {
  if (candle.count === 1 || candle.open === candle.close) return 'neutral';
  return candle.close > candle.open ? 'up' : 'down';
}

/**
 * Aggregate persisted BTC_USD_Price rows. `localDateParts`, when supplied,
 * receives a timestamp and returns [year, monthIndex, day] (or that shape as
 * an object) for deterministic local-day testing.
 */
export function aggregateBitcoinCandles(points, {
  interval,
  startMs,
  endMs,
  localDateParts,
} = {}) {
  if (!Array.isArray(points)
    || !Number.isFinite(startMs)
    || !Number.isFinite(endMs)
    || endMs <= startMs
    || !interval
    || !Number.isFinite(interval.value)
    || interval.value <= 0
    || !['minutes', 'day'].includes(interval.unit)) {
    return [];
  }

  const rows = points
    .map((point, ordinal) => ({
      timeMs: timestampMs(point?.time),
      value: num(point?.state),
      ordinal,
    }))
    .filter(({ timeMs, value }) => (
      Number.isFinite(timeMs)
      && value !== null
      && timeMs >= startMs
      && timeMs < endMs
    ))
    .sort((left, right) => left.timeMs - right.timeMs || left.ordinal - right.ordinal);

  const candles = new Map();
  for (const row of rows) {
    const bucket = interval.unit === 'minutes'
      ? minuteBucket(row.timeMs, interval.value)
      : dailyBucket(row.timeMs, localDateParts);
    const existing = candles.get(bucket.startMs);
    if (existing) {
      existing.high = Math.max(existing.high, row.value);
      existing.low = Math.min(existing.low, row.value);
      existing.close = row.value;
      existing.count += 1;
    } else {
      candles.set(bucket.startMs, {
        startMs: bucket.startMs,
        endMs: bucket.endMs,
        open: row.value,
        high: row.value,
        low: row.value,
        close: row.value,
        count: 1,
      });
    }
  }

  return [...candles.values()]
    .sort((left, right) => left.startMs - right.startMs)
    .map((candle) => ({ ...candle, direction: candleDirection(candle) }));
}

export function describeLatestBitcoinCandle(candles) {
  const candle = Array.isArray(candles) ? candles.at(-1) : null;
  if (!candle) return '';
  return `Latest candle: open $${WHOLE_DOLLARS.format(candle.open)}, high $${WHOLE_DOLLARS.format(candle.high)}, low $${WHOLE_DOLLARS.format(candle.low)}, close $${WHOLE_DOLLARS.format(candle.close)}.`;
}
