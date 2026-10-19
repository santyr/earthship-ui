import { HOUSEHOLD_TIMEZONE } from '../site.js';
const finite = value => typeof value === 'number' && Number.isFinite(value);

/** A partial current day is useful, but must not masquerade as full-day extrema. */
export function forecastDisplayDay(day, { nowMs = Date.now(), timezone = HOUSEHOLD_TIMEZONE } = {}) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(nowMs).map(p => [p.type, p.value]));
  const today = `${parts.year}-${parts.month}-${parts.day}`;
  if (day.date !== today || finite(day.summary.highF) || finite(day.summary.lowF)) return day;
  const temperatures = day.hours.filter(h => h.atMs >= nowMs && finite(h.tempF)).map(h => h.tempF);
  if (!temperatures.length) return day;
  return { ...day, summary: { ...day.summary, highF: Math.max(...temperatures), lowF: Math.min(...temperatures), temperatureScope: 'remaining' } };
}

