"""Reviewed Gunicorn extension entry point; legacy weather:app is unchanged.

Rain receipt capture is explicitly released here because the system service's
root-owned drop-in is not writable by the deployment user. A systemd override
can still set WEATHER_RAIN_EVIDENCE_ENABLE=0 for an immediate no-code disable
at the next worker reload. Bad/missing private policy never breaks weather.py.
"""
import os

from weather import app
from weather_temperature_config import configure_temperature_receiver
from weather_rain_config import configure_rain_receiver
from weather_radiation_config import configure_radiation_receiver
from weather_station_ingestion import configure_station_ingestion

temperature_evidence_collector = configure_temperature_receiver(app)
rain_evidence_collector = configure_rain_receiver(app, {
    'WEATHER_RAIN_EVIDENCE_ENABLE': os.environ.get('WEATHER_RAIN_EVIDENCE_ENABLE', '1'),
    'WEATHER_RAIN_EVIDENCE_POLICY': os.environ.get(
        'WEATHER_RAIN_EVIDENCE_POLICY',
        '/home/sat/.config/hex/weather-rain-policy.json'),
})
# Unlike the already-released rain path, radiation has no implicit activation
# or policy fallback. It must be explicitly configured after deployment gates.
radiation_evidence_collector = configure_radiation_receiver(app)

# Explicit release activation after all original raw-receipt hooks. The generic
# adapter remains default-off. Set this flag to 0 before reload for rollback.
# Site timezone is an installed station setting, not the web client's timezone.
station_ingestion = configure_station_ingestion(app, {
    'WEATHER_STATION_INGESTION_ENABLE': os.environ.get('WEATHER_STATION_INGESTION_ENABLE', '1'),
    'WEATHER_STATION_TIMEZONE': os.environ.get('WEATHER_STATION_TIMEZONE', 'America/Denver'),
    'WEATHER_STATION_RAIN_TOTALS': os.environ.get('WEATHER_STATION_RAIN_TOTALS', '/home/sat/.config/hex/weather-station-rain-totals.json'),
})
