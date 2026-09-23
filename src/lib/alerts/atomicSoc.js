const FIELDS = ['observedAt', 'reason', 'recordedAt', 'scaleObservedAt', 'soc',
  'status', 'streamEpoch', 'validUntil', 'version'];
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const EXPIRY_MS = 120_000;
const MAX_PUBLICATION_AGE_MS = 180_000;

export function atomicSocFreshness(raw, nowMs = Date.now()) {
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > 2048
      || !Number.isSafeInteger(nowMs) || nowMs <= 0) return null;
  try {
    const row = JSON.parse(raw);
    // The producer emits one compact flat JSON object. Requiring its canonical
    // serialization rejects duplicate keys and alternate encodings fail closed.
    if (!row || typeof row !== 'object' || Array.isArray(row)
        || JSON.stringify(row) !== raw
        || Object.keys(row).sort().join(',') !== FIELDS.join(',')) return null;
    if (row.version !== 1 || !UUID.test(row.streamEpoch)
        || row.status !== 'valid' || row.reason !== 'ok') return null;
    const { observedAt, recordedAt, scaleObservedAt, validUntil, soc } = row;
    if (![observedAt, recordedAt, scaleObservedAt, validUntil].every(Number.isSafeInteger)
        || !(0 < observedAt && observedAt <= recordedAt && recordedAt <= nowMs)
        || !(0 < scaleObservedAt && scaleObservedAt <= recordedAt)
        || nowMs - recordedAt > MAX_PUBLICATION_AGE_MS
        || validUntil !== Math.min(observedAt, scaleObservedAt) + EXPIRY_MS
        || nowMs >= validUntil
        || typeof soc !== 'number' || !Number.isFinite(soc)
        || soc < 0 || soc > 100) return null;
    return { recordedAt, validUntil, soc };
  } catch {
    return null;
  }
}
