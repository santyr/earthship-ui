import { num } from '../openhab/values.js';

export const HOME_STATE_COLORS = Object.freeze({
  positive: '#22c55e',
  negative: '#ef4444',
  neutral: '#8b93a1',
  bitcoin: '#f7931a',
});

export const HOME_AQI_TEXT_COLOR = '#f8fafc';

export const HOME_AQI_COLORS = Object.freeze({
  unavailable: HOME_STATE_COLORS.neutral,
  good: '#22c55e',
  moderate: '#eab308',
  sensitive: '#f97316',
  unhealthy: '#ef4444',
  veryUnhealthy: '#a855f7',
  hazardous: '#991b1b',
  beyond: '#991b1b',
});

export const HOME_WIND_COLORS = Object.freeze({
  neutral: HOME_STATE_COLORS.neutral,
  green: '#4caf50',
  orange: '#ff9800',
  red: '#f44336',
});

export const HOME_UV_COLORS = Object.freeze({
  neutral: HOME_STATE_COLORS.neutral,
  green: '#4caf50',
  yellow: '#ffeb3b',
  orange: '#ff9800',
  red: '#f44336',
  purple: '#9c27b0',
});

// Shared unit-tolerant state parsing (openhab/values.js num()): accepts
// unit-suffixed QuantityType states ("12.3 mph", "-4.2 A") and scientific
// notation, returns null for NULL/UNDEF/'' and non-numeric-leading strings.
// Home previously used Number() here, which silently dropped unit-carrying
// states (wind gust history max showed "—", "-4.2 A" battery current showed
// "idle" while discharging).
function finiteNumber(value) {
  return num(value);
}

export function batteryPowerFlowPresentation(raw) {
  const number = finiteNumber(raw);
  if (number === null) return { text: '—', glyph: '', color: HOME_STATE_COLORS.neutral };
  if (number === 0) return { text: '0 W', glyph: '', color: HOME_STATE_COLORS.neutral };
  const magnitude = Math.round(Math.abs(number));
  return {
    text: `${number > 0 ? '+' : '−'}${magnitude} W`,
    glyph: number > 0 ? '▲' : '▼',
    color: number > 0 ? HOME_STATE_COLORS.positive : '#f59e0b',
  };
}

export function relativeAgeText(raw, nowMs = Date.now()) {
  if (!raw || raw === 'NULL' || raw === 'UNDEF') return '—';
  const eventMs = new Date(raw).getTime();
  const clockMs = Number(nowMs);
  if (!Number.isFinite(eventMs) || !Number.isFinite(clockMs)) return '—';
  const diffMs = clockMs - eventMs;
  if (diffMs < 0) return '—';
  const minutes = diffMs / 60_000;
  if (minutes < 60) return `${Math.round(minutes)} m ago`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.round(hours)} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export function localDayHistoryRange(now = new Date()) {
  if (!(now instanceof Date) || Number.isNaN(now.getTime())) return null;
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0, 0);
  return {
    starttime: start.toISOString(),
    endtime: now.toISOString(),
  };
}

export function maxHistoryValue(points) {
  if (!Array.isArray(points)) return null;
  const values = points
    .map((point) => finiteNumber(point?.state))
    .filter((value) => value !== null);
  return values.length ? Math.max(...values) : null;
}
export function formatGoatFeedings(raw) {
  const count = finiteNumber(raw);
  if (count === null || count < 0) return 'Feedings unavailable';
  const rounded = Math.round(count);
  return `${rounded} ${rounded === 1 ? 'feeding' : 'feedings'} today`;
}

export function createGoatFeederTracker() {
  return { initialized: false, previous: null };
}

export function advanceGoatFeederTracker(tracker, raw) {
  const normalized = String(raw ?? '').trim().toUpperCase();
  const known = normalized === 'ON' || normalized === 'OFF' ? normalized : null;
  if (!known) {
    return {
      tracker: { initialized: Boolean(tracker?.initialized), previous: null },
      activated: false,
    };
  }
  if (!tracker?.initialized) {
    return { tracker: { initialized: true, previous: known }, activated: false };
  }
  return {
    tracker: { initialized: true, previous: known },
    activated: tracker.previous === 'OFF' && known === 'ON',
  };
}
const DAY_MS = 86_400_000;
const JULIAN_UNIX_EPOCH = 2_440_587.5;
const SEASON_EVENTS = Object.freeze([
  ['spring equinox', [2451623.80984, 365242.37404, 0.05169, -0.00411, -0.00057]],
  ['summer solstice', [2451716.56767, 365241.62603, 0.00325, 0.00888, -0.00030]],
  ['autumn equinox', [2451810.21715, 365242.01767, -0.11575, 0.00337, 0.00078]],
  ['winter solstice', [2451900.05952, 365242.74049, -0.06223, -0.00823, 0.00032]],
]);

