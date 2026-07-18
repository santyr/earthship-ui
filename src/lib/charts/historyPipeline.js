const DEFAULT_ALPHA = 0.25;

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

  for (const row of rows || []) {
    const time = row?.time instanceof Date
      ? row.time.getTime()
      : typeof row?.time === 'number'
        ? row.time
        : new Date(row?.time).getTime();
    const parsed = parseState(row?.state);
    if (!Number.isFinite(time) || !parsed) continue;
    const unit = row?.unit == null ? parsed.unit : String(row.unit).trim();
    if (units && unit && !units.has(unit)) {
      throw new TypeError(`Unsupported history unit: ${unit}`);
    }
    byTimestamp.set(time, {
      time,
      value: parsed.value,
      rawValue: parsed.value,
    });
  }

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

export function downsampleSegments(segments, { pointBudget }) {
  const nonEmpty = segments.filter((segment) => segment.length);
  const total = nonEmpty.reduce((sum, segment) => sum + segment.length, 0);
  const budget = Math.max(0, Math.floor(pointBudget));
  if (budget <= 0 || total === 0) return [];
  if (total <= budget) return nonEmpty;

  // A chart can contain more real gaps than render slots. Preserve the first
  // and last fragments (plus evenly spaced fragments between them) without
  // violating the global cap or manufacturing lines across those gaps.
  if (nonEmpty.length >= budget) {
    if (budget === 1) return [[nonEmpty[0][0]]];
    const selected = new Set();
    for (let index = 0; index < budget; index += 1) {
      selected.add(Math.round((index * (nonEmpty.length - 1)) / (budget - 1)));
    }
    return [...selected].map((index) => [nonEmpty[index][0]]);
  }

  const allocations = nonEmpty.map((segment) => Math.min(
    segment.length,
    Math.max(1, Math.floor((budget * segment.length) / total)),
  ));
  let allocated = allocations.reduce((sum, count) => sum + count, 0);

  while (allocated < budget) {
    const index = allocations.findIndex((count, i) => count < nonEmpty[i].length);
    if (index < 0) break;
    allocations[index] += 1;
    allocated += 1;
  }
  while (allocated > budget) {
    const index = allocations.findLastIndex((count) => count > 1);
    if (index < 0) break;
    allocations[index] -= 1;
    allocated -= 1;
  }

  return nonEmpty
    .map((segment, index) => downsampleSegment(segment, allocations[index]))
    .filter((segment) => segment.length);
}

export function prepareHistorySeries(rows, {
  expectedCadenceMs,
  maxGapMs,
  smoothing = 'none',
  alpha = DEFAULT_ALPHA,
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
  const segments = splitAtGaps(raw, gapMs);
  const filtered = smoothing === 'median3-ema'
    ? segments.map((segment) => ema(medianThree(segment), alpha))
    : segments;
  const renderBudget = Math.max(1, Math.floor(pointBudget ?? widthPx * 2));
  return {
    raw,
    displaySegments: downsampleSegments(filtered, { pointBudget: renderBudget }),
  };
}
