import { createHistoryWindow, getSeriesRequestWindow } from './periods.js';
import { getSeriesPolicy } from './seriesPolicy.js';
import { normalizeHistory } from './historyPipeline.js';

export const HISTORY_REQUEST_TIMEOUT_MS = 15_000;

export class HistoryRequestTimeoutError extends Error {
  constructor(timeoutMs = HISTORY_REQUEST_TIMEOUT_MS) {
    super('History request timed out after ' + (timeoutMs / 1_000) + ' seconds');
    this.name = 'HistoryRequestTimeoutError';
    this.code = 'history-request-timeout';
    this.timeoutMs = timeoutMs;
  }
}

function abortReason(signal) {
  return signal?.reason || new DOMException('History request aborted', 'AbortError');
}

export async function loadHistorySeries({
  client,
  series = [],
  hours,
  nowMs = Date.now(),
  signal,
} = {}) {
  if (!client?.getHistory) throw new TypeError('A history client is required');
  if (signal?.aborted) throw abortReason(signal);

  const window = createHistoryWindow(hours, { nowMs });
  if (series.length === 0) {
    return {
      state: 'empty',
      pointsPerSeries: [],
      errors: [],
      timedOut: false,
      nowMs,
      window,
    };
  }

  const controller = new AbortController();
  let rejectCancellation;
  let cancelled = false;
  const cancellation = new Promise((_, reject) => {
    rejectCancellation = reject;
  });
  const cancelBatch = (reason) => {
    if (cancelled) return;
    cancelled = true;
    rejectCancellation(reason);
    controller.abort(reason);
  };
  const handleCallerAbort = () => cancelBatch(abortReason(signal));
  signal?.addEventListener('abort', handleCallerAbort, { once: true });
  const deadline = setTimeout(() => {
    cancelBatch(new HistoryRequestTimeoutError());
  }, HISTORY_REQUEST_TIMEOUT_MS);

  let settled;
  try {
    settled = await Promise.allSettled(series.map((source) => {
      const policy = getSeriesPolicy(source);
      const request = Promise.resolve().then(() => client.getHistory(source.name, {
        ...getSeriesRequestWindow(policy, window),
        signal: controller.signal,
      }));
      return Promise.race([request, cancellation]);
    }));
  } finally {
    clearTimeout(deadline);
    signal?.removeEventListener('abort', handleCallerAbort);
  }

  if (signal?.aborted) throw abortReason(signal);

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
  const timedOut = errors.some(({ error }) => error?.code === 'history-request-timeout');

  return { state, pointsPerSeries, errors, timedOut, nowMs, window };
}
