// WMO weather-code -> icon/label mapping. Shared by any screen that renders
// Open-Meteo forecast codes (Forecast_Hourly_JSON / Forecast_Daily_JSON):
// the Home forecast strip (emoji, inline) and the Weather screen's hourly
// strip + 7-day rows (mdi icon names, via OhIcon).
//
// wmoIcon() returns a bare 'mdi:name' string — OhIcon accepts this directly
// (it only strips a leading 'iconify:' prefix if present, so a raw
// 'mdi:xxx' string passes through untouched).

const BANDS = [
  { max: 1, icon: 'mdi:weather-sunny', label: 'Sunny' },
  { max: 2, icon: 'mdi:weather-partly-cloudy', label: 'Partly Cloudy' },
  { max: 3, icon: 'mdi:weather-cloudy', label: 'Cloudy' },
  { max: 48, min: 45, icon: 'mdi:weather-fog', label: 'Fog' },
  { max: 57, min: 51, icon: 'mdi:weather-rainy', label: 'Drizzle' },
  { max: 67, min: 61, icon: 'mdi:weather-pouring', label: 'Rain' },
  { max: 77, min: 71, icon: 'mdi:weather-snowy', label: 'Snow' },
  { max: 82, min: 80, icon: 'mdi:weather-pouring', label: 'Showers' },
  { max: 86, min: 85, icon: 'mdi:weather-snowy-heavy', label: 'Snow Showers' },
  { max: 99, min: 95, icon: 'mdi:weather-lightning', label: 'Thunderstorm' },
];

function findBand(code) {
  if (code === null || code === undefined || code === 'NULL' || code === 'UNDEF' || code === '') return null;
  const c = Number(code);
  if (!Number.isFinite(c)) return null;
  // Finer-grained split within the 51-67 drizzle/rain range so a single
  // "heavy" code (63/65) reads as pouring rather than a light drizzle icon.
  if (c === 63 || c === 65 || c === 66 || c === 67) {
    return { icon: 'mdi:weather-pouring', label: 'Rain' };
  }
  return BANDS.find((b) => c <= b.max && (b.min === undefined || c >= b.min)) || null;
}

export function wmoIcon(code) {
  return findBand(code)?.icon ?? 'mdi:help-circle-outline';
}

export function wmoLabel(code) {
  return findBand(code)?.label ?? '—';
}
