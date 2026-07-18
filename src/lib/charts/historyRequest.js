import { createHistoryWindow, getSeriesRequestWindow } from './periods.js';
import { getSeriesPolicy } from './seriesPolicy.js';
import { normalizeHistory } from './historyPipeline.js';

export async function loadHistorySeries({
  client,
  series = [],
  hours,
  nowMs = Date.now(),
  signal,
} = {}) {
  if (!client?.getHistory) throw new TypeError('A history client is required');
  const window = createHistoryWindow(hours, { nowMs });
  const settled = await Promise.allSettled(series.map((source) => {
    const policy = getSeriesPolicy(source);
    return client.getHistory(source.name, {
      ...getSeriesRequestWindow(policy, window),
      signal,
    });
  }));

  if (signal?.aborted) {
    throw signal.reason || new DOMException('History request aborted', 'AbortError');
  }

  const errors = [];
  const pointsPerSeries = settled.map((result, index) => {
    if (result.status === 'fulfilled') {
      const points = Array.isArray(result.value) ? result.value : [];
      try {
        normalizeHistory(points, { allowedUnits: getSeriesPolicy(series[index]).allowedUnits });
        return points;
      } catch (error) {
        errors.push({ index, source: series[index], error });
        return [];
      }
    }
    errors.push({ index, source: series[index], error: result.reason });
    return [];
  });
  const hasData = pointsPerSeries.some((points) => points.length > 0);
  const state = errors.length === series.length && series.length > 0
    ? 'error'
    : errors.length > 0
      ? 'partial-error'
      : hasData
        ? 'ready'
        : 'empty';

  return { state, pointsPerSeries, errors, nowMs, window };
}
