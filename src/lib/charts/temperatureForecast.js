import { parseForecast10Day } from '../weather/forecastDetail.js';
import { parseThermalModelResult } from '../thermal/modelResult.js';
import { colors } from '../ui/tokens.js';

export const OUTDOOR = 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature';
export const INDOOR = 'AmbientWeatherWS2902A_IndoorSensor_Temperature';

export function temperatureForecast(series, items, nowMs) {
  const outdoor = series.some(({ name }) => name === OUTDOOR);
  const indoor = series.some(({ name }) => name === INDOOR);
  if (!outdoor && !indoor) return null;
  const result = outdoor
    ? parseForecast10Day(items.Forecast_10Day_JSON, { nowMs })
    : parseThermalModelResult(items.Thermal_Model_JSON, nowMs);
  const status = outdoor ? result.status : result.state;
  const label = outdoor ? 'Outdoor forecast' : 'Indoor forecast · shadow model';
  const rows = outdoor
    ? result.days.flatMap((day) => day.hours.map((hour) => ({ time: hour.atMs, state: hour.tempF })))
    : result.trajectory.map((hour) => ({ time: hour.atMs, state: hour.hallwayF }));
  const points = status === 'ready' && result.generatedAtMs <= nowMs ? rows.filter((row) => (
    row.time >= nowMs && row.time <= nowMs + 24 * 3600000 && Number.isFinite(row.state)
  )) : [];
  return {
    source: { name: outdoor ? 'Outdoor_Hourly_Forecast' : 'Indoor_Thermal_Forecast',
      label, color: colors.forecast, dashedFromNow: true, forecastLabel: label, markers: [] },
    points,
    description: points.length ? `${label} · next 24h` : `${label} ${status === 'stale' ? 'stale' : 'unavailable'}`,
  };
}
