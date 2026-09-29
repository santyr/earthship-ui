const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const TTL_MS = 120_000;
const MAX_PUBLICATION_AGE_MS = 180_000;
const BASIS = 'discover_bms_190_native_aux_v1';

export function freshBmsTemperatureF(raw, nowMs = Date.now()) {
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > 4096
      || !Number.isSafeInteger(nowMs) || nowMs <= 0) return null;
  try {
    const receipt = JSON.parse(raw);
    if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)
        || JSON.stringify(receipt) !== raw
        || Object.keys(receipt).sort().join(',') !== 'basis,fields,recordedAt,sequence,streamEpoch,version'
        || receipt.version !== 1 || receipt.basis !== BASIS
        || !UUID.test(receipt.streamEpoch)
        || !Number.isSafeInteger(receipt.sequence) || receipt.sequence <= 0
        || !Number.isSafeInteger(receipt.recordedAt)
        || receipt.recordedAt <= 0 || receipt.recordedAt > nowMs
        || nowMs - receipt.recordedAt > MAX_PUBLICATION_AGE_MS) return null;
    const fields = receipt.fields;
    if (!fields || typeof fields !== 'object' || Array.isArray(fields)
        || Object.keys(fields).sort().join(',') !== 'battery.remaining_ah,battery.temperature_raw') return null;
    const temperature = fields['battery.temperature_raw'];
    if (!temperature || typeof temperature !== 'object' || Array.isArray(temperature)
        || Object.keys(temperature).sort().join(',') !== 'observedAt,reason,status,validUntil,value'
        || temperature.status !== 'valid' || temperature.reason !== 'ok'
        || !Number.isSafeInteger(temperature.observedAt)
        || !Number.isSafeInteger(temperature.validUntil)
        || temperature.observedAt <= 0 || temperature.observedAt > receipt.recordedAt
        || temperature.validUntil !== temperature.observedAt + TTL_MS
        || nowMs >= temperature.validUntil
        || !Number.isSafeInteger(temperature.value)
        || temperature.value < 23300 || temperature.value > 33855) return null;
    return (temperature.value * 0.01 - 273) * 9 / 5 + 32;
  } catch {
    return null;
  }
}
