// Bind display and history identity to the already selected station product.
// A present but invalid v2 report must keep its unavailable absolute product.
export function pressureProduct(station, states) {
  const legacy = station.mode === 'legacy';
  return {
    item: legacy ? 'AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative' : 'WeatherStation_PressureAbsoluteV2',
    value: legacy ? states.AmbientWeatherWS2902A_WeatherDataWs2902a_PressureRelative : station.pressure.value,
    label: legacy ? 'Relative pressure' : 'Station pressure',
    chartTitle: legacy ? 'Relative pressure (legacy)' : 'Station pressure (absolute)',
  };
}
