import { localDateAt } from '../weather/forecastDetail.js';

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const OFFSET_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
const STREAM_EPOCH = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const LOCAL_HOUR = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Denver', hour: 'numeric', hourCycle: 'h23',
});

function overnightTargetEnd(predictionDay) {
  // Calendar arithmetic, not 24 elapsed hours: Mountain DST can change overnight.
  const nextDayMs = Date.parse(`${predictionDay}T00:00:00Z`) + 86_400_000;
  const summerCandidate = nextDayMs + 17 * 60 * 60_000;
  return summerCandidate + (11 - Number(LOCAL_HOUR.format(summerCandidate))) * 60 * 60_000;
}

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

export function parsePreDuskTroughReceipt(raw, { nowMs = Date.now() } = {}) {
  if (typeof raw !== 'string' || raw.length > 1024) return null;
  try {
    const receipt = JSON.parse(raw);
    if (receipt?.version !== 1 || receipt.basis !== 'atomic_soc_pre_dusk_v1'
      || !DATE.test(receipt.predictionDay)
      || !STREAM_EPOCH.test(receipt.socStreamEpoch)
      || !SHA256.test(receipt.socEvidenceSha256)
      || ![receipt.issuedAt, receipt.sunsetAt, receipt.morningIssuedAt,
        receipt.socRecordedAt].every(value => typeof value === 'string'
        && OFFSET_TIMESTAMP.test(value))) return null;
    const issuedAtMs = Date.parse(receipt.issuedAt);
    const sunsetAtMs = Date.parse(receipt.sunsetAt);
    const morningIssuedAtMs = Date.parse(receipt.morningIssuedAt);
    const socRecordedAtMs = Date.parse(receipt.socRecordedAt);
    const targetEndAtMs = overnightTargetEnd(receipt.predictionDay);
    if (![issuedAtMs, sunsetAtMs, morningIssuedAtMs, socRecordedAtMs].every(Number.isFinite)
      || issuedAtMs > nowMs + 60_000
      || !Number.isFinite(nowMs) || nowMs >= targetEndAtMs
      || [issuedAtMs, sunsetAtMs, morningIssuedAtMs].some(at =>
        localDateAt(at, 'America/Denver') !== receipt.predictionDay)
      || morningIssuedAtMs >= issuedAtMs
      || socRecordedAtMs > issuedAtMs || issuedAtMs - socRecordedAtMs > 120_000
      || sunsetAtMs - issuedAtMs < 60 * 60_000
      || sunsetAtMs - issuedAtMs >= 90 * 60_000
      || !bounded(receipt.socAtIssuePct, 100)
      || !bounded(receipt.overnightDropPct, 50)
      || receipt.socAtIssuePct === null || receipt.overnightDropPct === null
      || receipt.overnightDropPct < 1
      || !Number.isInteger(receipt.overnightTroughSocPct)
      || receipt.overnightTroughSocPct !== Math.round(Math.max(12,
        Math.min(99, receipt.socAtIssuePct - receipt.overnightDropPct)))) return null;
    return Object.freeze({
      predictionDay: receipt.predictionDay, issuedAtMs, targetEndAtMs,
      overnightTroughSocPct: receipt.overnightTroughSocPct,
      socAtIssuePct: receipt.socAtIssuePct,
      overnightDropPct: receipt.overnightDropPct,
      basis: 'pre-dusk',
    });
  } catch {
    return null;
  }
}

export function selectTroughForecast(preDusk) {
  if (preDusk) {
    return Object.freeze({ value: preDusk.overnightTroughSocPct,
      basis: 'pre-dusk', itemName: 'Predicted_SoC_Trough_PreDusk',
      issuedAtMs: preDusk.issuedAtMs, targetEndAtMs: preDusk.targetEndAtMs });
  }
  return null;
}
