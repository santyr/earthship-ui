import { HOUSEHOLD_TIMEZONE } from '../site.js';
import { contextualSkyIcon } from './celestial.js';
import { CONDITION_COLORS, wmoIcon, wmoLabel, wmoColor } from '../ui/wmo.js';
const finite = value => typeof value === 'number' && Number.isFinite(value);

/** Presentation derived from forecast quantities, never a synthetic source WMO code. */
export function forecastCondition(row = {}) {
  const code = row.weatherCode;
  if (finite(code) && code >= 0 && wmoLabel(code, row) !== '—') {
    return { icon: wmoIcon(code, row), label: wmoLabel(code, row), color: wmoColor(code, row), basis: 'weather-code' };
  }
  const amount = row.precipIn ?? row.precipSumIn;
  // Ignore sub-0.1 mm hourly / sub-1 mm daily ensemble traces for the glyph. Amounts remain
  // visible separately; temperature alone cannot establish precipitation type.
  const materialDepth = (finite(row.precipIn) ? 0.1 : 1) / 25.4;
  if (finite(amount) && amount >= materialDepth) {
    return { icon: 'mdi:weather-rainy', label: 'Precipitation forecast · type unspecified', color: CONDITION_COLORS.rain, basis: 'precipitation-amount' };
  }
  if (finite(row.cloudPct) && row.cloudPct >= 0 && row.cloudPct <= 100) {
    const cloud = row.cloudPct;
    const icon = cloud >= 75 ? 'mdi:weather-cloudy'
      : cloud >= 25 ? contextualSkyIcon('mdi:weather-partly-cloudy', row)
        : typeof row.isDay === 'boolean' ? contextualSkyIcon('mdi:weather-sunny', row) : 'mdi:cloud-outline';
    const label = cloud >= 75 ? 'Cloudy' : cloud >= 25 ? 'Partly cloudy' : 'Mostly clear';
    return { icon, label: `${label} · ${Math.round(cloud)}% cloud cover`, color: cloud >= 75 ? CONDITION_COLORS.cloudy : cloud < 25 && row.isDay === true ? CONDITION_COLORS.sunny : CONDITION_COLORS.partly, basis: 'cloud-cover' };
  }
  return { icon: 'mdi:help-circle-outline', label: 'Conditions unavailable', color: null, basis: 'unavailable' };
}

/** A partial current day is useful, but must not masquerade as full-day extrema. */
export function forecastDisplayDay(day, { nowMs = Date.now(), timezone = HOUSEHOLD_TIMEZONE } = {}) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(nowMs).map(p => [p.type, p.value]));
  const today = `${parts.year}-${parts.month}-${parts.day}`;
  if (day.date !== today || finite(day.summary.highF) || finite(day.summary.lowF)) return day;
  const temperatures = day.hours.filter(h => h.atMs >= nowMs && finite(h.tempF)).map(h => h.tempF);
  if (!temperatures.length) return day;
  return { ...day, summary: { ...day.summary, highF: Math.max(...temperatures), lowF: Math.min(...temperatures), temperatureScope: 'remaining' } };
}

/** Probabilities and depths have distinct dimensions; keep their axes distinct. */
export function precipitationMetric(hours) {
  const probability = hours.some(h => finite(h.precipPct));
  const values = hours.map(h => (probability ? h.precipPct : h.precipIn) ?? null);
  return { probability, unit: probability ? '%' : 'in', values,
    hasValues: values.some(finite), max: probability ? 100 : Math.max(0.01, ...values.filter(finite)),
    format: value => !finite(value) ? '—' : probability ? `${Math.round(value)}%`
      : value > 0 && value < 0.005 ? '<0.01 in' : `${value.toFixed(2)} in` };
}
