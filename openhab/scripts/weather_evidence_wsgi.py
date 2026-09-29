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

temperature_evidence_collector = configure_temperature_receiver(app)
rain_evidence_collector = configure_rain_receiver(app, {
    'WEATHER_RAIN_EVIDENCE_ENABLE': os.environ.get('WEATHER_RAIN_EVIDENCE_ENABLE', '1'),
    'WEATHER_RAIN_EVIDENCE_POLICY': os.environ.get(
        'WEATHER_RAIN_EVIDENCE_POLICY',
        '/home/sat/.config/hex/weather-rain-policy.json'),
})