function seasonInstant(year, coefficients) {
  const y = (year - 2000) / 1000;
  const jde = coefficients.reduce((sum, coefficient, power) => sum + coefficient * y ** power, 0);
  return new Date((jde - JULIAN_UNIX_EPOCH) * DAY_MS);
}

function localDayStamp(date) {
  return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate());
}

export function nextSeasonEvent(now = new Date()) {
  if (!(now instanceof Date) || Number.isNaN(now.getTime())) return null;
  const year = now.getFullYear();
  if (year < 2000 || year > 3000) return null;
  const today = localDayStamp(now);
  const candidates = [year, year + 1]
    .flatMap((candidateYear) => SEASON_EVENTS.map(([name, coefficients]) => {
      if (candidateYear > 3000) return null;
      return {
        name,
        instant: seasonInstant(candidateYear, coefficients),
      };
    }).filter(Boolean))
    .map((event) => ({ ...event, day: localDayStamp(event.instant) }))
    .filter((event) => event.day >= today)
    .sort((a, b) => a.day - b.day);
  const next = candidates[0];
  if (!next) return null;
  const days = Math.round((next.day - today) / DAY_MS);
  return {
    name: next.name,
    days,
    label: days === 0
      ? `${next.name} today`
      : `${days} ${days === 1 ? 'day' : 'days'} to ${next.name}`,
    instant: next.instant,
  };

}
function signedStateColor(value, neutral) {
  const number = finiteNumber(value);
  if (number === null || number === 0) return neutral;
  return number > 0 ? HOME_STATE_COLORS.positive : HOME_STATE_COLORS.negative;
}

export function netStateColor(value) {
  return signedStateColor(value, HOME_STATE_COLORS.neutral);
}

export function bitcoinStateColor(value) {
  return signedStateColor(value, HOME_STATE_COLORS.bitcoin);
}

export function windSpeedColor(value) {
  const number = finiteNumber(value);
  if (number === null || number < 5) return HOME_WIND_COLORS.neutral;
  if (number < 15) return HOME_WIND_COLORS.green;
  if (number < 25) return HOME_WIND_COLORS.orange;
  return HOME_WIND_COLORS.red;
}

export function uvIndexColor(value) {
  const number = finiteNumber(value);
  if (number === null || number < 0) return HOME_UV_COLORS.neutral;
  if (number <= 2) return HOME_UV_COLORS.green;
  if (number <= 5) return HOME_UV_COLORS.yellow;
  if (number <= 7) return HOME_UV_COLORS.orange;
  if (number <= 10) return HOME_UV_COLORS.red;
  return HOME_UV_COLORS.purple;
}

export function indoorTemperatureIconColor(value) {
  const number = finiteNumber(value);
  if (number === null) return HOME_STATE_COLORS.neutral;
  if (number < 60) return '#3498db';
  if (number < 68) return '#00bcd4';
  if (number < 74) return '#4caf50';
  if (number < 80) return '#ff9800';
  return '#f44336';
}

export function outdoorTemperatureIconColor(value) {
  const number = finiteNumber(value);
  if (number === null) return HOME_STATE_COLORS.neutral;
  if (number < 32) return '#ab47bc';
  if (number < 50) return '#3498db';
  if (number < 65) return '#00bcd4';
  if (number < 75) return '#4caf50';
  if (number < 85) return '#ff9800';
  return '#f44336';
}

export function outdoorConditionIcon(value) {
  const normalized = value == null ? '' : String(value).trim();
  return normalized && normalized !== 'NULL' && normalized !== 'UNDEF'
    ? normalized
    : 'iconify:mdi:weather-partly-cloudy';
}

const CURRENT_AQI_NUMBER = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;

function unavailableCurrentAqi() {
  return {
    value: null,
    band: 'Unavailable',
    status: 'unavailable',
    accent: HOME_AQI_COLORS.unavailable,
    textColor: HOME_AQI_TEXT_COLOR,
  };
}

