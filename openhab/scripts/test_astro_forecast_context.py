from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from astro_forecast_context import validate, optional_context

ORIGIN = datetime(2026, 9, 30, 12, 40, tzinfo=timezone.utc)
SITE = dict(latitude=38.3739919, longitude=-105.7744609, timezone_name='America/Denver')


def context():
    days = []
    for i in range(10):
        base = ORIGIN.replace(hour=6, minute=0) + timedelta(days=i)
        event = lambda hours: (base + timedelta(hours=hours)).isoformat()
        days.append({'day': base.date().isoformat(), 'sunriseAt': event(6.95),
            'daylightStartAt': event(7), 'sunsetAt': event(19), 'nextSunriseAt': event(30.95),
            'daylightSeconds': 43200, 'sunsetToNextSunriseSeconds': 43020,
            'noonElevationDegrees': 50.0, 'noonAzimuthDegrees': 180.0,
            'noonReferenceRadiationWm2': 700.0})
    return {'version': 1, 'schema': 'astro-future-solar-context/v1', 'sourceThing': 'astro:sun:local',
            'calculationVersion': 'openhab-astro-5.2.1', 'timezone': 'America/Denver',
            'geolocation': '38.3739919,-105.7744609', 'recordedAt': '2026-09-30T06:10:00Z',
            'validUntil': '2026-10-01T06:00:00Z', 'days': days}


def test_valid_context_retains_today_and_tomorrow_and_exact_origin_digest():
    value = context(); before = deepcopy(value); raw = json.dumps(value)
    result = validate(raw, origin=ORIGIN, **SITE)
    assert result['today'] == value['days'][0] and result['tomorrow'] == value['days'][1]
    assert len(result['sourceSha256']) == 64 and value == before


@pytest.mark.parametrize('damage', ['future', 'expired', 'site', 'zone', 'version', 'source',
                                   'bool', 'interval', 'adjacent', 'reorder', 'duplicate', 'extra', 'nan'])
def test_invalid_context_is_refused(damage):
    value = context()
    if damage == 'future': value['recordedAt'] = (ORIGIN + timedelta(seconds=1)).isoformat()
    elif damage == 'expired': value['validUntil'] = ORIGIN.isoformat()
    elif damage == 'site': value['geolocation'] = '38.3739919,-105'
    elif damage == 'zone': value['timezone'] = 'UTC'
    elif damage == 'version': value['calculationVersion'] = 'openhab-astro-5.3.0'
    elif damage == 'source': value['sourceThing'] = 'astro:sun:other'
    elif damage == 'bool': value['days'][0]['daylightSeconds'] = True
    elif damage == 'interval': value['days'][0]['daylightSeconds'] += 1
    elif damage == 'adjacent': value['days'][0]['nextSunriseAt'] = value['days'][1]['daylightStartAt']
    elif damage == 'reorder': value['days'].reverse()
    elif damage == 'extra': value['private'] = 'not allowed'
    elif damage == 'nan': value['days'][0]['noonElevationDegrees'] = float('nan')
    raw = json.dumps(value)
    if damage == 'duplicate': raw = raw[:-1] + ', "version": 1}'
    with pytest.raises(ValueError): validate(raw, origin=ORIGIN, **SITE)


def test_live_item_update_must_already_exist_at_issue():
    item = {'state': json.dumps(context()), 'lastStateUpdate': int(ORIGIN.timestamp()*1000) - 1}
    assert optional_context(lambda _: item, origin=ORIGIN, **SITE) is not None
    item['lastStateUpdate'] += 2
    assert optional_context(lambda _: item, origin=ORIGIN, **SITE) is None
    del item['lastStateUpdate']
    assert optional_context(lambda _: item, origin=ORIGIN, **SITE) is None


@pytest.mark.parametrize('first_day,expiry_hours', [('2026-03-08', 23), ('2026-11-01', 25)])
def test_local_midnight_expiry_and_future_day_events_across_dst(first_day, expiry_hours):
    from zoneinfo import ZoneInfo
    zone = ZoneInfo('America/Denver')
    first = datetime.fromisoformat(first_day).replace(tzinfo=zone)
    value = context()
    value['recordedAt'] = first.astimezone(timezone.utc).isoformat()
    expires = (first + timedelta(days=1)).astimezone(timezone.utc)
    value['validUntil'] = expires.isoformat()
    for index, row in enumerate(value['days']):
        at = first + timedelta(days=index)
        rise = (at + timedelta(hours=7)).astimezone(timezone.utc)
        start = rise + timedelta(minutes=3)
        sunset = (at + timedelta(hours=19)).astimezone(timezone.utc)
        next_rise = (at + timedelta(days=1, hours=7)).astimezone(timezone.utc)
        row.update(day=at.date().isoformat(), sunriseAt=rise.isoformat(),
            daylightStartAt=start.isoformat(), sunsetAt=sunset.isoformat(),
            nextSunriseAt=next_rise.isoformat(), daylightSeconds=(sunset-start).total_seconds(),
            sunsetToNextSunriseSeconds=(next_rise-sunset).total_seconds())
    origin = first.astimezone(timezone.utc) + timedelta(hours=1)
    assert (expires-first.astimezone(timezone.utc)).total_seconds() == expiry_hours * 3600
    assert validate(json.dumps(value), origin=origin, **SITE) is not None
