#!/usr/bin/env python3
"""Rehearse four daily OpenMeteo file Items/links in a networkless OpenHAB."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('forecast_provider',
    ROOT / 'scripts/qualify-openmeteo-forecast-temperature-provider.py')
provider = module_from_spec(spec)
spec.loader.exec_module(provider)

provider.SOURCE = ROOT / 'openhab/file-config/items/openmeteo-forecast-daily.items'
provider.CONTAINER_LABEL = 'hex.forecast.daily.qualification'
provider.CHANNELS = {
    'Forecast_Daily_PrecipSum': 'openmeteo:forecast:local:site:forecastDaily#precipitation-sum',
    'Forecast_Daily_PrecipProbMax': 'openmeteo:forecast:local:site:forecastDaily#precipitation-probability-max',
    'Forecast_Daily_WeatherCode': 'openmeteo:forecast:local:site:forecastDaily#weather-code',
    'Forecast_Daily_UVIndex': 'openmeteo:forecast:local:site:forecastDaily#uv-index',
}
provider.TYPES = {
    'Forecast_Daily_PrecipSum': 'Number:Length',
    'Forecast_Daily_PrecipProbMax': 'Number:Dimensionless',
    'Forecast_Daily_WeatherCode': 'Number',
    'Forecast_Daily_UVIndex': 'Number',
}

if __name__ == '__main__':
    provider.main()
