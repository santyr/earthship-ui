export function parseSourceTimestamp(value, nowMs = Date.now()) {
  let timestamp = null;
  if (typeof value === 'number') timestamp = value;
  else if (typeof value === 'string') {
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})(?:\[[A-Za-z0-9_+./-]+\])?$/.exec(value);
    if (!match) return null;
    const [, y, mo, d, h, mi, s, fraction = '', zone] = match;
    const year = Number(y), month = Number(mo), day = Number(d);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (month < 1 || month > 12 || day < 1 || day > days[month - 1]
      || Number(h) > 23 || Number(mi) > 59 || Number(s) > 59) return null;
    if (zone !== 'Z' && (Number(zone.slice(1, 3)) > 23 || Number(zone.slice(4)) > 59)) return null;
    timestamp = Date.parse(`${y}-${mo}-${d}T${h}:${mi}:${s}.${fraction.padEnd(3, '0').slice(0, 3)}${zone}`);
  }
  return Number.isFinite(nowMs) && Number.isFinite(timestamp) && timestamp > 0 && timestamp <= nowMs
    ? timestamp : null;
}
