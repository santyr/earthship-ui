const DEFAULT_ALPHA = 0.25;

export class HistoryDataError extends TypeError {
  constructor(message, code = 'invalid-history-data') {
    super(message);
    this.name = 'HistoryDataError';
    this.code = code;
  }
}

export class HistoryFragmentationError extends Error {
  constructor() {
    super('Data too fragmented for this range');
    this.name = 'HistoryFragmentationError';
    this.code = 'history-too-fragmented';
  }
}

function parseState(state) {
  if (typeof state === 'number') {
    return Number.isFinite(state) ? { value: state, unit: '' } : null;
  }
  if (typeof state !== 'string') return null;
  const match = state.trim().match(
    /^([-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)\s*(.*)$/i,
  );
  if (!match) return null;
  const value = Number(match[1]);
  return Number.isFinite(value) ? { value, unit: match[2].trim() } : null;
}

export function normalizeHistory(rows, { allowedUnits } = {}) {
  const units = allowedUnits ? new Set(allowedUnits) : null;
  const byTimestamp = new Map();

  if (!Array.isArray(rows)) {
    throw new HistoryDataError('History rows must be an array');
  }

  rows.forEach((row, index) => {
    const time = row?.time instanceof Date
      ? row.time.getTime()
      : typeof row?.time === 'number'
        ? row.time
        : new Date(row?.time).getTime();
    const parsed = parseState(row?.state);
    if (!Number.isFinite(time)) {
      throw new HistoryDataError(`Invalid history timestamp at row ${index}`);
    }
    if (!parsed) {
      throw new HistoryDataError(`Invalid history state at row ${index}`);
    }
    const explicitUnit = row?.unit == null ? '' : String(row.unit).trim();
    if (explicitUnit && parsed.unit && explicitUnit !== parsed.unit) {
      throw new HistoryDataError(`Conflicting history unit at row ${index}`);
    }
    const unit = explicitUnit || parsed.unit;
    if (units && !units.has(unit)) {
      throw new HistoryDataError(`Unsupported history unit: ${unit || '(unitless)'}`);
    }
    byTimestamp.set(time, {
      time,
      value: parsed.value,
      rawValue: parsed.value,
    });
  });

  return [...byTimestamp.values()].sort((left, right) => left.time - right.time);
}

export function inferCadence(points, expectedCadenceMs) {
  if (Number.isFinite(expectedCadenceMs) && expectedCadenceMs > 0) {
    return expectedCadenceMs;
  }
  const deltas = [];
  for (let index = 1; index < points.length; index += 1) {
    const delta = points[index].time - points[index - 1].time;
    if (delta > 0) deltas.push(delta);
  }
  if (!deltas.length) return Number.POSITIVE_INFINITY;
  deltas.sort((left, right) => left - right);
  return deltas[Math.floor((deltas.length - 1) / 2)];
}

export function splitAtGaps(points, maxGapMs) {
  if (!points.length) return [];
  const segments = [[points[0]]];
  for (let index = 1; index < points.length; index += 1) {
    const current = points[index];
    const previous = points[index - 1];
    if (current.time - previous.time > maxGapMs) segments.push([]);
    segments.at(-1).push(current);
  }
  return segments;
}

function median(left, middle, right) {
  return [left, middle, right].sort((a, b) => a - b)[1];
}

export function medianThree(points) {
  if (points.length < 3) return points.map((point) => ({ ...point }));
  return points.map((point, index) => ({
    ...point,
    value: index === 0 || index === points.length - 1
      ? point.value
      : median(points[index - 1].value, point.value, points[index + 1].value),
  }));
}

export function ema(points, alpha = DEFAULT_ALPHA) {
  if (points.length < 3) return points.map((point) => ({ ...point }));
  if (!Number.isFinite(alpha) || alpha <= 0 || alpha > 1) {
    throw new RangeError('EMA alpha must be greater than 0 and at most 1');
  }
  let previous = points[0].value;
  return points.map((point, index) => {
    if (index > 0) previous = alpha * point.value + (1 - alpha) * previous;
    return { ...point, value: previous };
  });
}

function downsampleSegment(points, budget) {
  if (points.length <= budget) return points;
  if (budget <= 0) return [];
  if (budget === 1) return [points[0]];
  if (budget === 2) return [points[0], points.at(-1)];

  const selected = new Set([0, points.length - 1]);
  const interiorBudget = budget - 2;
  const pairBuckets = Math.floor(interiorBudget / 2);
  const interiorLength = points.length - 2;

  for (let bucket = 0; bucket < pairBuckets; bucket += 1) {
    const start = 1 + Math.floor((bucket * interiorLength) / pairBuckets);
    const end = 1 + Math.floor(((bucket + 1) * interiorLength) / pairBuckets);
    let minIndex = start;
    let maxIndex = start;
    for (let index = start + 1; index < end; index += 1) {
      if (points[index].value < points[minIndex].value) minIndex = index;
      if (points[index].value > points[maxIndex].value) maxIndex = index;
    }
    selected.add(minIndex);
    selected.add(maxIndex);
  }

  // Equal extrema can collapse a min/max pair. Fill remaining slots with
  // deterministic samples so the render budget remains exact.
  for (let slot = 1; selected.size < budget && slot <= interiorLength; slot += 1) {
    selected.add(1 + Math.floor(((slot - 1) * interiorLength) / Math.max(1, budget - 2)));
  }
  for (let index = 1; selected.size < budget && index < points.length - 1; index += 1) {
    selected.add(index);
  }

  return [...selected]
    .sort((left, right) => left - right)
    .slice(0, budget)
    .map((index) => points[index]);
}

export function prepareHistorySeries(rows, {
  expectedCadenceMs,
  maxGapMs,
  allowedUnits,
  widthPx,
  pointBudget,
} = {}) {
  const raw = normalizeHistory(rows, { allowedUnits });
  if (!Number.isFinite(widthPx) || widthPx <= 0) {
    return { raw, displaySegments: [] };
  }
  const cadenceMs = inferCadence(raw, expectedCadenceMs);
  const gapMs = maxGapMs ?? 3 * cadenceMs;
  const renderBudget = Math.max(1, Math.floor(pointBudget ?? widthPx * 2));
  const fragments = splitAtGaps(raw, gapMs);
  if (fragments.length > renderBudget) throw new HistoryFragmentationError();
  const display = downsampleSegment(raw, renderBudget);
  return {
    raw,
    // Main/modal/Energy charts intentionally remain one unsmoothed source
    // line. Gap analysis above is a safety bound, not a visual segmentation.
    displaySegments: display.length ? [display] : [],
  };
}

export function prepareSparklineSeries(rows, {
  alpha = DEFAULT_ALPHA,
  allowedUnits = ['', '°F', '°C', '%', 'inHg', 'hPa', 'mbar'],
  widthPx = Number.POSITIVE_INFINITY,
  pointBudget,
} = {}) {
  const safeRows = Array.isArray(rows)
    ? rows.map((row, index) => ({
      ...row,
      // The Gallery demo uses category labels. Compact sparklines only need
      // stable ordering, so use the row index when a label is not date-like.
      time: Number.isFinite(row?.time) || Number.isFinite(new Date(row?.time).getTime())
        ? row.time
        : index,
    }))
    : rows;
  const raw = normalizeHistory(safeRows, { allowedUnits });
  const filtered = ema(medianThree(raw), alpha);
  if (!Number.isFinite(widthPx) || widthPx <= 0) return [];
  const budget = Math.max(1, Math.floor(pointBudget ?? widthPx * 2));
  return downsampleSegment(filtered, budget);
}
