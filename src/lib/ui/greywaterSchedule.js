// Presentation only. Timing and pump selection come from the live owner rule.
const names = { south: 'South', east: 'East' };
const blocks = {
  after_dark: 'Waiting for daylight', low_soc: 'Waiting for SoC',
  bms_comms_stale: 'Waiting for telemetry', invalid_voltage: 'Waiting for telemetry',
  invalid_soc: 'Waiting for telemetry', absurd_voltage: 'Safety hold',
  busy: 'Controller busy', multiple_pumps_on: 'Safety hold',
  orphan_outlet_off: 'Safety hold', ledger_recovered: 'Recovery hold',
};
const instant = value => typeof value === 'string' &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
  ? Date.parse(value) : NaN;

export function greywaterSchedule({ south, east, status, now = Date.now() }) {
  const active = [south === 'ON' ? 'South' : null, east === 'ON' ? 'East' : null].filter(Boolean);
  const known = [south, east].every(value => value === 'ON' || value === 'OFF');
  const result = {
    running: active.length > 0, known,
    label: active.length === 2 ? 'Both pumps on' : active.length ? `${active[0]} running` : known ? 'Idle' : 'Unavailable',
    next: 'Next unavailable', detail: 'Waiting for current controller scheduling data',
  };
  if (!known || active.length === 2 || typeof status !== 'string' || status.length > 2048 || !Number.isFinite(now)) return result;
  const fields = Object.create(null);
  for (const part of status.split(',')) {
    const at = part.indexOf('=');
    if (at < 1 || Object.hasOwn(fields, part.slice(0, at))) return result;
    fields[part.slice(0, at)] = part.slice(at + 1);
  }
  const evaluated = instant(fields.evaluatedAt);
  if (fields.scheduleVersion !== '1' || !Number.isFinite(evaluated) || now - evaluated > 120_000 || evaluated > now + 5000) return result;
  if (fields.scheduling === 'blocked') {
    result.next = blocks[fields.reason] || 'Waiting for controller';
    result.detail = 'No start time promised while controller conditions block a run';
  } else if (fields.scheduling === 'conditional') {
    const candidate = instant(fields.nextEligibleAt);
    if (!Object.hasOwn(names, fields.nextPump) || !Number.isFinite(candidate) ||
        candidate < evaluated || candidate - evaluated > 86400_000) return result;
    const time = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Denver',
      hour: 'numeric', minute: '2-digit' }).format(candidate);
    result.next = candidate <= now ? `${names[fields.nextPump]} eligible now` : `Earliest ${names[fields.nextPump]} · ${time}`;
    result.detail = 'Daylight and safety conditions must still permit a start. The pump is selected by local hour and can change if delayed.';
  }
  return result;
}
