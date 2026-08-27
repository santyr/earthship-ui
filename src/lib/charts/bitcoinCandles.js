import { num } from '../openhab/values.js';
import { escapeHtml } from './options.js';
import { HOME_STATE_COLORS } from '../ui/homeCardState.js';
import { echartsTheme } from '../ui/tokens.js';

export const BITCOIN_CANDLE_COLORS = Object.freeze({
  up: '#22c55e',
  down: '#ef4444',
  neutral: '#f7931a',
});

const WHOLE_DOLLARS = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 0,
});
const LOCAL_SUBDAY_TIME = new Intl.DateTimeFormat(undefined, {
  hour: 'numeric',
  minute: '2-digit',
});
const LOCAL_MONTH_DAY = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
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


function candleValue(candle) {
  return [candle.open, candle.close, candle.low, candle.high];
}

function tooltipValues(entry) {
  const value = entry?.data?.value ?? entry?.data ?? entry?.value;
  return Array.isArray(value) ? value : [];
}

function formatBitcoinPrice(value) {
  return Number.isFinite(value) ? '$' + WHOLE_DOLLARS.format(value) : '-';
}

function formatBitcoinCandleTimestamp(value, interval) {
  const timeMs = Number(value);
  if (!Number.isFinite(timeMs)) return String(value ?? '');
  const date = new Date(timeMs);
  if (Number.isNaN(date.getTime())) return String(value ?? '');
  return interval?.unit === 'day'
    ? LOCAL_MONTH_DAY.format(date)
    : LOCAL_SUBDAY_TIME.format(date);
}

function formatBitcoinCandleTooltip(params, interval) {
  const entry = (Array.isArray(params) ? params[0] : params) || {};
  const [open, close, low, high] = tooltipValues(entry);
  const timestamp = formatBitcoinCandleTimestamp(
    entry.axisValue ?? entry.axisValueLabel ?? '',
    interval,
  );
  return [
    '<div>' + escapeHtml(timestamp) + '</div>',
    '<div>Open: ' + escapeHtml(formatBitcoinPrice(open)) + '</div>',
    '<div>High: ' + escapeHtml(formatBitcoinPrice(high)) + '</div>',
    '<div>Low: ' + escapeHtml(formatBitcoinPrice(low)) + '</div>',
    '<div>Close: ' + escapeHtml(formatBitcoinPrice(close)) + '</div>',
  ].join('');
}

export function buildBitcoinCandleOption({
  candles = [],
  compact = false,
  interval = { unit: 'minutes', value: 60 },
} = {}) {
  const source = Array.isArray(candles) ? candles : [];
  const hiddenAxis = compact ? { show: false } : {};
  return {
    ...echartsTheme,
    grid: compact
      ? { left: 0, right: 0, top: 4, bottom: 0, containLabel: false }
      : { left: 48, right: 16, top: 24, bottom: 32, containLabel: true },
    tooltip: compact
      ? { show: false }
      : {
        trigger: 'axis',
        confine: true,
        formatter: (params) => formatBitcoinCandleTooltip(params, interval),
      },
    xAxis: {
      type: 'category',
      data: source.map(({ startMs }) => startMs),
      boundaryGap: true,
      axisLine: echartsTheme.categoryAxis.axisLine,
      axisTick: echartsTheme.categoryAxis.axisTick,
      axisLabel: compact
        ? echartsTheme.categoryAxis.axisLabel
        : {
          ...echartsTheme.categoryAxis.axisLabel,
          formatter: (value) => formatBitcoinCandleTimestamp(value, interval),
        },
      splitLine: echartsTheme.categoryAxis.splitLine,
      ...hiddenAxis,
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLine: echartsTheme.valueAxis.axisLine,
      axisTick: echartsTheme.valueAxis.axisTick,
      axisLabel: echartsTheme.valueAxis.axisLabel,
      splitLine: echartsTheme.valueAxis.splitLine,
      ...hiddenAxis,
    },
    series: [{
      name: 'Bitcoin',
      type: 'candlestick',
      data: source.map((candle) => (
        candle.direction === 'neutral'
          ? {
            value: candleValue(candle),
            itemStyle: {
              color: HOME_STATE_COLORS.bitcoin,
              borderColor: HOME_STATE_COLORS.bitcoin,
            },
          }
          : candleValue(candle)
      )),
      itemStyle: {
        color: HOME_STATE_COLORS.positive,
        color0: HOME_STATE_COLORS.negative,
        borderColor: HOME_STATE_COLORS.positive,
        borderColor0: HOME_STATE_COLORS.negative,
      },
    }],
    animation: false,
  };
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
