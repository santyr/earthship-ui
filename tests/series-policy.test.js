import { describe, expect, it } from 'vitest';
import { getSeriesPolicy } from '../src/lib/charts/seriesPolicy.js';

describe('chart series policy', () => {
  it.each([
    'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature',
    'AmbientWeatherWS2902A_IndoorSensor_Temperature',
    'AmbientWeatherWS2902A_WH31E_193_Temperature',
    'Shelly_HT1_Indoor_Temperature',
    'AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative',
    'AmbientWeatherWS2902A_WindSpeed',
    'MPPT60_PV_Power',
  ])('smooths supported continuous telemetry: %s', (name) => {
    expect(getSeriesPolicy(name).smoothing).toBe('median3-ema');
    expect(getSeriesPolicy(name).alpha).toBe(0.25);
  });

  it.each([
    'BMS_SOC',
    'AmbientWeatherWS2902A_WindGust',
    'AmbientWeatherWS2902A_RainFallDay',
    'Forecast_Temp',
    'Predicted_Curtailment_Hours',
    'SouthOutlet_Outlet2_Switch',
    'Thermal_Advisory',
    'BTC_USD_Price',
  ])('does not smooth operational, status, forecast, or non-registered data: %s', (name) => {
    expect(getSeriesPolicy(name).smoothing).toBe('none');
  });
});
