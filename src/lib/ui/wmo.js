// WMO weather-code -> icon/label mapping. Shared by any screen that renders
// Open-Meteo forecast codes (Forecast_Hourly_JSON / Forecast_Daily_JSON):
// the Home forecast strip (emoji, inline) and the Weather screen's hourly
// strip + 7-day rows (mdi icon names, via OhIcon).
//
// wmoIcon() returns a bare 'mdi:name' string — OhIcon accepts this directly
// (it only strips a leading 'iconify:' prefix if present, so a raw
// 'mdi:xxx' string passes through untouched).

// Condition colors (spec 2026-07-19). Anchored to tokens.js accents where
// one exists; all ≥3:1 contrast on the #11151c tile background.
export const CONDITION_COLORS = Object.freeze({
  sunny: '#eab308',
  clearNight: '#cbd5e1',
  partly: '#cbd5e1',
  cloudy: '#94a3b8',
  fog: '#8b93a1',
  rain: '#3b82f6',
  pouring: '#2563eb',
  snow: '#bfdbfe',
  thunder: '#8b5cf6',
});

const BANDS = [
  { max: 1, icon: 'mdi:weather-sunny', label: 'Sunny', colorKey: 'sunny' },
  { max: 2, icon: 'mdi:weather-partly-cloudy', label: 'Partly Cloudy', colorKey: 'partly' },
  { max: 3, icon: 'mdi:weather-cloudy', label: 'Cloudy', colorKey: 'cloudy' },
  { max: 48, min: 45, icon: 'mdi:weather-fog', label: 'Fog', colorKey: 'fog' },
  { max: 57, min: 51, icon: 'mdi:weather-rainy', label: 'Drizzle', colorKey: 'rain' },
  { max: 67, min: 61, icon: 'mdi:weather-pouring', label: 'Rain', colorKey: 'pouring' },
  { max: 77, min: 71, icon: 'mdi:weather-snowy', label: 'Snow', colorKey: 'snow' },
  { max: 82, min: 80, icon: 'mdi:weather-pouring', label: 'Showers', colorKey: 'pouring' },
  { max: 86, min: 85, icon: 'mdi:weather-snowy-heavy', label: 'Snow Showers', colorKey: 'snow' },
  { max: 99, min: 95, icon: 'mdi:weather-lightning', label: 'Thunderstorm', colorKey: 'thunder' },
];

function findBand(code) {
  if (code === null || code === undefined || code === 'NULL' || code === 'UNDEF' || code === '') return null;
  const c = Number(code);
  if (!Number.isFinite(c)) return null;
  // The 61-67 rain band already renders the pouring icon/label/colorKey, so
  // codes 63/65/66/67 need no special case.
  return BANDS.find((b) => c <= b.max && (b.min === undefined || c >= b.min)) || null;
}

export function wmoIcon(code) {
  return findBand(code)?.icon ?? 'mdi:help-circle-outline';
}

export function wmoLabel(code) {
  return findBand(code)?.label ?? '—';
}

export function wmoColor(code) {
  const key = findBand(code)?.colorKey;
  return key ? CONDITION_COLORS[key] : null;
}

const SKY_ICON_RULES = [
  [/night-partly|cloud-sun|partly/, 'partly'],
  [/weather-night|moon/, 'clearNight'],
  [/sunny|weather-sunset/, 'sunny'],
  [/fog|hazy/, 'fog'],
  [/pouring/, 'pouring'],
  [/rainy|drizzle|showers/, 'rain'],
  [/snowy|snow/, 'snow'],
  [/lightning|thunder/, 'thunder'],
  [/cloudy|cloud/, 'cloudy'],
];

export function skyIconColor(iconName) {
  if (!iconName || iconName === 'NULL' || iconName === 'UNDEF') return null;
  const name = String(iconName).replace(/^iconify:/, '');
  if (!/^(mdi|bi):/.test(name) || !/weather|cloud|moon|sun/.test(name)) return null;
  const rule = SKY_ICON_RULES.find(([re]) => re.test(name));
  return rule ? CONDITION_COLORS[rule[1]] : null;
}
