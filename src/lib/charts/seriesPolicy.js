const FIVE_MINUTES_MS = 5 * 60 * 1_000;
const ONE_MINUTE_MS = 60 * 1_000;

const TEMPERATURE_UNITS = ['', '°F', '°C'];
const PERCENT_UNITS = ['', '%'];

const SERIES = new Map([
  ['AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', { expectedCadenceMs: FIVE_MINUTES_MS, allowedUnits: TEMPERATURE_UNITS }],
  ['AmbientWeatherWS2902A_IndoorSensor_Temperature', { expectedCadenceMs: FIVE_MINUTES_MS, allowedUnits: TEMPERATURE_UNITS }],
  ['AmbientWeatherWS2902A_WH31E_193_Temperature', { expectedCadenceMs: FIVE_MINUTES_MS, allowedUnits: TEMPERATURE_UNITS }],
  ['Shelly_HT1_Indoor_Temperature', { expectedCadenceMs: FIVE_MINUTES_MS, allowedUnits: TEMPERATURE_UNITS }],
  ['Forecast_Temp', { expectedCadenceMs: FIVE_MINUTES_MS, allowedUnits: TEMPERATURE_UNITS, domain: 'forecast' }],
  ['AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative', { expectedCadenceMs: FIVE_MINUTES_MS, allowedUnits: ['', 'inHg', 'hPa', 'mbar'] }],
  ['AmbientWeatherWS2902A_WindSpeed', { expectedCadenceMs: ONE_MINUTE_MS, allowedUnits: ['', 'mph', 'km/h', 'm/s'] }],
  ['AmbientWeatherWS2902A_WindGust', { expectedCadenceMs: ONE_MINUTE_MS, allowedUnits: ['', 'mph', 'km/h', 'm/s'] }],
  ['AmbientWeatherWS2902A_RainFallDay', { expectedCadenceMs: FIVE_MINUTES_MS, allowedUnits: ['', 'in', '″', 'mm'] }],
  ['MPPT60_PV_Power', { expectedCadenceMs: FIVE_MINUTES_MS, allowedUnits: ['', 'W', 'kW'] }],
  ['BMS_SOC', { expectedCadenceMs: FIVE_MINUTES_MS, allowedUnits: PERCENT_UNITS }],
  ['Predicted_SoC_Trough_Tomorrow', { expectedCadenceMs: FIVE_MINUTES_MS, allowedUnits: PERCENT_UNITS }],
  ['BTC_USD_Price', { expectedCadenceMs: FIVE_MINUTES_MS, allowedUnits: ['', 'USD', '$'] }],
]);

export function getSeriesPolicy(seriesOrName) {
  const name = typeof seriesOrName === 'string' ? seriesOrName : seriesOrName?.name;
  const policy = SERIES.get(name);
  return {
    smoothing: 'none',
    domain: policy?.domain || 'history',
    expectedCadenceMs: policy?.expectedCadenceMs || FIVE_MINUTES_MS,
    allowedUnits: [...(policy?.allowedUnits || [''])],
  };
}
