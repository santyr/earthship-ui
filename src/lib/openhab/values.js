export function num(state) {
  if (state === undefined || state === null) return null;
  const s = String(state);
  if (s === 'NULL' || s === 'UNDEF' || s === '') return null;
  const n = parseFloat(s.replace(/[^0-9.+-]/g, ''));
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

export function runtimeText(minutes) {
  const n = num(minutes);
  if (n === null || n <= 0) return '—';
  if (n >= 10080) return '> 7 d';
  if (n >= 2880) return `${Math.floor(n / 1440)} d ${Math.round((n % 1440) / 60)} h`;
  if (n >= 60) return `${Math.floor(n / 60)} h ${Math.round(n % 60)} m`;
  return `${Math.round(n)} min`;
}
