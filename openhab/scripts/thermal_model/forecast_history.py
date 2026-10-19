"""Google-only original weather verification and neutral hourly bracketing.

No archived metric selector, forecast database or retired-provider receipt
adapter is available. Verification reconstructs the retained Google response.
"""
from datetime import datetime,timedelta,timezone

HOUR=timedelta(hours=1)
RUNTIME_PATHS=frozenset({
    'thermal_model/forecast_history.py','weather_learning/native_forecast.py',
    'weather_learning/config.py','weather_learning/contracts.py',
    'weather_learning/evidence.py','weather_learning/features.py',
    'weather_learning/weathernext_ee.py','weather_learning/normalize.py',
    'weather_learning/transport.py',
})


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('aware forecast timestamp required')
    return value.astimezone(timezone.utc)


def _window(origin, horizon_hours):
    origin = _utc(origin)
    if type(horizon_hours) is not int or not 1 <= horizon_hours <= 72:
        raise ValueError('forecast horizon must be 1 through 72 hours')
    first = origin.replace(minute=0, second=0, microsecond=0)
    target = origin + timedelta(hours=horizon_hours)
    last = target.replace(minute=0, second=0, microsecond=0)
    if last < target:
        last += HOUR
    return origin, tuple(first + i * HOUR for i in range(int((last - first) / HOUR) + 1))


def verify_origin_forecast_receipts(forecast):
    """Reconstruct the exact original Google capsule without source I/O."""
    from weather_learning.native_forecast import validate_native_forecast
    return validate_native_forecast(forecast)
