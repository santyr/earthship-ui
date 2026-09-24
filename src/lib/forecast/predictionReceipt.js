import { localDateAt } from '../weather/forecastDetail.js';

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const OFFSET_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

function bounded(value, max) {
  return value === null || (typeof value === 'number' && Number.isFinite(value)
    && value >= 0 && value <= max);
}

export function parsePredictionReceipt(raw, { nowMs = Date.now() } = {}) {
  if (typeof raw !== 'string' || raw.length > 1024) return null;
  try {
    const receipt = JSON.parse(raw);
    if (receipt?.version !== 1 || !DATE.test(receipt.predictionDay)
      || !OFFSET_TIMESTAMP.test(receipt.issuedAt)) return null;
    const issuedAtMs = Date.parse(receipt.issuedAt);
    if (!Number.isFinite(issuedAtMs) || issuedAtMs > nowMs + 60_000
      || localDateAt(issuedAtMs, 'America/Denver') !== receipt.predictionDay
      || localDateAt(nowMs, 'America/Denver') !== receipt.predictionDay) return null;
    if (!bounded(receipt.pvTodayKwh, 100)
      || !bounded(receipt.curtailmentHoursToday, 24)
      || !bounded(receipt.overnightTroughSocPct, 100)
      || typeof receipt.thermalAdvisory !== 'string'
      || !receipt.thermalAdvisory || receipt.thermalAdvisory.length > 256) return null;
    return Object.freeze({
      predictionDay: receipt.predictionDay,
      issuedAtMs,
      pvTodayKwh: receipt.pvTodayKwh,
      curtailmentHoursToday: receipt.curtailmentHoursToday,
      overnightTroughSocPct: receipt.overnightTroughSocPct,
      thermalAdvisory: receipt.thermalAdvisory,
    });
  } catch {
    return null;
  }
}
