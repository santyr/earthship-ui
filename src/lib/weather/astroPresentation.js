import { parseSourceTimestamp } from '../openhab/timestamp.js';
import { splitRoundedMinutes } from '../openhab/values.js';

import { HOUSEHOLD_TIMEZONE } from '../site.js';
export const ASTRO_SITE_TIMEZONE = HOUSEHOLD_TIMEZONE;
export const ASTRO_EVIDENCE_ITEMS = Object.freeze([
  'Sun_TimeLeft', 'Sun_NextSeason', 'Sun_Daylight_Duration',
  'Sun_Rise_Start', 'Sun_Set_End', 'Moon_MoonPhaseName',
]);
const siteDate = new Intl.DateTimeFormat('en-CA', {
  timeZone: ASTRO_SITE_TIMEZONE, year: 'numeric', month: '2-digit', day: '2-digit',
});
const seasons = { SPRING: ['Spring','🌱'], SUMMER: ['Summer','☀️'], AUTUMN: ['Autumn','🍂'], WINTER: ['Winter','❄️'] };
const phases = { NEW:'new', WAXING_CRESCENT:'waxing-crescent', FIRST_QUARTER:'first-quarter', WAXING_GIBBOUS:'waxing-gibbous', FULL:'full', WANING_GIBBOUS:'waning-gibbous', THIRD_QUARTER:'last-quarter', WANING_CRESCENT:'waning-crescent' };

function sameDay(a, b) {
  return Number.isFinite(a) && Number.isFinite(b) && siteDate.format(a) === siteDate.format(b);
}
function current(context, name) {
  const { states = {}, evidence = {}, now } = context;
  const row = evidence[name];
  const at = parseSourceTimestamp(row?.lastKnown, now);
  // Daily calculations expire at site midnight, not an observation's short TTL.
  return context.connected === true && row?.available === true
    && row.state === states[name] && at !== null && sameDay(at, now);
}
function durationSeconds(raw) {
  if (typeof raw !== 'string') return null;
  const match = /^([0-9]+(?:\.[0-9]+)?) (s|min|h|d)$/.exec(raw);
  if (!match) return null;
  const result = Number(match[1]) * { s:1, min:60, h:3600, d:86400 }[match[2]];
  return Number.isFinite(result) ? result : null;
}
export function nativeSeasonLabel(context) {
  if (!context.sunOnline || !['Sun_TimeLeft','Sun_NextSeason'].every(name => current(context,name))) return 'Season unavailable';
  // Astro publishes these together. Withhold intermediate SSE/rollover pairs;
  // never combine a new duration with a prior generation's name.
  if (Math.abs(context.evidence.Sun_TimeLeft.lastKnown - context.evidence.Sun_NextSeason.lastKnown) > 100) return 'Season unavailable';
  const seconds = durationSeconds(context.states.Sun_TimeLeft);
  const season = seasons[context.states.Sun_NextSeason];
  if (seconds === null || seconds > 366*86400 || !season) return 'Season unavailable';
  const days = Math.floor(seconds / 86400);
  return `${days === 0 ? 'less than 1 day' : `${days} ${days === 1 ? 'day' : 'days'}`} until ${season[0]} ${season[1]}`;
}
function currentSunBounds(context) {
  if (!context.sunOnline || !['Sun_Rise_Start','Sun_Set_End'].every(name => current(context,name))) return null;
  // The timestamp parser requires a finite upper bound; future daily events are valid.
  const endOfRange = 8640000000000000;
  const r = parseSourceTimestamp(context.states.Sun_Rise_Start, endOfRange);
  const s = parseSourceTimestamp(context.states.Sun_Set_End, endOfRange);
  if (r === null || s === null || r >= s || !sameDay(r,context.now) || !sameDay(s,context.now)) return null;
  return { sunrise:context.states.Sun_Rise_Start, sunset:context.states.Sun_Set_End };
}
export function nativeCurrentSkyContext(context) {
  return { at:context.now, ...(currentSunBounds(context) ?? {}), currentMoonIcon:nativeCurrentMoon(context) };
}
export function nativeDaylightText(context) {
  if (!currentSunBounds(context) || !current(context,'Sun_Daylight_Duration')) return '—';
  const seconds = durationSeconds(context.states.Sun_Daylight_Duration);
  if (!(seconds > 0 && seconds < 86400)) return '—';
  const { hours, minutes } = splitRoundedMinutes(seconds / 60);
  return `${hours}h ${minutes}m`;
}
export function siteTimeLabel(raw, locale) {
  const at = parseSourceTimestamp(raw, 8640000000000000);
  if (at === null) return '—';
  return new Date(at).toLocaleTimeString(locale, { timeZone:ASTRO_SITE_TIMEZONE, hour:'numeric', minute:'2-digit' })
    .replace(/\s?([AP])M$/i, (_,part) => part.toLowerCase());
}
export function nativeCurrentMoon(context) {
  if (!context.moonOnline || !current(context,'Moon_MoonPhaseName')) return 'mdi:weather-night';
  const phase = phases[context.states.Moon_MoonPhaseName];
  return phase ? `mdi:moon-${phase}` : 'mdi:weather-night';
}
