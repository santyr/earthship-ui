"""Optional gunicorn entry point; legacy weather:app remains unchanged on disk.

Deploy beside the installed weather.py. Existing service does not use this module
until explicitly switched; collection additionally requires explicit enable/policy.
"""
from weather import app
from weather_temperature_config import configure_temperature_receiver

temperature_evidence_collector = configure_temperature_receiver(app)
