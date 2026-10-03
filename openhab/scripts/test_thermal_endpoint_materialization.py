"""Daily origin selection must not allocate discarded rollout prefixes."""

from dataclasses import asdict, replace
from datetime import datetime, timezone

import pytest

import thermal_model.dynamics as dynamics
from test_thermal_dynamics import synthetic_2r2c_days


def eager_endpoints(prepared, steps):
    """Independent original eager implementation, including selection order."""
    ordered, valid, safe, confidences = prepared
    runs = [0] * len(ordered)
    for index in range(len(ordered) - 2, -1, -1):
        if ordered[index + 1].at - ordered[index].at == dynamics.STEP and safe[index + 1]:
            runs[index] = 1 + runs[index + 1]
    best = {}
    for index, origin in enumerate(ordered):
        if not valid[index] or runs[index] < steps:
            continue
        prefix = ordered[index + 1:index + steps + 1]
        endpoint = dynamics.RolloutEndpoint(
            origin, prefix, prefix[-1], min(confidences[index + 1:index + steps + 1])
        )
        day = origin.at.astimezone(dynamics.SITE_TIMEZONE).date()
        key = (-runs[index], origin.at)
        if day not in best or key < best[day][0]:
            best[day] = (key, endpoint)
    return tuple(value[1] for value in sorted(best.values(), key=lambda value: value[1].origin.at))


def test_only_selected_daily_endpoints_are_constructed(monkeypatch):
    rows, _ = synthetic_2r2c_days(5, 20261003)
    prepared = dynamics._prepare_endpoint_rows(rows, ())
    original = dynamics.RolloutEndpoint
    constructed = []

    def counted(*args, **kwargs):
        endpoint = original(*args, **kwargs)
        constructed.append(endpoint)
        return endpoint

    monkeypatch.setattr(dynamics, 'RolloutEndpoint', counted)
    selected = dynamics._eligible_daily_endpoints_from_prepared(prepared, 288)
    assert len(constructed) == len(selected)
    assert tuple(constructed) == selected


@pytest.mark.parametrize('steps', dynamics.IDENTIFICATION_HORIZON_STEPS)
@pytest.mark.parametrize('damage', ['none', 'gaps', 'invalid_actions', 'inactive_solar'])
def test_daily_endpoints_exactly_match_eager_reference(steps, damage):
    rows, _ = synthetic_2r2c_days(5, 71)
    # Exercise local midnight and the fall DST transition, with confidence minima
    # inside (not just at the end of) the selected prefixes.
    start = datetime(2026, 10, 31, 5, tzinfo=timezone.utc)
    rows = tuple(replace(row, at=start + index * dynamics.STEP,
                         action_confidence=(index % 17 + 1) / 17)
                 for index, row in enumerate(rows))
    inactive = ()
    if damage == 'gaps':
        rows = tuple(row for index, row in enumerate(rows) if index not in (50, 401, 799))
    elif damage == 'invalid_actions':
        rows = tuple(replace(row, vent_open=None) if index in (50, 401, 799) else row
                     for index, row in enumerate(rows))
    elif damage == 'inactive_solar':
        inactive = ('solar_outdoor',)
    prepared = dynamics._prepare_endpoint_rows(rows, inactive)
    expected = eager_endpoints(prepared, steps)
    actual = dynamics._eligible_daily_endpoints_from_prepared(prepared, steps)
    assert actual == expected
    for endpoint in actual:
        assert len(endpoint.forcings) == steps
        assert endpoint.target is endpoint.forcings[-1]


def test_complete_fit_matches_eager_reference(monkeypatch):
    rows, _ = synthetic_2r2c_days(8, 20260930)
    actual = dynamics.fit_dynamics_with_evidence(rows)
    monkeypatch.setattr(dynamics, '_eligible_daily_endpoints_from_prepared', eager_endpoints)
    expected = dynamics.fit_dynamics_with_evidence(rows)
    assert asdict(actual) == asdict(expected)


def test_empty_short_and_invalid_horizon_contracts():
    assert dynamics._eligible_daily_endpoints_from_prepared(((), (), (), []), 1) == ()
    rows, _ = synthetic_2r2c_days(5, 71)
    prepared = dynamics._prepare_endpoint_rows(rows[:1], ())
    assert dynamics._eligible_daily_endpoints_from_prepared(prepared, 288) == ()
    with pytest.raises(ValueError, match='identification horizon must be positive'):
        dynamics._eligible_daily_endpoints_from_prepared(prepared, 0)
