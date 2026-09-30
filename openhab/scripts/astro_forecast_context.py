"""Validate optional as-issued Astro geometry; never change a prediction."""

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from zoneinfo import ZoneInfo

ITEM = 'Astro_Forecast_Context_JSON'
MAX_BYTES = 16384
ROOT_FIELDS = {'version', 'schema', 'sourceThing', 'calculationVersion',
               'timezone', 'geolocation', 'recordedAt', 'validUntil', 'days'}
DAY_FIELDS = {'day', 'sunriseAt', 'daylightStartAt', 'sunsetAt', 'nextSunriseAt',
              'daylightSeconds', 'sunsetToNextSunriseSeconds', 'noonElevationDegrees',
              'noonAzimuthDegrees', 'noonReferenceRadiationWm2'}


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value: raise ValueError('duplicate solar field')
        value[key] = item
    return value


def _instant(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError('bounded solar instant required')
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.utcoffset() is None: raise ValueError('aware solar instant required')
    return at.astimezone(timezone.utc)


def validate(raw, *, origin, latitude, longitude, timezone_name):
    if (not isinstance(raw, str) or not 1 <= len(raw.encode()) <= MAX_BYTES
            or not isinstance(origin, datetime) or origin.utcoffset() is None):
        raise ValueError('bounded solar context and aware origin required')
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (latitude, longitude)):
        raise ValueError('finite issue site required')
    value = json.loads(raw, object_pairs_hook=_unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite solar JSON')))
    if (not isinstance(value, dict) or set(value) != ROOT_FIELDS
            or type(value['version']) is not int or value['version'] != 1
            or value['schema'] != 'astro-future-solar-context/v1'
            or value['sourceThing'] != 'astro:sun:local'
            or value['calculationVersion'] != 'openhab-astro-5.2.1'
            or value['timezone'] != timezone_name):
        raise ValueError('exact solar context authority required')
    if not isinstance(value['geolocation'], str) or len(value['geolocation']) > 128:
        raise ValueError('solar site unavailable')
    coordinates = [float(part) for part in value['geolocation'].split(',')]
    if (len(coordinates) not in (2, 3) or not all(math.isfinite(v) for v in coordinates)
            or not -90 <= coordinates[0] <= 90 or not -180 <= coordinates[1] <= 180
            or abs(coordinates[0] - latitude) > 1e-9 or abs(coordinates[1] - longitude) > 1e-9):
        raise ValueError('solar context site mismatch')
    zone = ZoneInfo(timezone_name)
    recorded, expires = map(_instant, (value['recordedAt'], value['validUntil']))
    first = recorded.astimezone(zone).date()
    expected_expiry = datetime.combine(first + timedelta(days=1), datetime.min.time(), zone)
    if not recorded <= origin < expires or expires != expected_expiry:
        raise ValueError('solar context unavailable at issue')
    days = value['days']
    if not isinstance(days, list) or len(days) != 10:
        raise ValueError('exact ten-day solar context required')
    for index, row in enumerate(days):
        day = first + timedelta(days=index)
        if not isinstance(row, dict) or set(row) != DAY_FIELDS or row['day'] != day.isoformat():
            raise ValueError('ordered solar days required')
        rise, start, sunset, next_rise = map(_instant, (row['sunriseAt'],
            row['daylightStartAt'], row['sunsetAt'], row['nextSunriseAt']))
        if (not rise < start < sunset < next_rise
                or any(at.astimezone(zone).date() != day for at in (rise, start, sunset))
                or next_rise.astimezone(zone).date() != day + timedelta(days=1)):
            raise ValueError('solar event date/order mismatch')
        for key, lo, hi in (('daylightSeconds', 0, 86400),
                            ('sunsetToNextSunriseSeconds', 0, 86400),
                            ('noonElevationDegrees', -90, 90), ('noonAzimuthDegrees', 0, 360),
                            ('noonReferenceRadiationWm2', 0, 1500)):
            number = row[key]
            if type(number) not in (int, float) or not math.isfinite(number) or not lo <= number <= hi:
                raise ValueError('finite solar feature required')
        if (abs(row['daylightSeconds'] - (sunset - start).total_seconds()) > 1e-6
                or abs(row['sunsetToNextSunriseSeconds'] - (next_rise - sunset).total_seconds()) > 1e-6
                or (index and days[index - 1]['nextSunriseAt'] != row['sunriseAt'])):
            raise ValueError('solar interval consistency mismatch')
    return {'version': 1, 'sourceSha256': sha256(raw.encode()).hexdigest(),
            'recordedAt': value['recordedAt'], 'today': days[0], 'tomorrow': days[1]}


def optional_context(get, *, origin, latitude, longitude, timezone_name):
    try:
        item = get('/items/' + ITEM)
        persisted = item.get('lastStateUpdate')
        if type(persisted) is not int or not 0 <= persisted <= origin.timestamp() * 1000:
            return None
        return validate(item['state'], origin=origin,
                        latitude=latitude, longitude=longitude, timezone_name=timezone_name)
    except Exception:
        return None  # Optional diagnostic input; never alter the forecast fallback.
