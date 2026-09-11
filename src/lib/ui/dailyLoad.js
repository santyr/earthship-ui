// Estimated energy from change-only persisted W states, not source-health proof.
// Requires native start-state carry; the caller must discard REST end look-ahead.
export function estimateDailyLoadKWh(rows, startMs, endMs) {
  if (!Array.isArray(rows) || !Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) return null;
  if (endMs === startMs) return 0;
  const points = [];
  for (const row of rows) {
    if (typeof row?.time !== 'number' || !Number.isFinite(row.time)) return null;
    if (row.time < startMs || row.time >= endMs) continue;
    if (row.unit != null && row.unit !== 'W') return null;
    const text = String(row.state ?? '').trim();
    if (!/^[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?:\s+W)?$/.test(text)) return null;
    const watts = Number(text.replace(/\s+W$/, ''));
    if (!Number.isFinite(watts)) return null;
    points.push({ time: row.time, watts });
  }
  points.sort((a, b) => a.time - b.time);
  if (points[0]?.time !== startMs) return null;
  let wattMs = 0;
  for (let index = 0; index < points.length; index++) {
    const point = points[index];
    const next = points[index + 1];
    if (next?.time === point.time && next.watts !== point.watts) return null;
    wattMs += point.watts * ((next?.time ?? endMs) - point.time);
  }
  return Number.isFinite(wattMs) ? wattMs / 3_600_000_000 : null;
}
