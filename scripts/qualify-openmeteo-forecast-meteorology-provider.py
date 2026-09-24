#!/usr/bin/env python3
"""Rehearse the three hourly meteorology Item/link providers in isolation.

This uses the same restored-registry, networkless OpenHAB provider/rollback
fixture as the temperature group. It does not qualify JDBC series behavior.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('forecast_provider',
    ROOT / 'scripts/qualify-openmeteo-forecast-temperature-provider.py')
provider = module_from_spec(spec)
spec.loader.exec_module(provider)

provider.SOURCE = ROOT / 'openhab/file-config/items/openmeteo-forecast-meteorology.items'
provider.CHANNELS = {
    'Forecast_Cloudiness': 'openmeteo:forecast:local:site:forecastHourly#cloudiness',
    'Forecast_Radiation': 'openmeteo:forecast:local:site:forecastHourly#shortwave-radiation',
    'Forecast_PrecipProb': 'openmeteo:forecast:local:site:forecastHourly#precipitation-probability',
}
provider.TYPES = {
    'Forecast_Cloudiness': 'Number:Dimensionless',
    'Forecast_Radiation': 'Number:Intensity',
    'Forecast_PrecipProb': 'Number:Dimensionless',
}

if __name__ == '__main__':
    provider.main()
