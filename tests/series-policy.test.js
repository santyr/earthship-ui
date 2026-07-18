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
  ])('keeps main-chart telemetry unsmoothed: %s', (name) => {
    expect(getSeriesPolicy(name).smoothing).toBe('none');
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

  it('defines exact history versus forecast domains', () => {
    expect(getSeriesPolicy('BMS_SOC').domain).toBe('history');
    expect(getSeriesPolicy('Forecast_Temp').domain).toBe('forecast');
    expect(getSeriesPolicy('Predicted_SoC_Trough_Tomorrow').domain).toBe('history');
  });

  it('defines strict unit allowlists for every supported numeric family', () => {
    expect(getSeriesPolicy('AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature').allowedUnits)
      .toEqual(expect.arrayContaining(['', '°F']));
    expect(getSeriesPolicy('BMS_SOC').allowedUnits).toEqual(expect.arrayContaining(['', '%']));
    expect(getSeriesPolicy('MPPT60_PV_Power').allowedUnits).toEqual(expect.arrayContaining(['', 'W']));
    expect(getSeriesPolicy('unknown-item').allowedUnits).toEqual(['']);
  });
});
