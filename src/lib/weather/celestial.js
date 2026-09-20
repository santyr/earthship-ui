import { getMoonIllumination } from 'suncalc';

const PHASES = ['new', 'waxing-crescent', 'first-quarter', 'waxing-gibbous',
  'full', 'waning-gibbous', 'last-quarter', 'waning-crescent'];

function instant(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : NaN;
  if (typeof value !== 'string' || !/T.*(?:Z|[+-]\d{2}:?\d{2})$/.test(value)) return NaN;
  return Date.parse(value);
}

export function moonPhaseIcon(at) {
  const time = instant(at);
  if (!Number.isFinite(time)) return 'mdi:weather-night';
  const { phase } = getMoonIllumination(new Date(time));
  return `mdi:moon-${PHASES[Math.round(phase * 8) % 8]}`;
}

export function isDaylight({ isDay, at, sunrise, sunset } = {}) {
  if (typeof isDay === 'boolean') return isDay;
  const time = instant(at), rise = instant(sunrise), set = instant(sunset);
  // Current Astro events must never be reused for a different forecast day.
  if (![time, rise, set].every(Number.isFinite) || rise >= set) return null;
  const offset = /([+-]\d{2}):?(\d{2})$/.exec(sunrise);
  const minutes = offset ? (Number(offset[1]) * 60 + (offset[1].startsWith('-') ? -1 : 1) * Number(offset[2])) : 0;
  const day = (t) => Math.floor((t + minutes * 60000) / 86400000);
  if (day(time) !== day(rise) || day(set) !== day(rise)) return null;
  return time >= rise && time < set;
}

export function contextualSkyIcon(icon, context) {
  const day = isDaylight(context);
  if (day === null) return icon;
  const name = String(icon).replace(/^iconify:/, '');
  if (/^(?:mdi:weather-(?:sunny|night)|mdi:moon-[a-z-]+|bi:(?:sun|moon)(?:-fill)?)$/.test(name)) {
    return day ? 'mdi:weather-sunny' : moonPhaseIcon(context.at);
  }
  if (/^(?:mdi:weather-(?:night-)?partly-cloudy|bi:cloud-(?:sun|moon)(?:-fill)?)$/.test(name)) {
    return day ? 'mdi:weather-partly-cloudy' : 'mdi:weather-night-partly-cloudy';
  }
  return icon;
}
