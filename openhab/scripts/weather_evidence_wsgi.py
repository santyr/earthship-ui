"""Optional gunicorn entry point; legacy weather:app remains unchanged on disk.

Deploy beside the installed weather.py. Existing service does not use this module
until explicitly switched; collection additionally requires explicit enable/policy.
"""
from weather import app
from weather_temperature_config import configure_temperature_receiver
from weather_rain_config import configure_rain_receiver

temperature_evidence_collector = configure_temperature_receiver(app)
rain_evidence_collector = configure_rain_receiver(app)
