from copy import deepcopy
from datetime import date, datetime, time, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest

spec = spec_from_file_location('astro_actions_qualifier', Path(__file__).with_name('qualify-astro-forecast-actions.py'))
q = module_from_spec(spec); sys.modules[spec.name] = q; spec.loader.exec_module(q)


def fixtures():
    rows = []
    for day in q.DAYS:
        start = datetime.combine(date.fromisoformat(day), time(6), q.ZONE)
        duration = 10 if day == '2026-12-21' else 14 if day == '2026-06-21' else 12
        end = start + timedelta(hours=duration)
        rows.append({'day': day, 'daylightStart': start.isoformat(),
                     'daylightEnd': end.isoformat(),
                     'sunriseStart': (start - timedelta(minutes=3)).isoformat(),
                     'sunriseEnd': start.isoformat(), 'sunsetStart': end.isoformat(),
                     'sunsetEnd': (end + timedelta(minutes=3)).isoformat(),
                     'noonElevation': '50.0 °', 'noonAzimuth': '175.0 °',
                     'noonRadiation': '800.0 W/m²', 'midnightRadiation': '0.0 W/m²'})
    return rows


def test_exact_dates_units_and_daylight_definition_pass_without_mutation():
    rows = fixtures(); before = deepcopy(rows)
    result = q.validate(rows)
    assert rows == before
    assert len(result) == 7
    assert result[0]['daylight_seconds'] == 43200
    assert result[-1]['daylight_seconds'] == 36000


@pytest.mark.parametrize('damage', ['wrong_day', 'missing', 'extra', 'no_zone',
                                   'bad_unit', 'nan', 'radiation_at_night',
                                   'boundary', 'reversed_seasons', 'solar_angle'])
def test_malformed_or_semantically_different_action_results_refused(damage):
    rows = fixtures()
    if damage == 'wrong_day': rows[0]['day'] = '2026-10-01'
    elif damage == 'missing': rows.pop()
    elif damage == 'extra': rows[0]['new_field'] = 'ignored?'
    elif damage == 'no_zone': rows[0]['daylightStart'] = '2026-09-30T06:00:00'
    elif damage == 'bad_unit': rows[0]['noonElevation'] = '0.8 rad'
    elif damage == 'nan': rows[0]['noonRadiation'] = 'NaN W/m²'
    elif damage == 'radiation_at_night': rows[0]['midnightRadiation'] = '1.0 W/m²'
    elif damage == 'boundary': rows[0]['daylightStart'] = rows[0]['sunriseStart']
    elif damage == 'solar_angle': rows[0]['noonAzimuth'] = '370.0 °'
    else:
        summer = next(row for row in rows if row['day'] == '2026-06-21')
        winter = next(row for row in rows if row['day'] == '2026-12-21')
        for row, hours in ((summer, 10), (winter, 14)):
            end = datetime.fromisoformat(row['sunriseEnd']) + timedelta(hours=hours)
            row['daylightEnd'] = row['sunsetStart'] = end.isoformat()
            row['sunsetEnd'] = (end + timedelta(minutes=3)).isoformat()
    with pytest.raises(ValueError): q.validate(rows)


def test_fixture_has_no_actuator_or_production_authority():
    source = q.fixture_source()
    assert q.THING in source and q.ITEM in source
    assert 'astro:sun:local' not in source and 'sendCommand' not in source
    assert 'triggers: []' in source
    assert all(name in source for name in ('getEventTime', 'getElevation', 'getAzimuth', 'getTotalRadiation'))


def test_file_rule_wait_survives_missing_registration_but_requires_idle():
    def missing(*_): raise RuntimeError('HTTP failure output withheld')
    assert q.ready_rule(missing) is None
    rule = {'uid': q.RULE, 'editable': False,
            'status': {'status': 'IDLE', 'statusDetail': 'NONE'}}
    assert q.ready_rule(lambda *_: rule) == rule
    for changed in ({**rule, 'editable': True}, {**rule, 'uid': 'other'},
                    {**rule, 'status': {'status': 'UNINITIALIZED', 'statusDetail': 'HANDLER_MISSING_ERROR'}}):
        assert q.ready_rule(lambda *_: changed) is None
