// Sole automatic owner of SouthOutlet outlet 1; greywater owns outlet 2.
// Fresh source-bound SoC >=98% enables the fan during daylight only.
const { rules, triggers, items } = require('openhab');
const FAN = 'SouthOutlet_Outlet1_Switch';
const SUN = 'Sun_Position_Elevation';
let lastCommand = null;
let lastCommandAt = 0;

function state(name) {
  try { return String(items.getItem(name).state); }
  catch (_) { return 'NULL'; }
}

// Preserve the atomic SoC receipt contract used by the protected pump owner.
// The held BMS_SOC display value cannot authorize an ON command.
function trustedSoc(currentMs) {
  const raw = state('BMS_SOC_Evidence_JSON');
  if (raw.length > 2048) return NaN;
  try {
    const row = JSON.parse(raw);
    const keys = ['observedAt', 'reason', 'recordedAt', 'scaleObservedAt', 'soc',
      'status', 'streamEpoch', 'validUntil', 'version'];
    if (!row || typeof row !== 'object' || Array.isArray(row)
        || JSON.stringify(row) !== raw
        || Object.keys(row).sort().join(',') !== keys.join(',')
        || row.version !== 1 || row.status !== 'valid' || row.reason !== 'ok'
        || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(row.streamEpoch)
        || ![row.observedAt, row.recordedAt, row.scaleObservedAt, row.validUntil]
          .every(Number.isSafeInteger)
        || !(0 < row.observedAt && row.observedAt <= row.recordedAt
          && row.recordedAt <= currentMs)
        || !(0 < row.scaleObservedAt && row.scaleObservedAt <= row.recordedAt)
        || currentMs - row.recordedAt > 180000
        || row.validUntil !== Math.min(row.observedAt, row.scaleObservedAt) + 120000
        || currentMs >= row.validUntil
        || typeof row.soc !== 'number' || !Number.isFinite(row.soc)
        || row.soc < 0 || row.soc > 100) return NaN;
    return row.soc;
  } catch (_) { return NaN; }
}

function eventTime(name) {
  const raw = state(name);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:?\d{2})$/.test(raw)) return NaN;
  return Date.parse(raw);
}

function daylight(currentMs) {
  try {
    const sun = items.getItem(SUN);
    const raw = String(sun.state);
    const elevation = /^-?\d+(?:\.\d+)? °$/.test(raw) ? Number(raw.slice(0, -2)) : NaN;
    const stamp = sun.lastStateUpdateInstant;
    const updatedAt = stamp === null || stamp === undefined ? NaN : Number(stamp.toEpochMilli());
    const start = eventTime('Sun_Daylight_Start');
    const end = eventTime('Sun_Set_Start');
    // Daily event bounds prevent a positive restored/held elevation from
    // authorizing ON after sunset. Native Astro elevation updates every 16 s.
    return Number.isFinite(elevation) && elevation > 0 && elevation <= 90
      && Number.isSafeInteger(updatedAt) && updatedAt > 0 && updatedAt <= currentMs
      && currentMs - updatedAt < 120000
      && Number.isSafeInteger(start) && Number.isSafeInteger(end)
      && start < end && end - start < 86400000
      && currentMs >= start && currentMs < end;
  } catch (_) { return false; }
}

function evaluate() {
  const now = Date.now();
  const soc = trustedSoc(now);
  const voltageText = state('DCData_Voltage');
  const voltage = /^\d+(?:\.\d+)? V$/.test(voltageText)
    ? Number(voltageText.slice(0, -2)) : NaN;
  const healthy = Number.isFinite(soc)
    && state('BMS_Comms_Status') === 'OK'
    && state('SchneiderTelemetry_Status').startsWith('OK,')
    && Number.isFinite(voltage) && voltage >= 40 && voltage <= 60;
  const isDaylight = daylight(now);
  const desired = healthy && soc >= 98 && isDaylight ? 'ON' : 'OFF';
  try {
    const fan = items.getItem(FAN);
    if (String(fan.state) === desired) return;
    // A changed target (especially safety OFF) is immediate. Retry identical
    // unacknowledged commands at most once every 30 seconds.
    const elapsed = now - lastCommandAt;
    if (lastCommand === desired && elapsed >= 0 && elapsed < 30000) return;
    lastCommand = desired;
    lastCommandAt = now;
    fan.sendCommand(desired);
    console.info('[south-planter-fan] command=' + desired
      + ' reason=' + (!healthy ? 'invalid_telemetry' : !isDaylight ? 'not_daylight' : 'soc_threshold')
      + ' soc=' + (Number.isFinite(soc) ? soc : 'unknown'));
  } catch (error) {
    console.error('[south-planter-fan] command failed: ' + error);
  }
}

rules.JSRule({
  id: 'hex_south_planter_fan',
  name: 'South planter fan at 98% battery SoC during daylight',
  description: 'Outlet 1 ON at fresh SoC >=98% during daylight; OFF after dark, below 98%, or on invalid telemetry.',
  triggers: [
    triggers.ItemStateUpdateTrigger('BMS_SOC_Evidence_JSON'),
    triggers.ItemStateChangeTrigger('BMS_Comms_Status'),
    triggers.ItemStateChangeTrigger('SchneiderTelemetry_Status'),
    triggers.ItemStateUpdateTrigger('DCData_Voltage'),
    triggers.ItemStateUpdateTrigger(SUN),
    triggers.ItemStateUpdateTrigger('Sun_Daylight_Start'),
    triggers.ItemStateUpdateTrigger('Sun_Set_Start'),
    triggers.ItemStateChangeTrigger(FAN),
    triggers.GenericCronTrigger('0/30 * * * * ?'),
  ],
  execute: evaluate,
});
