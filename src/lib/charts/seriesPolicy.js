const FIVE_MINUTES_MS = 5 * 60 * 1_000;
const ONE_MINUTE_MS = 60 * 1_000;

const CONTINUOUS_SERIES = new Map([
  ['AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', FIVE_MINUTES_MS],
  ['AmbientWeatherWS2902A_IndoorSensor_Temperature', FIVE_MINUTES_MS],
  ['AmbientWeatherWS2902A_WH31E_193_Temperature', FIVE_MINUTES_MS],
  ['Shelly_HT1_Indoor_Temperature', FIVE_MINUTES_MS],
  ['AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative', FIVE_MINUTES_MS],
  ['AmbientWeatherWS2902A_WindSpeed', ONE_MINUTE_MS],
  ['MPPT60_PV_Power', FIVE_MINUTES_MS],
]);

export function getSeriesPolicy(seriesOrName) {
  const name = typeof seriesOrName === 'string' ? seriesOrName : seriesOrName?.name;
  const expectedCadenceMs = CONTINUOUS_SERIES.get(name);
  if (expectedCadenceMs) {
    return { smoothing: 'median3-ema', alpha: 0.25, expectedCadenceMs };
  }
  return { smoothing: 'none', alpha: 0.25, expectedCadenceMs: FIVE_MINUTES_MS };
}