export function adaptCurrentAqi(raw) {
  const text = typeof raw === 'number' ? String(raw) : typeof raw === 'string' ? raw.trim() : '';
  if (!CURRENT_AQI_NUMBER.test(text)) return unavailableCurrentAqi();

  const numeric = Number(text);
  if (!Number.isFinite(numeric) || numeric < 0) return unavailableCurrentAqi();

  const value = Math.round(numeric);
  if (value <= 50) {
    return { value, band: 'Good', status: 'good', accent: HOME_AQI_COLORS.good, textColor: HOME_AQI_TEXT_COLOR };
  }
  if (value <= 100) {
    return { value, band: 'Moderate', status: 'moderate', accent: HOME_AQI_COLORS.moderate, textColor: HOME_AQI_TEXT_COLOR };
  }
  if (value <= 150) {
    return { value, band: 'Unhealthy for sensitive groups', status: 'unhealthy', accent: HOME_AQI_COLORS.sensitive, textColor: HOME_AQI_TEXT_COLOR };
  }
  if (value <= 200) {
    return { value, band: 'Unhealthy', status: 'unhealthy', accent: HOME_AQI_COLORS.unhealthy, textColor: HOME_AQI_TEXT_COLOR };
  }
  if (value <= 300) {
    return { value, band: 'Very unhealthy', status: 'critical', accent: HOME_AQI_COLORS.veryUnhealthy, textColor: HOME_AQI_TEXT_COLOR };
  }
  if (value <= 500) {
    return { value, band: 'Hazardous', status: 'critical', accent: HOME_AQI_COLORS.hazardous, textColor: HOME_AQI_TEXT_COLOR };
  }
  return { value, band: 'Beyond AQI / hazardous', status: 'critical', accent: HOME_AQI_COLORS.beyond, textColor: HOME_AQI_TEXT_COLOR };
}

export function aqiChipColor(value) {
  return adaptCurrentAqi(value).accent;
}

const RAIN_HARVEST_GALLONS_PER_INCH = 3500 * 0.623 * 0.8;

export function harvestedGallons(value) {
  const inches = finiteNumber(value);
  if (inches === null || inches < 0) return null;
  return Math.round(inches * RAIN_HARVEST_GALLONS_PER_INCH);
}

export function batteryDirectionState(chargingStatus, current) {
  const status = chargingStatus == null ? '' : String(chargingStatus).trim().toUpperCase();
  const amps = finiteNumber(current);
  if (status === 'ON' || (amps !== null && amps > 0)) {
    return { text: 'charging', glyph: '▲', color: HOME_STATE_COLORS.positive };
  }
  if (amps !== null && amps < 0) {
    return { text: 'discharging', glyph: '▼', color: '#f59e0b' };
  }
  if (status === 'OFF' || amps === 0) {
    return { text: 'idle', glyph: '●', color: HOME_STATE_COLORS.neutral };
  }
  return { text: 'unavailable', glyph: '—', color: HOME_STATE_COLORS.neutral };
}

function itemIcon(value, fallback) {
  const normalized = value == null ? '' : String(value).trim();
  return normalized && normalized !== 'NULL' && normalized !== 'UNDEF' ? normalized : fallback;
}

export function batteryIcon(value) {
  return itemIcon(value, 'iconify:mdi:battery');
}

export function greywaterState(value) {
  const state = value == null ? '' : String(value).trim().toUpperCase();
  if (state === 'ON') return { label: 'Running', color: '#3b82f6' };
  if (state === 'OFF') return { label: 'Idle', color: HOME_STATE_COLORS.neutral };
  return { label: 'Unavailable', color: HOME_STATE_COLORS.neutral };
}

export function pressurePresentation(value) {
  const trend = value == null ? '' : String(value).trim().toLowerCase();
  if (trend === 'falling') {
    return { icon: 'iconify:mdi:weather-lightning', color: '#ff5722', label: 'falling' };
  }
  if (trend === 'rising') {
    return { icon: 'iconify:mdi:gauge', color: '#2196f3', label: 'rising' };
  }
  if (trend === 'steady') {
    return { icon: 'iconify:mdi:gauge', color: HOME_STATE_COLORS.neutral, label: 'steady' };
  }
  return { icon: 'iconify:mdi:gauge', color: HOME_STATE_COLORS.neutral, label: '—' };
}

export function rainStateColor(value) {
  const inches = finiteNumber(value);
  return inches !== null && inches > 0 ? '#3b82f6' : HOME_STATE_COLORS.neutral;
}

export function rainRateChip(value) {
  const rate = finiteNumber(value);
  if (rate === null || rate <= 0) return null;
  const display = rate.toFixed(2).replace(/\.?0+$/, '');
  return `RAIN ${display} in/h`;
}

export function solarPvColor(value) {
  const watts = finiteNumber(value);
  if (watts === null || watts < 50) return HOME_STATE_COLORS.neutral;
  if (watts < 500) return '#ffc107';
  return '#ff9800';
}

export function curtailmentColor(value) {
  const hours = finiteNumber(value);
  return hours !== null && hours > 0 ? '#eab308' : HOME_STATE_COLORS.neutral;
}
