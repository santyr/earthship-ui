export { forecastDisplayDay } from './forecastRange.js';
import { CONDITION_COLORS, wmoIcon, wmoLabel, wmoColor } from '../ui/wmo.js';
const finite = value => typeof value === 'number' && Number.isFinite(value);

/** Presentation derived from forecast quantities, never a synthetic source WMO code. */
export function forecastCondition(row = {}) {
  const code = row.weatherCode;
  if (finite(code) && code >= 0 && wmoLabel(code, row) !== '—') {
    return { icon: wmoIcon(code, row), label: wmoLabel(code, row), color: wmoColor(code, row), basis: 'weather-code' };
  }
  if (Array.isArray(row.hours)) return dailyCondition(row);
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
      : cloud >= 25 ? (row.isDay === false ? 'mdi:weather-night-partly-cloudy' : row.isDay === true ? 'mdi:weather-partly-cloudy' : 'mdi:weather-cloudy')
        : row.isDay === false ? 'mdi:weather-night' : row.isDay === true ? 'mdi:weather-sunny' : 'mdi:cloud-outline';
    const label = cloud >= 75 ? 'Cloudy' : cloud >= 25 ? 'Partly cloudy' : 'Mostly clear';
    return { icon, label: `${label} · ${Math.round(cloud)}% cloud cover`, color: cloud >= 75 ? CONDITION_COLORS.cloudy : cloud < 25 && row.isDay === true ? CONDITION_COLORS.sunny : CONDITION_COLORS.partly, basis: 'cloud-cover' };
  }
  return { icon: 'mdi:help-circle-outline', label: 'Conditions unavailable', color: null, basis: 'unavailable' };
}

// A daily glyph summarizes the majority of qualified daylight periods, not
// the largest daily hazard or the 24-hour mean. These are display thresholds,
// not precipitation probabilities, source condition codes or skill claims.
function dailyCondition(row) {
  let hours = row.hours;
  let remainingWindow = false;
  if (row.precipitationScope === 'remaining') {
    const from = Date.parse(row.precipitationFromAt), through = Date.parse(row.precipitationThroughAt);
    remainingWindow = Number.isFinite(from) && Number.isFinite(through) && through > from;
    hours = remainingWindow
      ? hours.filter(h => Date.parse(h.at) > from && Date.parse(h.at) <= through) : [];
  }
  const daylight = hours.filter(h => h.isDay === true);
  const cloudValid = h => finite(h.cloudPct) && h.cloudPct >= 0 && h.cloudPct <= 100;
  const bucket = cloud => cloud < 25 ? 'sunny' : cloud >= 75 ? 'cloudy' : 'partly';
  const cloudsKnown = daylight.length > 0 && daylight.every(cloudValid);
  const clouds = cloudsKnown ? daylight.map(h => h.cloudPct) : [];
  const majority = values => ['sunny', 'cloudy', 'partly', 'wet'].find(value => values.filter(v => v === value).length > values.length / 2);
  const cloudWinner = cloudsKnown ? majority(clouds.map(bucket)) ?? 'partly' : null;
  const cloudPct = cloudWinner ? {sunny: 0, cloudy: 100, partly: 50}[cloudWinner] : row.cloudPct;
  const sky = forecastCondition({cloudPct, isDay: true});
  if (cloudsKnown) sky.label = `${cloudWinner === 'sunny' ? 'Mostly sunny' : cloudWinner === 'cloudy' ? 'Mostly cloudy' : 'Partly cloudy'} · predominant daylight sky`;
  const instants = daylight.map(h => Date.parse(h.at));
  const complete = daylight.length >= (remainingWindow ? 1 : 4) && hours.every(h => typeof h.isDay === 'boolean')
    && daylight.every(h => finite(h.precipIn) && h.precipIn >= 0)
    && instants.every((at, i) => Number.isFinite(at) && (!i || at - instants[i-1] === 3600000));
  if (!complete) {
    const fallback = sky.basis === 'unavailable' ? forecastCondition({...row, hours: undefined}) : sky;
    return {...fallback, label: `${fallback.label} · precipitation timing unavailable`};
  }
  const depths = daylight.map(h => h.precipIn * 25.4);
  const total = depths.reduce((sum, depth) => sum + depth, 0);
  const wet = depths.map(depth => depth + 1e-9 >= 0.1);
  if (total + 1e-9 >= 1 && cloudsKnown) {
    const conditions = daylight.map((h, i) => wet[i] ? 'wet' : bucket(h.cloudPct));
    const winner = majority(conditions);
    if (winner === 'wet') return {icon: 'mdi:weather-rainy', label: 'Precipitation through most daylight periods · type unspecified', color: CONDITION_COLORS.rain, basis: 'daylight-precipitation'};
    if (!winner && wet.filter(Boolean).length >= daylight.length / 4) return {icon: 'mdi:weather-partly-rainy', label: 'Mixed sky and precipitation during daylight · type unspecified', color: CONDITION_COLORS.rain, basis: 'daylight-mixed'};
    if (winner) {
      const condition = forecastCondition({cloudPct: {sunny: 0, cloudy: 100, partly: 50}[winner], isDay: true});
      condition.label = `${winner === 'sunny' ? 'Mostly sunny' : winner === 'cloudy' ? 'Mostly cloudy' : 'Partly cloudy'} · predominant daylight conditions; brief precipitation`;
      return condition;
    }
  }
  if (total + 1e-9 >= 1 && wet.filter(Boolean).length > daylight.length / 2) return {icon: 'mdi:weather-rainy', label: 'Precipitation through most daylight periods · type unspecified', color: CONDITION_COLORS.rain, basis: 'daylight-precipitation'};
  const dailyDepth = finite(row.precipSumIn) ? row.precipSumIn * 25.4 : null;
  const note = dailyDepth >= 1 && total < dailyDepth / 2 ? 'precipitation mainly outside daylight'
    : total > 0 ? 'brief/light precipitation' : '';
  return {...sky, label: note ? `${sky.label} · ${note}` : sky.label};
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
