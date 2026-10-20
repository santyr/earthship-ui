// Strict read-only view of the three matching shadow publication Items.
const FIELDS = ['version','schema','provider','mode','generation','generatedAt','decisionAt','status','reason','source','model','hours','automaticActuation'];
const SHA = /^[0-9a-f]{64}$/;
const unavailable = (reason) => ({ status: 'unavailable', reason, hours: [], source: null, model: null });
function closed(value, fields) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).sort().join('|') !== [...fields].sort().join('|')) throw new TypeError('Unexpected comparison fields');
}
function timestamp(value) {
  const match = typeof value === 'string' && value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/);
  if (!match || value.length > 64) throw new TypeError('Timestamp requires an offset');
  const [, y, m, d, h, min, sec] = match.map(Number);
  if (m < 1 || m > 12 || d < 1 || d > new Date(Date.UTC(y, m, 0)).getUTCDate() || h > 23 || min > 59 || sec > 59) throw new TypeError('Invalid timestamp');
  const result = Date.parse(value);
  if (!Number.isFinite(result)) throw new TypeError('Invalid timestamp');
  return result;
}
function number(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new TypeError('Finite temperature required');
  return value;
}
function fahrenheit(value) {
  return value === null ? null : number(number(value) * 1.8 + 32);
}
function sha(value) {
  if (typeof value !== 'string' || !SHA.test(value)) throw new TypeError('Original digest required');
}
export function parseProviderForecast(comparisonRaw, statusRaw, localRaw, { nowMs = Date.now(), connected = true } = {}) {
  if (!connected) return unavailable('OpenHAB disconnected');
  const raws = [comparisonRaw, statusRaw, localRaw];
  if (raws.some((raw) => typeof raw !== 'string' || !raw.trim() || ['NULL','UNDEF'].includes(raw.trim()))) return unavailable('WeatherNext not configured');
  if (raws.some((raw) => new TextEncoder().encode(raw).length >= 65536)) return unavailable('WeatherNext forecast exceeds size limit');
  if (new Set(raws.map((raw) => raw.trim())).size !== 1) return unavailable('WeatherNext publication incomplete');
  try {
    const value = JSON.parse(comparisonRaw); closed(value, FIELDS);
    if (value.version !== 2 || value.schema !== 'earthship-weather-provider-shadow/v2' || value.provider !== 'weathernext3' || value.mode !== 'shadow' || value.automaticActuation !== false) throw new TypeError('Unsupported shadow contract');
    sha(value.generation);
    const decisionAtMs = timestamp(value.decisionAt), generatedAtMs = timestamp(value.generatedAt);
    if (!Number.isFinite(nowMs) || generatedAtMs < decisionAtMs || generatedAtMs > nowMs + 300000) throw new TypeError('Invalid decision/completion clocks');
    if (!['READY','UNAVAILABLE'].includes(value.status) || !['NONE','NO_ELIGIBLE_SOURCE','UNTRAINED','MODEL_UNAVAILABLE'].includes(value.reason)) throw new TypeError('Unknown comparison status');
    if (!Array.isArray(value.hours) || value.hours.length > 360) throw new TypeError('Bounded forecast hours required');
    const model = value.model;
    closed(model, ['status','sha256','fittedAt','trainingEnd','sampleCount','targetDates','validation']);
    if (!['UNTRAINED','SHADOW_ONLY','UNAVAILABLE'].includes(model.status) || model.validation !== null) throw new TypeError('Unsupported validation claim');
    if ([[model.sampleCount, 50000], [model.targetDates, 366]].some(([n, bound]) => !Number.isSafeInteger(n) || n < 0 || n > bound) || model.targetDates > model.sampleCount) throw new TypeError('Invalid model sample support');
    if (model.status === 'SHADOW_ONLY') {
      sha(model.sha256);
      if (timestamp(model.trainingEnd) > timestamp(model.fittedAt) || timestamp(model.fittedAt) > decisionAtMs || !model.sampleCount) throw new TypeError('Model was not available at decision');
    } else if (model.sha256 !== null || model.fittedAt !== null || model.trainingEnd !== null || model.sampleCount || model.targetDates) throw new TypeError('Untrained model has training claims');
    if (value.status === 'UNAVAILABLE') {
      if (value.source !== null || value.hours.length) throw new TypeError('Unavailable source contains forecasts');
      return unavailable('WeatherNext source unavailable');
    }
    const source = value.source;
    closed(source, ['snapshotSha256','runId','initializedAt','firstSeenAt','ingestedAt','timezone']);
    sha(source.snapshotSha256);
    if (typeof source.runId !== 'string' || !source.runId.length || source.runId.length > 128) throw new TypeError('Source run required');
    new Intl.DateTimeFormat('en-US', { timeZone: source.timezone });
    const initializedAtMs = timestamp(source.initializedAt), firstSeenAtMs = timestamp(source.firstSeenAt), ingestedAtMs = timestamp(source.ingestedAt);
    if (!(initializedAtMs <= firstSeenAtMs && firstSeenAtMs <= ingestedAtMs && ingestedAtMs <= decisionAtMs) || decisionAtMs - initializedAtMs > 86400000) throw new TypeError('Source unavailable at decision');
    let previous = decisionAtMs;
    const hours = value.hours.map((row) => {
      closed(row, ['at','rawC','localC']);
      const atMs = timestamp(row.at);
      if (atMs <= previous || atMs > initializedAtMs + 360 * 3600000) throw new TypeError('Invalid forecast ordering/horizon');
      previous = atMs;
      number(row.rawC);
      if (model.status !== 'SHADOW_ONLY' && row.localC !== null) throw new TypeError('Untrained model has predictions');
      return Object.freeze({ at: row.at, atMs, rawF: fahrenheit(row.rawC), localF: fahrenheit(row.localC) });
    });
    if (!hours.length) throw new TypeError('Available source lacks targets');
    const stale = nowMs - generatedAtMs > 2 * 3600000 || nowMs - initializedAtMs > 86400000;
    return Object.freeze({ status: stale ? 'stale' : 'ready', reason: stale ? 'WeatherNext forecast stale' : '', generatedAtMs, decisionAtMs,
      source: Object.freeze({ ...source, initializedAtMs }), model: Object.freeze(model),
      sourceAgeHours: Math.max(0, (nowMs - initializedAtMs) / 3600000), horizonHours: (hours.at(-1).atMs - decisionAtMs) / 3600000,
      hours: Object.freeze(stale ? [] : hours) });
  } catch (error) { return unavailable(error?.message || 'WeatherNext forecast invalid'); }
}
