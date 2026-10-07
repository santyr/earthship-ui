"""Active qualification cannot extrapolate beyond supported thermal regimes."""
from datetime import timedelta
import json

import pytest

from test_thermal_release import inputs, NOW
from test_thermal_release_runtime import release_case
from thermal_model import release


def rows(mode='warm'):
    return [dict(at=NOW+timedelta(hours=hour), tempF=50, radiationWm2=0,
        windMph=0, weatherCode=0, mode=mode) for hour in range(3)]


def test_warm_only_qualification_does_not_authorize_current_winter(tmp_path, monkeypatch):
    thermal, args, _, now = release_case(tmp_path, monkeypatch)
    monkeypatch.setattr(thermal, '_forecast_rows', lambda *_: rows('winter'))
    sent = []
    assert thermal._release(args, now, put_state=lambda *values: sent.append(values),
        decision_clock=lambda: now, qualification_clock=lambda: now) == 1
    assert json.loads(sent[0][1])['status'] == 'unavailable'


@pytest.mark.parametrize('mode,expected', [('warm', ['warm']), ('winter', ['winter']),
    ('spring', ['shoulder']), ('fall_charge', ['shoulder'])])
def test_regime_mapping_uses_original_modes(mode, expected, monkeypatch):
    shadow = inputs(monkeypatch)['shadow']
    assert release.forecast_regimes(rows(mode), shadow) == expected


def test_intra_hour_transition_is_covered_even_between_output_points(monkeypatch):
    shadow = inputs(monkeypatch)['shadow']; forcing = rows()
    timeline = [(NOW, 'warm'), (NOW+timedelta(minutes=30), 'winter')]
    for row in forcing: row['_modeTimeline'] = timeline
    assert release.forecast_regimes(forcing, shadow) == ['warm', 'winter']


def test_future_transition_outside_actual_trajectory_does_not_change_coverage(monkeypatch):
    shadow = inputs(monkeypatch)['shadow']; forcing = rows()
    timeline = [(NOW, 'warm'), (NOW+timedelta(hours=2), 'winter')]
    for row in forcing: row['_modeTimeline'] = timeline
    assert release.forecast_regimes(forcing, shadow) == ['warm']


@pytest.mark.parametrize('damage', ['missing', 'uncovered', 'unknown', 'transition'])
def test_active_builder_refuses_unqualified_current_regime(monkeypatch, damage):
    data = inputs(monkeypatch)
    forcing = rows('winter' if damage == 'uncovered' else 'warm')
    if damage == 'unknown': forcing[0]['mode'] = 'unknown'
    elif damage == 'transition':
        for row in forcing: row['_modeTimeline'] = [(NOW, 'warm'), (NOW+timedelta(minutes=30), 'winter')]
    data['forecast_rows'] = None if damage == 'missing' else forcing
    output = release.build_release_output(**data)
    assert output['status'] == 'unavailable'
    assert output['release']['forecastQualified'] is False


def test_qualified_warm_trajectory_keeps_forecast_active(monkeypatch):
    data = inputs(monkeypatch); data['forecast_rows'] = rows()
    assert release.build_release_output(**data)['status'] == 'forecast_active'


def test_unqualified_shadow_remains_diagnostic_outside_release_regimes(monkeypatch):
    data = inputs(monkeypatch, skill=False); data['forecast_rows'] = rows('winter')
    output = release.build_release_output(**data)
    assert output['status'] == 'shadow'
    assert output['confidence']['grade'] == 'low'
    assert output['release']['forecastQualified'] is False
