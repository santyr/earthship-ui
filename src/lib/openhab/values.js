// Parse an openHAB item state into a finite number, or null.
// parseFloat handles unit-suffixed QuantityType states ("12.3 mph" -> 12.3,
// "-4.2 A" -> -4.2) AND preserves scientific notation ("1.0E-4 in" -> 1e-4),
// which the old regex-strip approach corrupted (it deleted the "E").
// NULL/UNDEF/'' and non-numeric-leading strings ("ON", "abc123") -> null.
export function num(state) {
  if (state === undefined || state === null) return null;
  const s = String(state).trim();
  if (s === 'NULL' || s === 'UNDEF' || s === '') return null;
  const n = parseFloat(s);
  return Number.isFinite(n) ? n : null;
}

export function fmt(state, unit = '', digits = 0) {
  const n = num(state);
  return n === null ? '—' : n.toFixed(digits) + unit;
}

// Forecast rain amounts (inches) render only when strictly positive — dry
// days/hours stay clean with no "0.00″" clutter. Two decimals + typographic
// double-prime, e.g. "0.24″".
export function rainAmountText(value) {
  const n = num(value);
  return n !== null && n > 0 ? `${n.toFixed(2)}″` : null;
}

// Default = full-bank thresholds (4P 400 Ah since 2026-07-18); pass
// full=false only for the retired interim single-module bands.
export function socBands(soc, full = true) {
  const n = num(soc);
  if (n === null) return '#6b7280';
  const [g, y, o] = full ? [50, 30, 12] : [60, 40, 12];
  if (n <= o) return '#ef4444';
  if (n <= y) return '#f97316';
  if (n <= g) return '#eab308';
  return '#22c55e';
}

// Round a fractional minute count to whole minutes FIRST, then split into
// hours/minutes so boundary values can never render as "1 h 60 m"
// (e.g. 119.6 min -> { total: 120, hours: 2, minutes: 0 }).
export function splitRoundedMinutes(minutesFloat) {
  const total = Math.round(minutesFloat);
  return { total, hours: Math.floor(total / 60), minutes: total % 60 };
}

export function runtimeText(minutes) {
  const n = num(minutes);
  if (n === null || n <= 0) return '—';
  const { total, hours, minutes: mins } = splitRoundedMinutes(n);
  if (total >= 10080) return '> 7 d';
  if (total >= 2880) {
    // Same carry discipline one unit up: round to whole hours, then split
    // into days/hours so 4289.9 min can never render as "2 d 24 h".
    const totalHours = Math.round(total / 60);
    return `${Math.floor(totalHours / 24)} d ${totalHours % 24} h`;
  }
  if (total >= 60) return `${hours} h ${mins} m`;
  return `${total} min`;
}
