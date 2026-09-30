import { createHistoryWindow, getSeriesRequestWindow } from './periods.js';
import { getSeriesPolicy } from './seriesPolicy.js';
import { filterValidHistoryRows, normalizeHistory } from './historyPipeline.js';

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
  invalidRowPolicy = 'strict',
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
      const request = Promise.resolve().then(() => {
        const bounds = { ...getSeriesRequestWindow(policy, window) };
        if (source.validFrom !== undefined) {
          const cutoff = typeof source.validFrom === 'string' ? Date.parse(source.validFrom) : NaN;
          if (!Number.isFinite(cutoff)) throw new TypeError('Invalid series location boundary');
          if (cutoff > Date.parse(bounds.endtime)) return [];
          bounds.starttime = new Date(Math.max(Date.parse(bounds.starttime), cutoff)).toISOString();
        }
        return client.getHistory(source.name, {
          ...bounds,
          ...(source.name === 'BMS_SOC' && source.validFrom === undefined ? { includeStartState: true } : {}),
          signal: controller.signal,
        });
      });
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
        const validation = { allowedUnits: getSeriesPolicy(series[index]).allowedUnits };
        const validated = invalidRowPolicy === 'omit' ? filterValidHistoryRows(points, validation) : points;
        const normalized = normalizeHistory(validated, validation);
        if (series[index].validFrom === undefined) return validated;
        // Even if the persistence provider returns a predecessor, never show
        // pre-move readings under the sensor's new physical location.
        const cutoff = Date.parse(series[index].validFrom);
        const allowed = new Set(normalized.filter((point) => point.time >= cutoff).map((point) => point.time));
        return validated.filter((point) => allowed.has(point.time instanceof Date ? point.time.getTime()
          : typeof point.time === 'number' ? point.time : Date.parse(point.time)));
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
