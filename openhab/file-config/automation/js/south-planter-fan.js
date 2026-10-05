// Sole automatic owner of SouthOutlet outlet 1; greywater owns outlet 2.
// Fresh source-bound SoC >=98% enables the fan; every other case selects OFF.
const { rules, triggers, items } = require('openhab');
const FAN = 'SouthOutlet_Outlet1_Switch';
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
  const desired = healthy && soc >= 98 ? 'ON' : 'OFF';
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
      + ' reason=' + (healthy ? 'soc_threshold' : 'invalid_telemetry')
      + ' soc=' + (Number.isFinite(soc) ? soc : 'unknown'));
  } catch (error) {
    console.error('[south-planter-fan] command failed: ' + error);
  }
}

rules.JSRule({
  id: 'hex_south_planter_fan',
  name: 'South planter fan at 98% battery SoC',
  description: 'Outlet 1 ON at fresh SoC >=98%; OFF below 98% or on invalid battery telemetry.',
  triggers: [
    triggers.ItemStateUpdateTrigger('BMS_SOC_Evidence_JSON'),
    triggers.ItemStateChangeTrigger('BMS_Comms_Status'),
    triggers.ItemStateChangeTrigger('SchneiderTelemetry_Status'),
    triggers.ItemStateUpdateTrigger('DCData_Voltage'),
    triggers.ItemStateChangeTrigger(FAN),
    triggers.GenericCronTrigger('0/30 * * * * ?'),
  ],
  execute: evaluate,
});
