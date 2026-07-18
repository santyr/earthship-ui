export const HISTORY_PERIODS = Object.freeze([4, 24, 168, 720]);

export const HISTORY_PERIOD_PRESETS = Object.freeze([
  { label: '4h', hours: 4 },
  { label: '24h', hours: 24 },
  { label: '7d', hours: 168 },
  { label: '30d', hours: 720 },
]);

const DEFAULT_PERIOD_HOURS = 24;
export const DEFAULT_FORECAST_LOOKAHEAD_MS = 18 * 60 * 60 * 1_000;

export function isHistoryPeriod(hours) {
  return HISTORY_PERIODS.includes(hours);
}

export function snapHistoryPeriod(hours) {
  if (!Number.isFinite(hours)) return DEFAULT_PERIOD_HOURS;
  return HISTORY_PERIODS.reduce((closest, candidate) => (
    Math.abs(candidate - hours) < Math.abs(closest - hours) ? candidate : closest
  ), HISTORY_PERIODS[0]);
}

export function createHistoryWindow(hours, {
  nowMs = Date.now(),
  lookaheadMs = DEFAULT_FORECAST_LOOKAHEAD_MS,
} = {}) {
  if (!isHistoryPeriod(hours)) {
    throw new RangeError(`Unsupported history period: ${hours}`);
  }
  if (!Number.isFinite(nowMs)) {
    throw new TypeError('History window nowMs must be finite');
  }
  if (!Number.isFinite(lookaheadMs) || lookaheadMs < 0) {
    throw new TypeError('History forecast lookahead must be a non-negative number');
  }

  const history = Object.freeze({
    starttime: new Date(nowMs - hours * 60 * 60 * 1_000).toISOString(),
    endtime: new Date(nowMs).toISOString(),
  });
  const forecast = Object.freeze({
    starttime: new Date(nowMs).toISOString(),
    endtime: new Date(nowMs + lookaheadMs).toISOString(),
  });

  return Object.freeze({
    hours,
    nowMs,
    history,
    forecast,
    // Compatibility fields for non-series-aware callers. New chart requests
    // must use getSeriesRequestWindow() below.
    starttime: history.starttime,
    historyEndtime: history.endtime,
    forecastStarttime: forecast.starttime,
    endtime: forecast.endtime,
  });
}

export function getSeriesRequestWindow(seriesOrPolicy, requestWindow) {
  const domain = seriesOrPolicy?.domain
    || (typeof seriesOrPolicy === 'object' && seriesOrPolicy?.name?.startsWith('Forecast_')
      ? 'forecast'
      : undefined);
  const name = typeof seriesOrPolicy === 'string' ? seriesOrPolicy : seriesOrPolicy?.name;
  const isForecast = domain === 'forecast'
    || name?.startsWith('Forecast_');
  return isForecast ? requestWindow.forecast : requestWindow.history;
}
